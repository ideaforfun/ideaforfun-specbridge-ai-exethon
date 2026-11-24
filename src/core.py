"""Deterministic API diff, evidence-backed ownership, and request drafting.

All example data is synthetic. This module does not call external services.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

WEIGHTS = {"official_rr": 30, "system_owner": 25, "api_scope": 20, "history": 15, "active_org": 10}


@dataclass(frozen=True)
class Change:
    change_id: str
    api_id: str
    field_group: str
    field: str
    kind: str
    severity: str
    before: Any
    after: Any
    source_refs: list[str]

    def as_dict(self):
        return asdict(self)


def _fields(api: dict, group: str) -> dict[str, dict]:
    return {f["name"]: f for f in api.get(group, [])}


def _api_map(spec: dict) -> dict[str, dict]:
    if not isinstance(spec, dict) or not isinstance(spec.get("apis"), list):
        raise ValueError("규격 파일은 apis 배열을 포함한 JSON 객체여야 합니다.")
    apis = spec["apis"]
    if any(not isinstance(api, dict) or not isinstance(api.get("id"), str) for api in apis):
        raise ValueError("각 API는 문자열 id가 있어야 합니다.")
    if len({api["id"] for api in apis}) != len(apis):
        raise ValueError("API id 중복이 있습니다.")
    for api in apis:
        for group in ("request", "response", "errors"):
            fields = api.get(group, [])
            if not isinstance(fields, list) or any(not isinstance(f, dict) or not isinstance(f.get("name"), str) for f in fields):
                raise ValueError(f"{api['id']}의 {group}은 name이 있는 객체의 배열이어야 합니다.")
            if len({f["name"] for f in fields}) != len(fields):
                raise ValueError(f"{api['id']}의 {group}에 중복 필드가 있습니다.")
    return {api["id"]: api for api in apis}


def compare_specs(old: dict, new: dict) -> list[dict]:
    """Compare simplified MVP API schemas. Does not claim full OpenAPI compatibility."""
    old_map, new_map = _api_map(old), _api_map(new)
    changes: list[dict] = []

    def emit(api_id: str, group: str, field: str, kind: str, severity: str, before: Any, after: Any):
        index = len(changes) + 1
        changes.append(Change(
            change_id=f"CHG-{index:03d}", api_id=api_id, field_group=group,
            field=field, kind=kind, severity=severity,
            before=before, after=after,
            source_refs=[f"{old.get('version','old')}:{api_id}:{group}:{field}",
                         f"{new.get('version','new')}:{api_id}:{group}:{field}"],
        ).as_dict())

    for api_id in sorted(set(old_map) | set(new_map)):
        before_api, after_api = old_map.get(api_id), new_map.get(api_id)
        if before_api is None:
            emit(api_id, "api", api_id, "API_ADDED", "MEDIUM", None, after_api)
            continue
        if after_api is None:
            emit(api_id, "api", api_id, "API_REMOVED", "HIGH", before_api, None)
            continue
        for group in ("request", "response", "errors"):
            previous, current = _fields(before_api, group), _fields(after_api, group)
            for field in sorted(set(previous) | set(current)):
                a, b = previous.get(field), current.get(field)
                if a is None:
                    is_required = group == "request" and b.get("required", False)
                    emit(api_id, group, field,
                         "REQUIRED_FIELD_ADDED" if is_required else "FIELD_ADDED",
                         "HIGH" if is_required else "MEDIUM" if group == "errors" else "LOW", None, b)
                elif b is None:
                    emit(api_id, group, field, "FIELD_REMOVED", "HIGH", a, None)
                else:
                    structural = [k for k in ("type", "required", "enum") if a.get(k) != b.get(k)]
                    if structural:
                        emit(api_id, group, field, "FIELD_CONTRACT_CHANGED", "HIGH", a, b)
                    elif a.get("description") != b.get("description"):
                        emit(api_id, group, field, "DESCRIPTION_CHANGED", "LOW", a, b)
    # Surface changes requiring action first in the demo UI.
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    changes.sort(key=lambda c: (order.get(c["severity"], 3), c["api_id"], c["field"]))
    for index, item in enumerate(changes, 1):
        item["change_id"] = f"CHG-{index:03d}"
    return changes


def _work_type(change: dict) -> str:
    if change["kind"] == "DESCRIPTION_CHANGED":
        return "DOCUMENTATION_REVIEW"
    if change["field_group"] == "request":
        return "REQUEST_MAPPING"
    if change["field_group"] == "response":
        return "RESPONSE_MAPPING"
    if change["field_group"] == "errors":
        return "ERROR_HANDLING"
    return "API_LIFECYCLE"


def recommend_owners(changes: list[dict], catalog: dict) -> list[dict]:
    """Return candidate ownership recommendations, never auto-assign responsibility."""
    orgs = {o["id"]: o for o in catalog.get("organizations", [])}
    systems = [s for s in catalog.get("systems", []) if s.get("active", True)]
    rules = catalog.get("responsibility_rules", [])
    result: list[dict] = []
    for change in changes:
        wt = _work_type(change)
        matching = [s for s in systems if change["api_id"] in s.get("api_ids", [])]
        candidates = []
        for system in matching:
            for rule in rules:
                if rule.get("system_id") != system["id"] or wt not in rule.get("work_types", []):
                    continue
                org = orgs.get(rule.get("org_id"))
                if not org or not org.get("active", True):
                    continue
                evidence = [
                    {"id": f"EVD-RR-{rule['id']}", "kind": "OFFICIAL_RR", "source": rule.get("source", "등록된 업무분장"),
                     "supports": "해당 업무 유형의 공식 담당으로 등록", "verified": bool(rule.get("approved", False))},
                    {"id": f"EVD-SYS-{system['id']}", "kind": "SYSTEM_CATALOG", "source": system.get("source", "시스템 카탈로그"),
                     "supports": f"{change['api_id']} API 연결 시스템", "verified": bool(system.get("approved", False))},
                ]
                # Missing proof is not scored as negative evidence; record evidence coverage separately.
                points = {
                    "official_rr": 100 if rule.get("approved") else None,
                    "system_owner": 100 if system.get("owner_org_id") == org["id"] and system.get("approved") else None,
                    "api_scope": 100 if change["api_id"] in system.get("api_ids", []) and system.get("approved") else None,
                    "history": 100 if any(h.get("org_id") == org["id"] and h.get("work_type") == wt and h.get("api_id") == change["api_id"]
                                          for h in catalog.get("history", [])) else None,
                    "active_org": 100 if org.get("active") else None,
                }
                score = round(sum(WEIGHTS[k] * (v or 0) for k, v in points.items()) / 100)
                coverage = sum(WEIGHTS[k] for k, v in points.items() if v is not None)
                candidates.append({"org_id": org["id"], "org_name": org["name"], "system_id": system["id"],
                                   "role": rule.get("role", "R"), "work_type": wt,
                                   "score": score, "evidence_coverage": coverage,
                                   "points": points, "evidence": evidence,
                                   "approved": False})
        candidates.sort(key=lambda c: (-c["score"], c["org_id"]))
        by_system = {}
        for candidate in candidates:
            if candidate["role"] == "R":
                by_system.setdefault(candidate["system_id"], []).append(candidate)
        conflicts = set()
        for system_id, candidates_for_system in by_system.items():
            official = {c["org_id"] for c in candidates_for_system if c["evidence"][0]["verified"]}
            first = candidates_for_system[0]
            if len(official) > 1 or any(
                c["org_id"] != first["org_id"] and first["score"] - c["score"] < 15
                for c in candidates_for_system[1:]
            ):
                conflicts.add(system_id)
        for c in candidates:
            c["decision"] = ("REVIEW_CONFLICT" if c["system_id"] in conflicts and c["role"] == "R"
                             else "REVIEW_REQUIRED" if c["score"] < 85 or c["evidence_coverage"] < 90
                             else "RECOMMEND_REVIEW")
        result.append({"change": change, "work_type": wt, "candidates": candidates,
                       "status": "REVIEW_CONFLICT" if conflicts else "HUMAN_REVIEW_REQUIRED" if candidates else "UNRESOLVED",
                       "notes": "동일 역할 담당 경합" if conflicts else "담당자 검토 필요"})
    return result


WORK_TEMPLATES = {
    "REQUEST_MAPPING": ["요청 파라미터 생성 및 유효성 검사 로직 확인", "관련 인증·권한 처리 영향 검토", "정상·누락·기존 버전 호환성 테스트"],
    "RESPONSE_MAPPING": ["수신 응답 필드 파싱 및 데이터 사용 여부 확인", "저장·조회 시스템의 연계 영향 검토", "신규 필드 유무별 회귀 테스트"],
    "ERROR_HANDLING": ["신규 오류코드 매핑 및 재시도 정책 검토", "오류 메시지 및 인증 연계 검토", "오류 응답별 회귀 테스트"],
    "API_LIFECYCLE": ["API 호출 지점 및 대체 API 확인", "연계 대상 및 배포 영향도 검토", "서비스 통합 테스트"],
    "DOCUMENTATION_REVIEW": ["문서 설명 외 실제 계약 변경이 없는지 확인"]
}


def build_ticket(record: dict) -> dict:
    change = record["change"]
    primary = next((c for c in record["candidates"] if c["role"] == "R"), None)
    return {
        "title": f"[{change['api_id']}] {change['field']} {change['kind']} 대응 검토",
        "change_id": change["change_id"],
        "assignee_suggestion": primary["org_name"] if primary and record["status"] != "REVIEW_CONFLICT" else "담당 조직 미확정",
        "status": "DRAFT_REVIEW_REQUIRED",
        "tasks": WORK_TEMPLATES[record["work_type"]],
        "evidence": [e["id"] for c in record["candidates"] for e in c["evidence"]],
        "source_refs": change["source_refs"],
        "warning": "가상 데이터 기반 초안. 담당자 승인 후에만 실제 업무 배정 가능"
    }
