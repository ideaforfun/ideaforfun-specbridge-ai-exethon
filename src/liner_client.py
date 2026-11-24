"""Liner HTTP adapter with dependency injection for offline tests."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://platform.liner.com/api/v1"


class LinerError(RuntimeError):
    pass


def _request(endpoint, payload, api_key=None, *, opener=None):
    key = api_key or os.getenv("LINER_API_KEY")
    if not key or key == "replace_with_your_liner_api_key":
        raise LinerError("LINER_API_KEY가 설정되지 않았습니다.")
    request = Request(BASE+endpoint, data=json.dumps(payload, ensure_ascii=False).encode(),
                      headers={"x-api-key":key,"Content-Type":"application/json"}, method="POST")
    try:
        with (opener or urlopen)(request, timeout=75) as response:
            result = json.loads(response.read().decode())
    except HTTPError as exc:
        code = exc.code
        exc.close()
        raise LinerError(f"Liner API HTTP {code}") from None
    except (URLError, TimeoutError):
        raise LinerError("Liner API에 연결할 수 없습니다.") from None
    except ValueError:
        raise LinerError("Liner API 응답이 올바른 JSON이 아닙니다.") from None
    if not isinstance(result, dict):
        raise LinerError("Liner API 응답은 JSON 객체여야 합니다.")
    return result


def search_web(query, api_key=None, *, opener=None):
    data = _request("/tools/search/web", {"query":query, "country_code":"kr", "lang":"ko",
                    "max_results":5, "include_knowledge":False},api_key,opener=opener)
    results = data.get("results", [])
    if not isinstance(results,list) or any(not isinstance(row,dict) for row in results):
        raise LinerError("Liner 검색 결과 형식을 확인할 수 없습니다.")
    return results


def _completion(context, prompt, response_format, api_key=None, *, opener=None):
    data = _request("/chat/completions", {
        "model":os.getenv("LINER_MODEL","liner-gpt-router"),
        "messages":[{"role":"system","content":prompt},
                    {"role":"user","content":json.dumps(context,ensure_ascii=False)}],
        "response_format":response_format,"stream":False,
    },api_key,opener=opener)
    try:
        value = json.loads(data["choices"][0]["message"]["content"])
    except (KeyError,IndexError,TypeError,ValueError):
        raise LinerError("Liner Model 응답을 해석할 수 없습니다.") from None
    if not isinstance(value,dict):
        raise LinerError("Liner Model 응답은 JSON 객체여야 합니다.")
    return value


def review_with_liner(record, api_key=None, *, opener=None):
    allowed = {e["id"] for c in record["candidates"] for e in c["evidence"]}
    reply = _completion(record, "한국어 JSON으로 summary, risk(LOW|MEDIUM|HIGH), review_questions 문자열 배열, "
                       "cited_evidence_ids 문자열 배열을 반환하세요. 입력 근거만 인용하고 사람의 승인을 대신하지 마세요.",
                       {"type":"json_object"},api_key,opener=opener)
    if (reply.keys() != {"summary","risk","review_questions","cited_evidence_ids"}
            or not isinstance(reply["summary"],str) or not reply["summary"].strip()
            or reply["risk"] not in ("LOW","MEDIUM","HIGH")
            or any(not isinstance(reply[key],list) or any(not isinstance(item,str) for item in reply[key])
                   for key in ("review_questions","cited_evidence_ids"))
            or not allowed.issuperset(reply["cited_evidence_ids"])):
        raise LinerError("Liner Model 응답의 형식 또는 근거 ID가 올바르지 않습니다.")
    return reply


def draft_law_brief(change, impact, routes, api_key=None, *, opener=None):
    evidence = {f"{side.upper()}-{change['id']}":change[side] for side in ("before","after") if change[side]}
    departments = {row["department"]["id"]:row["outcomes"] for row in routes if row["department"]}
    if not departments:
        raise LinerError("등록된 검토 부서가 없습니다.")
    item_schema = {"type":"object","properties":{
        "department_id":{"type":"string","enum":list(departments)},
        "question":{"type":"string"},
        "evidence_id":{"type":"string","enum":list(evidence)}},
        "required":["department_id","question","evidence_id"],"additionalProperties":False}
    schema = {"type":"object","properties":{"summary":{"type":"string"},
                  "reviews":{"type":"array","items":item_schema}},
              "required":["summary","reviews"],"additionalProperties":False}
    event = _completion({"public_clauses":evidence,"synthetic_review_areas":departments,
                         "business":impact["business"],"engineering":impact["engineering"]},
        "공개 근거를 바탕으로 검토자용 한국어 JSON을 작성하세요. 요약 2문장, 부서별로 질문 한 문장씩 제출하세요. "
        "각 질문에 입력에 있는 근거 ID를 사용하세요. 적용 의무, 담당자, R/A와 배포를 결정하지 마세요.",
        {"type":"json_schema","json_schema":{"name":"specbridge_law_brief","strict":True,"schema":schema}},
        api_key,opener=opener)
    if (event.keys() != {"summary","reviews"} or not isinstance(event["summary"],str)
            or not 0 < len(event["summary"].strip()) <= 500 or not isinstance(event["reviews"],list)
            or len(event["reviews"]) != len(departments)):
        raise LinerError("Liner 브리핑 형식 또는 부서 수가 올바르지 않습니다.")
    seen = set()
    for row in event["reviews"]:
        if (not isinstance(row,dict) or row.keys() != item_schema["properties"].keys()
                or any(not isinstance(value,str) or not value.strip() for value in row.values())
                or len(row["question"]) > 300 or row["department_id"] not in departments
                or row["department_id"] in seen or row["evidence_id"] not in evidence):
            raise LinerError("Liner 브리핑에 미등록 부서, 근거 또는 잘못된 질문이 있습니다.")
        seen.add(row["department_id"])
    return event | {"evidence":evidence}
