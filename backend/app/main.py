"""FastAPI application: local OAS/Kong ingestion, test generation, execution."""
from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import executor, generator, kong as kong_mod, oas
from .config import DATA_DIR, Credential, get_config, update_config

app = FastAPI(title="OAS ⇄ Kong Test Workbench")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class Index:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.ops: Dict[str, Dict] = {}
        self.kong: Dict[str, Any] = {"routes": [], "groups": [], "files": []}
        self.drift: Dict[str, Any] = {"unrouted_operations": [], "orphaned_routes": []}
        self.scanned_at: Optional[float] = None
        self.errors: List[str] = []


INDEX = Index()
BASELINE_FILE = DATA_DIR / "baseline.json"
RESULTS_FILE = DATA_DIR / "test_results.json"


def _load_results() -> Dict[str, Dict[str, Any]]:
    try:
        if RESULTS_FILE.is_file():
            return json.loads(RESULTS_FILE.read_text("utf-8"))
    except Exception:
        pass
    return {}


def _save_result(endpoint_id: str, testcase_id: str, result: Dict[str, Any]) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        all_res = _load_results()
        ep_res = all_res.setdefault(endpoint_id, {})
        ep_res[testcase_id] = result
        RESULTS_FILE.write_text(json.dumps(all_res, indent=2), "utf-8")
    except Exception:
        pass


def _calc_endpoint_status(endpoint_id: str, all_results: Dict[str, Dict[str, Any]]) -> str:
    res = all_results.get(endpoint_id)
    if not res:
        return "untested"
    statuses = [v.get("passed") for v in res.values()]
    if any(s is False for s in statuses):
        return "failed"
    if any(s is True for s in statuses):
        return "passed"
    return "untested"


def _load_baseline(dirs: List[str]) -> Optional[Dict[str, Any]]:
    """Snapshot of operations/routes already seen. Reset if the source folders changed."""
    try:
        data = json.loads(BASELINE_FILE.read_text("utf-8"))
        return data if data.get("dirs") == dirs else None
    except Exception:
        return None


def _save_baseline(ops: List[Dict], routes: List[Dict], dirs: List[str]) -> Dict[str, Any]:
    now = time.time()
    base = {"dirs": dirs, "created_at": now,
            "endpoints": {o["id"]: now for o in ops}, "routes": {r["name"]: now for r in routes}}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BASELINE_FILE.write_text(json.dumps(base, indent=2), "utf-8")
    return base


def _flag_new(ops: List[Dict], kong: Dict, drift: Dict, dirs: List[str], create_ok: bool) -> None:
    base = _load_baseline(dirs)
    if base is None and create_ok:  # first scan: everything present now is the baseline
        base = _save_baseline(ops, kong["routes"], dirs)
    base = base or {"endpoints": {}, "routes": {}}
    new_routes = {r["name"] for r in kong["routes"] if r["name"] not in base["routes"]}
    for o in ops:
        o["is_new"] = create_ok and o["id"] not in base["endpoints"]
        if o["kong"]:
            o["kong"]["new_routes"] = [n for n in o["kong"]["routes"] if n in new_routes]
    for r in drift["orphaned_routes"]:
        r["is_new"] = r["name"] in new_routes
    kong["new_routes"] = sorted(new_routes)


def rescan() -> Dict[str, Any]:
    cfg = get_config()
    errors: List[str] = []
    ops: List[Dict] = []
    kong: Dict[str, Any] = {"routes": [], "groups": [], "files": [], "global_plugins": [], "consumers": []}
    oas_dir, kong_dir = Path(cfg.oas_dir), Path(cfg.kong_dir)
    if not oas_dir.is_dir():
        errors.append(f"OAS directory not found: {cfg.oas_dir}")
    else:
        try:
            ops = oas.load_operations(oas_dir)
        except Exception as e:
            errors.append(f"OAS parse error: {e}")
    if not kong_dir.is_dir():
        errors.append(f"Kong directory not found: {cfg.kong_dir}")
    else:
        try:
            kong = kong_mod.parse_kong(kong_dir)
        except Exception as e:
            errors.append(f"Kong parse error: {e}")
    drift = kong_mod.correlate(ops, kong)
    _flag_new(ops, kong, drift, [cfg.oas_dir, cfg.kong_dir], create_ok=bool(ops or kong["routes"]))
    with INDEX.lock:
        INDEX.ops = {o["id"]: o for o in ops}
        INDEX.kong, INDEX.drift = kong, drift
        INDEX.scanned_at, INDEX.errors = time.time(), errors
    return summary()


def summary() -> Dict[str, Any]:
    with INDEX.lock:
        res = _load_results()
        tested = sum(1 for oid in INDEX.ops if _calc_endpoint_status(oid, res) != "untested")
        untested = len(INDEX.ops) - tested
        return {
            "scanned_at": INDEX.scanned_at, "errors": INDEX.errors,
            "operations": len(INDEX.ops), "kong_routes": len(INDEX.kong["routes"]),
            "kong_files": INDEX.kong.get("files", []), "acl_groups": INDEX.kong.get("groups", []),
            "unrouted": len(INDEX.drift["unrouted_operations"]),
            "orphaned": len(INDEX.drift["orphaned_routes"]),
            "new_endpoints": sum(1 for o in INDEX.ops.values() if o.get("is_new")),
            "new_routes": len(INDEX.kong.get("new_routes", [])),
            "tested_endpoints": tested,
            "untested_endpoints": untested,
        }


@app.post("/api/baseline/ack")
def api_ack_baseline():
    """Mark everything currently indexed as seen (clears the NEW flags)."""
    cfg = get_config()
    with INDEX.lock:
        _save_baseline(list(INDEX.ops.values()), INDEX.kong["routes"], [cfg.oas_dir, cfg.kong_dir])
    return rescan()


async def _watch() -> None:
    """Re-index automatically when local files change."""
    from watchfiles import awatch
    while True:
        cfg = get_config()
        paths = [p for p in {cfg.oas_dir, cfg.kong_dir} if Path(p).is_dir()]
        if not paths:
            await asyncio.sleep(3)
            continue
        stop = asyncio.Event()

        async def watcher() -> None:
            async for _ in awatch(*paths, stop_event=stop, debounce=800):
                await asyncio.to_thread(rescan)

        task = asyncio.create_task(watcher())
        snapshot = (cfg.oas_dir, cfg.kong_dir)
        while (get_config().oas_dir, get_config().kong_dir) == snapshot:
            await asyncio.sleep(1)
        stop.set()
        with contextlib.suppress(Exception):
            await task


@app.on_event("startup")
async def _startup() -> None:
    await asyncio.to_thread(rescan)
    app.state.watch = asyncio.create_task(_watch())


@app.on_event("shutdown")
async def _shutdown() -> None:
    app.state.watch.cancel()


# ------------------------------------------------------------------ config
class ConfigPatch(BaseModel):
    oas_dir: Optional[str] = None
    kong_dir: Optional[str] = None
    target_url: Optional[str] = None
    verify_tls: Optional[bool] = None
    credentials: Optional[List[Credential]] = None


@app.get("/api/config")
def api_get_config():
    return {**get_config().model_dump(), "status": summary()}


@app.post("/api/config")
def api_set_config(patch: ConfigPatch):
    data = patch.model_dump(exclude_none=True)
    paths_changed = any(k in data and data[k] != getattr(get_config(), k) for k in ("oas_dir", "kong_dir"))
    update_config(data)
    status = rescan() if paths_changed else summary()
    return {**get_config().model_dump(), "status": status}


@app.post("/api/rescan")
def api_rescan():
    return rescan()


# --------------------------------------------------------------- endpoints
def _public(op: Dict, all_results: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict:
    res = all_results if all_results is not None else _load_results()
    data = {k: op[k] for k in ("id", "method", "path", "full_path", "spec_file", "operation_id", "summary",
                              "tags", "deprecated", "kong", "drift", "is_new")}
    data["test_status"] = _calc_endpoint_status(op["id"], res)
    return data


@app.get("/api/endpoints")
def api_endpoints():
    with INDEX.lock:
        res = _load_results()
        return {
            "endpoints": [_public(o, res) for o in INDEX.ops.values()],
            "drift": INDEX.drift,
            "acl_groups": INDEX.kong.get("groups", []),
            "status": summary_unlocked(res),
        }


def summary_unlocked(res: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    if res is None:
        res = _load_results()
    tested = sum(1 for oid in INDEX.ops if _calc_endpoint_status(oid, res) != "untested")
    untested = len(INDEX.ops) - tested
    return {"scanned_at": INDEX.scanned_at, "errors": INDEX.errors, "operations": len(INDEX.ops),
            "kong_routes": len(INDEX.kong["routes"]), "kong_files": INDEX.kong.get("files", []),
            "unrouted": len(INDEX.drift["unrouted_operations"]), "orphaned": len(INDEX.drift["orphaned_routes"]),
            "new_endpoints": sum(1 for o in INDEX.ops.values() if o.get("is_new")),
            "new_routes": len(INDEX.kong.get("new_routes", [])),
            "tested_endpoints": tested,
            "untested_endpoints": untested}


def _op(endpoint_id: str) -> Dict:
    with INDEX.lock:
        op = INDEX.ops.get(endpoint_id)
    if not op:
        raise HTTPException(404, "Unknown endpoint")
    return op


@app.get("/api/endpoints/{endpoint_id}/testcases")
def api_testcases(endpoint_id: str):
    op = _op(endpoint_id)
    with INDEX.lock:
        groups = list(INDEX.kong.get("groups", []))
    return {"endpoint": _public(op), "testcases": generator.generate_tests(op, groups)}


class ExecuteRequest(BaseModel):
    endpoint_id: str
    testcase: Dict[str, Any]
    base_url: Optional[str] = None


@app.post("/api/execute")
async def api_execute(req: ExecuteRequest):
    op = _op(req.endpoint_id)
    cfg = get_config()
    res = await executor.execute(
        op, req.testcase, req.base_url or cfg.target_url,
        [c.model_dump() for c in cfg.credentials], cfg.verify_tls)
    tc_id = req.testcase.get("id") or "tc"
    _save_result(req.endpoint_id, tc_id, res)
    return res


@app.get("/api/results")
def api_get_results():
    return _load_results()


@app.delete("/api/results")
def api_clear_results():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text("{}", "utf-8")
    return {"status": "cleared"}
