from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

try:
    from core.paths import app_data_dir

    STATE_FILE = os.path.join(str(app_data_dir()), "single_runtime_state.json")
except Exception:
    STATE_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "single_runtime_state.json",
    )


def bj_now_iso() -> str:
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))
    return now.isoformat(timespec="seconds")


def save_single_runtime_state(state: Dict[str, Any]) -> bool:
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        payload = {
            "version": 1,
            "saved_at_bj": bj_now_iso(),
            **(state or {}),
        }
        tmp_file = STATE_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, STATE_FILE)
        return True
    except Exception:
        return False


def load_single_runtime_state() -> Dict[str, Any]:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def clear_single_runtime_state() -> bool:
    try:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        return True
    except Exception:
        return False
