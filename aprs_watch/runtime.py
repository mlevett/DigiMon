import json
import logging
import logging.handlers
import os
import socket
import threading
import time
from pathlib import Path

from .config import write_json
from .core import Monitor
from .notify import Notifier


class InstanceLock:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0)
                if not self.stream.read(1):
                    self.stream.write(b"0")
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            self.stream = None
            raise RuntimeError("A monitor already uses this data folder. Open the GUI to view its status.") from None
        return self

    def __exit__(self, *args):
        if self.stream:
            self.stream.close()


def is_running(folder):
    try:
        with InstanceLock(Path(folder) / "monitor.lock"):
            return False
    except RuntimeError:
        return True


def load_state(folder):
    try:
        data = json.loads((Path(folder) / "status.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class Worker:
    def __init__(self, cfg, folder):
        self.cfg, self.folder = cfg, Path(folder)
        self.stop = threading.Event()
        self.thread = None
        self.error = None
        self.events, self.messages = [], []
        self.logger = logging.getLogger(f"aprs_watch.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.last_write = 0

    def report(self, message):
        self.logger.info(message)
        self.messages.append({"time": time.time(), "message": message})
        self.messages[:] = self.messages[-40:]

    def emit(self, events):
        for event in events:
            self.events.append(event)
            self.events[:] = self.events[-40:]
            self.report(event["title"])
            self.notifier.submit(event)

    def save(self, force=False):
        now = time.time()
        if not force and now - self.last_write < 1:
            return
        data = self.monitor.snapshot(now)
        data.update(events=list(self.events), messages=list(self.messages), pid=os.getpid())
        write_json(self.folder / "status.json", data)
        self.last_write = now

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name="aprs-monitor")
        self.thread.start()

    def run(self):
        handler = None
        try:
            with InstanceLock(self.folder / "monitor.lock"):
                handler = logging.handlers.RotatingFileHandler(self.folder / "monitor.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
                handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
                self.logger.addHandler(handler)
                saved = load_state(self.folder)
                self.events = saved.get("events", [])[-40:]
                self.monitor = Monitor(self.cfg, time.time(), saved)
                self.notifier = Notifier(self.cfg, self.report)
                self.notifier.thread.start()
                self.report("Monitor started")
                self.save(True)
                retry = 1
                try:
                    while not self.stop.is_set():
                        started = time.monotonic()
                        try:
                            self.session()
                        except (OSError, ValueError) as error:
                            self.report(f"APRS feed disconnected ({type(error).__name__}); reconnecting")
                        self.emit(self.monitor.connection(False, time.time()))
                        self.save(True)
                        if time.monotonic() - started > 60:
                            retry = 1
                        deadline = time.monotonic() + retry
                        while not self.stop.is_set() and time.monotonic() < deadline:
                            self.emit(self.monitor.tick(time.time()))
                            self.save()
                            self.stop.wait(0.5)
                        retry = min(retry * 2, 60)
                finally:
                    self.notifier.stop.set()
                    self.notifier.thread.join(timeout=15)
                    self.monitor.connection(False, time.time())
                    self.report("Monitor stopped")
                    self.save(True)
        except Exception as error:
            self.error = f"{type(error).__name__}: {error}"
            self.logger.error(self.error)
        finally:
            if handler:
                self.logger.removeHandler(handler)
                handler.close()

    def session(self):
        cfg = self.cfg
        target = cfg["callsign"]
        # Bare and -0 are the same AX.25 address; subscribe to both representations.
        calls = target[:-2] + "/" + target if target.endswith("-0") else target + "/" + target + "-0" if "-" not in target else target
        filters = " ".join(([f"b/{calls}"] if cfg["match"] != "digipeated" else []) +
                           ([f"d/{calls}"] if cfg["match"] != "beacon" else []))
        with socket.create_connection((cfg["host"], cfg["port"]), timeout=10) as sock:
            sock.settimeout(0.5)
            buffer = b""
            received = time.monotonic()
            handshake_started = received
            sent_login, acknowledged = False, False
            while not self.stop.is_set():
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        raise OSError("Server closed connection")
                    received = time.monotonic()
                    buffer += chunk
                    if len(buffer) > 65536:
                        raise ValueError("APRS line too long")
                    while b"\n" in buffer:
                        raw, buffer = buffer.split(b"\n", 1)
                        line = raw.decode("ascii", errors="replace").strip("\r")
                        if len(line) > 2048:
                            continue
                        if not sent_login:
                            if not line.startswith("#"):
                                raise ValueError("Invalid server greeting")
                            sock.sendall(f'user {cfg["login"]} pass -1 vers DigiMon 1.0 filter {filters}\r\n'.encode("ascii"))
                            sent_login = True
                        elif line.lower().startswith("# logresp"):
                            parts = line.replace(",", " ").split()
                            if len(parts) < 4 or parts[2].upper() != cfg["login"] or parts[3].lower() not in ("verified", "unverified"):
                                raise ValueError("Login rejected")
                            if not acknowledged:
                                acknowledged = True
                                self.report("APRS feed connected (receive only)")
                                self.emit(self.monitor.connection(True, time.time()))
                        elif acknowledged and not line.startswith("#"):
                            self.emit(self.monitor.packet(line, time.time()))
                except socket.timeout:
                    pass
                current = time.monotonic()
                if not acknowledged and current - handshake_started > 20:
                    raise OSError("Login handshake timed out")
                if current - received > cfg["feed_timeout_seconds"]:
                    raise OSError("Feed heartbeat timed out")
                self.emit(self.monitor.tick(time.time()))
                self.save()
