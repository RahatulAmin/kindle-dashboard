# Rahat Dashboard for KUAL

Phase 2.5B adds a native full-screen dashboard for a jailbroken Paperwhite 2 on firmware 5.12.2. Phase 2.5A proved KUAL launch, NAS download and `eips -g` on the physical device. This release still needs physical testing of framework shutdown, periodic full refresh and recovery. The package defaults to the safe one-shot preview. Nothing launches at boot.

## Install or upgrade over USB from Windows

1. Save and extract `rahat-dashboard.zip` using **Extract All**. If your Windows machine already has SSH access to Dashboard NAS, PowerShell can copy the archive with `scp user@192.0.2.10:/srv/kindle-dashboard/project/kindle-native/rahat-dashboard.zip .`.
2. Stop any running Kindle dashboard and wait for Home before connecting USB. Copy the extracted `extensions\rahat-dashboard` folder to the Kindle drive's root `extensions` folder. Replace the old packaged files and keep your existing `config.sh` and `state` folder. The final path is `E:\extensions\rahat-dashboard\config.xml` (substitute the drive letter), or `/mnt/us/extensions/rahat-dashboard/config.xml` on the Kindle.
3. For a new install, copy `config.sh.example` to `config.sh`. Enable **View → Show → File name extensions** in File Explorer and preserve Unix LF and UTF-8 without BOM. Use `SERVER_URL='http://192.0.2.10:8765'` and `IMAGE_PATH='/api/kindle/image.png'` for the first test. Omit `FULLSCREEN_ENABLED` or set it to `no` initially. The refreshed ZIP uses the address verified on your Kindle.
4. Eject the Kindle in Windows and disconnect USB before opening KUAL. Check the Kindle is on the same Wi-Fi network as Dashboard NAS.

If the NAS app is stopped, start it in a foreground NAS terminal using the current trusted LAN address.

```sh
cd /srv/kindle-dashboard/project
umask 077
bash scripts/prepare-storage.sh && APP_HOST=192.0.2.10 PYTHONPATH=backend .venv/bin/python -m app
```

Visit `http://192.0.2.10:8765/api/kindle/image.png` from Windows to check that the synthetic PNG is reachable. The optional `/api/kindle/dashboard.png` serves real data only after an administrator enables trusted-LAN Kindle sharing in **Settings**. Both image requests use no admin cookies or credentials. Keep the synthetic endpoint for the first full-screen test.

## Verify recovery with the framework running

1. In KUAL, run **Test NAS Connection**, then **Test Native Image Display**. Confirm the preview and return Home. This version keeps those actions from Phase 2.5A.
2. With the normal Kindle interface running, verify that a physical long press can restart this exact Kindle. Hold the power button for about 40 seconds and release, then confirm Home and KUAL return. [Amazon Kindle restart instructions](https://digprjsurvey.amazon.com/csad/help/node/G9WDGDTCSDQMSU7Z)
3. After the restart, open **KUAL → Rahat Dashboard → Rehearse Power Button Recovery**. Within 45 seconds, briefly press the power button once, then wake the Kindle if it sleeps. Connect USB after the action finishes and confirm `state/dashboard.log` contains `Recovery rehearsal passed`. This action leaves the framework running and verifies a real 32-bit `KEY_POWER` press using the detected input device. The proof is bound to the current boot and that device path. If the rehearsal fails, leave full-screen disabled.

## First full-screen test (manual approval)

Only proceed after both recovery checks above pass and you approve stopping the GUI for this test. While still on the same boot, edit the Kindle's `config.sh` via USB.

```sh
FULLSCREEN_ENABLED=yes
REFRESH_SECONDS=30
FULL_REFRESH_EVERY=2
SESSION_LIMIT_SECONDS=120
```

1. Eject USB. Open **KUAL → Rahat Dashboard → Start Dashboard**. A detached supervisor checks the recovery proof and monitors the key before fetching the first frame. It requests a framework stop only after validating a fresh 758 × 1024 grayscale PNG.
2. Confirm the dashboard remains on the full screen and the timestamp changes across refreshes. The first paint and every second update use `eips -f -g` in this configuration. Offline fetches preserve and redraw the last valid image.
3. Press the power button **once**, then wait for Home to restore. The Kindle may sleep as part of normal power handling. If it sleeps, wake it and give Home time to repaint. Expect startup to take tens of seconds and allow up to two minutes before using the reboot fallback. KUAL may be unavailable while the framework is down.
4. Confirm Home, touch, Wi-Fi and KUAL work normally. Collect the log. If manual exit succeeds, repeat the test and let the 120-second session limit restore Home without pressing power. Keep the timed limit until both tests pass.
5. After those physical checks succeed, `SESSION_LIMIT_SECONDS=0` allows a persistent manual session. `REFRESH_SECONDS` supports 30–3600 seconds, `FULL_REFRESH_EVERY` supports 1–60 updates, and the session limit supports 60–9999 seconds or 0. The default preview flag remains `no`; if enabled, each reboot still requires a fresh recovery rehearsal.

## Stop, recover and collect logs

- **Normal full-screen exit:** Press the physical power button briefly once. If a shell connection already exists, `/bin/sh /mnt/us/extensions/rahat-dashboard/stop.sh` is an alternative. The KUAL Stop action is useful only when KUAL is available.
- **Restoration:** The supervisor terminates its display worker before restarting the `framework` job and requesting Home. A failed draw, worker exit, lost power monitor, missing runtime directory, or elapsed session limit triggers the same restoration. The supervisor handles normal termination signals. A crash that kills the supervisor itself may require a restart.
- **Unresponsive screen:** Let restoration finish and try waking once if the device slept. If Home still fails to return, use the verified physical restart (hold power about 40 seconds, then release). A reboot starts the Kindle normally. After restarting you may remove a stale `state/active` directory over USB if it blocks another test. Set `FULLSCREEN_ENABLED=no` before retrying a failure.
- **NAS unavailable:** A failed initial download leaves the framework running. After startup a failed refresh keeps the last verified image and retries on the configured interval. Each fetch has 5-second connection and 20-second total limits.
- **Logs:** After Home returns, connect USB and copy `extensions\rahat-dashboard\state\dashboard.log` and, if present, `dashboard.log.1`. Include firmware and what the screen did. Keep `last-good.png` private if it contains real dashboard data.

Only the Upstart `framework` job is stopped. Power management, automatic sleep, Wi-Fi and battery and thermal protections retain their stock settings. Refreshes and the session timer run while the device is awake. The extension changes no root filesystem files or startup settings.

The recovery design follows the PW2 references for detaching with `setsid`, drawing after the framework stops, and requesting Home after restoration. The Kindle's exact `initctl` behavior, power handling during takeover, and native full-refresh option remain part of the physical test. [PW2 framework notes](https://github.com/jackwuwei/kindle-dashboard#4-pitfalls-read-before-changing-anything) · [PW2 display and recovery code](https://github.com/ZEUSGMJ/kindle-homelab-dashboard/blob/main/kindle-extension/bin/dash_loop.sh) · [Upstart command reference](https://manpages.debian.org/wheezy/upstart/start.8.en.html)
