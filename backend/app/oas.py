"""OpenAPI multi-file ingestion: $ref dereferencing + operation extraction."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

import yaml

HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
MAX_DEPTH = 40


class Resolver:
    """Dereferences internal and cross-file $refs. Circular refs become
    ``{"x-circular": ref}`` placeholders; resolved components carry
    ``x-schema-name`` so implicit discriminator mappings can be derived."""

    def __init__(self) -> None:
        self._docs: Dict[str, Any] = {}

    def load(self, file: Path) -> Any:
        key = str(file.resolve())
        if key not in self._docs:
            self._docs[key] = yaml.safe_load(file.read_text("utf-8"))
        return self._docs[key]

    @staticmethod
    def _pointer(doc: Any, pointer: str) -> Any:
        node = doc
        if pointer in ("", "/"):
            return node
        for part in pointer.lstrip("/").split("/"):
            part = unquote(part).replace("~1", "/").replace("~0", "~")
            node = node[int(part)] if isinstance(node, list) else node[part]
        return node

    def _split(self, ref: str, file: Path) -> Tuple[Optional[Path], str]:
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", ref):
            return None, ""
        path_part, _, pointer = ref.partition("#")
        target = file if not path_part else (file.parent / unquote(path_part)).resolve()
        return target, pointer

    def deref(self, node: Any, file: Path, stack: Tuple = (), depth: int = 0) -> Any:
        if depth > MAX_DEPTH:
            return {"x-circular": "max-depth"}
        if isinstance(node, list):
            return [self.deref(x, file, stack, depth + 1) for x in node]
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if isinstance(ref, str):
            return self._resolve_ref(ref, file, stack, depth)
        out: Dict[str, Any] = {}
        for k, v in node.items():
            if k == "discriminator" and isinstance(v, dict):
                out[k] = self._deref_discriminator(v, file, stack, depth)
            else:
                out[k] = self.deref(v, file, stack, depth + 1)
        return out

    def _resolve_ref(self, ref: str, file: Path, stack: Tuple, depth: int) -> Any:
        target_file, pointer = self._split(ref, file)
        name = pointer.rstrip("/").split("/")[-1] if pointer else (target_file.stem if target_file else ref)
        if target_file is None:
            return {"x-unresolved": ref, "x-schema-name": name}
        key = (str(target_file), pointer)
        if key in stack:
            return {"x-circular": ref, "x-schema-name": name}
        try:
            target = self._pointer(self.load(target_file), pointer)
        except Exception as e:
            return {"x-unresolved": ref, "x-error": str(e), "x-schema-name": name}
        res = self.deref(target, target_file, stack + (key,), depth + 1)
        if isinstance(res, dict):
            res = {**res, "x-schema-name": name}
        return res

    def _deref_discriminator(self, disc: Dict, file: Path, stack: Tuple, depth: int) -> Dict:
        out = dict(disc)
        resolved: Dict[str, Any] = {}
        for key, ref in (disc.get("mapping") or {}).items():
            ref = str(ref)
            if "/" not in ref and "#" not in ref:
                ref = f"#/components/schemas/{ref}"
            tf, ptr = self._split(ref, file)
            if tf is None or (str(tf), ptr) in stack:
                resolved[key] = {"x-circular": ref}
                continue
            resolved[key] = self._resolve_ref(ref, file, stack, depth + 1)
        out["x-resolved"] = resolved
        return out


def find_root_specs(directory: Path) -> List[Path]:
    roots: List[Path] = []
    if not directory.exists():
        return roots
    for p in sorted(directory.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".yaml", ".yml", ".json"):
            continue
        try:
            doc = yaml.safe_load(p.read_text("utf-8"))
        except Exception:
            continue
        if isinstance(doc, dict) and str(doc.get("openapi", "")).startswith("3") and "paths" in doc:
            roots.append(p)
    return roots


def _server_base_path(spec: Dict) -> str:
    servers = spec.get("servers") or []
    if not servers:
        return ""
    url = servers[0].get("url", "")
    for name, var in (servers[0].get("variables") or {}).items():
        url = url.replace("{" + name + "}", str(var.get("default", "")))
    path = urlsplit(url).path if "://" in url else url
    return "/" + path.strip("/") if path.strip("/") else ""


def endpoint_id(spec_file: str, method: str, path: str) -> str:
    return hashlib.sha1(f"{spec_file}|{method.upper()}|{path}".encode()).hexdigest()[:10]


def load_operations(directory: Path) -> List[Dict[str, Any]]:
    """Operations with fully dereferenced parameters/body/responses."""
    resolver = Resolver()
    ops: List[Dict[str, Any]] = []
    for spec_file in find_root_specs(directory):
        raw = resolver.load(spec_file)
        base = _server_base_path(raw)
        rel = str(spec_file.relative_to(directory)).replace("\\", "/")
        for path, item in (raw.get("paths") or {}).items():
            item = resolver.deref(item, spec_file)
            if not isinstance(item, dict):
                continue
            shared = item.get("parameters") or []
            for method in HTTP_METHODS:
                op = item.get(method)
                if not isinstance(op, dict):
                    continue
                params = {(p.get("in"), p.get("name")): p for p in shared if isinstance(p, dict)}
                params.update({(p.get("in"), p.get("name")): p
                               for p in (op.get("parameters") or []) if isinstance(p, dict)})
                body = op.get("requestBody")
                ops.append({
                    "id": endpoint_id(rel, method, path),
                    "method": method.upper(),
                    "path": path,
                    "base_path": base,
                    "full_path": (base + path) or "/",
                    "spec_file": rel,
                    "operation_id": op.get("operationId"),
                    "summary": op.get("summary") or op.get("description") or "",
                    "tags": op.get("tags") or ["untagged"],
                    "deprecated": bool(op.get("deprecated")),
                    "parameters": [p for p in params.values() if p.get("in") in ("path", "query", "header")],
                    "request_body": body if isinstance(body, dict) else None,
                    "responses": op.get("responses") or {},
                })
    return ops
