"""
HWP 텍스트 및 페이지 정보 추출기
우선순위:
  1. pyhwpx (설치된 경우)
  2. olefile + zlib 직접 파싱 (BodyText/Section 스트림)
딥링크: 한글 오토메이션 API (HWPFrame.HwpObject) 또는 pyhwpx
"""
import logging
import zlib
from typing import List

from .base_extractor import BaseExtractor, PageChunk

logger = logging.getLogger(__name__)

# HWP 레코드 태그 상수
HWPTAG_PARA_TEXT = 66


class HWPExtractor(BaseExtractor):
    """HWP 파일 텍스트 추출 (pyhwpx 또는 olefile 폴백)"""

    def extract(self) -> List[PageChunk]:
        # pyhwpx 우선 시도
        try:
            return self._extract_with_pyhwpx()
        except ImportError:
            logger.debug("pyhwpx 미설치 → olefile 방식으로 전환")
        except Exception as exc:
            logger.warning("[HWP] pyhwpx 추출 실패, olefile 시도: %s", exc)

        # olefile 폴백
        try:
            return self._extract_with_olefile()
        except Exception as exc:
            logger.error("[HWP] 추출 오류 %s: %s", self.file_path, exc, exc_info=True)

        return []

    # ── pyhwpx ──────────────────────────────────────────────────────────────

    def _extract_with_pyhwpx(self) -> List[PageChunk]:
        import pyhwpx  # type: ignore

        chunks: List[PageChunk] = []
        hwp = pyhwpx.Hwp()
        hwp.open(str(self.file_path))
        total_pages: int = getattr(hwp, "PageCount", 1)

        abs_path = str(self.file_path.resolve()).replace("\\", "\\\\")

        for page_num in range(1, total_pages + 1):
            text = hwp.GetTextFromPage(page_num) if hasattr(hwp, "GetTextFromPage") else ""
            if not text.strip():
                continue

            page_label = f"{page_num}페이지"
            page_link_cmd = (
                f"python -c \""
                f"import pyhwpx; "
                f"hwp=pyhwpx.Hwp(); "
                f"hwp.open(r'{abs_path}'); "
                f"hwp.MoveToPage({page_num})\""
            )

            chunks.append(
                self._build_chunk(
                    text=text,
                    page_num=page_num,
                    page_label=page_label,
                    page_link_cmd=page_link_cmd,
                    extra_meta={"total_pages": total_pages},
                )
            )

        hwp.quit()
        return chunks

    # ── olefile 직접 파싱 ──────────────────────────────────────────────────

    def _extract_with_olefile(self) -> List[PageChunk]:
        import olefile  # type: ignore

        chunks: List[PageChunk] = []

        if not olefile.isOleFile(str(self.file_path)):
            logger.warning("[HWP] OLE 형식이 아닙니다: %s", self.file_path)
            return chunks

        ole = olefile.OleFileIO(str(self.file_path))
        abs_path = str(self.file_path.resolve()).replace("\\", "\\\\")

        section_idx = 0
        page_num = 1

        while ole.exists(f"BodyText/Section{section_idx}"):
            raw = ole.openstream(f"BodyText/Section{section_idx}").read()

            # HWP 섹션 데이터는 zlib 압축(raw deflate, wbits=-15)
            try:
                data = zlib.decompress(raw, -15)
            except zlib.error:
                data = raw

            text = self._parse_hwp_records(data)

            if text.strip():
                page_label = f"{page_num}페이지"
                # 한글 오토메이션 API 딥링크 (HWPFrame.HwpObject)
                page_link_cmd = (
                    f"python -c \""
                    f"import win32com.client; "
                    f"hwp=win32com.client.Dispatch('HWPFrame.HwpObject'); "
                    f"hwp.XHwpWindows.Item(0).Visible=True; "
                    f"hwp.Open(r'{abs_path}', 'HWP', 'forceopen:true'); "
                    f"hwp.MovePos(3, {page_num}, 0)\""
                )

                chunks.append(
                    self._build_chunk(
                        text=text,
                        page_num=page_num,
                        page_label=page_label,
                        page_link_cmd=page_link_cmd,
                        extra_meta={"section_idx": section_idx},
                    )
                )
                page_num += 1

            section_idx += 1

        ole.close()
        return chunks

    # ── HWP 바이너리 레코드 파서 ───────────────────────────────────────────

    @staticmethod
    def _parse_hwp_records(data: bytes) -> str:
        """
        HWP5 레코드 스트림에서 HWPTAG_PARA_TEXT(66) 텍스트 추출
        레코드 헤더: 4바이트 (TagID 10bit | Level 10bit | Size 12bit)
        Size == 0xFFF 이면 다음 4바이트에 실제 크기
        """
        texts: List[str] = []
        i = 0

        while i < len(data) - 4:
            header = int.from_bytes(data[i : i + 4], "little")
            tag_id = header & 0x3FF
            size = (header >> 20) & 0xFFF

            if size == 0xFFF:
                if i + 8 > len(data):
                    break
                size = int.from_bytes(data[i + 4 : i + 8], "little")
                i += 8
            else:
                i += 4

            if i + size > len(data):
                break

            if tag_id == HWPTAG_PARA_TEXT:
                try:
                    raw_text = data[i : i + size].decode("utf-16-le", errors="ignore")
                    clean = "".join(
                        ch for ch in raw_text if ord(ch) >= 0x20 or ch in "\n\t"
                    )
                    if clean.strip():
                        texts.append(clean)
                except Exception:
                    pass

            i += size

        return "\n".join(texts)
