# 로컬 문서 지능 검색 시스템

외장하드 내 TB 단위 문서(PPT, Word, PDF, Excel, HWP)를 자연어로 검색하고,  
결과 클릭 시 해당 파일의 **특정 페이지**로 자동 이동하는 시스템입니다.

## 아키텍처

```
┌─────────────────────────────────────────────────────┐
│  Streamlit UI (main.py)                             │
│    ├─ 인덱싱 패널 (폴더 선택 → 증분 인덱싱)              │
│    ├─ 하이브리드 검색 (의미 + 키워드)                    │
│    └─ 결과 카드 + 📂 열기 버튼 (딥링크)                  │
├─────────────────────────────────────────────────────┤
│  L1: SQLite  — 파일 경로·해시·수정일 추적               │
│  L2: Qdrant  — 텍스트 벡터 + 딥링크 payload 저장        │
│  L3: BM25    — 키워드 역인덱스 (pickle)                 │
└─────────────────────────────────────────────────────┘
```

## 포맷별 지원 현황

| 포맷 | 라이브러리 | 페이지 추출 | 딥링크 |
|------|-----------|------------|--------|
| PDF | PyMuPDF | `page.number` (0-based) | `Acrobat.exe /A "page=N"` |
| PPTX | python-pptx | 슬라이드 인덱스 (1-based) | win32com `GotoSlide(N)` |
| DOCX | python-docx | `lastRenderedPageBreak` XML | win32com `Selection.GoTo` |
| XLSX | openpyxl | 시트명 + 셀 주소 | win32com `Sheets.Activate()` |
| HWP | pyhwpx / olefile | 섹션/페이지 번호 | HWPFrame.HwpObject `MovePos` |

## 빠른 시작

### 1. 사전 요구사항

- Docker Desktop (Qdrant 컨테이너용)
- Python 3.10+
- Windows 10/11 (딥링크 자동화는 Windows 전용)

### 2. 실행

```bat
cd doc-search
run.bat
```

`run.bat`이 자동으로:
1. Docker로 Qdrant 컨테이너 시작
2. Python 가상환경 생성 및 패키지 설치
3. Streamlit 앱 실행 → http://localhost:8501

### 3. 수동 설치

```bat
cd doc-search
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pywin32           # Office 자동화 (선택)
# pip install pyhwpx          # HWP 고급 추출 (선택)
```

### 4. 환경 설정

```bat
copy .env.example .env
```

`.env` 파일에서 PDF 뷰어 경로 등 설정:

```env
PDF_VIEWER_PATH=C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe
EMBED_MODEL=BAAI/bge-m3
```

## 검색 방식

| 모드 | 설명 |
|------|------|
| 하이브리드 | Semantic + BM25를 RRF로 결합 (기본값, 권장) |
| 의미 기반 | Qdrant 벡터 유사도만 사용 |
| 키워드 | BM25 역인덱스만 사용 |

## 임베딩 모델

| 모델 | 크기 | 특징 |
|------|------|------|
| `BAAI/bge-m3` | 2.3GB | 한국어 포함 100개 언어, 고성능 (기본값) |
| `paraphrase-multilingual-MiniLM-L12-v2` | 278MB | 경량, 빠름 |

## 프로젝트 구조

```
doc-search/
├── app/
│   ├── main.py                    # Streamlit UI
│   ├── config.py                  # 환경 설정
│   ├── indexer/
│   │   ├── base_extractor.py      # 추상 기본 클래스 + PageChunk
│   │   ├── pdf_extractor.py       # PyMuPDF
│   │   ├── pptx_extractor.py      # python-pptx
│   │   ├── docx_extractor.py      # python-docx
│   │   ├── xlsx_extractor.py      # openpyxl
│   │   ├── hwp_extractor.py       # pyhwpx / olefile
│   │   └── index_manager.py       # SQLite(L1) + Qdrant(L2/L3) 관리
│   ├── search/
│   │   └── searcher.py            # 하이브리드 검색 (RRF)
│   └── automation/
│       └── opener.py              # 딥링크 파일 열기 자동화
├── data/                          # SQLite DB, BM25 인덱스 저장
├── requirements.txt
├── .env.example
├── run.bat                        # 원클릭 실행 스크립트
└── README.md
```
