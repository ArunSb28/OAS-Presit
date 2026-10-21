# Role & Objective
Act as a Principal API Infrastructure & Automation Engineer. Build a full-stack, automated API test-generation and execution workbench that reads directly from local file system directories:
1. `OAS_DIR`: Local path to a directory containing OpenAPI Specification files (OAS 3.0 / 3.1 in YAML/JSON).
2. `KONG_DIR`: Local path to a directory containing declarative Kong Gateway configuration files (decK format / `kong.yml`).

The application must parse the local folders, resolve cross-file relative `$ref` references, correlate Kong routes and ACL policies with OAS endpoints, handle polymorphic schemas (`discriminator`), automatically generate a complete matrix of positive and negative test cases, and provide an interactive React frontend for payload inspection, editing, and execution.

---

# Tech Stack & Architecture

## Backend (`/backend`)
- **Runtime:** Python 3.11+
- **Framework:** FastAPI with Uvicorn
- **File System Watcher / Parser:** `watchfiles` or `watchdog` (to detect local file edits in real time)
- **OAS Processing:** `prance` or `openapi-spec-validator` (dereferencing local relative file pointers, e.g., `$ref: './schemas/Payment.yaml'`)
- **Kong Parsing:** `PyYAML`
- **Payload Synthesis:** `hypothesis-jsonschema` or `jsf`
- **Execution & Validation:** `httpx` (async proxy client to avoid CORS) and `jsonschema`

## Frontend (`/frontend`)
- **Framework:** React 18+ with TypeScript (Vite)
- **Styling:** Tailwind CSS + Lucide Icons
- **JSON Editing & Inspection:** `@monaco-editor/react`

---

# Core Functional Specifications

## 1. Local Directory Configuration & Ingestion Engine
- **Configurable Local Paths:**
  - Provide an initial configuration via `.env` / environment variables: `OAS_LOCAL_PATH` and `KONG_LOCAL_PATH`.
  - Provide a Settings modal in the frontend to view or update these paths at runtime and trigger a re-scan.
- **Multi-File OAS Dereferencing:**
  - Recursively traverse `OAS_LOCAL_PATH`.
  - Resolve internal pointers and local cross-file references cleanly using the directory root as the base URI.
  - Index every operation by `operationId`, HTTP `method`, and `path`.
- **Kong Declarative Parser:**
  - Recursively parse all `.yaml`/`.yml` files in `KONG_LOCAL_PATH`.
  - Extract `services`, `routes` (`paths`, `methods`, `strip_path`, `prefixes`), and route/service-level plugins:
    - `acl` (`allow` and `deny` consumer groups)
    - Authentication plugins (`key-auth`, `jwt`, `basic-auth`, `oauth2`)
- **Route Correlation & Drift Detection:**
  - Match Kong routes to OAS paths (handling prefix matching and `strip_path: true|false`).
  - Flag drift conditions in the UI:
    - **Unrouted OAS Operations** (defined in spec, missing in Kong).
    - **Orphaned Kong Routes** (exposed in Kong, missing in OAS).

---

## 2. Test Matrix Generation Engine
For every correlated endpoint, inspect OAS parameters (path, query, header) and `requestBody`:
- **Happy Path (Minimal):** Generate payloads populated ONLY with fields where `required: true`.
- **Happy Path (Maximal):** Generate payloads populating all mandatory and optional fields.
- **Single-Fault Missing Required Checks:**
  - Generate $N$ test cases omitting exactly ONE required parameter, header, or body property at a time (Expected: `400 Bad Request` / `422 Unprocessable Entity`).
- **Data Type & Boundary Violations:**
  - Invert data types (e.g., string for integer).
  - Test boundaries: `minimum - 1`, `maximum + 1`, `minLength - 1`, `maxLength + 1`, regex `pattern` violations, and unmapped `enum` values (Expected: `400 Bad Request`).

---

## 3. Polymorphism & Discriminator Generator
When `requestBody` uses `discriminator` with `oneOf`, `anyOf`, or `allOf`:
- Extract `discriminator.propertyName` and explicit or implicit `mapping`.
- **Sub-Schema Forking:** Branch execution into separate test suites for each mapped discriminator variant (e.g., `card` vs `bank`).
- **Variant Suite:** Lock the discriminator key to the target value, resolve its specific sub-schema, and generate required/optional/boundary tests specifically for that variant.
- **Discriminator Negative Tests:**
  1. Missing discriminator field entirely (`400 Bad Request`).
  2. Unmapped discriminator value (`400 Bad Request`).
  3. **Polymorphic Bleed:** Setting discriminator property to Variant A, but supplying required fields from Variant B (`400 Bad Request`).

---

## 4. Kong Gateway & ACL Security Tests
- **Authorized ACL Group:** Inject valid credentials for a consumer group listed in `acl.config.allow` (`200 OK`).
- **Forbidden ACL Group:** Inject valid credentials for a consumer group NOT in `acl.config.allow` (`403 Forbidden`).
- **Unauthenticated:** Omit auth headers/keys required by the plugin (`401 Unauthorized`).

---

## 5. Frontend UI Specifications
Implement a 3-pane responsive layout:
1. **Top Bar:**
   - Local directory path displays with a **"Re-scan Local Folders"** button.
   - Target Base URL input (e.g., `http://localhost:8000` or `https://staging-gateway`).
   - **ACL Token Manager Modal:** Allows users to map consumer group names (from Kong YAML) to actual test tokens/headers so live security tests succeed.
2. **Left Sidebar:**
   - Searchable list of all endpoints, filterable by Tag/Service.
   - Badges for HTTP Method (`GET`, `POST`, `PUT`, `DELETE`), Kong route status, and drift alerts.
3. **Main Workspace (Selected API):**
   - **Endpoint Summary:** OAS path, mapped Kong route, required headers, and active ACL groups.
   - **Categorized Test Case Matrix:**
     - *Positive (Minimal / Maximal)*
     - *Polymorphic Discriminator Variants (sub-tabs per discriminator value)*
     - *Negative: Missing Required*
     - *Negative: Type & Boundary Violations*
     - *Kong Security & ACL Checks*
   - **Interactive Test Drawer / Inspector:**
     - Clicking any test case displays an editable Monaco Editor for Params, Headers, and JSON Body.
     - **"Run Test"** and **"Run All Cases"** buttons.
     - Live execution via the backend proxy showing response status, response latency (ms), response headers, JSON response body, and OAS schema validation results (Pass/Fail with field diffs).

---

## Backend Endpoints to Implement

- `GET /api/config`: Get configured local directory paths.
- `POST /api/config`: Update local directory paths and re-scan.
- `POST /api/rescan`: Manually trigger re-parsing of `OAS_DIR` and `KONG_DIR`.
- `GET /api/endpoints`: Return all indexed endpoints, mapped Kong routes, and drift report.
- `GET /api/endpoints/{endpoint_id}/testcases`: Return generated test matrix for the chosen endpoint.
- `POST /api/execute`: Execute a test case via `httpx` proxy, validate against OAS contract, and return results.