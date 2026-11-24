# SpecBridge AI: Codex instructions

## Product goal
Build a Korean-language, evidence-backed API-change management MVP for the Liner EXE-THON hackathon. A user compares synthetic API spec versions, reviews system impacts and RACI ownership, and exports a draft development ticket. Do not claim to assign work automatically.

## Safety/data rules
- All bundled sample data is synthetic. Never upload private corporate specifications, credentials, or personal data to the Liner API.
- Never print or commit `LINER_API_KEY`, `.env`, API secrets, or full production logs.
- LLM outputs are untrusted recommendations. Validate citations against evidence IDs and never invent departments.
- An unknown owner is `UNRESOLVED`, not an invented assignment. Do not silently change ownership rules.
- Any external request must be initiated by a button in the UI, and the UI must show when remote services are used.

## Development rules
- Keep the JSON schema in `data/` working and maintain backward compatibility.
- `src/core.py` is deterministic and must not make HTTP calls.
- `src/liner_client.py` is the only Liner HTTP adapter.
- Test with `python -m unittest discover -s tests -v` after changes.
- Avoid unnecessary dependencies. Keep basic Streamlit UI usable without API keys.
- Clearly label confidence scores as heuristic suitability, not statistical probabilities.

## Implementation roadmap
1. Expand change types, version-aware relation model, and missing evidence handling.
2. Improve rule-based R&R to capture conflicting official owners, validity periods and RACI roles.
3. Add Liner model structured validation of work items, schema validation, and prompt-versioned eval fixtures.
4. Add optional PDF/Excel import with extract-and-review workflow, not just free-form model diff.
5. Add synthetic regression evaluations, trace export, and polished Korean demo UI.
