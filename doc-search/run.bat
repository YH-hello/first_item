@echo off
chcp 65001 > nul
title 로컬 문서 지능 검색 시스템

echo ============================================================
echo   Local Doc-Intelligence Search System
echo ============================================================
echo.

:: ── 1. Qdrant 컨테이너 확인 및 시작 ────────────────────────────────────────
echo [1/3] Qdrant 컨테이너 시작 중...
cd /d "%~dp0.."
docker compose up -d qdrant
if %errorlevel% neq 0 (
    echo [경고] docker compose 실패. Qdrant가 이미 실행 중이거나 Docker가 없습니다.
)
echo.

:: ── 2. 가상환경 활성화 (없으면 생성) ────────────────────────────────────────
echo [2/3] Python 가상환경 준비 중...
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo     가상환경 생성 중...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo     의존성 패키지 설치 중... (최초 실행 시 시간이 걸립니다)
    python.exe -m pip install --upgrade pip
    pip install -r requirements.txt -q
    echo     [선택] Windows COM 자동화 패키지 설치 (pywin32)...
    pip install pywin32 -q
) else (
    call .venv\Scripts\activate.bat
)
echo.

:: ── 3. .env 파일 확인 ───────────────────────────────────────────────────────
if not exist ".env" (
    echo [알림] .env 파일이 없습니다. .env.example을 복사합니다.
    copy .env.example .env > nul
    echo     .env 파일을 열어 PDF 뷰어 경로 등을 설정해 주세요.
    echo.
)

:: ── 4. Streamlit 앱 실행 ─────────────────────────────────────────────────────
echo [3/3] Streamlit 앱 시작 중...
echo.
echo   브라우저: http://localhost:8501
echo   종료:     Ctrl+C
echo.

streamlit run app\main.py --server.port 8501 --server.headless false

pause
