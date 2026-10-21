"""Test execution through an async httpx proxy + OAS response-contract validation."""
from __future__ import annotations

import base64
import json
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
from jsonschema import Draft202012Validator

_STRIP = {"discriminator", "xml", "externalDocs", "example", "x-circular", "x-unresolved",
          "x-schema-name", "x-error", "readOnly", "writeOnly"}


def to_jsonschema(node: Any) -> Any:
    """Normalise OAS 3.0 schema dialect to JSON Schema 2020-12."""
    if isinstance(node, list):
        return [to_jsonschema(x) for x in node]
    if not isinstance(node, dict):
        return node
    out: Dict[str, Any] = {}
    for k, v in node.items():
        if k in _STRIP and not isinstance(v, dict) or k in ("discriminator", "x-circular", "x-unresolved"):
            continue
        if k in ("exclusiveMinimum", "exclusiveMaximum") and isinstance(v, bool):
            continue
        if k in ("properties",) and isinstance(v, dict):
            out[k] = {pk: to_jsonschema(pv) for pk, pv in v.items()}
        elif k in ("example", "default", "enum", "const", "examples"):
            out[k] = v
        else:
            out[k] = to_jsonschema(v)
    if node.get("nullable") is True and "type" in out and isinstance(out["type"], str):
        out["type"] = [out["type"], "null"]
    for k, b in (("minimum", "exclusiveMinimum"), ("maximum", "exclusiveMaximum")):
        if node.get(b) is True and k in node:
            out[b] = node[k]
            out.pop(k, None)
    return out


def _status_ok(status: int, expected: List[str]) -> bool:
    for e in expected:
        e = str(e).lower()
        if e.endswith("xx") and status // 100 == int(e[0]):
            return True
        if e.isdigit() and status == int(e):
            return True
    return False


def _response_schema(op: Dict, status: int) -> Optional[Dict]:
    responses = op.get("responses") or {}
    resp = responses.get(str(status)) or responses.get(f"{status // 100}XX") or \
        responses.get(f"{status // 100}xx") or responses.get("default")
    if not isinstance(resp, dict):
        return None
    content = resp.get("content") or {}
    ct = next((c for c in content if c == "application/json" or c.endswith("+json")), None)
    return (content.get(ct) or {}).get("schema") if ct else None


def contract_check(op: Dict, status: int, body: Any, is_json: bool) -> Dict[str, Any]:
    schema = _response_schema(op, status)
    if schema is None:
        return {"validated": False, "valid": None, "errors": [], "note": f"No JSON response schema declared for {status}"}
    if not is_json:
        return {"validated": True, "valid": False, "errors": [{"path": "$", "message": "Response body is not JSON"}]}
    validator = Draft202012Validator(to_jsonschema(schema))
    errors = [{"path": "$" + "".join(f"[{p!r}]" if isinstance(p, str) else f"[{p}]" for p in e.absolute_path),
               "message": e.message[:300]} for e in sorted(validator.iter_errors(body), key=lambda e: list(map(str, e.absolute_path)))]
    return {"validated": True, "valid": not errors, "errors": errors[:25]}


def _credential(auth: Dict, creds: List[Dict]) -> Optional[Dict]:
    group = auth.get("group")
    if group in (None, "", "*"):
        return creds[0] if creds else None
    return next((c for c in creds if c["group"] == group), None)


async def execute(op: Dict, tc: Dict, base_url: str, creds: List[Dict], verify: bool = True) -> Dict[str, Any]:
    req = tc["request"]
    path = tc.get("public_path") or op["full_path"]
    for k, v in (req.get("path_params") or {}).items():
        path = path.replace("{" + k + "}", quote(str(v), safe=""))
    url = base_url.rstrip("/") + path
    headers = {k: str(v) for k, v in (req.get("headers") or {}).items()}
    query = dict(req.get("query") or {})

    auth = tc.get("auth") or {"mode": "none"}
    if auth.get("mode") == "group" and auth.get("scheme"):
        cred = _credential(auth, creds)
        sc = auth["scheme"]
        secret = None if cred is None else (
            f"{cred.get('username', '')}:{cred.get('password', '')}" if sc["type"] == "basic"
            else cred.get("token") or None)
        if secret is None or (sc["type"] == "basic" and not cred.get("username")):
            return {"skipped": True, "passed": None,
                    "error": f"No usable credential configured for ACL group '{auth.get('group')}' – add one in the Credential Manager."}
        token = secret
        if sc["type"] == "header":
            headers[sc["name"]] = token
        elif sc["type"] == "query":
            query[sc["name"]] = token
        elif sc["type"] == "bearer":
            headers["Authorization"] = f"Bearer {token}"
        elif sc["type"] == "basic":
            headers["Authorization"] = "Basic " + base64.b64encode(token.encode()).decode()

    kwargs: Dict[str, Any] = {}
    body, ct = req.get("body"), req.get("content_type")
    if body is not None:
        if ct and "json" in ct:
            kwargs["content"] = json.dumps(body)
            headers.setdefault("Content-Type", ct)
        elif ct and "x-www-form-urlencoded" in ct and isinstance(body, dict):
            kwargs["data"] = body
        elif ct and "multipart" in ct and isinstance(body, dict):
            kwargs["files"] = {k: (None, str(v)) for k, v in body.items()}
        else:
            kwargs["content"] = body if isinstance(body, (str, bytes)) else json.dumps(body)
            if ct:
                headers.setdefault("Content-Type", ct)

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(verify=verify, timeout=30.0, follow_redirects=False) as client:
            r = await client.request(tc["method"], url, params=query, headers=headers, **kwargs)
    except httpx.HTTPError as e:
        return {"passed": False, "error": f"{type(e).__name__}: {e}", "url": url, "time_ms": None}
    elapsed = round((time.perf_counter() - start) * 1000, 1)

    try:
        parsed: Any = r.json()
        is_json = True
    except Exception:
        parsed, is_json = r.text, False

    status_ok = _status_ok(r.status_code, tc.get("expected") or ["2xx"])
    contract = None
    if tc.get("validate_contract") and 200 <= r.status_code < 300 or (is_json and 400 <= r.status_code < 600 and _response_schema(op, r.status_code)):
        contract = contract_check(op, r.status_code, parsed, is_json)
    contract_ok = contract is None or contract.get("valid") in (True, None)
    return {
        "passed": status_ok and contract_ok,
        "status": r.status_code,
        "status_ok": status_ok,
        "expected": tc.get("expected"),
        "time_ms": elapsed,
        "url": str(r.request.url),
        "request_headers": {k: ("***" if k.lower() in ("authorization", "apikey", "x-api-key") else v)
                            for k, v in r.request.headers.items()},
        "headers": dict(r.headers),
        "body": parsed,
        "is_json": is_json,
        "contract": contract,
    }
