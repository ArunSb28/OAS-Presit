"""FastAPI application: local OAS/Kong ingestion, test generation, execution."""
from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import executor, generator, kong as kong_mod, oas
from .config import Credential, get_config, update_config

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
    with INDEX.lock:
        INDEX.ops = {o["id"]: o for o in ops}
        INDEX.kong, INDEX.drift = kong, drift
        INDEX.scanned_at, INDEX.errors = time.time(), errors
    return summary()


def summary() -> Dict[str, Any]:
    with INDEX.lock:
        return {
            "scanned_at": INDEX.scanned_at, "errors": INDEX.errors,
            "operations": len(INDEX.ops), "kong_routes": len(INDEX.kong["routes"]),
            "kong_files": INDEX.kong.get("files", []), "acl_groups": INDEX.kong.get("groups", []),
            "unrouted": len(INDEX.drift["unrouted_operations"]),
            "orphaned": len(INDEX.drift["orphaned_routes"]),
        }


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
def _public(op: Dict) -> Dict:
    return {k: op[k] for k in ("id", "method", "path", "full_path", "spec_file", "operation_id", "summary",
                              "tags", "deprecated", "kong", "drift")}


@app.get("/api/endpoints")
def api_endpoints():
    with INDEX.lock:
        return {
            "endpoints": [_public(o) for o in INDEX.ops.values()],
            "drift": INDEX.drift,
            "acl_groups": INDEX.kong.get("groups", []),
            "status": summary_unlocked(),
        }


def summary_unlocked() -> Dict[str, Any]:
    return {"scanned_at": INDEX.scanned_at, "errors": INDEX.errors, "operations": len(INDEX.ops),
            "kong_routes": len(INDEX.kong["routes"]), "kong_files": INDEX.kong.get("files", []),
            "unrouted": len(INDEX.drift["unrouted_operations"]), "orphaned": len(INDEX.drift["orphaned_routes"])}


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
    return await executor.execute(
        op, req.testcase, req.base_url or cfg.target_url,
        [c.model_dump() for c in cfg.credentials], cfg.verify_tls)
