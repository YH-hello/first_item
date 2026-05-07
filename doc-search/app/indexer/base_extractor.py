"""
포맷별 추출기 기본 클래스 및 공통 데이터 구조 정의
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class PageChunk:
    """페이지·슬라이드·시트 단위 텍스트 청크"""

    file_path: str          # 파일 절대 경로
    file_name: str          # 파일명
    file_type: str          # 확장자 (pdf, pptx, docx, xlsx, hwp)
    text: str               # 추출된 텍스트
    page_num: int           # 페이지/슬라이드/시트 번호 (1-based)
    page_label: str         # 표시용 레이블 (예: "5페이지", "3번째 슬라이드")
    page_link_cmd: str      # 딥링크 실행 명령 문자열
    extra_meta: dict = field(default_factory=dict)


class BaseExtractor(ABC):
    """파일 포맷별 텍스트 및 페이지 정보 추출 추상 기본 클래스"""

    def __init__(self, file_path: str) -> None:
        self.file_path: Path = Path(file_path)
        self.file_name: str = self.file_path.name
        self.file_type: str = self.file_path.suffix.lstrip(".").lower()

    @abstractmethod
    def extract(self) -> List[PageChunk]:
        """텍스트와 페이지 메타데이터를 추출하여 PageChunk 리스트 반환"""
        ...

    def _build_chunk(
        self,
        text: str,
        page_num: int,
        page_label: str,
        page_link_cmd: str,
        extra_meta: Optional[dict] = None,
    ) -> PageChunk:
        return PageChunk(
            file_path=str(self.file_path.resolve()),
            file_name=self.file_name,
            file_type=self.file_type,
            text=text.strip(),
            page_num=page_num,
            page_label=page_label,
            page_link_cmd=page_link_cmd,
            extra_meta=extra_meta or {},
        )
