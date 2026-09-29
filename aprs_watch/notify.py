import base64
import json
import os
import queue
import smtplib
import ssl
import subprocess
import sys
import threading
import urllib.request
from email.message import EmailMessage


def channels(cfg):
    return (["desktop"] if cfg["desktop"] else []) + [name for name in ("email", "webhook") if cfg[name]["enabled"]]


def deliver(name, cfg, event):
    title, body = event["title"], event["message"]
    if name == "webhook":
        hook = cfg["webhook"]
        payload = {"discord": {"content": f"**{title}**\n{body}", "allowed_mentions": {"parse": []}},
                   "slack": {"text": f"{title}\n{body}"}, "generic": event}[hook["format"]]
        request = urllib.request.Request(hook["url"], data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json", "User-Agent": "DigiMon/1.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError("Webhook rejected notification")
    elif name == "email":
        mail = cfg["email"]
        message = EmailMessage()
        message["Subject"] = f"[DigiMon] {title}"
        message["From"], message["To"] = mail["from"], mail["to"]
        message.set_content(body)
        context = ssl.create_default_context()
        connection = smtplib.SMTP_SSL(mail["host"], mail["port"], timeout=10, context=context) if mail["security"] == "ssl" else smtplib.SMTP(mail["host"], mail["port"], timeout=10)
        with connection as smtp:
            if mail["security"] == "starttls":
                smtp.starttls(context=context)
            if mail["username"]:
                password = os.environ.get(mail["password_env"])
                if not password:
                    raise ValueError("SMTP password environment variable is unset")
                smtp.login(mail["username"], password)
            refused = smtp.send_message(message)
            if refused:
                raise RuntimeError("Some email recipients were rejected")
    elif name == "desktop":
        if sys.platform.startswith("linux"):
            subprocess.run(["notify-send", "--app-name=DigiMon", "--", title, body], check=True, timeout=10, capture_output=True)
        elif sys.platform == "darwin":
            script = 'on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run'
            subprocess.run(["osascript", "-e", script, title, body], check=True, timeout=10, capture_output=True)
        elif sys.platform == "win32":
            # Pass user content through the environment, never as executable PowerShell.
            script = 'Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; $n=New-Object System.Windows.Forms.NotifyIcon; $n.Icon=[System.Drawing.SystemIcons]::Information; $n.Visible=$true; $n.ShowBalloonTip(5000,$env:APRS_NOTICE_TITLE,$env:APRS_NOTICE_BODY,[System.Windows.Forms.ToolTipIcon]::Info); Start-Sleep -Seconds 6; $n.Dispose()'
            env = dict(os.environ, APRS_NOTICE_TITLE=title, APRS_NOTICE_BODY=body)
            encoded = base64.b64encode(script.encode("utf-16le")).decode()
            subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                           env=env, check=True, timeout=12, capture_output=True, creationflags=0x08000000)
        else:
            raise RuntimeError("Desktop notifications unavailable on this platform")


class Notifier:
    """Network delivery never blocks the APRS feed. Failed channels retry independently."""
    def __init__(self, cfg, report):
        self.cfg, self.report = cfg, report
        self.jobs = queue.Queue(maxsize=100)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True, name="notifications")

    def submit(self, event):
        if not channels(self.cfg):
            self.report("No notification channels enabled; event recorded locally")
        for channel in channels(self.cfg):
            try:
                self.jobs.put_nowait((channel, event, 0))
            except queue.Full:
                self.report(f"Notification queue full; {channel} alert was not delivered")

    def run(self):
        while not self.stop.is_set():
            try:
                channel, event, attempt = self.jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                deliver(channel, self.cfg, event)
                self.report(f"{channel.capitalize()} delivered: {event['title']}")
            except Exception as error:
                # Exception text may contain a secret webhook URL; do not log it.
                self.report(f"{channel.capitalize()} delivery failed ({type(error).__name__}), attempt {attempt + 1}/3")
                if attempt < 2 and not self.stop.wait(2 ** attempt):
                    try:
                        self.jobs.put_nowait((channel, event, attempt + 1))
                    except queue.Full:
                        self.report("Notification retry dropped: queue full")
            finally:
                self.jobs.task_done()
