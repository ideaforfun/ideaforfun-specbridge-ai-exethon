"""SpecBridge AI · synthetic-data-first hackathon MVP."""
import json
import os
import sqlite3
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.audit import history, save_result, scope_key
from src.law_ui import show_law, show_org
from src.core import build_ticket, compare_specs, recommend_owners
from src.liner_client import LinerError, review_with_liner, search_web

load_dotenv()
ROOT = Path(__file__).resolve().parent
AUDIT_DB = Path(os.getenv("SPECBRIDGE_AUDIT_DB", str(ROOT / "data/reviews.sqlite3")))


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def from_upload(upload, fallback):
    if upload is None:
        return load_json(fallback)
    if upload.size > 2 * 1024 * 1024:
        raise ValueError("2MB 이하 JSON 규격 파일만 지원합니다.")
    return json.loads(upload.getvalue().decode("utf-8-sig"))


st.set_page_config(page_title="SpecBridge AI", page_icon="🔗", layout="wide")
st.title("🔗 SpecBridge AI")
st.caption("API·법령 변경 → 영향 검토 → 부서 협업 → 개발 요청서")
st.warning("🧪 해커톤 데모: 기본 규격, 조직, 시스템, 개발 이력은 모두 가상 데이터입니다. 실제 사내 문서·개인정보는 업로드하지 마세요.")

workspace = st.sidebar.radio("작업 공간",("API 규격 비교","법령 변경 검토","전사 조직도"))
demo = ROOT / "data/liner_hackathon"
if workspace == "법령 변경 검토":
    show_law(load_json(demo/"self_transfer_case.json"),load_json(demo/"catalog.json"),
             load_json(demo/"cross_functional_review.json"),AUDIT_DB)
    st.stop()
if workspace == "전사 조직도":
    show_org(load_json(demo/"catalog.json"))
    st.stop()

with st.sidebar:
    use_four = st.toggle("4개 금융사 API 시나리오")
    st.subheader("1 · 규격 입력")
    old_upload = st.file_uploader("이전 규격 (JSON)", type="json", key="old")
    new_upload = st.file_uploader("신규 규격 (JSON)", type="json", key="new")
    st.caption("업로드하지 않으면 내장된 가상 V1/V2를 사용합니다.")
    st.subheader("2 · 실행 모드")
    online = st.toggle("Liner Model API 사용", value=False)
    st.caption("기본 모드는 비용이 발생하지 않는 오프라인 데모입니다. API 사용 버튼을 누를 때만 외부 요청합니다.")
    safe_to_send = st.checkbox("Liner API로 전송할 데이터가 공개자료 또는 가상 데이터임을 확인", value=False)
    st.markdown("[Liner API 키 발급](https://platform.liner.com/)")

try:
    old = from_upload(old_upload, demo/"spec_before.json" if use_four else ROOT/"data/spec_v1.json")
    new = from_upload(new_upload, demo/"spec_after.json" if use_four else ROOT/"data/spec_v2.json")
    catalog = load_json(demo/"catalog.json" if use_four else ROOT/"data/catalog.json")
    changes = compare_specs(old, new)
    recommendations = recommend_owners(changes, catalog)
except (ValueError, KeyError, TypeError, json.JSONDecodeError, UnicodeError) as exc:
    st.error(f"규격 파싱 실패: {exc}")
    st.stop()

left, mid, right = st.columns(3)
left.metric("변경 항목", len(changes))
mid.metric("높은 영향도", sum(c["severity"] == "HIGH" for c in changes))
right.metric("담당 미확정", sum(not r["candidates"] for r in recommendations))

if not recommendations:
    st.success("변경된 규격 항목이 없습니다.")
    st.stop()

st.subheader("변경 목록")
labels = [f"{r['change']['change_id']} · {r['change']['api_id']} · {r['change']['field']} ({r['change']['kind']})" for r in recommendations]
sel = st.selectbox("분석할 변경 선택", list(range(len(labels))), format_func=lambda index: labels[index])
record = recommendations[sel]
change = record["change"]

col_a, col_b = st.columns([1, 1])
with col_a:
    st.markdown("#### 🔍 변경 분석 (Agent 1)")
    st.write(f"**API:** `{change['api_id']}`")
    st.write(f"**유형:** `{change['kind']}` / **위험도:** `{change['severity']}`")
    st.write(f"**영역 및 필드:** `{change['field_group']}.{change['field']}`")
    with st.expander("정확한 변경 전후 데이터", expanded=True):
        st.write("이전 규격")
        st.json(change["before"])
        st.write("신규 규격")
        st.json(change["after"])
    with st.expander("규격 근거 위치"):
        for ref in change["source_refs"]:
            st.code(ref)
with col_b:
    st.markdown("#### 🧭 담당 조직 (Agent 2)")
    if not record["candidates"]:
        st.error("담당 조직을 식별할 수 없습니다. 반드시 수동 검토하세요.")
    else:
        if record["status"] == "REVIEW_CONFLICT":
            st.warning("동일 시스템의 R 역할이 충돌합니다. 담당자가 근거를 비교해 주세요.")
        for candidate in record["candidates"]:
            st.markdown(f"**{candidate['org_name']}** · RACI `{candidate['role']}`")
            st.progress(candidate["score"] / 100, text=f"담당 적합도 {candidate['score']}/100 · 근거 확보율 {candidate['evidence_coverage']}%")
            st.caption(f"판단 상태: {candidate['decision']} · 예측 확률이 아닌 규칙 기반 점수")
            with st.expander(f"근거 확인 · {candidate['org_name']}"):
                for evidence in candidate["evidence"]:
                    st.write(f"`{evidence['id']}` | {evidence['source']} | {evidence['supports']}")
        st.info("⚠️ 추천은 승인 전 초안입니다. 이 화면만으로 담당 부서를 확정하지 않습니다.")

st.divider()
st.subheader("개발 요청서 초안")
ticket = build_ticket(record)
st.markdown(f"**{ticket['title']}**")
st.write("추천 담당:", ticket["assignee_suggestion"])
for task in ticket["tasks"]:
    st.write("•", task)
st.caption(ticket["warning"])
st.download_button("⬇️ 요청서 JSON 저장", json.dumps(ticket, ensure_ascii=False, indent=2),
                   file_name=f"ticket_{change['change_id']}.json", mime="application/json")

scope = scope_key(old,new,change["change_id"])
with st.form(f"review_{scope}"):
    st.markdown("#### 담당자 검토")
    reviewer = st.text_input("검토자",max_chars=80)
    decision = st.radio("검토 결과",["검토 대기","추천 수용","재검토 필요","담당 부서 변경 필요"],horizontal=True)
    rationale = st.text_area("사유 또는 추가 근거",max_chars=2000)
    if st.form_submit_button("검토 기록 저장"):
        try:
            save_result(AUDIT_DB,scope,change["change_id"],reviewer,decision,rationale)
            st.success("검토 결과를 로컬 이력에 저장했습니다.")
        except (ValueError,sqlite3.Error) as exc:
            st.error(str(exc))
try:
    saved = history(AUDIT_DB,scope)
    if saved:
        st.dataframe([{"검토자":x["actor"],"결과":x["status"],"사유":x["note"],"시각":x["recorded_at"]} for x in saved],hide_index=True)
except sqlite3.Error:
    st.error("검토 이력을 읽을 수 없습니다.")
st.divider()
st.subheader("라이너 API 연동")
if not online:
    st.info("오프라인 데모 실행 중. Liner API 호출이 필요하면 왼쪽에서 'Liner Model API 사용'을 켜세요.")
else:
    if not safe_to_send:
        st.warning("실제 API 호출 전 왼쪽에서 공개/가상 데이터 전송 확인을 체크하세요.")
    if st.button("🤖 Liner Model API로 추천 근거 재검증", disabled=not safe_to_send):
        try:
            with st.spinner("AI가 가상 근거를 검증하고 있습니다..."):
                st.session_state[f"liner_{scope}"] = review_with_liner(record)
        except LinerError as exc:
            st.error(str(exc))
    previous = st.session_state.get(f"liner_{scope}")
    if previous:
        st.success("Model API 응답 수신 (실제 담당 확정은 아님)")
        st.json(previous)
    query = st.text_input("외부 공개 기술 자료 검색", value="금융 마이데이터 표준 API 규격 변경 공지")
    if st.button("🔎 Liner Search API로 공개 자료 검색", disabled=not safe_to_send):
        try:
            with st.spinner("외부 검색 중..."):
                st.session_state["web_results"] = search_web(query)
        except LinerError as exc:
            st.error(str(exc))
    if "web_results" in st.session_state:
        st.caption("검색 결과는 공식 변경 확정 자료가 아닙니다. 출처를 별도 검증하세요.")
        for item in st.session_state["web_results"]:
            st.markdown(f"- [{item.get('title','Untitled')}]({item.get('url','#')}) · {item.get('date','날짜 미상')}")
            st.caption(item.get("description", ""))

with st.expander("원본 분석 JSON"):
    st.json(record)
