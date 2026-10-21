"""Runtime configuration: local OAS/Kong directories, target URL, ACL credentials.

Initial values come from environment variables / ``.env``
(``OAS_LOCAL_PATH``, ``KONG_LOCAL_PATH``); runtime edits persist to data/config.json.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
CONFIG_FILE = DATA_DIR / "config.json"
CREDENTIALS_FILE = DATA_DIR / "credentials.json"
SAMPLES_DIR = ROOT / "samples"


def _load_dotenv() -> None:
    for candidate in (ROOT / ".env", ROOT / "backend" / ".env"):
        if candidate.exists():
            for line in candidate.read_text("utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


class Credential(BaseModel):
    group: str
    username: str = ""   # basic-auth user (or consumer name)
    password: str = ""   # basic-auth password
    token: str = ""      # api key / bearer token (key-auth, jwt, oauth2)


class AppConfig(BaseModel):
    oas_dir: str = ""
    kong_dir: str = ""
    target_url: str = "http://localhost:9000"
    verify_tls: bool = True
    credentials: List[Credential] = Field(default_factory=list)


_lock = threading.Lock()
_config: Optional[AppConfig] = None


def _initial() -> AppConfig:
    _load_dotenv()
    return AppConfig(
        oas_dir=os.environ.get("OAS_LOCAL_PATH", str(SAMPLES_DIR / "oas")),
        kong_dir=os.environ.get("KONG_LOCAL_PATH", str(SAMPLES_DIR / "kong")),
        target_url=os.environ.get("TARGET_URL", "http://localhost:9000"),
        credentials=[
            Credential(group="admins", username="alice", password="alice-pass", token="admin-key-123"),
            Credential(group="readers", username="bob", password="bob-pass", token="reader-key-456"),
            Credential(group="guests", username="gina", password="gina-pass", token="guest-key-789"),
        ],
    )


def _save() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(_config.model_dump_json(indent=2, exclude={"credentials"}), "utf-8")
    CREDENTIALS_FILE.write_text(
        json.dumps([c.model_dump() for c in _config.credentials], indent=2), "utf-8")


def get_config() -> AppConfig:
    global _config
    with _lock:
        if _config is None:
            _config = _initial()
            if CONFIG_FILE.exists():
                saved = json.loads(CONFIG_FILE.read_text("utf-8"))
                _config = AppConfig(**{**_config.model_dump(), **saved})
            if CREDENTIALS_FILE.exists():
                _config.credentials = [Credential(**c) for c in json.loads(CREDENTIALS_FILE.read_text("utf-8"))]
            else:
                _save()  # first run: materialise credentials.json
        return _config


def update_config(patch: Dict[str, Any]) -> AppConfig:
    cfg = get_config()
    with _lock:
        data = cfg.model_dump()
        data.update({k: v for k, v in patch.items() if v is not None and k in data})
        new = AppConfig(**data)
        for k, v in new.__dict__.items():
            setattr(cfg, k, v)
        _save()
    return cfg
