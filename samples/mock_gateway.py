"""Tiny mock Kong-style gateway for demoing the workbench against samples/.

    cd backend && .venv\\Scripts\\python ..\\samples\\mock_gateway.py     (listens on :9000)

It enforces key-auth + ACL from the Kong config, validates params/body against
the OAS, and replies with a schema-conformant example.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import uvicorn  # noqa: E402
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse, Response  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from app import generator, kong as kong_mod, oas  # noqa: E402
from app.config import get_config  # noqa: E402
from app.executor import to_jsonschema  # noqa: E402

app = FastAPI()
cfg = get_config()
OPS = oas.load_operations(Path(cfg.oas_dir))
KONG = kong_mod.parse_kong(Path(cfg.kong_dir))
kong_mod.correlate(OPS, KONG)
KEYS = {c.token: c.group for c in cfg.credentials}


def _regex(template: str) -> re.Pattern:
    return re.compile("^" + re.sub(r"\{[^}/]+\}", r"[^/]+", re.escape(template).replace("\\{", "{").replace("\\}", "}")) + "$")


ROUTES = [(o, _regex(o["kong"]["public_path"])) for o in OPS if o["kong"]]


def _coerce(v: str, schema: dict):
    t = (schema or {}).get("type")
    try:
        if t == "integer":
            return int(v)
        if t == "number":
            return float(v)
        if t == "boolean":
            return {"true": True, "false": False}[v.lower()]
    except (ValueError, KeyError):
        return v
    return v


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def gateway(path: str, request: Request):
    full = "/" + path
    op = next((o for o, rx in ROUTES if o["method"] == request.method and rx.match(full)), None)
    if not op:
        return JSONResponse({"message": "no Route matched with those values"}, 404)
    k = op["kong"]
    if k["auth"]:
        key = request.headers.get("apikey") or request.query_params.get("apikey") or \
            request.headers.get("authorization", "").removeprefix("Bearer ")
        if not key:
            return JSONResponse({"message": "No API key found in request"}, 401)
        if key not in KEYS:
            return JSONResponse({"message": "Invalid authentication credentials"}, 401)
        grp = KEYS[key]
        if (k["acl_allow"] and grp not in k["acl_allow"]) or grp in k["acl_deny"]:
            return JSONResponse({"message": "You cannot consume this service"}, 403)

    # params
    values = {"path": {}, "query": dict(request.query_params), "header": dict(request.headers)}
    tmpl = re.sub(r"\{[^}/]+\}", "([^/]+)", k["public_path"])
    m = re.match("^" + tmpl + "$", full)
    if m:
        values["path"] = dict(zip(re.findall(r"\{([^}/]+)\}", k["public_path"]), m.groups()))
    errors = []
    for p in op["parameters"]:
        src = values[p["in"]]
        key = p["name"].lower() if p["in"] == "header" else p["name"]
        if key not in {x.lower() if p["in"] == "header" else x for x in src}:
            if p.get("required"):
                errors.append(f"missing {p['in']} {p['name']}")
            continue
        raw = next(v for kk, v in src.items() if (kk.lower() if p["in"] == "header" else kk) == key)
        errs = list(Draft202012Validator(to_jsonschema(p.get("schema") or {}), format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(_coerce(raw, p.get("schema"))))
        errors += [f"{p['name']}: {e.message}" for e in errs]

    ct, schema = generator.body_schema(op.get("request_body"))
    if schema is not None:
        raw = await request.body()
        if not raw:
            if op["request_body"].get("required"):
                errors.append("body required")
        else:
            try:
                errors += [e.message for e in Draft202012Validator(to_jsonschema(schema), format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(json.loads(raw))]
            except json.JSONDecodeError:
                errors.append("invalid JSON body")
    if errors:
        return JSONResponse({"message": "validation failed", "errors": errors[:10]}, 400)

    code = next((c for c in op["responses"] if str(c).startswith("2")), "200")
    if str(code) == "204":
        return Response(status_code=204)
    content = (op["responses"].get(code) or {}).get("content") or {}
    rschema = next(iter(content.values()), {}).get("schema") if content else None
    body = generator.gen_value(rschema, "max") if rschema else {"ok": True}
    return JSONResponse(body, int(code))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000)
