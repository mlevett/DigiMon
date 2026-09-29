# DigiMon

The Python module (`aprs_watch`), configuration locations and service identifiers retain their original names so existing settings continue to work. The application and GitHub project are named **DigiMon**.

A small, receive-only digipeater monitor for **MB7UPH**, with a **20-minute** absence threshold. Both settings are editable. It runs as a desktop application or a background process supervised by your operating system.

Enable **desktop, email and webhook** notifications independently, in any combination. It sends an absence alert, a recovery notice when a matching packet returns, and separate feed outage/recovery notices. Reminders are optional and disabled by default.

## Start on Linux

Requires Python 3.10 or later. The monitoring engine uses only Python's standard library. The GUI additionally needs Tk; desktop alerts need `notify-send`.

On Debian/Ubuntu:

```sh
sudo apt install python3 python3-tk libnotify-bin
```

Extract the application, open a terminal in the `DigiMon` folder, and run:

```sh
python3 -m aprs_watch
```

Alternatively, build a single-file Python application with `python3 build.py`. The resulting `dist/DigiMon.pyz` can be launched from any folder with `python3 /path/to/DigiMon.pyz` (Windows: `py C:\path\to\DigiMon.pyz`). It supports the same commands and options. Python and the platform's GUI/notification components are still required. The service templates below use the extracted source folder.

1. Leave **MB7UPH** and **20 minutes** selected, or change them.
2. Enter your own APRS login callsign with a distinct SSID for this application. The connection is receive-only and uses `pass -1`; no APRS passcode or API key is required. Do not reuse the login of a simultaneously connected APRS client.
3. Open **Notifications** and select any combination of delivery channels.
4. Choose **Test alerts**, then **Save settings** and **Start monitoring**.

Closing a GUI-owned monitor stops it. To keep it running independently, use the service instructions below. Opening the GUI while the service runs shows its status using the same configuration/data folder. Stop the service before changing its settings. The GUI's Stop button only controls a monitor it started.

Installing this package does not contact a station or install a service. The default login is intentionally blank; enter yours before starting.

## Alerts and what “seen” means

- **Both** (default): a packet originating from MB7UPH, or MB7UPH appearing in the already-used RF relay path.
- **Beacon**: packets originating from the station, including status/telemetry; this is not restricted to position beacons.
- **Digipeated**: only packets relayed through the station's used path.
- Unused requested hops and the receiving IGate after the APRS q construct do not count as a relay. Callsign SSIDs are exact, except bare callsigns and `-0` are treated as equivalent.
- The absence timer begins once the server acknowledges the connection. A station never seen since startup still triggers an alert after 20 minutes of observation.
- On a broken or silent feed, station alerts pause. A silent feed is disconnected after 120 seconds without any received data. A separate feed-failure alert follows after 5 minutes disconnected; that delay is configurable.
- Every reconnection starts a fresh, continuous 20-minute observation window. Saved last-seen time and open incidents survive restarts. An open absence incident will not generate another initial alert after restart; its next matching packet generates recovery.
- Last-seen timestamps use the time this application receives a matching packet. There is no historical APRS lookup and no monitoring while the computer is asleep or off.

APRS-IS visibility depends on nearby IGates, propagation, packet duplication, and relay path tracing. A station may work on RF without appearing in this feed. Conversely, an internet-originated station beacon proves APRS activity, not that its RF transmitter is healthy. Use **Digipeated** when relay evidence is essential. Lost feed coverage is reported as unknown, rather than proof that MB7UPH is down.

## Notification settings

### Email

Enter the SMTP host, port, encryption (`starttls`, typically port 587; or `ssl`, typically 465), username, sender and recipient addresses. Multiple recipients can be comma-separated. Use your provider's app password where required.

Passwords are read from the environment variable named in settings; the default is `APRS_WATCH_SMTP_PASSWORD`. For an interactive Linux/macOS launch without writing the password in shell history:

```sh
read -r -s APRS_WATCH_SMTP_PASSWORD
export APRS_WATCH_SMTP_PASSWORD
python3 -m aprs_watch
```

The `read` command waits for you to enter the password and press Enter. In PowerShell:

```powershell
$secret = Read-Host 'SMTP app password' -AsSecureString
$env:APRS_WATCH_SMTP_PASSWORD = [System.Net.NetworkCredential]::new('', $secret).Password
py -m aprs_watch
```

SMTP supports password authentication over TLS; OAuth-only mail providers require a suitable SMTP relay or another channel. Credentials must also be available to the service account when running in the background.

### Webhook

Enable webhook alerts, enter an HTTPS endpoint and choose **discord**, **slack**, or **generic**. Generic sends JSON containing `kind`, `title`, `message`, `time` (Unix timestamp), and `callsign`. Discord mentions are disabled. A successful HTTP response confirms endpoint acceptance, not that a person saw the alert.

Webhook URLs may contain credentials and are stored in the local config file. Keep that file private. On POSIX systems newly saved config/state files use owner-only permissions. On Windows use an account-private folder with appropriate filesystem permissions.

### Desktop

Linux uses `notify-send`, macOS uses the system notification mechanism through AppleScript, and Windows uses a notification-area balloon. OS notification settings may suppress presentation.

A visible logged-in desktop session is required. A Windows service or macOS boot daemon cannot display desktop alerts. For an unattended/headless system, select email and/or webhook. Linux user services can display alerts when their user desktop's notification bus is available; test after installing the service. Enable multiple channels for useful redundancy.

Each failed channel receives up to three delivery attempts; other channels are still attempted. Delivery results are visible under **Activity** and in `monitor.log`. Pending notifications are in memory, so stopping or crashing the process can lose pending delivery. Alert transport is best-effort; test the configured channels before relying on them.

## Background mode and status

From the application folder:

```sh
python3 -m aprs_watch init
python3 -m aprs_watch run
python3 -m aprs_watch status
python3 -m aprs_watch test-alert
```

`init` creates a default configuration only if one does not exist. Configure it before `run`. `run` stays in the foreground for supervision by a service manager and exits on Ctrl+C or a termination signal. `status` prints the last snapshot plus whether the monitor is running. `test-alert` contacts every enabled channel and returns a failing exit status if any channel fails.

All commands accept `--config /absolute/path/config.json` and `--data-dir /absolute/path/data`. The default data directory is `data` beside the configuration.

Default configuration locations:

| Platform | Location |
| --- | --- |
| Linux | `~/.config/aprs-watch/config.json` (honours `XDG_CONFIG_HOME`) |
| macOS | `~/Library/Application Support/APRSWatch/config.json` |
| Windows | `%LOCALAPPDATA%\APRSWatch\config.json` |

The data folder contains `status.json`, a lock file preventing duplicate monitors using that folder, and up to four 1 MB rotating log files. Keep the same data folder across GUI/service use. Stop both before moving the app or changing configuration.

## Linux service (recommended)

Configure and test the application first, then stop the GUI-owned monitor.

1. Copy `services/aprs-watch.service` to `~/.config/systemd/user/aprs-watch.service` (create the directory if necessary).
2. Edit `WorkingDirectory` to the absolute extracted application folder. Edit `ExecStart` if your Python executable or configuration location differs. Python must be 3.10+. Quote paths containing spaces. The supplied config path assumes the normal `~/.config` location.
3. For email, create `~/.config/aprs-watch/secrets.env` containing `APRS_WATCH_SMTP_PASSWORD=your-app-password`. Protect it with `chmod 600 ~/.config/aprs-watch/secrets.env`. Use systemd environment-file quoting if the value contains spaces or special characters.
4. Enable the user service:

```sh
systemctl --user daemon-reload
systemctl --user enable --now aprs-watch.service
systemctl --user status aprs-watch.service
```

To keep it running after logout and start the user manager at boot:

```sh
loginctl enable-linger "$USER"
```

Your system may require administrator authorization for lingering. A desktop is still required for desktop notifications; email/webhooks work without one. Stop or remove the service with:

```sh
systemctl --user stop aprs-watch.service
systemctl --user disable --now aprs-watch.service
```

After configuration changes, restart with `systemctl --user restart aprs-watch.service`. To inspect service-level failures use `journalctl --user -u aprs-watch.service`; normal activity/delivery logs live in the application's data folder.

## macOS

Install Python 3.10+ with Tk support, then run `python3 -m aprs_watch` from the app folder. `python3 -m tkinter` checks that Tk is usable.

For a persistent background process at login, edit every placeholder in `services/org.aprswatch.monitor.plist` and copy it to `~/Library/LaunchAgents/`. Use an absolute Python executable, application folder and configuration file path. Load it with:

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/org.aprswatch.monitor.plist"
```

Unload before editing configuration:

```sh
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/org.aprswatch.monitor.plist"
```

If using email, supply the password variable to launchd via a protected `EnvironmentVariables` dictionary in the plist; shell environment variables are not automatically inherited by jobs. A LaunchAgent starts at login. For pre-login operation an administrator can install an adapted LaunchDaemon with an explicit `UserName`, service-accessible paths, and email/webhook notifications.

## Windows

Install Python 3.10+ including Tcl/Tk. From the extracted app folder:

```powershell
py -m aprs_watch
```

For a real Windows service, use the third-party [WinSW service wrapper](https://github.com/winsw/winsw). It is not bundled:

1. Put the application under `C:\APRSWatch\app` and a validated configuration at `C:\APRSWatch\config.json`. Disable desktop notifications for the service.
2. Edit the Python path in `services/APRSWatch.xml`, then place that XML and a compatible WinSW executable together in `C:\APRSWatch`, named `APRSWatch.xml` and `APRSWatch.exe`.
3. Supply the SMTP password to the service environment if needed, for example through a protected WinSW `<env name="APRS_WATCH_SMTP_PASSWORD" value="..."/>` setting. XML-escape special characters. Restrict access to files containing credentials.
4. In an Administrator terminal in that folder, run `APRSWatch.exe install`, then `APRSWatch.exe start`. Use `APRSWatch.exe stop` and `APRSWatch.exe uninstall` to remove it. Ensure the service account can read the app and write its data folder.
5. To view service status in the GUI, launch `py -m aprs_watch gui --config C:\APRSWatch\config.json --data-dir C:\APRSWatch\data` from the app folder with an account permitted to access those files.

## Verification and limitations

Run the automated suite from the application folder:

```sh
python3 -m unittest discover -s tests -v
```

Tests cover APRS matching, alert timing, reconnection grace, restart state, channel selection, mocked email/webhook delivery, retry isolation, locking, and a local TCP server exercising login, absence and recovery end-to-end. The local integration test requires loopback socket access.

All 25 automated tests passed on Linux, including the local TCP integration test. The GUI was rendered and checked at 960×790 and 800×700. The Linux systemd service file passed syntax verification with its application path filled in; the macOS plist and Windows XML parsed successfully. Windows/macOS code and service templates require verification on those operating systems. No real SMTP account, webhook endpoint, or live APRS login was supplied, so live delivery and station observation must be checked using your settings. This is a Python application, not a signed standalone installer.

Protocol and service references: [APRS-IS connections](https://aprs-is.net/Connecting.aspx), [server filters](https://www.aprs-is.net/javAPRSFilter.aspx), [TNC2 used-path explanation](https://raw.githubusercontent.com/wb2osz/direwolf-doc/main/APRS-Digipeaters.pdf), [systemd user lingering](https://www.freedesktop.org/software/systemd/man/252/loginctl.html), [Apple launch jobs](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html), and [WinSW configuration](https://github.com/winsw/winsw/blob/v3/docs/xml-config-file.md).
