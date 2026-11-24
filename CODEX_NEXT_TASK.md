# Paste this task into Codex in this project

You are developing SpecBridge AI for the Liner EXE-THON. Inspect README.md and AGENTS.md first. The code already contains a working offline Streamlit demo, synthetic API V1/V2 data, deterministic API diff, RACI recommendation, evidence references, and Liner HTTP adapters.

Please implement the **next increment** rather than rewriting the project:
1. Create structured schemas (Pydantic or typed validation) for change, candidate, evidence, and review output. Reject Liner model responses with hallucinated evidence IDs.
2. Add an audit trail to a local SQLite DB for human review decisions (who/when/why), and make saved decisions visible in the UI. Never automatically assign work.
3. Add a test fixture where two departments claim the same R role and verify 'review conflict'.
4. Improve UI to show change severities and evidence provenance clearly. Keep Korean UI.
5. Make a mockable Liner API adapter and add tests for success, HTTP 401/429 and malformed JSON (no real paid calls in tests).
6. Update README and run tests. Show a short test summary.

Constraints: Never expose API keys. Use only demo/synthetic data. Keep the offline experience fully usable. Do not invent any real corporate internal ownership records. Search API results must be labeled as candidates, not verified official notices.
