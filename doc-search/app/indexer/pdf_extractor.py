"""
PDF 텍스트 및 페이지 정보 추출기
라이브러리: PyMuPDF (fitz)
딥링크: Acrobat.exe /A "page=N" file.pdf
"""
import logging
from typing import List

import fitz  # PyMuPDF

from .base_extractor import BaseExtractor, PageChunk

logger = logging.getLogger(__name__)


class PDFExtractor(BaseExtractor):
    """PyMuPDF를 이용한 PDF 페이지별 텍스트 추출"""

    def extract(self) -> List[PageChunk]:
        chunks: List[PageChunk] = []
        try:
            doc = fitz.open(str(self.file_path))
            total = doc.page_count

            for page in doc:
                # fitz page.number는 0-based → 표시용은 1-based
                page_num = page.number + 1
                text = page.get_text("text")
                if not text.strip():
                    continue

                page_label = f"{page_num}페이지"

                # Acrobat /A 파라미터 기반 딥링크
                from config import PDF_VIEWER_PATH
                page_link_cmd = (
                    f'"{PDF_VIEWER_PATH}" /A "page={page_num}" '
                    f'"{self.file_path.resolve()}"'
                )

                chunks.append(
                    self._build_chunk(
                        text=text,
                        page_num=page_num,
                        page_label=page_label,
                        page_link_cmd=page_link_cmd,
                        extra_meta={"total_pages": total},
                    )
                )
            doc.close()

        except Exception as exc:
            logger.error("[PDF] 추출 오류 %s: %s", self.file_path, exc, exc_info=True)

        return chunks
