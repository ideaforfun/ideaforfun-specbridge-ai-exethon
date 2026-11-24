"""Public-law demonstration and local review workspace."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from .audit import history, request_reviews, save_result, scope_key
from .law import compare_law_versions, review_routes, tree
from .liner_client import LinerError, draft_law_brief

STATUS = {"REQUESTED":"검토 대기", "REVIEWED":"검토 의견 등록", "CHANGES_REQUIRED":"보완 요청"}


def _show_change(change, versions):
    for column, side, version, caption in zip(st.columns(2),("before","after"),versions,("개정 전","개정 후")):
        with column:
            st.markdown(f"**{caption}**")
            st.caption(version["version"])
            clause = change[side]
            if clause:
                st.text(clause["reference"])
                st.text(clause["text"])
                if clause["source_url"]:
                    st.link_button(f"{caption} 출처",clause["source_url"])
            else:
                st.caption("비교 범위에 해당 조항 없음")


def _show_uploaded():
    left,right = st.columns(2)
    before = left.file_uploader("이전 조문 JSON",type="json")
    after = right.file_uploader("개정 조문 JSON",type="json")
    st.caption("각 파일에 version과 clauses를 넣고, 같은 조항은 동일한 id로 입력하세요. 조항에는 reference, text 및 선택적인 source_url을 사용합니다.")
    if before is None or after is None:
        return
    try:
        if max(before.size,after.size)>2*1024*1024:
            raise ValueError("파일당 2MB 이하 JSON을 사용하세요.")
        versions = [json.loads(f.getvalue().decode("utf-8-sig")) for f in (before,after)]
        changes = {x["id"]:x for x in compare_law_versions(*versions)}
    except ValueError as exc:
        st.error(str(exc))
        return
    if not changes:
        st.info("조문 변경이 없습니다.")
        return
    choice = st.selectbox("변경 조문",list(changes),format_func=lambda code:f"{changes[code]['kind']} · {code}")
    _show_change(changes[choice],versions)


def _latest(events):
    return {event["target"]:event for event in reversed(events)}


def _review_workflow(db: Path, scope: str, routes: list[dict], audit_route: dict) -> dict:
    st.subheader("관계부서 검토")
    st.caption("요청과 의견은 앱의 로컬 SQLite에 저장됩니다.")
    routes_by_id = {route["id"]:route for route in [*routes,audit_route] if route["department"]}
    try:
        events = history(db, scope)
        latest = _latest(events)
    except sqlite3.Error:
        st.error("검토 이력을 읽을 수 없습니다.")
        return {}
    include_audit = st.checkbox("독립 감사 사유가 있음",key=f"audit_{scope}")
    if include_audit or "AUDIT" in latest:
        routes = [*routes,audit_route]

    def label(code):
        row = routes_by_id[code]
        return f"{row['department']['name']} · {row['purpose']}"

    for route in routes:
        with st.expander(label(route["id"]) if route["department"] else f"{route['purpose']} · 부서 확인 필요"):
            for item in route["outcomes"]:
                st.write("•",item)
    available = [x["id"] for x in routes if x["department"] and x["id"] not in latest]
    if available:
        with st.form(f"queue_{scope}"):
            selected = st.multiselect("요청할 부서",available,default=[id for id in available if id!="AUDIT"],format_func=label)
            actor = st.text_input("요청자",max_chars=80)
            note = st.text_area("요청 메모",max_chars=2000)
            if st.form_submit_button("검토 요청 등록"):
                try:
                    count = request_reviews(db,scope,selected,actor,note)
                    st.session_state[f"queued_{scope}"] = count
                    st.rerun()
                except (ValueError,sqlite3.Error) as exc:
                    st.error(str(exc))
    if (count := st.session_state.pop(f"queued_{scope}",None)) is not None:
        st.success(f"새 검토 요청 {count}건을 등록했습니다.")

    if latest:
        target = st.selectbox("의견을 기록할 부서",list(latest),format_func=label,key=f"department_{scope}")
        with st.form(f"opinion_{scope}_{latest[target]['id']}"):
            actor = st.text_input("검토자",max_chars=80)
            status = st.radio("검토 결과",("REVIEWED","CHANGES_REQUIRED"),format_func=STATUS.get,horizontal=True)
            note = st.text_area("검토 의견과 후속 조치",max_chars=2000)
            if st.form_submit_button("검토 의견 저장"):
                try:
                    save_result(db,scope,target,actor,status,note,expected_id=latest[target]["id"])
                    events = history(db,scope)
                    latest = _latest(events)
                    st.success("검토 의견을 이력에 추가했습니다.")
                except (ValueError,sqlite3.Error) as exc:
                    st.error(str(exc))
    st.dataframe([{"영역":x["purpose"],"부서":x["department"]["name"] if x["department"] else "미확정",
                   "상태":STATUS.get(latest.get(x["id"],{}).get("status"),"요청 전")} for x in routes],hide_index=True)
    if events:
        with st.expander("검토 요청·의견 이력"):
            st.dataframe([{"부서":label(x["target"]),"기록자":x["actor"],
                           "시각 (KST)":datetime.fromisoformat(x["recorded_at"]).astimezone(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
                           "상태":STATUS[x["status"]],"의견":x["note"]} for x in events],hide_index=True)
    return {x["id"]:{"department_id":x["department"]["id"] if x["department"] else None,
                     "status":latest.get(x["id"],{}).get("status","NOT_REQUESTED")} for x in routes}


def show_law(case: dict, catalog: dict, policy: dict, db: Path):
    st.header("법령 변경 검토")
    mode = st.radio("비교 자료",("본인정보 전송요구권 예시","조문 원문 JSON 직접 비교"),horizontal=True)
    if mode == "조문 원문 JSON 직접 비교":
        _show_uploaded()
        return
    st.subheader(case["title"])
    st.caption("공개 개정문을 바탕으로 본인전송 관련 조항을 요약했습니다. 가상회사 적용 여부는 법무·준법 검토가 필요합니다.")
    st.link_button("국가법령정보센터 개정문",case["source_url"])
    as_of = st.date_input("시행일 비교 기준일",datetime.now(ZoneInfo("Asia/Seoul")).date())
    st.dataframe([{"구분":label,"시행일":day,"기준일 상태":"시행 예정" if day>as_of.isoformat() else "시행일 도래"}
                   for label,day in case["milestones"]],hide_index=True)
    company_id = st.selectbox("검토할 가상회사",list(case["companies"]),format_func=lambda key:case["companies"][key]["name"])
    company = case["companies"][company_id]
    versions = (case["before"],case["after"])
    changes = {change["id"]:change for change in compare_law_versions(*versions)}
    change_id = st.selectbox("검토할 변경",list(changes),
                             format_func=lambda key:f"{changes[key]['kind']} · {case['impacts'][key]['title']}")
    change = changes[change_id]
    impact = case["impacts"][change_id]
    _show_change(change,versions)
    st.subheader("업무·시스템 영향 검토")
    systems = [x for x in catalog["systems"] if x["id"]==company["system_id"]]
    st.write("시스템 후보 · "+", ".join(x["name"] for x in systems))
    for title,detail in (("회사 확인 항목",company["focus"]),("현업",impact["business"]),("개발",impact["engineering"])):
        st.write(f"**{title}** · {detail}")
    st.info("실행 책임 R 및 승인 책임 A · 미확정. 승인된 책임분장 근거가 필요합니다.")
    routes = review_routes(catalog,policy,company_id,impact["routes"])
    audit_route, = review_routes(catalog,policy,company_id,["AUDIT"])
    scope = scope_key(case["id"],company_id,change,impact,policy["version"],[(x["id"],x["department"]) for x in routes])
    st.subheader("Liner 검토 브리핑")
    st.caption("버튼을 누르면 공개 조문 요약과 가상 부서의 검토 기준을 Liner Model API로 보냅니다.")
    key = f"brief_{scope}"
    if st.button("Liner로 검토 브리핑 생성",key=f"generate_{scope}"):
        st.session_state.pop(key,None)
        with st.spinner("조문 근거와 검토 질문을 정리하고 있습니다…"):
            try:
                st.session_state[key] = draft_law_brief(change,impact,routes)
            except LinerError as exc:
                st.error(str(exc))
    brief = st.session_state.get(key)
    if brief:
        st.success("Liner Model API 응답 · 부서 및 근거 ID 검증 완료")
        st.text(brief["summary"])
        departments = {x["department"]["id"]:x["department"]["name"] for x in routes if x["department"]}
        for question in brief["reviews"]:
            evidence = brief["evidence"][question["evidence_id"]]
            with st.container(border=True):
                st.markdown(f"**{departments[question['department_id']]}**")
                st.text(question["question"])
                st.link_button(f"조문 근거 · {evidence['reference']}",evidence["source_url"])
    reviews = _review_workflow(db,scope,routes,audit_route)
    st.subheader("개발 요청서 초안")
    for item in impact["acceptance"]:
        st.write("•",item)
    ticket = dict(status="DRAFT_REVIEW_REQUIRED",ownership_status="UNRESOLVED",company=company["name"],
                  change=change,systems=systems,business=impact["business"],engineering=impact["engineering"],
                  acceptance=impact["acceptance"],department_reviews=reviews)
    if brief:
        ticket["liner_brief"] = brief
    st.download_button("요청서 초안 JSON 저장",json.dumps(ticket,ensure_ascii=False,indent=2),
                       f"law_review_{company_id}_{change_id}.json","application/json")


def show_org(catalog):
    st.header("가상 금융회사 전사 조직도")
    names = list(dict.fromkeys(x["company"] for x in catalog["organization_units"]))
    company = st.selectbox("가상회사",names)
    departments = {x["name"]:x for x in catalog["organizations"] if x["company"]==company}
    st.caption(f"{len(departments)}개 가상 팀 · 보고 관계와 팀별 검토 담당자")
    st.code("\n".join(tree(catalog,company)),language=None)
    name = st.selectbox("팀 직무 보기",list(departments))
    st.write(departments[name]["mandate"])
