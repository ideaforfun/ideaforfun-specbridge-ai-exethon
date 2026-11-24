import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock
from urllib.error import HTTPError

from src.audit import history, request_reviews, save_result, scope_key
from src.core import build_ticket, compare_specs, recommend_owners
from src.law import compare_law_versions, review_routes, tree
from src.liner_client import LinerError, draft_law_brief, review_with_liner, search_web

DATA = Path(__file__).resolve().parents[1] / "data/liner_hackathon"


def read(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def reply(data):
    return Mock(return_value=BytesIO(json.dumps({"choices":[{"message":{"content":json.dumps(data)}}]}).encode()))


class SubmissionWorkflowTests(TestCase):
    def setUp(self):
        self.catalog = read("catalog.json")
        self.case = read("self_transfer_case.json")
        self.policy = read("cross_functional_review.json")
        self.changes = compare_law_versions(self.case["before"],self.case["after"])
        self.change = next(x for x in self.changes if x["id"]=="DOWNLOAD")
        self.impact = self.case["impacts"]["DOWNLOAD"]
        self.routes = review_routes(self.catalog,self.policy,"INS",self.impact["routes"])
        self.brief = {"summary":"검토 초안","reviews":[
            {"department_id":x["department"]["id"],"question":"검토 증적은 무엇인가요?","evidence_id":"AFTER-DOWNLOAD"}
            for x in self.routes]}

    def test_public_case_has_five_changes(self):
        self.assertEqual(len(self.changes),5)
        self.assertEqual(self.change["kind"],"신설")

    def test_law_invalid_input(self):
        with self.assertRaises(ValueError):
            compare_law_versions({},self.case["after"])

    def test_clause_reference_change(self):
        old={"version":"1","clauses":[{"id":"A","reference":"제1조","text":"내용"}]}
        new={"version":"2","clauses":[{"id":"A","reference":"제2조","text":"내용"}]}
        self.assertEqual(compare_law_versions(old,new)[0]["kind"],"조문 위치 변경")

    def test_law_brief_carries_validated_references(self):
        opener=reply(self.brief)
        output=draft_law_brief(self.change,self.impact,self.routes,"demo",opener=opener)
        self.assertEqual(output["reviews"],self.brief["reviews"])
        self.assertEqual(set(output["evidence"]),{"AFTER-DOWNLOAD"})
        self.assertEqual(json.loads(opener.call_args.args[0].data)["response_format"]["type"],"json_schema")

    def test_unknown_law_evidence_or_department_rejected(self):
        for field in ("evidence_id","department_id"):
            with self.subTest(field=field), self.assertRaises(LinerError):
                payload = self.brief | {"reviews":[self.brief["reviews"][0] | {field:"unknown"},*self.brief["reviews"][1:]]}
                draft_law_brief(self.change,self.impact,self.routes,"demo",opener=reply(payload))

    def test_duplicate_brief_department_rejected(self):
        with self.assertRaises(LinerError):
            draft_law_brief(self.change,self.impact,self.routes,"demo",
                            opener=reply(self.brief | {"reviews":[self.brief["reviews"][0]]*5}))

    def test_routes_only_use_selected_company(self):
        self.assertEqual(len(self.routes),5)
        self.assertTrue(all(x["department"]["company"]=="라이너보험" for x in self.routes))

    def test_four_companies_have_audit_branch(self):
        for company in self.case["companies"].values():
            values = tree(self.catalog,company["name"])
            self.assertTrue(any("감사위원회" in x for x in values))
            self.assertTrue(any("법무팀" in x for x in values))

    def test_bank_conflict_holds_assignment(self):
        changes = compare_specs(read("spec_before.json"),read("spec_after.json"))
        records = recommend_owners(changes,self.catalog)
        bank = next(x for x in records if x["change"]["api_id"]=="BANK-001")
        self.assertEqual(bank["status"],"REVIEW_CONFLICT")
        self.assertIn("미확정",build_ticket(bank)["assignee_suggestion"])

    def test_insurance_remains_unresolved(self):
        changes = compare_specs(read("spec_before.json"),read("spec_after.json"))
        records = recommend_owners(changes,self.catalog)
        insurance = next(x for x in records if x["change"]["api_id"]=="INS-001")
        self.assertEqual(insurance["status"],"UNRESOLVED")

    def test_review_request_idempotency_and_history(self):
        with TemporaryDirectory() as folder:
            db = Path(folder)/"audit.sqlite3"
            self.assertEqual(request_reviews(db,"scope",["LEGAL"],"데모","검토"),1)
            self.assertEqual(request_reviews(db,"scope",["LEGAL"],"데모","검토"),0)
            request, = history(db,"scope")
            save_result(db,"scope","LEGAL","데모","CHANGES_REQUIRED","보완",expected_id=request["id"])
            self.assertEqual([x["status"] for x in history(db,"scope")],["CHANGES_REQUIRED","REQUESTED"])
            self.assertEqual(history(db,"other"),[])

    def test_invalid_review_rejected(self):
        with TemporaryDirectory() as folder, self.assertRaises(ValueError):
            request_reviews(Path(folder)/"audit.sqlite3","scope",["LEGAL"],"","검토")

    def test_scope_is_case_specific(self):
        self.assertNotEqual(scope_key("INS","DOWNLOAD"),scope_key("BANK","DOWNLOAD"))

    def test_search_errors_are_sanitized(self):
        for code in (401,429):
            with self.subTest(code=code), self.assertRaisesRegex(LinerError,f"HTTP {code}"):
                search_web("자료","demo",opener=Mock(side_effect=HTTPError("https://example.com",code,"test",{},None)))

    def test_transport_invalid_json(self):
        with self.assertRaises(LinerError):
            search_web("자료","demo",opener=Mock(return_value=BytesIO(b"{")))

    def test_search_returns_candidate_items(self):
        demo=[{"title":"공개 자료 후보"}]
        self.assertEqual(search_web("자료","demo",opener=Mock(return_value=BytesIO(json.dumps({"results":demo}).encode()))),demo)

    def test_unregistered_api_evidence_rejected(self):
        response = {"summary":"데모","risk":"HIGH","review_questions":[],"cited_evidence_ids":["UNKNOWN"]}
        with self.assertRaises(LinerError):
            review_with_liner({"candidates":[]},"demo",opener=reply(response))

    def test_registered_api_evidence_valid(self):
        response = {"summary":"데모","risk":"HIGH","review_questions":[],"cited_evidence_ids":["EVD-1"]}
        self.assertEqual(review_with_liner({"candidates":[{"evidence":[{"id":"EVD-1"}]}]},"demo",
                                          opener=reply(response)),response)
