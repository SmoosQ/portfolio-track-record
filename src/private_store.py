"""Private atomic state and daily-partition storage helpers."""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_DIR = ROOT / "data" / "private"
STATE_PATH = PRIVATE_DIR / "state.json"


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def load_state() -> dict[str, Any]:
    ensure_private_directory(PRIVATE_DIR)
    if not STATE_PATH.exists():
        return {"version": 1}
    try:
        payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Private incremental state is unreadable.") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise RuntimeError("Private incremental state has an unsupported format.")
    return payload


def save_state(state: dict[str, Any]) -> None:
    state = {"version": 1, **state}
    _write_bytes(
        STATE_PATH,
        (json.dumps(state, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Private partition is unreadable: {path.name}") from exc


def write_json(path: Path, payload: Any) -> None:
    _write_bytes(
        path,
        (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"),
    )


def read_json_gzip(path: Path) -> Any:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Private compressed partition is unreadable: {path.name}") from exc


def write_json_gzip(path: Path, payload: Any) -> None:
    ensure_private_directory(path.parent)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as handle:
        json.dump(payload, handle, separators=(",", ":"))
        handle.write("\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _write_bytes(path: Path, content: bytes) -> None:
    ensure_private_directory(path.parent)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
