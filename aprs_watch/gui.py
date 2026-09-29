import copy
import json
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .config import DEFAULT, validate, write_json
from .core import utc
from .notify import channels, deliver
from .runtime import Worker, is_running, load_state

BG, PANEL, TEXT, MUTED, ACCENT = "#101b2b", "#19283d", "#edf3fa", "#9fb2c9", "#6bdfbd"


class App:
    def __init__(self, root, config_path, folder):
        self.root, self.path, self.folder = root, Path(config_path), Path(folder)
        self.worker = None
        self.testing = False
        self.test_results = None
        self.vars = {}
        self.rendered_log = ""
        root.title("DigiMon · Digipeater monitor")
        root.geometry("960x790")
        root.minsize(800, 700)
        root.configure(bg=BG)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Arial", 11))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TButton", font=("Arial", 10), padding=(14, 8))
        style.configure("TCheckbutton", background=BG, foreground=TEXT, font=("Arial", 10))
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 9))
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)
        ttk.Label(frame, text="DIGIMON", foreground=ACCENT, font=("Arial", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="Keep an eye on your digipeater.", font=("Arial", 23, "bold")).grid(row=1, column=0, sticky="w", pady=(7, 4))
        ttk.Label(frame, text="Live APRS-IS monitoring  /  Receive only", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        card = tk.Frame(frame, bg=PANEL, padx=20, pady=16)
        card.grid(row=3, column=0, sticky="ew", pady=20)
        self.status = tk.Label(card, text="●  Ready to monitor", bg=PANEL, fg=ACCENT, font=("Arial", 20, "bold"))
        self.status.pack(anchor="w")
        self.detail = tk.Label(card, text="Enter your APRS login callsign below, then start monitoring.", bg=PANEL, fg=MUTED, font=("Arial", 10), anchor="w", justify="left")
        self.detail.pack(anchor="w", pady=(8, 0))
        notebook = ttk.Notebook(frame)
        notebook.grid(row=4, column=0, sticky="nsew")
        station = self.scroll_tab(notebook, "Station & feed")
        notices = self.scroll_tab(notebook, "Notifications")
        history = ttk.Frame(notebook, padding=12)
        notebook.add(history, text="Activity")
        self.field(station, 0, "Digipeater callsign", "callsign")
        self.field(station, 1, "Your APRS login callsign", "login")
        self.field(station, 2, "Alert after (minutes)", "timeout_minutes")
        self.field(station, 3, "Count as seen", "match", ("both", "beacon", "digipeated"))
        self.field(station, 4, "APRS-IS server", "host")
        self.field(station, 5, "Server port", "port")
        self.field(station, 6, "Repeat alert (minutes; 0 = off)", "repeat_minutes")
        self.field(station, 7, "Feed failure alert (minutes)", "feed_alert_minutes")
        ttk.Label(station, text="“Both” counts own packets and used relay paths.\nA feed outage pauses station alerts; reconnecting starts a fresh observation window.\nUse your own callsign with a distinct APRS-IS SSID for this monitor.", style="Muted.TLabel", wraplength=780).grid(row=8, column=0, columnspan=2, sticky="w", pady=16)
        self.check(notices, 0, "Desktop notifications (requires a logged-in desktop session)", "desktop")
        self.check(notices, 1, "Webhook alerts", "webhook.enabled")
        self.field(notices, 2, "Webhook URL", "webhook.url", secret=True)
        self.field(notices, 3, "Webhook format", "webhook.format", ("discord", "slack", "generic"))
        self.check(notices, 4, "Email alerts", "email.enabled")
        self.field(notices, 5, "SMTP host", "email.host")
        self.field(notices, 6, "SMTP port", "email.port")
        self.field(notices, 7, "SMTP encryption", "email.security", ("starttls", "ssl"))
        self.field(notices, 8, "SMTP username", "email.username")
        self.field(notices, 9, "Password environment variable", "email.password_env")
        self.field(notices, 10, "From address", "email.from")
        self.field(notices, 11, "To addresses (comma separated)", "email.to")
        ttk.Label(notices, text="Enable any combination. SMTP passwords are read from the named environment variable.\nUse Test alerts to check delivery. Webhook URLs are saved in the local configuration.", style="Muted.TLabel", wraplength=790).grid(row=12, column=0, columnspan=2, sticky="w", pady=8)
        self.log = tk.Text(history, bg=PANEL, fg=TEXT, relief="flat", font=("Courier", 10), wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)
        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, sticky="ew", pady=(16, 8))
        self.start_button = ttk.Button(actions, text="Start monitoring", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(actions, text="Save settings", command=self.save)
        self.save_button.pack(side="right")
        self.test_button = ttk.Button(actions, text="Test alerts", command=self.test)
        self.test_button.pack(side="right", padx=8)
        self.footer = ttk.Label(frame, text="Not seen on APRS-IS does not necessarily mean offline on RF.", style="Muted.TLabel")
        self.footer.grid(row=6, column=0, sticky="w")
        self.cfg = copy.deepcopy(DEFAULT)
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for key, value in data.items():
                    if key in self.cfg and isinstance(self.cfg[key], dict):
                        self.cfg[key].update(value)
                    else:
                        self.cfg[key] = value
            except (ValueError, OSError, TypeError) as error:
                messagebox.showerror("Configuration could not be loaded", str(error))
        for key, variable in self.vars.items():
            parts = key.split(".")
            variable.set(self.cfg[parts[0]][parts[1]] if len(parts) > 1 else self.cfg[key])
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def scroll_tab(self, notebook, title):
        wrapper = ttk.Frame(notebook)
        notebook.add(wrapper, text=title)
        canvas = tk.Canvas(wrapper, bg=BG, highlightthickness=0, height=320)
        bar = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=bar.set)
        body = ttk.Frame(canvas, padding=16)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        return body

    def field(self, parent, row, label, key, choices=None, secret=False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 20), pady=4)
        variable = tk.StringVar()
        self.vars[key] = variable
        widget = ttk.Combobox(parent, textvariable=variable, values=choices, state="readonly") if choices else ttk.Entry(parent, textvariable=variable, show="•" if secret else "")
        widget.grid(row=row, column=1, sticky="ew", pady=4)
        parent.columnconfigure(1, weight=1)

    def check(self, parent, row, label, key):
        variable = tk.BooleanVar()
        self.vars[key] = variable
        ttk.Checkbutton(parent, text=label, variable=variable).grid(row=row, column=0, columnspan=2, sticky="w", pady=5)

    def collect(self):
        cfg = copy.deepcopy(self.cfg)
        for key, variable in self.vars.items():
            parts = key.split(".")
            if len(parts) > 1:
                cfg[parts[0]][parts[1]] = variable.get()
            else:
                cfg[key] = variable.get()
        return validate(cfg)

    def save(self):
        try:
            if is_running(self.folder):
                raise ValueError("Stop the monitor or background service before saving settings.")
            cfg = self.collect()
            write_json(self.path, cfg)
            self.cfg = cfg
            self.footer.configure(text=f"Settings saved: {self.path}")
            return True
        except (ValueError, OSError, TypeError) as error:
            messagebox.showerror("Check your settings", str(error))
            return False

    def start(self):
        if self.save():
            self.worker = Worker(self.cfg, self.folder)
            self.worker.start()

    def stop(self):
        if self.worker:
            self.worker.stop.set()
            self.footer.configure(text="Stopping monitor…")

    def test(self):
        try:
            cfg = self.collect()
            selected = channels(cfg)
            if not selected:
                raise ValueError("Enable at least one notification channel")
        except (ValueError, TypeError) as error:
            messagebox.showerror("Check your settings", str(error))
            return
        self.testing = True
        self.test_button.configure(state="disabled")
        def send():
            results = []
            event = {"kind": "test", "title": f"DigiMon test · {cfg['callsign']}", "message": "Your selected notification channel is working.", "time": time.time(), "callsign": cfg["callsign"]}
            for name in selected:
                try:
                    deliver(name, cfg, event)
                    results.append(f"{name}: delivered")
                except Exception as error:
                    results.append(f"{name}: failed ({type(error).__name__}); check settings and credentials")
            self.test_results = "\n".join(results)
        threading.Thread(target=send, daemon=True).start()

    def refresh(self):
        running = is_running(self.folder)
        own = bool(self.worker and self.worker.thread.is_alive())
        self.start_button.configure(state="disabled" if running or own else "normal")
        self.stop_button.configure(state="normal" if own else "disabled")
        self.save_button.configure(state="disabled" if running or own else "normal")
        data = load_state(self.folder)
        if data:
            state = data.get("status", "Unknown") if running else "Stopped"
            if running and time.time() - data.get("updated", 0) > 30:
                state = "Monitor not responding"
            self.status.configure(text=f"●  {data.get('callsign', '')}  ·  {state}", fg="#ffbb79" if state in ("Not seen", "Feed unavailable", "Monitor not responding") else ACCENT)
            self.detail.configure(text=f"Last observed: {utc(data.get('last_seen'))}  |  {data.get('evidence') or 'No packets yet'}\n" + ("Viewing background service · stop it before changing settings" if running and not own else "Monitoring in this window" if own else "Start monitoring to resume observation"))
            content = "\n".join(f"{utc(item['time'])}  {item['message']}" for item in data.get("messages", []))
            if data.get("last_packet"):
                content += "\n\nLast matching packet:\n" + data["last_packet"]
            if content != self.rendered_log:
                self.log.configure(state="normal")
                self.log.delete("1.0", "end")
                self.log.insert("end", content)
                self.log.configure(state="disabled")
                self.log.see("end")
                self.rendered_log = content
        if self.worker and not own and self.worker.error:
            messagebox.showerror("Monitor stopped", self.worker.error)
            self.worker.error = None
        if self.test_results is not None:
            messagebox.showinfo("Test alert results", self.test_results)
            self.test_results = None
            self.testing = False
            self.test_button.configure(state="normal")
        self.root.after(1000, self.refresh)

    def close(self):
        if self.worker and self.worker.thread.is_alive():
            self.stop()
            self.root.after(200, self.close)
        else:
            self.root.destroy()


def launch(config_path, folder):
    root = tk.Tk()
    App(root, config_path, folder)
    root.mainloop()
