from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import kong as K

def op(path, params=(), method="GET"):
    return {"method": method, "full_path": path, "parameters": list(params)}

def route(paths, methods=("GET",), strip=False, svc=""):
    return {"name": "r", "paths": paths, "methods": list(methods), "strip_path": strip, "service_path": svc}

PID = {"in": "path", "name": "id", "schema": {"type": "string", "pattern": "^pay_[a-z0-9]{8}$"}}
NUM = {"in": "path", "name": "id", "schema": {"type": "integer"}}


def test_regex_uses_param_schema():
    assert K.match_route(route(["~/v1/pay/[a-z_]+[a-z0-9]*$"]), op("/v1/pay/{id}", [PID]))


def test_regex_no_match():
    assert K.match_route(route([r"~/v1/pay/\d+$"]), op("/v1/pay/{id}", [PID])) is None
    assert K.match_route(route([r"~/v1/pay/\d+$"]), op("/v1/pay/{id}", [NUM]))


def test_named_group_pcre():
    assert K.match_route(route([r"~/v1/pay/(?<id>\d+)$"]), op("/v1/pay/{id}", [NUM]))


def test_regex_beats_prefix():
    prefix = K.match_route(route(["/v1/pay"]), op("/v1/pay/{id}", [NUM]))
    rx = K.match_route(route([r"~/v1/pay/\d+$"]), op("/v1/pay/{id}", [NUM]))
    assert rx[1] > prefix[1]


def test_method_filter():
    assert K.match_route(route(["/v1/pay"], methods=("POST",)), op("/v1/pay")) is None


def test_strip_path_upstream():
    m = K.match_route(route(["/customers"], strip=True, svc="/v1/customers"), op("/v1/customers"))
    assert m and m[0] == "/customers"
