"""
시스템 전역 설정 모듈
환경변수(.env) 또는 기본값으로 동작합니다.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트에서 .env 로드
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Qdrant 연결 ─────────────────────────────────────────────────────────────
QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION: str = os.getenv("QDRANT_COLLECTION", "doc_search")

# ── 데이터 저장 경로 ─────────────────────────────────────────────────────────
DATA_DIR: Path = Path(os.getenv("DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

SQLITE_DB_PATH: Path = DATA_DIR / "metadata.db"
BM25_INDEX_PATH: Path = DATA_DIR / "bm25_index.pkl"

# ── 임베딩 모델 ─────────────────────────────────────────────────────────────
EMBED_MODEL_NAME: str = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
EMBED_DEVICE: str = os.getenv("EMBED_DEVICE", "cpu")

# ── 청킹 설정 ────────────────────────────────────────────────────────────────
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "64"))

# ── 검색 설정 ────────────────────────────────────────────────────────────────
SEARCH_TOP_K: int = int(os.getenv("SEARCH_TOP_K", "10"))
SEMANTIC_WEIGHT: float = float(os.getenv("SEMANTIC_WEIGHT", "0.7"))
KEYWORD_WEIGHT: float = float(os.getenv("KEYWORD_WEIGHT", "0.3"))

# ── 지원 파일 확장자 ─────────────────────────────────────────────────────────
SUPPORTED_EXTENSIONS: set = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls", ".hwp"}

# ── PDF 뷰어 경로 ────────────────────────────────────────────────────────────
PDF_VIEWER_PATH: str = os.getenv(
    "PDF_VIEWER_PATH",
    r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
)
