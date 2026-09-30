"""Packet matching and alert state machine; independent of UI and networking."""
from datetime import datetime, timezone


def utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if timestamp else "Never observed"


def canonical(call):
    call = call.upper()
    return call[:-2] if call.endswith("-0") else call


def evidence(packet, callsign, mode="both"):
    if packet.startswith("#") or ":" not in packet or ">" not in packet.split(":", 1)[0]:
        return None
    header, payload = packet.split(":", 1)
    source, route = header.split(">", 1)
    target = canonical(callsign)
    if not payload:
        return None
    if mode != "digipeated" and canonical(source) == target:
        return "Own packet"
    if mode == "beacon":
        return None
    # Only the RF path before the q construct counts. The entry IGate is not a digi.
    path = []
    for hop in route.split(",")[1:]:
        if hop.startswith("q") or hop.rstrip("*") in ("TCPIP", "TCPXX"):
            break
        path.append(hop)
    # TNC2 may mark just the last used hop; preceding hops are also used.
    used = [i for i, hop in enumerate(path) if hop.endswith("*")]
    if used and any(canonical(hop.rstrip("*")) == target for hop in path[:max(used) + 1]):
        return "Relayed packet"
    return None


class Monitor:
    def __init__(self, config, now, saved=None):
        self.cfg = config
        saved = saved or {}
        if saved.get("callsign") != config["callsign"] or saved.get("match") != config["match"]:
            saved = {}
        self.last_seen = saved.get("last_seen")
        if not isinstance(self.last_seen, (int, float)) or not 0 < self.last_seen <= now:
            self.last_seen = None
        self.last_packet = saved.get("last_packet", "") if self.last_seen else ""
        self.last_evidence = saved.get("evidence", "") if self.last_seen else ""
        self.missing = bool(saved.get("missing", False))
        self.last_alert = now  # Restart must not immediately repeat an old incident.
        self.connected = False
        self.observing_since = None
        self.disconnected_since = now
        self.feed_alerted = False
        self.started = now

    def event(self, kind, title, message, now):
        return {"kind": kind, "title": title, "message": message, "time": now,
                "callsign": self.cfg["callsign"]}

    def connection(self, connected, now):
        events = []
        if connected == self.connected:
            return events
        self.connected = connected
        if connected:
            self.observing_since = now
            if self.feed_alerted:
                events.append(self.event("feed_recovered", "APRS feed restored",
                                         "The feed is connected again. Station observation has resumed.", now))
            self.feed_alerted = False
        else:
            self.disconnected_since = now
            self.observing_since = None
        return events

    def packet(self, line, now):
        reason = evidence(line, self.cfg["callsign"], self.cfg["match"])
        if not reason:
            return []
        self.last_seen, self.last_packet, self.last_evidence = now, line, reason
        if self.missing:
            self.missing = False
            return [self.event("recovered", f'{self.cfg["callsign"]} seen again',
                               f"{reason} observed at {utc(now)}.", now)]
        return []

    def tick(self, now):
        if not self.connected:
            if not self.feed_alerted and now - self.disconnected_since >= self.cfg["feed_alert_minutes"] * 60:
                self.feed_alerted = True
                return [self.event("feed_lost", "APRS feed unavailable",
                                   "Station status is unknown. The monitor is reconnecting; check its internet connection and APRS server.", now)]
            return []
        # Require a full continuous observation window after every connection gap.
        baseline = max(self.observing_since, self.last_seen or self.observing_since)
        if now - baseline < self.cfg["timeout_minutes"] * 60:
            return []
        repeat = self.cfg["repeat_minutes"] * 60
        if not self.missing or (repeat and now - self.last_alert >= repeat):
            self.missing, self.last_alert = True, now
            return [self.event("missing", f'{self.cfg["callsign"]} not seen',
                               f'No matching packet for at least {self.cfg["timeout_minutes"]:g} minutes of continuous monitoring. '
                               f'Last observed: {utc(self.last_seen)}. APRS-IS visibility does not prove RF availability.', now)]
        return []

    def snapshot(self, now):
        status = "Feed unavailable" if not self.connected else "Not seen" if self.missing else "Seen recently" if self.last_seen and now - self.last_seen < self.cfg["timeout_minutes"] * 60 else "Observing"
        return {"callsign": self.cfg["callsign"], "match": self.cfg["match"], "status": status,
                "connected": self.connected, "last_seen": self.last_seen,
                "last_packet": self.last_packet, "evidence": self.last_evidence,
                "missing": self.missing, "updated": now}
