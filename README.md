# DigiMon

**Keep an eye on your APRS digipeater and get an alert when it goes quiet.**

DigiMon is a small desktop and background app that watches one station on APRS-IS, the internet feed for the Automatic Packet Reporting System (APRS). A digipeater relays APRS packets over radio; DigiMon looks for its own packets or evidence that it has relayed someone else's.

Choose the digipeater you want to monitor. DigiMon alerts you after **20 minutes** without a matching packet by default, and you can change the waiting time and notification methods. When the station is seen again, DigiMon sends a recovery notice.

You can:

- See the station's last observed time, last matching packet and recent activity.
- Receive desktop, email or webhook alerts, in any combination.
- Get separate alerts if the APRS feed fails and when it recovers.
- Run it in a desktop window or as a background service.

DigiMon is receive-only: it does not transmit APRS packets or control your radio. You do not need a radio connected to the computer, an APRS passcode or an API key. You do need an internet connection and your own APRS login callsign.

> An alert means “not seen on APRS-IS”, rather than a confirmed radio fault. Radio coverage and the stations forwarding packets to the internet affect what DigiMon can see.

## Contents

- [Get started](#get-started)
- [How monitoring works](#how-monitoring-works)
- [Set up notifications](#set-up-notifications)
- [Run without the desktop window](#run-without-the-desktop-window)
- [Run automatically as a service](#run-automatically-as-a-service)
- [Settings and saved data](#settings-and-saved-data)
- [Troubleshooting](#troubleshooting)
- [For developers](#for-developers)

## Get started

### 1. Download and open the app folder

Download and extract this project, or clone the repository. Open a terminal in the folder containing `README.md` and the `digimon` directory. The commands below run from that folder.

DigiMon needs **Python 3.10 or later**. Its monitoring engine uses only Python's standard library, so no extra Python packages are needed to run from source. The desktop window also needs **Tk**, Python's GUI toolkit.

### 2. Launch DigiMon

#### Windows

Install Python 3.10 or later with Tcl/Tk support. In PowerShell, run:

```powershell
py --version
py -m digimon
```

If your installation provides `python` instead of `py`, use `python` in these commands.

#### Linux

On Debian or Ubuntu, install Python, Tk and the desktop notification helper:

```sh
sudo apt install python3 python3-tk libnotify-bin
python3 --version
python3 -m digimon
```

On other distributions, install the equivalent packages. Tk is only needed for the desktop window; `notify-send` is only needed for desktop alerts.

#### macOS

Install Python 3.10 or later with Tk support, then run:

```sh
python3 --version
python3 -m tkinter
python3 -m digimon
```

The Tk command opens a small test window. Close it before continuing.

### 3. Choose what to monitor

In the **Station & feed** tab:

| Setting | What to enter |
| --- | --- |
| **Digipeater callsign** | Enter the callsign of the station you want to watch, including its SSID if it uses one. |
| **Your APRS login callsign** | Your own callsign, with a distinct SSID suffix for this app. Do not reuse the login of another APRS client connected at the same time. |
| **Alert after (minutes)** | How long the station can go unseen before an alert. The default is `20`. |
| **Count as seen** | Start with `both`, or choose a more specific match mode below. |
| **APRS-IS server / Server port** | Leave `rotate.aprs2.net` and `14580` unless you need a different server. |
| **Repeat alert (minutes; 0 = off)** | Leave `0` for one absence alert per incident, or set a reminder interval. |
| **Feed failure alert (minutes)** | How long a disconnected feed can remain unavailable before a separate alert. The default is `5`. |

Both callsign fields start blank so you can enter your digipeater and your own login. DigiMon uses a receive-only login (`pass -1`); there is no APRS passcode to enter.

### 4. Test your alerts and start

1. Open **Notifications** and enable the delivery methods you want. Desktop notifications are enabled by default.
2. Fill in the details for email or webhooks if you use them; see [notification setup](#set-up-notifications).
3. Click **Test alerts** and check that each enabled method works.
4. Click **Save settings**, then **Start monitoring**.

The status panel shows the current state and last observed time. The **Activity** tab shows connection events and notification results. It is normal to see **Observing** while waiting for the first matching packet.

**Keep the window open to keep monitoring.** Closing a monitor started by the GUI stops it. For unattended use, follow the [service setup](#run-automatically-as-a-service).

## How monitoring works

DigiMon connects to APRS-IS, requests a filtered feed for your chosen callsign, and checks incoming packet headers. Every matching packet updates the last-seen time and resets the absence timer.

### What counts as “seen”?

| Mode | Matching activity | When to use it |
| --- | --- | --- |
| `both` (default) | A packet sent by the station, or a packet relayed through its already-used radio path. | You want to know whether the station is showing any matching activity. |
| `beacon` | A packet originating from the station, including status and telemetry packets. | You want to watch the station's own transmissions. This mode is not limited to position beacons. |
| `digipeated` | A packet whose used radio relay path includes the station. | You specifically want evidence of relaying. |

A requested but unused relay hop does not count. Neither does a station listed only as the receiving internet gateway (IGate) after the APRS `q` construct. SSIDs match exactly, except that a bare callsign and its `-0` form are treated as equivalent.

### When alerts happen

With the default settings:

- **Station absence:** after 20 continuous minutes of observation without a match, DigiMon sends an alert. This also applies if the station has never been seen since startup.
- **Station recovery:** the next matching packet closes that absence incident and sends a recovery notice.
- **Feed failure:** if the connection breaks, station absence alerts pause and DigiMon tries to reconnect. After 5 minutes disconnected, it sends a separate feed alert.
- **Feed recovery:** if a feed alert was sent, reconnecting sends a recovery notice. Every reconnection starts a fresh 20-minute observation window before an absence alert can be raised.

Observation begins when the server acknowledges the login. A feed that sends no data for 120 seconds is treated as disconnected; this is separate from the station's absence timer.

For example, if the last matching packet arrives at 12:00 and the feed stays connected, the default absence alert is due around 12:20. If the feed drops and reconnects at 12:15, DigiMon waits through a new observation window, until around 12:35, before reporting an absence.

The last-seen time and open station absence incident are saved across restarts. Restarting does not send another initial alert for an already-open incident; a new matching packet still produces recovery. Optional reminders are off by default.

### What the results can tell you

DigiMon records when **this app receives** a matching packet. It does not look up historical APRS traffic, and it cannot monitor while the computer is asleep or off.

A station can be working on radio without appearing in APRS-IS, depending on nearby IGates, radio propagation, duplicate handling and relay path tracing. A station's internet-originated packet also does not prove its radio transmitter is working. Choose `digipeated` when evidence of relaying matters, and treat alerts as a reason to investigate.

## Set up notifications

Enable any combination of channels in **Notifications**. Test them before relying on unattended monitoring.

### Desktop

Desktop alerts need a logged-in graphical session:

- **Windows:** a notification-area balloon.
- **Linux:** `notify-send` and an available desktop notification bus.
- **macOS:** system notifications through AppleScript.

Your operating system's notification settings may suppress them. Windows services and macOS boot daemons cannot show desktop alerts; use email or a webhook for those setups.

### Email

Enter your provider's SMTP settings:

| Field | What it means |
| --- | --- |
| SMTP host | Your outgoing mail server. |
| SMTP port / encryption | Commonly `587` with `starttls`, or `465` with `ssl`; use your provider's settings. |
| SMTP username | The account used to send mail. |
| Password environment variable | The **name** of the variable holding your password, not the password itself. Default: `DIGIMON_SMTP_PASSWORD`. |
| From address | The sender address allowed by your provider. |
| To addresses | One or more recipients, separated by commas. |

Use an app password if your provider requires one. DigiMon supports SMTP password authentication over TLS; an OAuth-only provider needs a suitable SMTP relay or a different notification channel.

Set the password before launching DigiMon from the same terminal. These examples prompt for it without putting it directly in shell history.

**Windows PowerShell:**

```powershell
$secret = Read-Host 'SMTP app password' -AsSecureString
$env:DIGIMON_SMTP_PASSWORD = [System.Net.NetworkCredential]::new('', $secret).Password
py -m digimon
```

**Linux or macOS, using Bash:**

```bash
read -r -s -p 'SMTP app password: ' DIGIMON_SMTP_PASSWORD
export DIGIMON_SMTP_PASSWORD
python3 -m digimon
```

Type the password and press Enter when prompted. On macOS, run `bash` first if your terminal uses another shell. These variables apply to this shell session and its child processes; a background service needs its own password configuration.

### Webhook

Enable **Webhook alerts**, enter an HTTPS webhook URL and choose its format:

- `discord`: a Discord webhook message, with mentions disabled.
- `slack`: a Slack webhook message.
- `generic`: JSON containing `kind`, `title`, `message`, `time` (Unix timestamp) and `callsign`.

Webhook URLs can contain credentials and are saved in the configuration file. Keep that file private. A successful HTTP response means the endpoint accepted the request, not that someone has read the alert.

### Delivery and retries

During monitoring, each failed channel gets up to three delivery attempts in total, and other channels are still attempted. Results appear in **Activity** and `monitor.log`. Pending deliveries are held in memory, so stopping or crashing the app can lose them. Delivery is best-effort; using more than one channel can help.

## Run without the desktop window

Use command-line mode for a headless computer or a process managed by your operating system. In the commands below, Windows users can replace `python3` with `py`.

If you have not saved settings through the GUI, create a configuration first:

```sh
python3 -m digimon init
```

This prints the new file's location. Edit it to set the digipeater callsign, your APRS login callsign and notification channels before continuing. The command refuses to overwrite an existing configuration. [config.example.json](config.example.json) shows all supported settings; both blank callsign fields must be filled in before use. On a headless machine, set `desktop` to `false` and configure email and/or a webhook.

```sh
python3 -m digimon test-alert
python3 -m digimon run
```

`run` keeps running in the terminal until you press Ctrl+C or it receives a termination signal. It does not install a service or detach itself into the background.

From another terminal, check the saved status:

```sh
python3 -m digimon status
```

| Command | Purpose |
| --- | --- |
| `gui` (or no command) | Open the desktop window. |
| `init` | Create a default configuration if one does not already exist. |
| `run` | Run the monitor without a GUI. |
| `status` | Print the last saved status and whether a monitor is running. |
| `test-alert` | Try each enabled channel once; exit with a failure status if any channel fails. |

All commands accept `--config` and `--data-dir`, for example:

```sh
python3 -m digimon run --config /absolute/path/config.json --data-dir /absolute/path/data
```

Use the same configuration and data directory when switching between the GUI and a service. The GUI can display a running service's status, but its **Stop** button only stops a monitor it started itself. Stop the service before editing settings, then restart it to load your changes.

## Run automatically as a service

Configure and test DigiMon first, then stop any monitor running in the GUI. Installing or extracting the app does not install a service automatically.

The templates in [services](services) use the extracted source folder. Replace their placeholder paths with absolute paths on your computer, and ensure the service account can read the app and write its configuration/data location.

### Linux: systemd user service

1. Create `~/.config/systemd/user/` if needed, and copy [services/digimon.service](services/digimon.service) into it.
2. Edit `WorkingDirectory` to your app folder. Check `ExecStart`: Python must be 3.10 or later, and the supplied configuration path assumes `~/.config/digimon/config.json`. Quote paths containing spaces.
3. For email, create `~/.config/digimon/secrets.env` containing `DIGIMON_SMTP_PASSWORD=your-app-password`. Protect it with `chmod 600 ~/.config/digimon/secrets.env`. Use systemd environment-file quoting for special characters.
4. Enable and start the service:

```sh
systemctl --user daemon-reload
systemctl --user enable --now digimon.service
systemctl --user status digimon.service
```

To keep it running after logout and start the user manager at boot:

```sh
loginctl enable-linger "$USER"
```

Your system may require administrator authorization. Desktop alerts still need your user's desktop notification bus; test them from the service. Email and webhooks work without a desktop session.

Useful service commands:

```sh
# Stop before changing app settings
systemctl --user stop digimon.service

# Start again or reload changed app settings
systemctl --user restart digimon.service

# Stop and disable automatic startup
systemctl --user disable --now digimon.service

# Inspect service-level errors
journalctl --user -u digimon.service
```

### macOS: launchd agent

For a background process that starts when you log in:

1. Edit every placeholder in [services/org.digimon.monitor.plist](services/org.digimon.monitor.plist), including the absolute Python executable, application folder and configuration path.
2. Copy it into `~/Library/LaunchAgents/`, creating the directory if necessary.
3. For email, supply the password variable through a protected `EnvironmentVariables` dictionary in the plist. Jobs do not automatically inherit your terminal's environment.
4. Load it:

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/org.digimon.monitor.plist"
```

Stop and unload it before editing settings:

```sh
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/org.digimon.monitor.plist"
```

Run the bootstrap command again to start it. This LaunchAgent starts at login. Pre-login monitoring needs an administrator-configured LaunchDaemon with an explicit `UserName`, accessible paths and email/webhook notifications.

### Windows: WinSW service

The service template uses the third-party [WinSW service wrapper](https://github.com/winsw/winsw), which is not bundled with DigiMon.

1. Put the app in `C:\DigiMon\app` and your tested configuration at `C:\DigiMon\config.json`. Disable desktop notifications in that configuration.
2. Edit the Python executable path in [services/DigiMon.xml](services/DigiMon.xml). Place that XML and a compatible WinSW executable together in `C:\DigiMon`, named `DigiMon.xml` and `DigiMon.exe`.
3. For email, supply the password to the service environment, for example with a protected WinSW `<env name="DIGIMON_SMTP_PASSWORD" value="..."/>` setting. XML-escape special characters and restrict access to credential files.
4. Open PowerShell as Administrator in `C:\DigiMon` and run:

```powershell
.\DigiMon.exe install
.\DigiMon.exe start
```

Ensure the service account can read the app and write `C:\DigiMon\data`. To view it in the GUI, run this from the app folder with an account that can access those files:

```powershell
py -m digimon gui --config C:\DigiMon\config.json --data-dir C:\DigiMon\data
```

Stop it before changing settings, then start it again:

```powershell
.\DigiMon.exe stop
.\DigiMon.exe start
```

To remove the service, stop it and run `.\DigiMon.exe uninstall` from the Administrator PowerShell window.

## Settings and saved data

Default configuration locations:

| Platform | Configuration file |
| --- | --- |
| Windows | `%LOCALAPPDATA%\DigiMon\config.json` |
| Linux | `~/.config/digimon/config.json` (honours `XDG_CONFIG_HOME`) |
| macOS | `~/Library/Application Support/DigiMon/config.json` |

By default, a `data` directory beside the configuration contains:

- `status.json`: the saved status, last matching packet and station incident state.
- A lock file to prevent duplicate monitors using the same data directory.
- `monitor.log` and up to three rotated backups, about 1 MB each.

Keep the same data directory to preserve monitoring history when switching between the desktop app and a service. Stop monitoring before moving files or editing configuration. Newly saved configuration/state files use owner-only permissions on POSIX systems; on Windows, use an account-private folder with suitable filesystem permissions.

The app is **DigiMon**. Its Python module and terminal command use the lowercase spelling `digimon`.

### Upgrading from the earlier name

Launch the updated app with `python3 -m digimon` (Windows: `py -m digimon`). If you installed the earlier package with pip, uninstall `digimon-aprs`, then install this version from the project folder with `python3 -m pip install .`. The installed terminal command is `digimon`.

If there is no configuration in the new DigiMon location, the app automatically uses an existing configuration in the old `aprs-watch` (Linux) or `APRSWatch` (Windows/macOS) folder. It uses the same data folder there, preserving last-seen information and open incidents. An explicit `--config` path takes precedence. Saved email settings still use whichever password environment variable they name; new configurations use `DIGIMON_SMTP_PASSWORD`.

To move everything to the new location, stop the monitor and any old service first, then move the old configuration folder, including `data` and any `secrets.env`, to the DigiMon location in the table above. If a DigiMon configuration already exists, back up both folders and choose which settings to keep rather than overwriting them. Preserve the privacy of credential files and update any custom configuration/data paths.

Existing services are not renamed automatically. Stop and disable/remove the old service before installing the new template:

- **Linux:** disable `aprs-watch.service` with `systemctl --user disable --now aprs-watch.service`, then follow the `digimon.service` instructions above.
- **macOS:** unload `org.aprswatch.monitor.plist` using `launchctl bootout`, remove the old plist from `~/Library/LaunchAgents/`, then install `org.digimon.monitor.plist`.
- **Windows:** use the old WinSW wrapper to stop and uninstall the `APRSWatch` service, then install the `DigiMon` service.

The new templates use the new configuration locations. Move your existing settings there first or edit the template to point at the existing configuration and data. If you keep a saved email setting that names `APRS_WATCH_SMTP_PASSWORD`, supply that variable to the service too. Do not run both the old and new services.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `py` or `python3` is not found | Check that Python 3.10+ is installed and available in your terminal. On Windows, try `python` if `py` is unavailable. |
| `No module named digimon` | Run the command from the extracted project folder containing `digimon`. |
| Tk / `tkinter` is missing | Install Python's Tk support. Check with `python3 -m tkinter` (Windows: `py -m tkinter`). A headless system can use `run` without Tk. |
| “Enter a valid callsign” | Fill in **Digipeater callsign** with the station you want to monitor. |
| “Enter a valid login” | Fill in **Your APRS login callsign**. The default and example configurations intentionally leave it blank. |
| **Observing** or “Never observed” | The app is waiting for matching traffic. Check the target callsign, SSID and match mode. It does not retrieve past packets. |
| **Feed unavailable** | Check internet access and the configured APRS-IS host/port. DigiMon retries automatically; **Activity** and `monitor.log` show connection errors. |
| No desktop alert | Check OS notification settings, the logged-in desktop session and, on Linux, `notify-send`. Use email/webhooks for unattended services. |
| Email test fails | Check SMTP details, sender/recipient addresses and whether the password variable is available to the process that launched DigiMon. |
| Alerts work in the GUI but not the service | Check the service's configuration path, account permissions and password environment. A service does not necessarily inherit your terminal's settings. |
| Settings cannot be saved or a monitor is already running | Stop the existing monitor or service first. The GUI cannot stop a service it did not start. |

## For developers

### Run the tests

From the project folder:

```sh
python3 -m unittest discover -s tests -v
```

On Windows, replace `python3` with `py`. The suite covers packet matching, alert timing, reconnection windows, saved state, channel selection, mocked notification delivery, retries and locking. It also uses a local TCP server to exercise login, absence and recovery, so loopback socket access is needed.

Automated tests do not verify delivery to your real email account or webhook, live APRS traffic, or service behaviour on every platform. Test those with your own configuration.

### Build a portable Python archive

```sh
python3 build.py
python3 dist/DigiMon.pyz
```

The build creates `dist/DigiMon.pyz`, which you can launch from any folder using its path. On Windows, use `py build.py` and `py dist\DigiMon.pyz`. The archive supports the same commands and options as `python3 -m digimon`.

Python and the relevant GUI/notification components are still required. This archive is not a standalone executable or signed installer.

### Code layout

| File | Responsibility |
| --- | --- |
| `digimon/core.py` | Packet matching and alert state. |
| `digimon/runtime.py` | APRS connection, reconnects, saved status, locking and logs. |
| `digimon/notify.py` | Desktop, email and webhook delivery. |
| `digimon/gui.py` | Desktop interface. |
| `digimon/config.py` | Defaults and settings validation. |
| `digimon/__main__.py` | Command-line entry point. |
| `services/` | Background service templates. |
| `tests/` | Automated tests. |
