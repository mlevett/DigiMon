import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

from .config import DEFAULT, read, write_json
from .notify import channels, deliver
from .runtime import Worker, is_running, load_state


def default_home():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "APRSWatch"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "APRSWatch"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "aprs-watch"


def main():
    parser = argparse.ArgumentParser(description="DigiMon — cross-platform digipeater monitor")
    parser.add_argument("command", nargs="?", default="gui", choices=["gui", "run", "init", "status", "test-alert"])
    parser.add_argument("--config", type=Path, default=default_home() / "config.json")
    parser.add_argument("--data-dir", type=Path, help="Default: data/ beside the configuration")
    args = parser.parse_args()
    folder = args.data_dir or args.config.parent / "data"
    try:
        if args.command == "gui":
            from .gui import launch
            launch(args.config, folder)
        elif args.command == "init":
            if args.config.exists():
                raise ValueError(f"Configuration already exists: {args.config}")
            write_json(args.config, DEFAULT)
            print(f"Created {args.config}. Set the digipeater callsign, your APRS login callsign and notification channels before starting.")
        elif args.command == "status":
            data = load_state(folder)
            data["running"] = is_running(folder)
            if not data["running"]:
                data["status"] = "Stopped"
            elif time.time() - data.get("updated", 0) > 30:
                data["status"] = "Monitor not responding"
            print(json.dumps(data, indent=2))
        elif args.command == "test-alert":
            cfg = read(args.config)
            selected = channels(cfg)
            if not selected:
                raise ValueError("No notification channels enabled")
            failed = False
            for name in selected:
                try:
                    deliver(name, cfg, {"kind": "test", "title": f"DigiMon test · {cfg['callsign']}", "message": "Your selected notification channel is working.", "time": time.time(), "callsign": cfg["callsign"]})
                    print(f"{name}: delivered")
                except Exception as error:
                    print(f"{name}: failed ({type(error).__name__}); check configuration and credentials", file=sys.stderr)
                    failed = True
            return 1 if failed else 0
        else:
            worker = Worker(read(args.config), folder)
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: worker.stop.set())
            worker.run()
            if worker.error:
                raise RuntimeError(worker.error)
    except (ValueError, OSError, RuntimeError, ImportError) as error:
        print(f"DigiMon: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
