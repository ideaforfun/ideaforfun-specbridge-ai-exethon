"""Offline clause comparison and catalog-based review routing."""
from difflib import unified_diff
from urllib.parse import urlsplit


def clause_index(version: dict) -> dict:
    if not isinstance(version, dict) or not isinstance(version.get("version"), str) or not isinstance(version.get("clauses"), list):
        raise ValueError("version 문자열과 clauses 배열이 필요합니다.")
    result = {}
    for clause in version["clauses"]:
        fields = ("id", "reference", "text")
        if not isinstance(clause, dict) or any(
            not isinstance(clause.get(key), str) or not clause[key].strip() for key in fields
        ):
            raise ValueError("조문마다 id, reference, text를 입력하세요.")
        code = clause["id"].strip()
        if code in result:
            raise ValueError("같은 버전의 조문 ID가 중복됩니다.")
        source = clause.get("source_url", "")
        if not isinstance(source, str):
            raise ValueError("조문 출처는 HTTPS URL이어야 합니다.")
        if source:
            parsed = urlsplit(source)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("조문 출처는 인증정보가 없는 HTTPS URL이어야 합니다.")
        result[code] = {key:clause[key].strip() for key in fields} | {"source_url":source}
    return result


def compare_law_versions(before: dict, after: dict) -> list[dict]:
    previous, current = clause_index(before), clause_index(after)
    result = []
    for code in dict.fromkeys([*previous,*current]):
        old, new = previous.get(code), current.get(code)
        if old is None:
            kind = "신설"
        elif new is None:
            kind = "삭제"
        elif old["text"].split() != new["text"].split():
            kind = "변경"
        elif old["reference"] != new["reference"]:
            kind = "조문 위치 변경"
        else:
            continue
        result.append(dict(id=code, kind=kind, before=old, after=new))
    return result


def review_routes(catalog: dict, policy: dict, company: str, route_ids: list[str]) -> list[dict]:
    registry = {org["id"]:org for org in catalog["organizations"] if org["active"]}
    rules = {rule["id"]:rule for rule in policy["routing"]}
    result = []
    for code in dict.fromkeys(route_ids):
        rule = rules[code]
        department = registry.get(rule["review_with"].get(company))
        if department and not department["id"].startswith(f"ORG-{company}-"):
            department = None
        result.append({"id":code,"purpose":rule["purpose"],"outcomes":rule["outcomes"],"department":department})
    return result


def tree(catalog: dict, company: str) -> list[str]:
    children = {}
    for node in catalog["organization_units"] + catalog["organizations"]:
        if node["company"] == company:
            children.setdefault(node["parent_id"], []).append(node)

    def walk(parent, prefix):
        for index, node in enumerate(children.get(parent, [])):
            last = index + 1 == len(children[parent])
            name = node["name"].removeprefix(company+" ")
            alias = f" · {node['reviewer_alias']}" if "reviewer_alias" in node else ""
            yield prefix + ("└─ " if last else "├─ " if parent else "") + name + alias
            yield from walk(node["id"], prefix + ("   " if last else "│  "))

    return list(walk(None,""))
