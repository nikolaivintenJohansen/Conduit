# Sandbox credentials (Task 11)

Use after `docker compose up -d` and `python scripts/seed_sandbox.py`.

| Item | Value |
|------|-------|
| Email | `sandbox@example.com` |
| Password | `sandbox123` |
| API key | `sk-uaw-sandbox00000000000000000000000001` |
| Starting balance | $10.00 |

## Local stack

```powershell
docker compose up -d postgres redis
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python scripts/seed_sandbox.py
pytest -v
uvicorn services.app.main:app --reload
```

## Test database

Tests use `uaw_test` by default. Create it once:

```powershell
docker compose exec postgres psql -U uaw -d uaw -c "CREATE DATABASE uaw_test;"
$env:TEST_DATABASE_URL = "postgresql+psycopg://uaw:uaw@localhost:5432/uaw_test"
psql $env:TEST_DATABASE_URL -f schemas/001_initial.sql
pytest -v
```

## Mock provider

`services/gateway/mock_provider.py` returns deterministic completions and token costs without calling live LLM APIs. Use it in tests and local gateway development until Task 7 wires real providers.
