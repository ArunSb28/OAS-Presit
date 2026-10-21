"""Kong declarative (decK) parsing and OAS route correlation / drift detection."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

AUTH_PLUGINS = ("key-auth", "jwt", "basic-auth", "oauth2")
_TEMPLATE = re.compile(r"\{[^}/]+\}")


def parse_kong(directory: Path) -> Dict[str, Any]:
    services: List[Dict] = []
    routes: List[Dict] = []
    global_plugins: List[Dict] = []
    consumers: List[Dict] = []
    files: List[str] = []
    if not directory.exists():
        return {"routes": [], "global_plugins": [], "groups": [], "files": [], "consumers": []}

    for p in sorted(directory.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".yaml", ".yml"):
            continue
        try:
            doc = yaml.safe_load(p.read_text("utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict) or not any(k in doc for k in ("services", "routes", "plugins", "consumers")):
            continue
        files.append(str(p.relative_to(directory)).replace("\\", "/"))
        for svc in doc.get("services") or []:
            services.append(svc)
        for r in doc.get("routes") or []:
            r = dict(r)
            r["_service_ref"] = r.get("service") if isinstance(r.get("service"), str) else (r.get("service") or {}).get("name")
            routes.append(r)
        global_plugins += [pl for pl in doc.get("plugins") or [] if not (pl.get("route") or pl.get("service"))]
        for pl in doc.get("plugins") or []:  # top-level plugins scoped to route/service
            scope = pl.get("route") or pl.get("service")
            if scope:
                name = scope if isinstance(scope, str) else scope.get("name")
                pl = {**pl, "_scope": ("route" if pl.get("route") else "service"), "_scope_name": name}
                global_plugins.append(pl)
        consumers += doc.get("consumers") or []

    svc_by_name = {s.get("name"): s for s in services}
    flat: List[Dict] = []
    for svc in services:
        for r in svc.get("routes") or []:
            r = dict(r)
            r["_service_ref"] = svc.get("name")
            flat.append(r)
    flat += routes

    scoped = [p for p in global_plugins if p.get("_scope")]
    true_global = [p for p in global_plugins if not p.get("_scope")]
    out_routes = []
    for r in flat:
        svc = svc_by_name.get(r.get("_service_ref")) or {}
        svc_path = svc.get("path") or ""
        if not svc_path and svc.get("url"):
            m = re.match(r"^\w+://[^/]+(/.*)?$", svc["url"])
            svc_path = (m.group(1) or "") if m else ""
        plugins: Dict[str, Dict] = {}
        for pl in true_global:
            plugins[pl["name"]] = {"name": pl["name"], "config": pl.get("config") or {}, "scope": "global"}
        for pl in (svc.get("plugins") or []) + [x for x in scoped if x["_scope"] == "service" and x["_scope_name"] == svc.get("name")]:
            plugins[pl["name"]] = {"name": pl["name"], "config": pl.get("config") or {}, "scope": "service"}
        for pl in (r.get("plugins") or []) + [x for x in scoped if x["_scope"] == "route" and x["_scope_name"] == r.get("name")]:
            plugins[pl["name"]] = {"name": pl["name"], "config": pl.get("config") or {}, "scope": "route"}
        acl = plugins.get("acl", {}).get("config", {})
        out_routes.append({
            "name": r.get("name") or "(unnamed)",
            "service": svc.get("name"),
            "paths": r.get("paths") or [],
            "methods": [m.upper() for m in (r.get("methods") or [])],
            "strip_path": r.get("strip_path", True),
            "service_path": svc_path.rstrip("/"),
            "tags": r.get("tags") or [],
            "plugins": list(plugins.values()),
            "auth": [p for p in plugins if p in AUTH_PLUGINS],
            "acl_allow": acl.get("allow") or [],
            "acl_deny": acl.get("deny") or [],
        })

    groups = set()
    for r in out_routes:
        groups.update(r["acl_allow"])
        groups.update(r["acl_deny"])
    for c in consumers:
        for a in c.get("acls") or []:
            if a.get("group"):
                groups.add(a["group"])
    return {"routes": out_routes, "global_plugins": true_global, "groups": sorted(groups),
            "files": files, "consumers": [c.get("username") for c in consumers]}


def _segments(p: str) -> List[str]:
    return [s for s in p.strip("/").split("/") if s]


def _prefix_match(prefix: str, path: str) -> bool:
    a, b = _segments(prefix), _segments(path)
    return len(a) <= len(b) and all(x == y or _TEMPLATE.fullmatch(y) for x, y in zip(a, b))


def kong_regex(pattern: str) -> Optional[re.Pattern]:
    """Compile a Kong (PCRE) route regex. Kong anchors at the start of the path."""
    pattern = re.sub(r"\(\?<([A-Za-z_]\w*)>", r"(?P<\1>", pattern)  # (?<id>..) -> (?P<id>..)
    try:
        return re.compile(pattern)
    except re.error:
        return None


def path_samples(op: Dict) -> List[str]:
    """Concrete paths for an OAS operation, with path params filled from their own
    schemas (pattern/enum/format) so regex routes like ~/pay/[a-z]+ can be tested."""
    if "_samples" in op:
        return op["_samples"]
    from .generator import gen_value  # local import: avoid import cycle
    path = op["full_path"]
    schemas = {p["name"]: p.get("schema") or {} for p in op.get("parameters", []) if p.get("in") == "path"}
    names = re.findall(r"\{([^}/]+)\}", path)
    constrained = any(k in s for s in schemas.values() for k in ("pattern", "enum", "const", "format"))
    out: List[str] = []
    for fallback in ((None,) if constrained else (None, "1", "abc", "a1b2", "A1")):
        s = path
        for n in names:
            v = fallback
            if v is None:
                try:
                    v = gen_value(schemas.get(n, {}), "min")
                except Exception:
                    v = None
                v = "1" if v is None else v
            s = s.replace("{" + n + "}", str(v))
        if s not in out:
            out.append(s)
    op["_samples"] = out
    return out


def match_route(route: Dict, op: Dict) -> Optional[Tuple[str, Tuple[int, int]]]:
    """Return (public path clients call, precedence rank) or None.
    Rank follows Kong: regex routes beat prefix routes; longer prefix beats shorter."""
    method, full_path = op["method"], op["full_path"]
    if route["methods"] and method not in route["methods"]:
        return None
    svc = route["service_path"]
    best: Optional[Tuple[str, Tuple[int, int]]] = None
    for rp in route["paths"]:
        if rp.startswith("~"):
            rx = kong_regex(rp[1:])
            if rx and any(rx.match(s) for s in path_samples(op)):
                cand = (full_path, (1, len(rp)))
            else:
                cand = None
        elif _prefix_match(rp, full_path):  # OAS documents the public gateway path
            cand = (full_path, (0, len(_segments(rp))))
        elif svc and route["strip_path"] and (full_path == svc or full_path.startswith(svc + "/")):
            # OAS documents the upstream path; Kong strips the prefix and prepends the service path
            cand = (rp.rstrip("/") + full_path[len(svc):], (0, len(_segments(rp))))
        elif svc and not route["strip_path"] and full_path.startswith(svc + "/") and \
                _prefix_match(rp, full_path[len(svc):]):
            cand = (full_path[len(svc):], (0, len(_segments(rp))))
        else:
            cand = None
        if cand and (best is None or cand[1] > best[1]):
            best = cand
    return best


def correlate(ops: List[Dict], kong: Dict) -> Dict[str, Any]:
    routes = kong["routes"]
    matched_routes = set()
    for op in ops:
        hits = []
        for r in routes:
            m = match_route(r, op)
            if m is not None:
                hits.append((r, m[0], m[1]))
                matched_routes.add(r["name"])
        hits.sort(key=lambda h: h[2], reverse=True)  # Kong precedence: most specific first
        op["kong"] = None
        if hits:
            r, pub, _ = hits[0]
            plugins = {p["name"]: p for p in r["plugins"]}
            op["kong"] = {
                "routes": [h[0]["name"] for h in hits],
                "service": r["service"],
                "public_path": pub,
                "strip_path": r["strip_path"],
                "plugins": r["plugins"],
                "auth": r["auth"],
                "acl_allow": r["acl_allow"],
                "acl_deny": r["acl_deny"],
                "key_names": (plugins.get("key-auth", {}).get("config") or {}).get("key_names") or ["apikey"],
            }
        op["drift"] = "ok" if hits else "unrouted"
    orphaned = [r for r in routes if r["name"] not in matched_routes]
    return {
        "unrouted_operations": [{"id": o["id"], "method": o["method"], "path": o["full_path"]}
                                for o in ops if o["drift"] == "unrouted"],
        "orphaned_routes": [{"name": r["name"], "paths": r["paths"], "methods": r["methods"],
                             "service": r["service"]} for r in orphaned],
    }
