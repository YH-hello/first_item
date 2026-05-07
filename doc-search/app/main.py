"""
로컬 문서 지능 검색 시스템 — Streamlit UI
"""
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# app/ 디렉토리를 import 경로에 추가
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ── 페이지 설정 ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="로컬 문서 지능 검색",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ─────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
/* 전체 배경 */
[data-testid="stAppViewContainer"] { background: #13131f; }
[data-testid="stSidebar"] { background: #1a1a2e; }

/* 결과 카드 */
.doc-card {
    background: #1e1e30;
    border: 1px solid #2e2e4a;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 10px;
    transition: border-color 0.2s, box-shadow 0.2s;
}
.doc-card:hover {
    border-color: #7c6af7;
    box-shadow: 0 0 0 1px #7c6af733;
}
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
}
.file-name {
    font-size: 1.05rem;
    font-weight: 600;
    color: #e2e0ff;
}
.page-badge {
    background: #2e2e4a;
    color: #9b8ffa;
    border: 1px solid #4a4a6a;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.8rem;
    white-space: nowrap;
}
.file-path {
    font-size: 0.76rem;
    color: #555577;
    margin: 2px 0 8px;
    word-break: break-all;
}
.preview-text {
    font-size: 0.88rem;
    color: #9090b0;
    line-height: 1.65;
    border-left: 3px solid #3a3a5a;
    padding-left: 10px;
    margin: 4px 0;
}
.meta-row {
    display: flex;
    gap: 14px;
    margin-top: 8px;
    font-size: 0.74rem;
    color: #444466;
}
.meta-tag {
    background: #252540;
    padding: 2px 8px;
    border-radius: 4px;
}
</style>
""",
    unsafe_allow_html=True,
)

# ── 리소스 캐싱 ─────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner="AI 모델 및 인덱스 로딩 중…")
def get_index_manager():
    from indexer.index_manager import IndexManager
    return IndexManager()


@st.cache_resource(show_spinner=False)
def get_searcher(_im):
    from search.searcher import HybridSearcher
    return HybridSearcher(_im)


# ── 파일 타입 아이콘 ─────────────────────────────────────────────────────────
_ICONS = {
    "pdf": "📄",
    "pptx": "📊", "ppt": "📊",
    "docx": "📝", "doc": "📝",
    "xlsx": "📈", "xls": "📈",
    "hwp": "📃",
}


def file_icon(ft: str) -> str:
    return _ICONS.get(ft.lower(), "📁")


# ── 세션 초기화 ──────────────────────────────────────────────────────────────
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "last_query" not in st.session_state:
    st.session_state.last_query = ""
if "open_feedback" not in st.session_state:
    st.session_state.open_feedback = {}


# ════════════════════════════════════════════════════════════════════════════
# 사이드바
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ 관리 패널")
    st.divider()

    # ── 인덱싱 섹션 ─────────────────────────────────────────────────────────
    st.markdown("### 📂 문서 인덱싱")
    scan_dir = st.text_input(
        "검색 대상 폴더",
        placeholder="예: D:\\문서\\외장하드",
        key="scan_dir",
    )
    recursive = st.checkbox("하위 폴더 모두 포함", value=True)

    col_a, col_b = st.columns(2)
    with col_a:
        btn_index = st.button("🚀 인덱싱 시작", use_container_width=True, type="primary")
    with col_b:
        btn_refresh = st.button("🔄 새로고침", use_container_width=True)

    if btn_index:
        if not scan_dir:
            st.warning("폴더 경로를 입력해주세요.")
        elif not Path(scan_dir).exists():
            st.error(f"폴더가 없습니다: {scan_dir}")
        else:
            im = get_index_manager()
            log_box = st.empty()
            progress_bar = st.progress(0)
            status_text = st.empty()

            indexed_files = [0]
            last_name = [""]

            def _cb(fname: str, chunks: int):
                indexed_files[0] += 1
                last_name[0] = fname
                log_box.info(f"✅ [{indexed_files[0]}] {fname}  ({chunks}청크)")

            with st.spinner("인덱싱 진행 중…"):
                try:
                    t0 = time.time()
                    stats = im.index_directory(scan_dir, recursive=recursive, progress_callback=_cb)
                    elapsed = time.time() - t0
                    log_box.empty()
                    progress_bar.empty()
                    st.success(
                        f"**인덱싱 완료** ({elapsed:.1f}초)\n\n"
                        f"- 전체 파일: **{stats['total']}개**\n"
                        f"- 신규 인덱스: **{stats['indexed']}개**\n"
                        f"- 건너뜀(기존): **{stats['skipped']}개**\n"
                        f"- 오류: **{stats['error']}개**\n"
                        f"- 총 청크: **{stats['chunks']}개**"
                    )
                    # 캐시 무효화 없이 인스턴스는 계속 사용 (BM25 in-place 업데이트됨)
                    st.rerun()
                except Exception as e:
                    st.error(f"인덱싱 오류: {e}")

    st.divider()

    # ── 인덱스 현황 ─────────────────────────────────────────────────────────
    st.markdown("### 📊 인덱스 현황")
    try:
        im = get_index_manager()
        stats_data = im.get_stats()
        c1, c2 = st.columns(2)
        c1.metric("인덱싱 파일", f"{stats_data['indexed_files']:,}개")
        c2.metric("총 청크", f"{stats_data['total_chunks']:,}개")
        c1.metric("Qdrant 벡터", f"{stats_data['qdrant_vectors']:,}개")
        c2.metric("BM25 문서", f"{stats_data['bm25_docs']:,}개")
    except Exception as e:
        st.warning(f"Qdrant 연결 필요\n`{e}`")

    st.divider()

    # ── 인덱싱된 파일 목록 ───────────────────────────────────────────────────
    with st.expander("📋 인덱싱된 파일 목록", expanded=False):
        try:
            im = get_index_manager()
            file_list = im.get_indexed_files()
            if file_list:
                for item in file_list[:50]:
                    icon = file_icon(Path(item["file_path"]).suffix.lstrip("."))
                    dt = datetime.fromtimestamp(item["indexed_time"]).strftime("%m/%d %H:%M")
                    st.markdown(
                        f"{icon} `{Path(item['file_path']).name}` "
                        f"— {item['chunk_count']}청크 ({dt})"
                    )
            else:
                st.caption("인덱싱된 파일이 없습니다.")
        except Exception:
            st.caption("목록을 불러올 수 없습니다.")

    st.divider()

    # ── 검색 옵션 ────────────────────────────────────────────────────────────
    st.markdown("### 🔍 검색 옵션")
    search_mode = st.radio(
        "검색 방식",
        options=["hybrid", "semantic", "keyword"],
        format_func=lambda x: {
            "hybrid": "🔀 하이브리드 (권장)",
            "semantic": "🧠 의미 기반 (벡터)",
            "keyword": "🔑 키워드 (BM25)",
        }[x],
        index=0,
    )
    top_k = st.slider("결과 최대 수", min_value=5, max_value=50, value=10, step=5)

    st.divider()
    st.caption("Local Doc-Intelligence Search\nPowered by LlamaIndex · Qdrant · Streamlit")


# ════════════════════════════════════════════════════════════════════════════
# 메인 영역
# ════════════════════════════════════════════════════════════════════════════
st.markdown(
    "<h1 style='margin-bottom:4px'>🔍 로컬 문서 지능 검색</h1>"
    "<p style='color:#666;font-size:0.95rem;margin-bottom:20px'>"
    "PPT · Word · PDF · Excel · HWP — 자연어로 검색하고 클릭 한 번으로 해당 페이지로 이동</p>",
    unsafe_allow_html=True,
)

# ── 검색 폼 ─────────────────────────────────────────────────────────────────
with st.form("search_form", clear_on_submit=False):
    col_q, col_btn = st.columns([5, 1])
    with col_q:
        query = st.text_input(
            "검색어",
            value=st.session_state.last_query,
            placeholder="예: '2023년 매출 현황', '계약 조항 위약금', '프로젝트 WBS 일정'",
            label_visibility="collapsed",
        )
    with col_btn:
        submitted = st.form_submit_button("검색", use_container_width=True, type="primary")

if submitted and query.strip():
    st.session_state.last_query = query
    im = get_index_manager()
    searcher = get_searcher(im)

    with st.spinner("검색 중…"):
        try:
            results = searcher.search(query, mode=search_mode, top_k=top_k)
            st.session_state.search_results = [r.to_dict() for r in results]
            st.session_state.open_feedback = {}
        except Exception as e:
            st.error(f"검색 오류: {e}")
            st.session_state.search_results = []

# ── 검색 결과 표시 ──────────────────────────────────────────────────────────
results_data = st.session_state.search_results

if results_data:
    q_label = st.session_state.last_query
    mode_label = {"hybrid": "하이브리드", "semantic": "의미 기반", "keyword": "키워드"}.get(search_mode, search_mode)
    st.markdown(f"**{q_label}** — **{len(results_data)}개** 결과 · {mode_label} 검색")
    st.divider()

    for i, r in enumerate(results_data):
        icon = file_icon(r["file_type"])
        feedback_key = f"fb_{i}"

        # 카드 + 열기 버튼
        col_card, col_open = st.columns([6, 1])

        with col_card:
            st.markdown(
                f"""<div class="doc-card">
  <div class="card-header">
    <span class="file-name">{icon} {r["file_name"]}</span>
    <span class="page-badge">{r["page_label"]}</span>
  </div>
  <div class="file-path">📁 {r["file_path"]}</div>
  <div class="preview-text">{r["text_preview"].replace(chr(10), "<br>")}</div>
  <div class="meta-row">
    <span class="meta-tag">관련도 {r["score"]:.4f}</span>
    <span class="meta-tag">{r["source"]}</span>
    <span class="meta-tag">{r["file_type"].upper()}</span>
  </div>
</div>""",
                unsafe_allow_html=True,
            )

        with col_open:
            # 버튼 수직 위치 맞추기
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

            if st.button(
                "📂 열기",
                key=f"open_{i}",
                use_container_width=True,
                help=f"{r['file_name']} — {r['page_label']}",
            ):
                from automation.opener import open_at_page

                ok = open_at_page(
                    file_path=r["file_path"],
                    page_num=r["page_num"],
                    file_type=r["file_type"],
                    page_link_cmd=r.get("page_link_cmd", ""),
                    extra_meta=r.get("extra_meta", {}),
                )
                st.session_state.open_feedback[feedback_key] = (
                    f"✅ {r['file_name']}  {r['page_label']} 열림"
                    if ok
                    else f"⚠️ 파일을 열 수 없습니다: {r['file_path']}"
                )
                st.rerun()

            # 열기 피드백
            fb = st.session_state.open_feedback.get(feedback_key)
            if fb:
                if fb.startswith("✅"):
                    st.success(fb, icon="✅")
                else:
                    st.warning(fb, icon="⚠️")

elif st.session_state.last_query:
    st.info("검색 결과가 없습니다. 먼저 사이드바에서 폴더를 인덱싱해 주세요.")
else:
    # 초기 화면 안내
    st.markdown(
        """
<div style="text-align:center;padding:60px 0;color:#444466;">
    <div style="font-size:4rem;margin-bottom:16px">🗂️</div>
    <div style="font-size:1.2rem;font-weight:600;color:#8888aa;margin-bottom:8px">
        시작하는 방법
    </div>
    <div style="color:#555577;line-height:2">
        1. 왼쪽 사이드바에서 <b>검색 대상 폴더 경로</b>를 입력하세요<br>
        2. <b>인덱싱 시작</b> 버튼을 눌러 문서를 분석합니다<br>
        3. 위 검색창에 자연어로 검색어를 입력하세요
    </div>
</div>
""",
        unsafe_allow_html=True,
    )
