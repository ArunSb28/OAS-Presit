# OAS ⇄ Kong Test Workbench

Reads **local** OpenAPI 3.x specs and declarative Kong (decK) configs, correlates routes/ACLs with
operations, generates positive/negative/polymorphic/security test matrices and runs them live.

```
backend/   FastAPI · PyYAML · httpx · jsonschema · watchfiles
frontend/  React 18 + TS (Vite) · Tailwind v4 · Monaco · lucide-react
samples/   demo OAS (multi-file, discriminator), kong.yml, mock gateway
```

## Run

```powershell
# backend (port 8000)
cd backend
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt
$env:OAS_LOCAL_PATH = "D:\path\to\oas"; $env:KONG_LOCAL_PATH = "D:\path\to\kong"   # optional, defaults to ./samples
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000

# frontend (port 5173, proxies /api -> 8000)
cd frontend; npm install; npm run dev

# optional demo gateway (port 9000) enforcing key-auth + ACL + OAS validation
cd backend; .\.venv\Scripts\python ..\samples\mock_gateway.py
# optional: run every generated test against it
.\.venv\Scripts\python ..\samples\smoke_run.py
```

Config: `OAS_LOCAL_PATH`, `KONG_LOCAL_PATH`, `TARGET_URL` (env or `.env`); runtime edits via the UI
Settings modal persist to `data/config.json`. File edits in either folder trigger an automatic re-scan.

## API

| Endpoint | Purpose |
|---|---|
| `GET/POST /api/config` | directories, target URL, ACL credentials |
| `POST /api/rescan` | re-parse `OAS_DIR` + `KONG_DIR` |
| `GET /api/endpoints` | endpoints + Kong correlation + drift report |
| `GET /api/endpoints/{id}/testcases` | generated test matrix |
| `POST /api/execute` | httpx proxy execution + OAS response-contract validation |

## Notes
- Route matching handles prefix paths, `~regex` paths, `strip_path` true/false and service `path`.
- Auth is injected per Kong plugin: key-auth (header/query), jwt/oauth2 (Bearer), basic-auth (`user:pass`).
- Payload synthesis is built in (including regex-pattern sampling) instead of hypothesis-jsonschema/jsf,
  for deterministic, dependency-light output.
