from __future__ import annotations

import json
import os

try:
    from core.paths import app_data_dir

    CONFIG_FILE = os.path.join(str(app_data_dir()), "config_data.json")
except Exception:
    CONFIG_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config_data.json",
    )

DEFAULT_CONFIG = {
    "accounts": [],
    "campus": "崇山校区图书馆",
    "room": "三楼智慧研修空间",
    "day_start": "09:00",
    "day_end": "21:00",
    "mode": "single",
    "dry_run": False,
    "cross_room": False,
    "cross_room_rooms": {},
    "receiver_email": "",
    "pre_notify": 30,
    "auto_cancel": False,
    "priority_mode": "longest_first",
    "preferred_seats": {},
    "theme": "auto",  # "auto" | "light" | "dark"
    "low_animation": False,
    "first_launch_help_shown": False,
}


def save_config(config: dict):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def load_config() -> dict:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULT_CONFIG, **data}
    except Exception:
        pass
    return dict(DEFAULT_CONFIG)
