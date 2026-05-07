"""
계층형 인덱스 관리자
 - L1: SQLite  → 파일 경로, 해시, 수정일 추적 (증분 인덱싱)
 - L2/L3: Qdrant → 텍스트 벡터 + 딥링크 payload 저장
 - BM25: 키워드 검색용 역인덱스 (pickle 직렬화)
"""
import hashlib
import logging
import pickle
import sqlite3
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

import config
from indexer.base_extractor import PageChunk
from indexer.docx_extractor import DOCXExtractor
from indexer.hwp_extractor import HWPExtractor
from indexer.pdf_extractor import PDFExtractor
from indexer.pptx_extractor import PPTXExtractor
from indexer.xlsx_extractor import XLSXExtractor

logger = logging.getLogger(__name__)

EXTRACTORS = {
    ".pdf": PDFExtractor,
    ".pptx": PPTXExtractor,
    ".ppt": PPTXExtractor,
    ".docx": DOCXExtractor,
    ".doc": DOCXExtractor,
    ".xlsx": XLSXExtractor,
    ".xls": XLSXExtractor,
    ".hwp": HWPExtractor,
}


class IndexManager:
    """SQLite(L1) + Qdrant(L2/L3) 계층형 인덱스 관리자"""

    def __init__(self) -> None:
        logger.info("IndexManager 초기화 중...")
        self.embed_model = SentenceTransformer(
            config.EMBED_MODEL_NAME,
            device=config.EMBED_DEVICE,
        )
        self._embed_dim: int = self.embed_model.get_sentence_embedding_dimension()

        self.qdrant = QdrantClient(host=config.QDRANT_HOST, port=config.QDRANT_PORT)
        self._init_sqlite()
        self._init_qdrant()

        # BM25 인덱스 (메모리, pickle로 영속화)
        self.bm25: Optional[BM25Okapi] = None
        self.bm25_docs: List[Dict] = []
        self._load_bm25_index()
        logger.info("IndexManager 준비 완료 (embed_dim=%d)", self._embed_dim)

    # ── SQLite (L1) ─────────────────────────────────────────────────────────

    def _init_sqlite(self) -> None:
        self.conn = sqlite3.connect(str(config.SQLITE_DB_PATH), check_same_thread=False)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS indexed_files (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path     TEXT    UNIQUE NOT NULL,
                file_hash     TEXT    NOT NULL,
                modified_time REAL    NOT NULL,
                indexed_time  REAL    NOT NULL,
                chunk_count   INTEGER DEFAULT 0,
                status        TEXT    DEFAULT 'indexed'
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fp ON indexed_files(file_path)"
        )
        self.conn.commit()

    def _get_record(self, file_path: str) -> Optional[Dict]:
        row = self.conn.execute(
            "SELECT file_path, file_hash, modified_time, chunk_count, status "
            "FROM indexed_files WHERE file_path=?",
            (file_path,),
        ).fetchone()
        if row:
            return dict(zip(["file_path", "file_hash", "modified_time", "chunk_count", "status"], row))
        return None

    def _upsert_record(
        self,
        file_path: str,
        file_hash: str,
        modified_time: float,
        chunk_count: int,
        status: str = "indexed",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO indexed_files
                (file_path, file_hash, modified_time, indexed_time, chunk_count, status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                file_hash     = excluded.file_hash,
                modified_time = excluded.modified_time,
                indexed_time  = excluded.indexed_time,
                chunk_count   = excluded.chunk_count,
                status        = excluded.status
            """,
            (file_path, file_hash, modified_time, time.time(), chunk_count, status),
        )
        self.conn.commit()

    # ── Qdrant (L2/L3) ──────────────────────────────────────────────────────

    def _init_qdrant(self) -> None:
        existing = [c.name for c in self.qdrant.get_collections().collections]
        if config.QDRANT_COLLECTION not in existing:
            self.qdrant.create_collection(
                collection_name=config.QDRANT_COLLECTION,
                vectors_config=VectorParams(
                    size=self._embed_dim,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Qdrant 컬렉션 생성: %s", config.QDRANT_COLLECTION)

    # ── BM25 ────────────────────────────────────────────────────────────────

    def _load_bm25_index(self) -> None:
        if config.BM25_INDEX_PATH.exists():
            try:
                with open(config.BM25_INDEX_PATH, "rb") as f:
                    data = pickle.load(f)
                self.bm25 = data["bm25"]
                self.bm25_docs = data["docs"]
                logger.info("BM25 인덱스 로드 완료 (%d docs)", len(self.bm25_docs))
            except Exception as exc:
                logger.warning("BM25 인덱스 로드 실패: %s", exc)

    def _save_bm25_index(self) -> None:
        with open(config.BM25_INDEX_PATH, "wb") as f:
            pickle.dump({"bm25": self.bm25, "docs": self.bm25_docs}, f)

    def _append_bm25(self, new_entries: List[Dict]) -> None:
        """새 청크를 BM25 인덱스에 추가하고 재빌드"""
        # 기존 docs 에서 같은 file_path 항목 제거 (재인덱싱 시 중복 방지)
        if new_entries:
            fp = new_entries[0]["file_path"]
            self.bm25_docs = [d for d in self.bm25_docs if d["file_path"] != fp]

        self.bm25_docs.extend(new_entries)

        if self.bm25_docs:
            tokenized = [d["text"].split() for d in self.bm25_docs]
            self.bm25 = BM25Okapi(tokenized)
            self._save_bm25_index()

    # ── 유틸 ────────────────────────────────────────────────────────────────

    @staticmethod
    def _file_hash(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65_536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _chunk_id(file_path: str, page_num: int, text_head: str) -> int:
        """Qdrant PointID용 uint64 생성 (MD5 앞 16자리 hex → int)"""
        key = f"{file_path}:{page_num}:{text_head[:40]}"
        return abs(int(hashlib.md5(key.encode()).hexdigest()[:16], 16))

    # ── 인덱싱 ──────────────────────────────────────────────────────────────

    def needs_indexing(self, file_path: Path) -> bool:
        record = self._get_record(str(file_path.resolve()))
        if not record or record["status"] == "error":
            return True
        if file_path.stat().st_mtime > record["modified_time"]:
            return self._file_hash(file_path) != record["file_hash"]
        return False

    def index_file(
        self,
        file_path: Path,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> int:
        """단일 파일 인덱싱. 반환: 추가된 청크 수"""
        ext = file_path.suffix.lower()
        ExtractorClass = EXTRACTORS.get(ext)
        if not ExtractorClass:
            logger.warning("지원하지 않는 형식: %s", file_path)
            return 0

        abs_str = str(file_path.resolve())

        try:
            chunks: List[PageChunk] = ExtractorClass(str(file_path)).extract()
            if not chunks:
                self._upsert_record(abs_str, self._file_hash(file_path), file_path.stat().st_mtime, 0, "empty")
                return 0

            # 임베딩
            texts = [c.text for c in chunks]
            embeddings: np.ndarray = self.embed_model.encode(
                texts,
                batch_size=8,
                show_progress_bar=False,
                normalize_embeddings=True,
            )

            # Qdrant upsert
            points: List[PointStruct] = []
            bm25_entries: List[Dict] = []

            for chunk, vec in zip(chunks, embeddings):
                pid = self._chunk_id(chunk.file_path, chunk.page_num, chunk.text)
                points.append(
                    PointStruct(
                        id=pid,
                        vector=vec.tolist(),
                        payload={
                            "file_path": chunk.file_path,
                            "file_name": chunk.file_name,
                            "file_type": chunk.file_type,
                            "page_num": chunk.page_num,
                            "page_label": chunk.page_label,
                            "page_link_cmd": chunk.page_link_cmd,
                            "text": chunk.text[:1200],
                            **chunk.extra_meta,
                        },
                    )
                )
                bm25_entries.append(
                    {
                        "chunk_id": pid,
                        "text": chunk.text,
                        "file_path": chunk.file_path,
                        "file_name": chunk.file_name,
                        "file_type": chunk.file_type,
                        "page_num": chunk.page_num,
                        "page_label": chunk.page_label,
                        "page_link_cmd": chunk.page_link_cmd,
                    }
                )

            self.qdrant.upsert(
                collection_name=config.QDRANT_COLLECTION,
                points=points,
            )
            self._append_bm25(bm25_entries)
            self._upsert_record(
                abs_str,
                self._file_hash(file_path),
                file_path.stat().st_mtime,
                len(chunks),
            )

            if progress_callback:
                progress_callback(file_path.name, len(chunks))

            logger.info("인덱싱 완료: %s (%d 청크)", file_path.name, len(chunks))
            return len(chunks)

        except Exception as exc:
            logger.error("인덱싱 오류 %s: %s", file_path, exc, exc_info=True)
            self._upsert_record(
                abs_str,
                "",
                file_path.stat().st_mtime if file_path.exists() else 0,
                0,
                "error",
            )
            return 0

    def index_directory(
        self,
        directory: str,
        recursive: bool = True,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> Dict:
        """디렉토리 전체 증분 인덱싱"""
        root = Path(directory)
        if not root.exists():
            raise ValueError(f"디렉토리가 존재하지 않습니다: {directory}")

        pattern = "**/*" if recursive else "*"
        files = [
            f
            for f in root.glob(pattern)
            if f.is_file() and f.suffix.lower() in config.SUPPORTED_EXTENSIONS
        ]

        stats = {"total": len(files), "indexed": 0, "skipped": 0, "error": 0, "chunks": 0}

        for fp in files:
            if self.needs_indexing(fp):
                n = self.index_file(fp, progress_callback)
                if n > 0:
                    stats["indexed"] += 1
                    stats["chunks"] += n
                else:
                    stats["error"] += 1
            else:
                stats["skipped"] += 1

        return stats

    def delete_file_index(self, file_path: str) -> None:
        """특정 파일의 인덱스 삭제"""
        abs_str = str(Path(file_path).resolve())
        # BM25에서 제거
        self.bm25_docs = [d for d in self.bm25_docs if d["file_path"] != abs_str]
        if self.bm25_docs:
            self.bm25 = BM25Okapi([d["text"].split() for d in self.bm25_docs])
        self._save_bm25_index()
        # SQLite 삭제
        self.conn.execute("DELETE FROM indexed_files WHERE file_path=?", (abs_str,))
        self.conn.commit()

    def get_stats(self) -> Dict:
        """인덱스 통계 반환"""
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(chunk_count), 0) "
            "FROM indexed_files WHERE status='indexed'"
        ).fetchone()
        try:
            info = self.qdrant.get_collection(config.QDRANT_COLLECTION)
            qdrant_vectors = info.vectors_count or 0
        except Exception:
            qdrant_vectors = -1

        return {
            "indexed_files": row[0],
            "total_chunks": row[1],
            "qdrant_vectors": qdrant_vectors,
            "bm25_docs": len(self.bm25_docs),
        }

    def get_indexed_files(self) -> List[Dict]:
        """인덱싱된 파일 목록 반환"""
        rows = self.conn.execute(
            "SELECT file_path, chunk_count, status, indexed_time FROM indexed_files ORDER BY indexed_time DESC"
        ).fetchall()
        return [
            {"file_path": r[0], "chunk_count": r[1], "status": r[2], "indexed_time": r[3]}
            for r in rows
        ]
