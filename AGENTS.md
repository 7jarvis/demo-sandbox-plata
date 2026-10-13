# Notes for AI coding agents

`app/` is a small card-payments service (Starlette + SQLite, web UI and
JSON API) — the system under test. `tests/` is a black-box Python test
framework for it. Test documentation is in `docs/` (Russian).

## Hard rules

- Tests never import `app/`. Expected values come from `docs/` and
  `tests/framework/money.py`, not from service code.
- API tests go through the layers: test → `framework/services` →
  `framework/adapters` → `framework/http_client`. Responses are parsed by
  strict models in `framework/models` (unknown/missing fields, bad formats
  and broken invariants fail).
- UI tests use the page objects in `framework/pages`; assertions stay in
  tests. Locators are verified on the running page before they are written
  (Playwright MCP or `scripts/inspect_page.py`).
- Every test owns its data (its own customer and cards). No `time.sleep`,
  no credentials in code.
- Every test has `@case("TC-...")` and the case exists in
  `docs/test-cases`; `scripts/check_traceability.py` enforces it in CI.
- Do not change service code to make a test pass. A failing test is a
  finding: report it.

## Commands

```
make up            # app on :8000 (docker compose)
make install       # test dependencies + Chromium
make smoke         # smoke suite
make regression    # full suite
make lint          # ruff + mypy
python scripts/check_traceability.py
python scripts/inspect_page.py /cards --sign-in +52XXXXXXXXXX --check '...'
```
