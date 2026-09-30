import json
import math
import os
import re
from pathlib import Path

DEFAULT = {
    "callsign": "", "login": "", "timeout_minutes": 20,
    "match": "both", "host": "rotate.aprs2.net", "port": 14580,
    "feed_timeout_seconds": 120, "feed_alert_minutes": 5,
    "repeat_minutes": 0,
    "desktop": True,
    "webhook": {"enabled": False, "url": "", "format": "discord"},
    "email": {"enabled": False, "host": "", "port": 587, "security": "starttls",
              "username": "", "password_env": "DIGIMON_SMTP_PASSWORD",
              "from": "", "to": ""},
}


def validate(data):
    cfg = json.loads(json.dumps(DEFAULT))
    for key, value in data.items():
        if key not in cfg:
            raise ValueError(f"Unknown setting: {key}")
        if isinstance(cfg[key], dict):
            if not isinstance(value, dict) or set(value) - set(cfg[key]):
                raise ValueError(f"Invalid {key} settings")
            cfg[key].update(value)
        else:
            cfg[key] = value
    for key in ("callsign", "login"):
        cfg[key] = str(cfg[key]).strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,6}(?:-[A-Z0-9]{1,2})?", cfg[key]):
            raise ValueError(f"Enter a valid {key} (callsign with optional SSID)")
    if cfg["match"] not in ("beacon", "digipeated", "both"):
        raise ValueError("Match must be beacon, digipeated, or both")
    for key in ("timeout_minutes", "feed_timeout_seconds", "feed_alert_minutes", "repeat_minutes"):
        cfg[key] = float(cfg[key])
        if not math.isfinite(cfg[key]) or cfg[key] < 0 or (key != "repeat_minutes" and cfg[key] == 0):
            raise ValueError(f"Invalid {key}")
    cfg["port"] = int(cfg["port"])
    if not 1 <= cfg["port"] <= 65535:
        raise ValueError("Port must be 1–65535")
    if not re.fullmatch(r"[A-Za-z0-9.:-]+", cfg["host"]):
        raise ValueError("Invalid APRS server hostname")
    hook = cfg["webhook"]
    if hook["enabled"] and not hook["url"]:
        raise ValueError("Enter a webhook URL or disable webhook alerts")
    if hook["url"] and not hook["url"].startswith("https://"):
        raise ValueError("Webhook URL must start with https://")
    if hook["format"] not in ("discord", "slack", "generic"):
        raise ValueError("Webhook format must be discord, slack, or generic")
    mail = cfg["email"]
    if mail["enabled"] and not mail["host"]:
        raise ValueError("Enter an SMTP server or disable email alerts")
    if mail["security"] not in ("starttls", "ssl"):
        raise ValueError("Email security must be starttls or ssl")
    mail["port"] = int(mail["port"])
    if not 1 <= mail["port"] <= 65535:
        raise ValueError("Invalid email port")
    if mail["host"] and (not mail["from"] or not mail["to"]):
        raise ValueError("Email requires both sender and recipient")
    for value in (mail["host"], mail["from"], mail["to"], mail["username"]):
        if "\r" in value or "\n" in value:
            raise ValueError("Email settings must be single lines")
    return cfg


def read(path):
    return validate(json.loads(Path(path).read_text(encoding="utf-8")))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
    os.replace(temporary, path)
