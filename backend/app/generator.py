"""Synthetic payload generation + positive/negative test-matrix builder."""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

try:  # Python 3.11+
    import re._parser as sre_parse  # type: ignore
except Exception:  # pragma: no cover
    import sre_parse  # type: ignore

G_POS = "Positive"
G_DISC = "Discriminator Variants"
G_MISSING = "Missing Required"
G_BOUND = "Boundary & Mutation"
G_SEC = "Kong Security & ACL"

POLY = ("oneOf", "anyOf", "discriminator")
MAX_DEPTH = 6

# --------------------------------------------------------------------------- #
# schema utilities
# --------------------------------------------------------------------------- #


def _merge(dst: Dict, src: Dict) -> None:
    for k, v in src.items():
        if k == "properties" and isinstance(v, dict):
            dst.setdefault("properties", {}).update(v)
        elif k == "required" and isinstance(v, list):
            dst["required"] = list(dict.fromkeys([*dst.get("required", []), *v]))
        elif k == "x-schema-name" and k in dst:
            continue
        else:
            dst[k] = v


def flatten(schema: Any, strip_poly: bool = False) -> Dict:
    """Merge allOf into a single schema. ``strip_poly`` drops oneOf/anyOf/discriminator."""
    if not isinstance(schema, dict):
        return {}
    s = dict(schema)
    parts = s.pop("allOf", None) or []
    merged: Dict = {}
    for part in parts:
        _merge(merged, flatten(part, strip_poly=True))
    _merge(merged, s)
    if strip_poly:
        for k in POLY:
            merged.pop(k, None)
    return merged


def find_disc(schema: Any) -> Optional[Tuple[Dict, Dict]]:
    if not isinstance(schema, dict):
        return None
    for c in [schema, *(schema.get("allOf") or [])]:
        if isinstance(c, dict) and isinstance(c.get("discriminator"), dict) \
                and c["discriminator"].get("propertyName"):
            return c, c["discriminator"]
    return None


def variants(schema: Any) -> Optional[Tuple[str, Dict[str, Dict]]]:
    """(propertyName, {key: flattened variant schema incl. shared parent props})."""
    found = find_disc(schema)
    if not found:
        return None
    holder, disc = found
    prop = disc["propertyName"]
    raw: Dict[str, Any] = {}
    mapping = disc.get("x-resolved") or {}
    options = holder.get("oneOf") or holder.get("anyOf") or []
    if mapping:
        raw = {k: v for k, v in mapping.items() if isinstance(v, dict) and "x-circular" not in v}
    else:
        for opt in options:
            if not isinstance(opt, dict) or "x-circular" in opt:
                continue
            fo = flatten(opt, strip_poly=True)
            pschema = (fo.get("properties") or {}).get(prop) or {}
            key = pschema.get("const") or (pschema.get("enum") or [None])[0] or opt.get("x-schema-name")
            if key:
                raw[str(key)] = opt
    if not raw:
        return None
    base_src = {k: v for k, v in flatten(schema).items() if k not in POLY}
    base = flatten(base_src, strip_poly=True)
    base.pop("type", None)
    out: Dict[str, Dict] = {}
    for key, vs in raw.items():
        merged: Dict = {}
        _merge(merged, base)
        _merge(merged, flatten(vs, strip_poly=True))
        merged.setdefault("type", "object")
        out[key] = merged
    return prop, out


def concretize(schema: Any, lock: Optional[str] = None) -> Tuple[Dict, Optional[Tuple[str, str]]]:
    """Resolve allOf / oneOf / discriminator to one concrete schema (+ lock info)."""
    if not isinstance(schema, dict):
        return {}, None
    v = variants(schema)
    if v:
        prop, vs = v
        key = lock if lock in vs else next(iter(vs))
        return vs[key], (prop, key)
    s = flatten(schema)
    opts = s.get("oneOf") or s.get("anyOf")
    if opts:
        pick = next((o for o in opts if isinstance(o, dict) and o.get("type") != "null" and "x-circular" not in o), None)
        s.pop("oneOf", None)
        s.pop("anyOf", None)
        if pick:
            merged: Dict = {}
            _merge(merged, s)
            _merge(merged, flatten(pick))
            return merged, None
    return s, None


def _type(s: Dict) -> str:
    t = s.get("type")
    if isinstance(t, list):
        t = next((x for x in t if x != "null"), "string")
    if t:
        return t
    if "properties" in s:
        return "object"
    if "items" in s:
        return "array"
    return "string"


# --------------------------------------------------------------------------- #
# value generation
# --------------------------------------------------------------------------- #

_FORMATS = {
    "date-time": "2024-01-15T10:30:00Z", "date": "2024-01-15", "time": "10:30:00Z",
    "email": "user@example.com", "uuid": "123e4567-e89b-12d3-a456-426614174000",
    "uri": "https://example.com/resource", "url": "https://example.com/resource",
    "hostname": "example.com", "ipv4": "192.168.1.10", "ipv6": "2001:db8::1",
    "byte": "aGVsbG8=", "password": "P@ssw0rd!", "binary": "binary-data",
}
_CATS = {"CATEGORY_DIGIT": "1", "CATEGORY_WORD": "a", "CATEGORY_SPACE": " ",
         "CATEGORY_NOT_DIGIT": "a", "CATEGORY_NOT_WORD": "-", "CATEGORY_NOT_SPACE": "a"}


def regex_sample(pattern: str) -> Optional[str]:
    """Produce one string matching ``pattern`` (best effort)."""
    def seq(items) -> str:
        return "".join(one(i) for i in items)

    def one(item) -> str:
        op, av = item
        n = str(op)
        if n == "LITERAL":
            return chr(av)
        if n == "NOT_LITERAL":
            return "a" if chr(av) != "a" else "b"
        if n == "ANY":
            return "a"
        if n == "IN":
            neg = any(str(o) == "NEGATE" for o, _ in av)
            chars = []
            for o, a in av:
                on = str(o)
                if on == "LITERAL":
                    chars.append(chr(a))
                elif on == "RANGE":
                    chars.append(chr(a[0]))
                elif on == "CATEGORY":
                    chars.append(_CATS.get(str(a), "a"))
            if neg:
                return next(c for c in "aZ0_-" if c not in chars)
            return chars[0] if chars else "a"
        if n in ("MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"):
            lo, hi, sub = av
            cnt = max(lo, 1)
            cnt = min(cnt, hi) if hi < 1000 else cnt
            return seq(sub) * cnt
        if n == "SUBPATTERN":
            return seq(av[-1])
        if n == "BRANCH":
            return seq(av[1][0])
        if n == "CATEGORY":
            return _CATS.get(str(av), "a")
        return ""

    try:
        out = seq(sre_parse.parse(pattern))
        return out if re.search(pattern, out) else None
    except Exception:
        return None


def _gen_string(s: Dict) -> str:
    lo, hi = s.get("minLength", 0) or 0, s.get("maxLength")
    pat = s.get("pattern")
    if pat:
        v = regex_sample(pat)
        if v is not None:
            return v
    fmt = s.get("format")
    v = _FORMATS.get(fmt, "string")
    if fmt not in _FORMATS and hi is not None and hi < len(v):
        v = v[:hi]
    if len(v) < lo:
        v = v + "a" * (lo - len(v))
    if hi is not None and len(v) > hi and fmt not in _FORMATS:
        v = v[:hi]
    return v


def _gen_number(s: Dict, integer: bool) -> Any:
    lo, hi = s.get("minimum"), s.get("maximum")
    xlo, xhi = s.get("exclusiveMinimum"), s.get("exclusiveMaximum")
    step = 1 if integer else 0.5
    if xlo is True:
        xlo, lo = lo, None
    if xhi is True:
        xhi, hi = hi, None
    if isinstance(xlo, (int, float)) and not isinstance(xlo, bool):
        lo = xlo + step
    if isinstance(xhi, (int, float)) and not isinstance(xhi, bool):
        hi = xhi - step
    v: Any = 1
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    mo = s.get("multipleOf")
    if mo and v % mo:
        v = (int(v // mo) + 1) * mo
        if hi is not None and v > hi:
            v = int(hi // mo) * mo
    return int(v) if integer else float(v)


def extract_schema_example(s: Any) -> Tuple[bool, Any]:
    if not isinstance(s, dict):
        return False, None
    if "example" in s and s["example"] is not None:
        return True, copy.deepcopy(s["example"])
    exs = s.get("examples")
    if isinstance(exs, list) and len(exs) > 0 and exs[0] is not None:
        return True, copy.deepcopy(exs[0])
    if isinstance(exs, dict) and exs:
        first = next(iter(exs.values()))
        if isinstance(first, dict) and "value" in first:
            return True, copy.deepcopy(first["value"])
        if first is not None:
            return True, copy.deepcopy(first)
    return False, None


def extract_param_example(p: Dict) -> Tuple[bool, Any]:
    if not isinstance(p, dict):
        return False, None
    if "example" in p and p["example"] is not None:
        return True, copy.deepcopy(p["example"])
    exs = p.get("examples")
    if isinstance(exs, dict) and exs:
        first = next(iter(exs.values()))
        if isinstance(first, dict) and "value" in first:
            return True, copy.deepcopy(first["value"])
        if first is not None:
            return True, copy.deepcopy(first)
    if isinstance(exs, list) and len(exs) > 0 and exs[0] is not None:
        return True, copy.deepcopy(exs[0])
    schema = p.get("schema")
    if isinstance(schema, dict):
        return extract_schema_example(schema)
    return False, None


def gen_value(schema: Any, mode: str, lock: Optional[str] = None, depth: int = 0, _top: bool = True) -> Any:
    """mode: 'min' (required only) | 'max' (everything). Returns None for unresolvable."""
    if not isinstance(schema, dict) or "x-circular" in schema or "x-unresolved" in schema or depth > MAX_DEPTH:
        return None
    s, lockinfo = concretize(schema, lock if depth == 0 else None)
    if "const" in s:
        return s["const"]
    if s.get("enum"):
        return s["enum"][0]

    has_ex, ex_val = extract_schema_example(s)
    t = _type(s)

    if t == "object":
        props = s.get("properties") or {}
        req = set(s.get("required") or [])
        if has_ex and isinstance(ex_val, dict):
            obj = dict(ex_val)
            if mode == "max":
                for name, ps in props.items():
                    if name not in obj and isinstance(ps, dict) and not ps.get("readOnly"):
                        v = gen_value(ps, mode, depth=depth + 1)
                        if v is not None or ps.get("nullable"):
                            obj[name] = v
            for name in req:
                if name not in obj:
                    ps = props.get(name) or {}
                    v = gen_value(ps, mode, depth=depth + 1)
                    if v is not None:
                        obj[name] = v
            if lockinfo:
                obj[lockinfo[0]] = lockinfo[1]
            return obj

        obj: Dict[str, Any] = {}
        for name, ps in props.items():
            if isinstance(ps, dict) and ps.get("readOnly"):
                continue
            if name in req or mode == "max":
                v = gen_value(ps, mode, depth=depth + 1)
                if v is not None or (isinstance(ps, dict) and ps.get("nullable")):
                    obj[name] = v
        if lockinfo:
            obj[lockinfo[0]] = lockinfo[1]
        return obj

    if t == "array":
        if has_ex and isinstance(ex_val, list):
            return ex_val
        item = gen_value(s.get("items") or {}, mode, depth=depth + 1)
        n = s.get("minItems", 0) or 0
        if mode == "max":
            n = max(n, 1)
        if s.get("maxItems") is not None:
            n = min(n, s["maxItems"])
        return [item] * n if item is not None else []

    if has_ex and ex_val is not None:
        return ex_val

    if "default" in s and s["default"] is not None:
        return s["default"]

    # Fallback: auto-generate data according to schema rules
    if t == "integer":
        return _gen_number(s, True)
    if t == "number":
        return _gen_number(s, False)
    if t == "boolean":
        return True
    return _gen_string(s)


# --------------------------------------------------------------------------- #
# mutation helpers
# --------------------------------------------------------------------------- #


def bad_values(schema: Dict, allow_type_swap: bool = True) -> List[Tuple[str, Any]]:
    s, _ = concretize(schema)
    out: List[Tuple[str, Any]] = []
    t = _type(s)
    if allow_type_swap:
        swap = {"integer": ("string", "not-a-number"), "number": ("string", "not-a-number"),
                "boolean": ("string", "not-a-boolean"), "array": ("string", "not-an-array"),
                "object": ("string", "not-an-object"), "string": ("integer", 12345)}
        lbl, val = swap.get(t, ("string", "x"))
        out.append((f"type: {lbl} instead of {t}", val))
    if t in ("integer", "number"):
        if s.get("minimum") is not None:
            xm = s.get("exclusiveMinimum") is True
            out.append(("minimum violated", s["minimum"] if xm else s["minimum"] - 1))
        if isinstance(s.get("exclusiveMinimum"), (int, float)) and not isinstance(s.get("exclusiveMinimum"), bool):
            out.append(("exclusiveMinimum violated", s["exclusiveMinimum"]))
        if s.get("maximum") is not None:
            xm = s.get("exclusiveMaximum") is True
            out.append(("maximum violated", s["maximum"] if xm else s["maximum"] + 1))
        if isinstance(s.get("exclusiveMaximum"), (int, float)) and not isinstance(s.get("exclusiveMaximum"), bool):
            out.append(("exclusiveMaximum violated", s["exclusiveMaximum"]))
    if t == "string":
        if (s.get("minLength") or 0) > 0:
            out.append(("minLength - 1", "a" * (s["minLength"] - 1)))
        if s.get("maxLength") is not None:
            out.append(("maxLength + 1", "a" * min(s["maxLength"] + 1, 5000)))
        if s.get("pattern") and not re.search(s["pattern"], "!!!invalid!!!"):
            out.append(("pattern violated", "!!!invalid!!!"))
        bad_fmt = {"email": "not-an-email", "uuid": "not-a-uuid", "date": "31-12-2024",
                   "date-time": "yesterday", "uri": "not a uri", "ipv4": "999.1.1.1"}
        if s.get("format") in bad_fmt:
            out.append((f"format {s['format']} violated", bad_fmt[s["format"]]))
    if t == "array":
        if (s.get("minItems") or 0) > 0:
            out.append(("minItems - 1", [gen_value(s.get("items") or {}, "min")] * (s["minItems"] - 1)))
        if s.get("maxItems") is not None:
            out.append(("maxItems + 1", [gen_value(s.get("items") or {}, "min")] * min(s["maxItems"] + 1, 500)))
    if s.get("enum"):
        out.append(("unmapped enum value", "__invalid_enum_value__"))
    return out


def _iter_props(schema: Dict, path: Tuple[str, ...] = (), depth: int = 0) -> Iterator[Tuple[Tuple[str, ...], Dict]]:
    s, _ = concretize(schema)
    if depth > 3:
        return
    for name, ps in (s.get("properties") or {}).items():
        if not isinstance(ps, dict) or ps.get("readOnly") or "x-circular" in ps:
            continue
        yield path + (name,), ps
        c, _ = concretize(ps)
        if _type(c) == "object" and c.get("properties"):
            yield from _iter_props(ps, path + (name,), depth + 1)


def _required_paths(schema: Dict, path: Tuple[str, ...] = (), depth: int = 0) -> Iterator[Tuple[str, ...]]:
    s, _ = concretize(schema)
    if depth > 3:
        return
    props = s.get("properties") or {}
    for name in s.get("required") or []:
        yield path + (name,)
        ps = props.get(name)
        if isinstance(ps, dict):
            c, _ = concretize(ps)
            if _type(c) == "object":
                yield from _required_paths(ps, path + (name,), depth + 1)


def _get(obj: Any, path: Tuple[str, ...]) -> Tuple[bool, Any]:
    for p in path:
        if not isinstance(obj, dict) or p not in obj:
            return False, None
        obj = obj[p]
    return True, obj


def _set(obj: Dict, path: Tuple[str, ...], value: Any) -> bool:
    ok, parent = _get(obj, path[:-1])
    if ok and isinstance(parent, dict):
        parent[path[-1]] = value
        return True
    return False


def _del(obj: Dict, path: Tuple[str, ...]) -> bool:
    ok, parent = _get(obj, path[:-1])
    if ok and isinstance(parent, dict) and path[-1] in parent:
        del parent[path[-1]]
        return True
    return False


# --------------------------------------------------------------------------- #
# request / test-case construction
# --------------------------------------------------------------------------- #

_BUCKET = {"path": "path_params", "query": "query", "header": "headers"}
_SKIP_HEADERS = {"content-type", "accept", "authorization"}


def extract_body_examples(rb: Optional[Dict]) -> List[Dict[str, Any]]:
    """Return list of {"name": str, "description": str, "value": Any, "content_type": str}."""
    if not rb or not isinstance(rb, dict):
        return []
    content = rb.get("content") or {}
    if not isinstance(content, dict):
        return []
    out: List[Dict[str, Any]] = []
    for ct, media in content.items():
        if not isinstance(media, dict):
            continue
        # 1. media-level named examples
        exs = media.get("examples")
        if isinstance(exs, dict):
            for k, ex_obj in exs.items():
                if isinstance(ex_obj, dict):
                    val = ex_obj.get("value") if "value" in ex_obj else ex_obj
                    desc = ex_obj.get("description") or ex_obj.get("summary") or f"OpenAPI example '{k}'"
                    name = ex_obj.get("summary") or k
                else:
                    val = ex_obj
                    desc = f"OpenAPI example '{k}'"
                    name = k
                out.append({"name": str(name), "description": str(desc), "value": copy.deepcopy(val), "content_type": ct})
        # 2. media-level single example
        if "example" in media and media["example"] is not None:
            if not any(o["value"] == media["example"] for o in out):
                out.append({
                    "name": "Specified Example",
                    "description": "Defined in requestBody example.",
                    "value": copy.deepcopy(media["example"]),
                    "content_type": ct,
                })
        # 3. schema-level examples
        schema = media.get("schema")
        if isinstance(schema, dict):
            if "example" in schema and schema["example"] is not None:
                if not any(o["value"] == schema["example"] for o in out):
                    out.append({
                        "name": "Schema Example",
                        "description": "Defined in requestBody schema example.",
                        "value": copy.deepcopy(schema["example"]),
                        "content_type": ct,
                    })
            schema_exs = schema.get("examples")
            if isinstance(schema_exs, list):
                for i, ex_val in enumerate(schema_exs):
                    if not any(o["value"] == ex_val for o in out):
                        out.append({
                            "name": f"Schema Example {i + 1}",
                            "description": f"Defined in requestBody schema examples [{i}].",
                            "value": copy.deepcopy(ex_val),
                            "content_type": ct,
                        })
            elif isinstance(schema_exs, dict):
                for k, ex_obj in schema_exs.items():
                    val = ex_obj.get("value") if isinstance(ex_obj, dict) and "value" in ex_obj else ex_obj
                    if not any(o["value"] == val for o in out):
                        desc = (ex_obj.get("description") or ex_obj.get("summary")) if isinstance(ex_obj, dict) else f"Schema example '{k}'"
                        name = (ex_obj.get("summary") or k) if isinstance(ex_obj, dict) else k
                        out.append({"name": str(name), "description": str(desc), "value": copy.deepcopy(val), "content_type": ct})
    return out


def body_schema(rb: Optional[Dict]) -> Tuple[Optional[str], Optional[Dict]]:
    if not rb:
        return None, None
    content = rb.get("content") or {}
    if not content:
        return None, None
    ct = "application/json" if "application/json" in content else next(
        (c for c in content if c.endswith("+json")), next(iter(content)))
    return ct, (content[ct] or {}).get("schema") or {}


def build_request(op: Dict, mode: str, lock: Optional[str] = None) -> Dict[str, Any]:
    req: Dict[str, Any] = {"path_params": {}, "query": {}, "headers": {}, "body": None, "content_type": None}
    for p in op["parameters"]:
        if p["in"] == "header" and p["name"].lower() in _SKIP_HEADERS:
            continue
        if p["in"] == "path" or p.get("required") or mode == "max":
            has_ex, ex_val = extract_param_example(p)
            v = ex_val if (has_ex and ex_val is not None) else gen_value(p.get("schema") or {}, mode)
            if v is not None:
                req[_BUCKET[p["in"]]][p["name"]] = str(v) if p["in"] != "query" else v
    ct, schema = body_schema(op.get("request_body"))
    if ct and schema is not None:
        req["content_type"] = ct
        flat, _ = concretize(schema, lock)
        needs = op["request_body"].get("required") or bool(flat.get("required")) or bool(find_disc(schema))
        if mode == "max" or needs:
            rb = op.get("request_body") or {}
            media = (rb.get("content") or {}).get(ct) or {}
            has_media_ex, media_ex = extract_schema_example(media)
            if has_media_ex and media_ex is not None and not lock:
                req["body"] = copy.deepcopy(media_ex)
            else:
                req["body"] = gen_value(schema, mode, lock=lock)
    return req


def auth_scheme(kong: Optional[Dict]) -> Optional[Dict]:
    if not kong or not (kong["auth"] or kong["acl_allow"] or kong["acl_deny"]):
        return None
    plugins = {p["name"]: p for p in kong["plugins"]}
    if "key-auth" in plugins:
        cfg = plugins["key-auth"].get("config") or {}
        where = "query" if cfg.get("key_in") == ["query"] else "header"
        return {"plugin": "key-auth", "type": where, "name": (cfg.get("key_names") or ["apikey"])[0]}
    if "basic-auth" in plugins:
        return {"plugin": "basic-auth", "type": "basic", "name": "Authorization"}
    plugin = "jwt" if "jwt" in plugins else "oauth2" if "oauth2" in plugins else "acl"
    return {"plugin": plugin, "type": "bearer", "name": "Authorization"}


def generate_tests(op: Dict, known_groups: List[str]) -> List[Dict[str, Any]]:
    tests: List[Dict[str, Any]] = []
    kong = op.get("kong")
    scheme = auth_scheme(kong)
    allow = (kong or {}).get("acl_allow") or []
    deny = (kong or {}).get("acl_deny") or []
    default_group = (allow[0] if allow else next((g for g in known_groups if g not in deny), "*")) if scheme else None

    def auth(mode: str = "group", group: Optional[str] = None) -> Dict:
        if not scheme:
            return {"mode": "none", "scheme": None, "group": None}
        return {"mode": mode, "scheme": scheme, "group": group if mode == "group" else None}

    def add(group: str, name: str, desc: str, req: Dict, expected: List[str], *, subgroup: Optional[str] = None,
            auth_cfg: Optional[Dict] = None, contract: bool = False) -> None:
        tests.append({
            "id": f"{op['id']}-{len(tests) + 1}", "group": group, "subgroup": subgroup, "name": name,
            "description": desc, "method": op["method"], "path": op["path"],
            "public_path": (kong or {}).get("public_path") or op["full_path"],
            "request": copy.deepcopy(req), "expected": expected,
            "auth": auth_cfg or auth("group", default_group), "validate_contract": contract,
        })

    ok, bad = ["2xx"], ["400", "422"]
    ct, bschema = body_schema(op.get("request_body"))
    disc = variants(bschema) if bschema else None

    # ---- Examples (from OpenAPI requestBody & parameter examples) ----
    body_examples = extract_body_examples(op.get("request_body"))
    for ex in body_examples:
        r_ex = build_request(op, "max")
        r_ex["body"] = copy.deepcopy(ex["value"])
        r_ex["content_type"] = ex["content_type"]
        add(G_POS, f"Example: {ex['name']}", f"Generated from OpenAPI example payload ({ex['description']}).", r_ex, ok, contract=True)

    param_examples_added = 0
    for p in op.get("parameters", []):
        if p.get("in") == "header" and p["name"].lower() in _SKIP_HEADERS:
            continue
        exs = p.get("examples")
        if isinstance(exs, dict) and len(exs) > 1 and param_examples_added < 4:
            for ex_k, ex_v in exs.items():
                val = ex_v.get("value") if isinstance(ex_v, dict) and "value" in ex_v else ex_v
                if val is not None:
                    r_pex = build_request(op, "min")
                    r_pex[_BUCKET[p["in"]]][p["name"]] = str(val) if p["in"] != "query" else val
                    ex_label = (ex_v.get("summary") or ex_k) if isinstance(ex_v, dict) else ex_k
                    add(G_POS, f"Example ({p['name']}): {ex_label}",
                        f"Generated from OpenAPI example for parameter '{p['name']}'.", r_pex, ok, contract=True)
                    param_examples_added += 1

    # ---- Positive Minimal / Maximal (using examples when present, else auto-generated data) ----
    mn, mx = build_request(op, "min"), build_request(op, "max")
    add(G_POS, "Minimal – required fields only", "Only mandatory parameters, headers and body fields (from examples or auto-generated).", mn, ok, contract=True)
    add(G_POS, "Maximal – all fields populated", "All mandatory and optional fields (from examples or auto-generated synthetic data).", mx, ok, contract=True)

    # ---- Missing required (params/headers) ----
    for p in op["parameters"]:
        if p.get("required") and p["in"] in ("query", "header") and p["name"].lower() not in _SKIP_HEADERS:
            r = copy.deepcopy(mn)
            r[_BUCKET[p["in"]]].pop(p["name"], None)
            add(G_MISSING, f"Missing {p['in']} param '{p['name']}'", "Single-fault: required parameter omitted.", r, bad)

    # ---- Param boundary / type ----
    for p in op["parameters"]:
        if p["in"] == "header" and p["name"].lower() in _SKIP_HEADERS:
            continue
        for label, val in bad_values(p.get("schema") or {}, allow_type_swap=_type(concretize(p.get("schema") or {})[0]) != "string"):
            r = copy.deepcopy(mx)
            r[_BUCKET[p["in"]]][p["name"]] = val if p["in"] == "query" else str(val)
            add(G_BOUND, f"{p['in']} '{p['name']}': {label}", "Constraint violation on parameter.", r, bad)

    # ---- Body (non-polymorphic) ----
    if bschema is not None and not disc:
        for path in _required_paths(bschema):
            r = copy.deepcopy(mn)
            if r["body"] is not None and _del(r["body"], path):
                add(G_MISSING, f"Missing body property '{'.'.join(path)}'", "Single-fault: required body property omitted.", r, bad)
        for path, ps in _iter_props(bschema):
            for label, val in bad_values(ps):
                r = copy.deepcopy(mx)
                if r["body"] is not None and _set(r["body"], path, val):
                    add(G_BOUND, f"body '{'.'.join(path)}': {label}", "Constraint violation on body property.", r, bad)

    # ---- Discriminator ----
    if disc and bschema is not None:
        prop, vs = disc
        for key, vschema in vs.items():
            sub = key
            rmin, rmax = build_request(op, "min", lock=key), build_request(op, "max", lock=key)
            add(G_DISC, f"[{key}] Minimal", f"Discriminator '{prop}' locked to '{key}'; required fields only.", rmin, ok, subgroup=sub, contract=True)
            add(G_DISC, f"[{key}] Maximal", f"Discriminator '{prop}' locked to '{key}'; all fields.", rmax, ok, subgroup=sub, contract=True)
            for path in _required_paths(vschema):
                if path == (prop,):
                    continue
                r = copy.deepcopy(rmin)
                if r["body"] is not None and _del(r["body"], path):
                    add(G_DISC, f"[{key}] Missing '{'.'.join(path)}'", "Variant-specific required property omitted.", r, bad, subgroup=sub)
            for path, ps in _iter_props(vschema):
                if path == (prop,):
                    continue
                for label, val in bad_values(ps):
                    r = copy.deepcopy(rmax)
                    if r["body"] is not None and _set(r["body"], path, val):
                        add(G_DISC, f"[{key}] '{'.'.join(path)}': {label}", "Variant-specific constraint violation.", r, bad, subgroup=sub)
        # negatives
        base = build_request(op, "min", lock=next(iter(vs)))
        r = copy.deepcopy(base)
        if isinstance(r["body"], dict):
            r["body"].pop(prop, None)
            add(G_DISC, "Missing discriminator property", f"'{prop}' omitted entirely.", r, bad, subgroup="Negative")
            r = copy.deepcopy(base)
            r["body"][prop] = "__unmapped_discriminator__"
            add(G_DISC, "Invalid discriminator value", f"'{prop}' set to an unmapped value.", r, bad, subgroup="Negative")
        keys = list(vs)
        for a in keys:
            props_a = set((vs[a].get("properties") or {}))
            other = next((b for b in keys if b != a and (set(vs[b].get("required") or []) - props_a - {prop})), None)
            if other:
                r = build_request(op, "max", lock=other)
                if isinstance(r["body"], dict):
                    r["body"][prop] = a
                    add(G_DISC, f"Polymorphic bleed: '{a}' with '{other}' fields",
                        f"Discriminator says '{a}' but payload carries '{other}' required fields.", r, bad, subgroup="Negative")

    # ---- Kong security ----
    if scheme:
        for g in allow:
            add(G_SEC, f"Authorized group '{g}'", "Valid credential for a group in acl.allow.", mx, ok, auth_cfg=auth("group", g), contract=True)
        forbidden = [g for g in known_groups if g not in allow] if allow else list(deny)
        for g in forbidden[:4]:
            add(G_SEC, f"Forbidden group '{g}'", "Valid credential for a group NOT permitted by the ACL.", mx, ["403"], auth_cfg=auth("group", g))
        if not allow and not deny and not forbidden:
            pass
        add(G_SEC, "Missing credentials", "No authentication credentials supplied.", mx, ["401"], auth_cfg=auth("none"))
    return tests
