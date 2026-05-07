"""
파일 딥링크 자동화 모듈
각 포맷별로 특정 페이지/슬라이드/시트로 직접 이동합니다.

우선순위 전략:
 PDF   → Acrobat /A "page=N"  →  SumatraPDF -page N  →  OS 기본 프로그램
 PPTX  → win32com PowerPoint.Application GotoSlide   →  OS 기본 프로그램
 DOCX  → win32com Word.Application Selection.GoTo    →  OS 기본 프로그램
 XLSX  → win32com Excel.Application Sheets.Activate  →  OS 기본 프로그램
 HWP   → win32com HWPFrame.HwpObject MovePos         →  pyhwpx  →  OS 기본
"""
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# SumatraPDF 후보 경로
_SUMATRA_PATHS = [
    r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
    r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
    r"C:\Users\{user}\AppData\Local\SumatraPDF\SumatraPDF.exe",
]


def open_at_page(
    file_path: str,
    page_num: int,
    file_type: str,
    page_link_cmd: str = "",
    extra_meta: dict = None,
) -> bool:
    """
    파일을 특정 페이지로 직접 열기.

    Parameters
    ----------
    file_path    : 절대 경로 문자열
    page_num     : 대상 페이지/슬라이드/시트 번호 (1-based)
    file_type    : 파일 확장자 (pdf, pptx, docx, xlsx, hwp)
    page_link_cmd: index_manager가 생성한 실행 명령 (참조용)
    extra_meta   : 추가 메타데이터 (sheet_name 등)
    """
    path = Path(file_path)
    if not path.exists():
        logger.error("파일이 존재하지 않습니다: %s", file_path)
        return False

    ft = file_type.lower().lstrip(".")
    extra_meta = extra_meta or {}

    dispatch = {
        "pdf": _open_pdf,
        "pptx": _open_pptx,
        "ppt": _open_pptx,
        "docx": _open_docx,
        "doc": _open_docx,
        "xlsx": _open_xlsx,
        "xls": _open_xlsx,
        "hwp": _open_hwp,
    }

    handler = dispatch.get(ft)
    if handler:
        try:
            return handler(path, page_num, extra_meta)
        except Exception as exc:
            logger.error("[%s] 오픈 오류: %s", ft.upper(), exc)

    return _open_default(path)


# ── PDF ─────────────────────────────────────────────────────────────────────

def _open_pdf(path: Path, page_num: int, _meta: dict) -> bool:
    from config import PDF_VIEWER_PATH

    # Adobe Acrobat
    if PDF_VIEWER_PATH and Path(PDF_VIEWER_PATH).exists():
        subprocess.Popen([PDF_VIEWER_PATH, "/A", f"page={page_num}", str(path)])
        logger.info("Acrobat으로 열기: %s p.%d", path.name, page_num)
        return True

    # SumatraPDF (무료, 경량)
    for sp in _SUMATRA_PATHS:
        sp = sp.replace("{user}", os.environ.get("USERNAME", ""))
        if Path(sp).exists():
            subprocess.Popen([sp, f"-page {page_num}", str(path)])
            logger.info("SumatraPDF로 열기: %s p.%d", path.name, page_num)
            return True

    logger.warning("PDF 뷰어 없음 → OS 기본 프로그램으로 열기")
    return _open_default(path)


# ── PowerPoint ───────────────────────────────────────────────────────────────

def _open_pptx(path: Path, slide_idx: int, _meta: dict) -> bool:
    if sys.platform != "win32":
        return _open_default(path)

    try:
        import win32com.client  # type: ignore

        ppt = win32com.client.Dispatch("PowerPoint.Application")
        ppt.Visible = True
        prs = ppt.Presentations.Open(str(path.resolve()))
        # 편집 모드에서 슬라이드 이동
        prs.Windows(1).View.GotoSlide(slide_idx)
        logger.info("PowerPoint 슬라이드 %d로 이동: %s", slide_idx, path.name)
        return True

    except ImportError:
        logger.warning("pywin32 미설치 → OS 기본 프로그램으로 열기")
    except Exception as exc:
        logger.error("PowerPoint COM 오류: %s", exc)

    return _open_default(path)


# ── Word ─────────────────────────────────────────────────────────────────────

def _open_docx(path: Path, page_num: int, _meta: dict) -> bool:
    if sys.platform != "win32":
        return _open_default(path)

    try:
        import win32com.client  # type: ignore

        word = win32com.client.Dispatch("Word.Application")
        word.Visible = True
        doc = word.Documents.Open(str(path.resolve()))
        # wdGoToPage=1, wdGoToAbsolute=1
        doc.ActiveWindow.Selection.GoTo(What=1, Which=1, Count=page_num)
        logger.info("Word %d페이지로 이동: %s", page_num, path.name)
        return True

    except ImportError:
        logger.warning("pywin32 미설치 → OS 기본 프로그램으로 열기")
    except Exception as exc:
        logger.error("Word COM 오류: %s", exc)

    return _open_default(path)


# ── Excel ────────────────────────────────────────────────────────────────────

def _open_xlsx(path: Path, sheet_idx: int, meta: dict) -> bool:
    if sys.platform != "win32":
        return _open_default(path)

    try:
        import win32com.client  # type: ignore

        xl = win32com.client.Dispatch("Excel.Application")
        xl.Visible = True
        wb = xl.Workbooks.Open(str(path.resolve()))

        sheet_name = meta.get("sheet_name")
        if sheet_name:
            wb.Sheets(sheet_name).Activate()
        elif sheet_idx <= wb.Sheets.Count:
            wb.Sheets(sheet_idx).Activate()

        logger.info("Excel 시트 '%s'로 이동: %s", sheet_name or sheet_idx, path.name)
        return True

    except ImportError:
        logger.warning("pywin32 미설치 → OS 기본 프로그램으로 열기")
    except Exception as exc:
        logger.error("Excel COM 오류: %s", exc)

    return _open_default(path)


# ── HWP ─────────────────────────────────────────────────────────────────────

def _open_hwp(path: Path, page_num: int, _meta: dict) -> bool:
    if sys.platform != "win32":
        return _open_default(path)

    # 한글 오토메이션 API (HWPFrame.HwpObject)
    try:
        import win32com.client  # type: ignore

        hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
        hwp.XHwpWindows.Item(0).Visible = True
        hwp.Open(str(path.resolve()), "HWP", "forceopen:true")
        # MovePos(3=페이지이동, page_num, 0)
        hwp.MovePos(3, page_num, 0)
        logger.info("한글 %d페이지로 이동: %s", page_num, path.name)
        return True

    except ImportError:
        logger.warning("pywin32 미설치 → pyhwpx 시도")
    except Exception as exc:
        logger.warning("한글 COM 오류: %s → pyhwpx 시도", exc)

    # pyhwpx 폴백
    try:
        import pyhwpx  # type: ignore

        hwp = pyhwpx.Hwp()
        hwp.open(str(path.resolve()))
        hwp.MoveToPage(page_num)
        logger.info("pyhwpx %d페이지로 이동: %s", page_num, path.name)
        return True

    except ImportError:
        logger.warning("pyhwpx 미설치 → OS 기본 프로그램으로 열기")
    except Exception as exc:
        logger.error("pyhwpx 오류: %s", exc)

    return _open_default(path)


# ── OS 기본 ──────────────────────────────────────────────────────────────────

def _open_default(path: Path) -> bool:
    """OS 연결 프로그램으로 열기 (페이지 이동 없음)"""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        logger.info("기본 프로그램으로 열기: %s", path.name)
        return True
    except Exception as exc:
        logger.error("파일 열기 실패 %s: %s", path, exc)
        return False
