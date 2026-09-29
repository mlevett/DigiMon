import copy
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from aprs_watch.config import DEFAULT, validate, write_json
from aprs_watch.core import Monitor, evidence
from aprs_watch.notify import channels, deliver, Notifier
from aprs_watch.runtime import Worker, InstanceLock, is_running, load_state


def config(**overrides):
    data = copy.deepcopy(DEFAULT)
    data.update(login="G0ABC-W", desktop=False, **overrides)
    return validate(data)


class PacketTests(unittest.TestCase):
    def test_own_packet(self):
        self.assertEqual(evidence("MB7UPH>APRS,WIDE2-1:!position", "MB7UPH"), "Own packet")

    def test_used_path(self):
        self.assertEqual(evidence("G0ABC>APRS,MB7UPH*,WIDE2-1,qAR,IGATE:!position", "MB7UPH"), "Relayed packet")

    def test_implied_used_hop(self):
        self.assertEqual(evidence("G0ABC>APRS,MB7UPH,OTHER*,qAR,IGATE:data", "MB7UPH"), "Relayed packet")

    def test_unused_hop_does_not_count(self):
        self.assertIsNone(evidence("G0ABC>APRS,OTHER*,MB7UPH:data", "MB7UPH"))
        self.assertIsNone(evidence("G0ABC>APRS,MB7UPH:data", "MB7UPH"))

    def test_igate_does_not_count(self):
        self.assertIsNone(evidence("G0ABC>APRS,OTHER*,qAR,MB7UPH:data", "MB7UPH"))

    def test_internet_path_does_not_count(self):
        self.assertIsNone(evidence("G0ABC>APRS,TCPIP*,MB7UPH*:data", "MB7UPH"))

    def test_ssid_and_zero(self):
        self.assertIsNone(evidence("MB7UPH-1>APRS:data", "MB7UPH"))
        self.assertEqual(evidence("MB7UPH-0>APRS:data", "MB7UPH"), "Own packet")

    def test_modes(self):
        self.assertIsNone(evidence("MB7UPH>APRS:data", "MB7UPH", "digipeated"))
        self.assertIsNone(evidence("G0ABC>APRS,MB7UPH*:data", "MB7UPH", "beacon"))

    def test_bad_and_third_party_payload(self):
        for line in ("# heartbeat", "broken", "G0ABC>APRS:", "G0ABC>APRS:}MB7UPH>APRS:data"):
            self.assertIsNone(evidence(line, "MB7UPH"))


class StateTests(unittest.TestCase):
    def setUp(self):
        self.monitor = Monitor(config(), 1000)
        self.monitor.connection(True, 1000)

    def test_never_seen_alert_at_threshold(self):
        self.assertEqual(self.monitor.tick(2199), [])
        self.assertEqual(self.monitor.tick(2200)[0]["kind"], "missing")
        self.assertEqual(self.monitor.tick(2300), [])

    def test_packet_resets_timer(self):
        self.monitor.packet("MB7UPH>APRS:data", 1500)
        self.assertEqual(self.monitor.tick(2200), [])
        self.assertEqual(self.monitor.tick(2700)[0]["kind"], "missing")

    def test_one_recovery_per_incident(self):
        self.monitor.tick(2200)
        self.assertEqual(self.monitor.packet("MB7UPH>APRS:data", 2210)[0]["kind"], "recovered")
        self.assertEqual(self.monitor.packet("MB7UPH>APRS:data", 2220), [])

    def test_disconnect_separate_and_reconnect_grace(self):
        self.monitor.connection(False, 2100)
        self.assertEqual(self.monitor.tick(2300), [])
        self.assertEqual(self.monitor.tick(2400)[0]["kind"], "feed_lost")
        self.assertEqual(self.monitor.tick(2500), [])
        self.assertEqual(self.monitor.connection(True, 3000)[0]["kind"], "feed_recovered")
        self.assertEqual(self.monitor.tick(4199), [])
        self.assertEqual(self.monitor.tick(4200)[0]["kind"], "missing")

    def test_no_connection_ever(self):
        monitor = Monitor(config(), 1000)
        self.assertEqual(monitor.tick(1300)[0]["kind"], "feed_lost")

    def test_repeat_alert(self):
        monitor = Monitor(config(repeat_minutes=10), 1000)
        monitor.connection(True, 1000)
        monitor.tick(2200)
        self.assertEqual(monitor.tick(2799), [])
        self.assertEqual(monitor.tick(2800)[0]["kind"], "missing")

    def test_restart_restores_incident_without_duplicate(self):
        self.monitor.tick(2200)
        monitor = Monitor(config(), 3000, self.monitor.snapshot(2200))
        monitor.connection(True, 3000)
        self.assertEqual(monitor.tick(5000), [])
        self.assertEqual(monitor.packet("MB7UPH>APRS:data", 5001)[0]["kind"], "recovered")

    def test_different_station_resets_history(self):
        self.monitor.packet("MB7UPH>APRS:data", 1100)
        monitor = Monitor(config(callsign="MB7XYZ"), 1200, self.monitor.snapshot(1100))
        self.assertIsNone(monitor.last_seen)

    def test_future_saved_time_is_rejected(self):
        saved = {"callsign": "MB7UPH", "match": "both", "last_seen": 999999}
        self.assertIsNone(Monitor(config(), 1000, saved).last_seen)


class ConfigAndNotificationTests(unittest.TestCase):
    def test_invalid_config(self):
        for overrides in ({"callsign": "MB7UPH\nBAD"}, {"timeout_minutes": 0}, {"timeout_minutes": "nan"}, {"port": 99999}, {"match": "x"}, {"host": "a\nb"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                config(**overrides)

    def test_channels_independent(self):
        cfg = config()
        self.assertEqual(channels(cfg), [])
        cfg["desktop"] = cfg["email"]["enabled"] = cfg["webhook"]["enabled"] = True
        self.assertEqual(channels(cfg), ["desktop", "email", "webhook"])

    def test_webhook_payloads(self):
        cfg = config()
        event = {"kind": "test", "title": "Hello", "message": "World"}
        cfg["webhook"]["url"] = "https://example.invalid/secret"
        for fmt, key in (("discord", "content"), ("slack", "text"), ("generic", "kind")):
            cfg["webhook"]["format"] = fmt
            with patch("urllib.request.urlopen") as send:
                send.return_value.__enter__.return_value.status = 204
                deliver("webhook", cfg, event)
                request = send.call_args.args[0]
                self.assertIn(key, json.loads(request.data))

    def test_smtp_tls_and_password_environment(self):
        cfg = config()
        cfg["email"].update(host="smtp.invalid", username="operator", **{"from": "a@example.com", "to": "b@example.com"})
        with patch.dict(os.environ, APRS_WATCH_SMTP_PASSWORD="secret"), patch("smtplib.SMTP") as constructor:
            smtp = constructor.return_value.__enter__.return_value
            smtp.send_message.return_value = {}
            deliver("email", cfg, {"title": "Test", "message": "Body"})
            smtp.starttls.assert_called_once()
            smtp.login.assert_called_once_with("operator", "secret")
            smtp.send_message.assert_called_once()

    def test_failed_channel_does_not_block_another(self):
        cfg = config()
        cfg["email"]["enabled"] = cfg["webhook"]["enabled"] = True
        attempts = []
        reports = []
        def fake(channel, *_):
            attempts.append(channel)
            if channel == "email":
                raise OSError("secret must never appear")
        notifier = Notifier(cfg, reports.append)
        with patch("aprs_watch.notify.deliver", fake):
            notifier.thread.start()
            notifier.submit({"title": "Test"})
            notifier.jobs.join()
            notifier.stop.set()
            notifier.thread.join(2)
        self.assertEqual(attempts.count("email"), 3)
        self.assertEqual(attempts.count("webhook"), 1)
        self.assertNotIn("secret must never appear", str(reports))

    def test_lock_and_atomic_state(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(is_running(folder))
            with InstanceLock(Path(folder) / "monitor.lock"):
                self.assertTrue(is_running(folder))
            self.assertFalse(is_running(folder))
            write_json(Path(folder) / "status.json", {"last_seen": 123})
            self.assertEqual(load_state(folder)["last_seen"], 123)


class IntegrationTests(unittest.TestCase):
    def test_local_feed_alert_and_recovery(self):
        """Exercise the actual socket, login, parser, timers and persisted status."""
        with tempfile.TemporaryDirectory() as folder, socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            server.settimeout(5)
            cfg = config(host="127.0.0.1", port=server.getsockname()[1], timeout_minutes=0.01)
            received = []
            release = threading.Event()
            def feed():
                with server.accept()[0] as client:
                    client.settimeout(3)
                    client.sendall(b"# local test server\r\n")
                    received.append(client.recv(2048).decode())
                    client.sendall(b"# logresp G0ABC-W unverified, server TEST\r\n")
                    release.wait(4)
                    client.sendall(b"MB7UPH>APRS:!test packet\r\n")
                    release.clear()
                    release.wait(3)
            thread = threading.Thread(target=feed, daemon=True)
            thread.start()
            worker = Worker(cfg, folder)
            worker.start()
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and not any(e["kind"] == "missing" for e in worker.events):
                    time.sleep(0.05)
                self.assertTrue(any(e["kind"] == "missing" for e in worker.events))
                release.set()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not any(e["kind"] == "recovered" for e in worker.events):
                    time.sleep(0.05)
                self.assertTrue(any(e["kind"] == "recovered" for e in worker.events))
                self.assertIn("pass -1", received[0])
                self.assertIn("b/MB7UPH/MB7UPH-0 d/MB7UPH/MB7UPH-0", received[0])
            finally:
                worker.stop.set()
                release.set()
                worker.thread.join(5)
                thread.join(5)
            self.assertIsNone(worker.error)
            self.assertFalse(worker.thread.is_alive())
            self.assertIsNotNone(load_state(folder)["last_seen"])


if __name__ == "__main__":
    unittest.main()
