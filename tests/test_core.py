import json
import unittest
from pathlib import Path
from src.core import compare_specs, recommend_owners, build_ticket

ROOT = Path(__file__).resolve().parent.parent

def read(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


class DiffTests(unittest.TestCase):
    def setUp(self):
        self.old = read("spec_v1.json")
        self.new = read("spec_v2.json")
        self.changes = compare_specs(self.old, self.new)

    def test_detects_expected_five_changes(self):
        self.assertEqual(len(self.changes), 5)
        kinds = {c["kind"] for c in self.changes}
        self.assertIn("REQUIRED_FIELD_ADDED", kinds)
        self.assertIn("FIELD_CONTRACT_CHANGED", kinds)
        self.assertIn("DESCRIPTION_CHANGED", kinds)

    def test_required_parameter_is_high(self):
        target = next(c for c in self.changes if c["field"] == "purpose_code")
        self.assertEqual(target["severity"], "HIGH")

    def test_ownership_is_evidence_backed(self):
        recommendations = recommend_owners(self.changes, read("catalog.json"))
        target = next(r for r in recommendations if r["change"]["field"] == "purpose_code")
        self.assertEqual(target["candidates"][0]["org_id"], "ORG-API")
        self.assertEqual(target["candidates"][0]["role"], "R")
        self.assertTrue(target["candidates"][0]["evidence"])
        self.assertEqual(target["status"], "HUMAN_REVIEW_REQUIRED")
        self.assertFalse(target["candidates"][0]["approved"])

    def test_ticket_is_unassigned_draft(self):
        rec = recommend_owners(self.changes, read("catalog.json"))[0]
        ticket = build_ticket(rec)
        self.assertEqual(ticket["status"], "DRAFT_REVIEW_REQUIRED")
        self.assertTrue(ticket["tasks"])

    def test_missing_ownership_does_not_fabricate(self):
        changes = self.changes
        results = recommend_owners(changes, {"organizations": [], "systems": [], "responsibility_rules": []})
        self.assertTrue(all(r["status"] == "UNRESOLVED" for r in results))

    def test_reject_duplicate_api_ids(self):
        bad = dict(self.new)
        bad["apis"] = self.new["apis"] * 2
        with self.assertRaises(ValueError):
            compare_specs(self.old, bad)


if __name__ == "__main__":
    unittest.main()
