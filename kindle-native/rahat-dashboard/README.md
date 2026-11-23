# Rahat Dashboard for KUAL

Phase 2.5B adds a native full-screen dashboard for a jailbroken Paperwhite 2 on firmware 5.12.2. Phase 2.5A proved KUAL launch, NAS download and `eips -g` on the physical device. Physical Phase 2.5B logs confirmed KEY_POWER, a successful framework restart, accepted Home requests and claim release. Home still did not visibly repaint. This version changes the display handoff and needs a new physical retest. The package defaults to the safe one-shot preview. Nothing launches at boot.

## Install or upgrade over USB from Windows

1. Save and extract `rahat-dashboard.zip` using **Extract All**. If your Windows machine already has SSH access to Dashboard NAS, PowerShell can copy the archive with `scp user@192.0.2.10:/srv/kindle-dashboard/project/kindle-native/rahat-dashboard.zip .`.
2. Stop any running Kindle dashboard and wait for Home before connecting USB. Copy the extracted `extensions\rahat-dashboard` folder to the Kindle drive's root `extensions` folder. Replace the old packaged files and keep your existing `config.sh` and `state` folder. The final path is `E:\extensions\rahat-dashboard\config.xml` (substitute the drive letter), or `/mnt/us/extensions/rahat-dashboard/config.xml` on the Kindle.
3. For a new install, copy `config.sh.example` to `config.sh`. Enable **View → Show → File name extensions** in File Explorer and preserve Unix LF and UTF-8 without BOM. Use `SERVER_URL='http://192.0.2.10:8765'` and `IMAGE_PATH='/api/kindle/image.png'` for the first test. For both installs and upgrades, omit `FULLSCREEN_ENABLED` or set it to `no` before opening KUAL. Repeat both recovery checks with this version before opting in. The refreshed ZIP uses the address verified on your Kindle.
4. Eject the Kindle in Windows and disconnect USB before opening KUAL. Check the Kindle is on the same Wi-Fi network as Dashboard NAS.

All five KUAL actions call `/bin/sh /mnt/us/extensions/rahat-dashboard/<script>.sh`. Relative commands such as `./start.sh` failed on the physical Paperwhite 2. Use the exact installation folder above so the absolute commands resolve.

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
2. Confirm the dashboard remains on the full screen and the timestamp changes across refreshes. The first paint and every second update use `eips -f -g` in this configuration. If startup fails, collect the log before retrying.
3. On the first trial, press the power button briefly **once** after the first redraw. Watch for a brief blank frame, then Kindle Home. The clear may be invisible if the Kindle sleeps. If the screen remains blank or shows the old dashboard and the Kindle appears asleep, wake it once during the recovery window. Verify that Kindle Home becomes visible and responds to touch. Allow up to two minutes for framework startup and repaint before using the verified reboot fallback. Keep KUAL out of the recovery path.
4. Once Home is visibly back, check touch, Wi-Fi and KUAL. Run **Stop / Restore Kindle** and check for `No dashboard action running.` Then run **Test NAS Connection** to confirm no lock blocks new work. Copy the log before the next trial.
5. If the first trial restores Home, run another and leave power and touch alone for the full 120 seconds. Confirm Home visibly returns, then collect the log again. If the screen sleeps on its own, note that and wake the device to allow recovery to run. Keep `SESSION_LIMIT_SECONDS=120` and set `FULLSCREEN_ENABLED=no` after these tests or after any failed recovery. This release only accepts 120 seconds in full-screen mode.

## Stop, recover and collect logs

- **Normal full-screen exit:** Press the physical power button briefly once. If a shell connection already exists, `/bin/sh /mnt/us/extensions/rahat-dashboard/stop.sh` is an alternative. The KUAL Stop action is useful only when KUAL is available.
- **Restoration:** The supervisor revokes dashboard drawing and terminates its display process group. After confirming the group is quiescent and the framework is still stopped, it attempts one `eips -c` clear. It issues no framebuffer writes after framework startup begins. It reuses a running framework and checks the PW2 app-manager and power state before bounded Home requests. If the power daemon reports sleep, it waits for a wake during the request window. It sends no synthetic wake and changes no power settings. A failed draw, worker exit, lost power monitor, missing runtime directory, or elapsed session limit triggers the same restoration. The supervisor handles normal termination signals and bounds waits on its display worker, power reader, and service commands. The 120-second deadline uses the kernel uptime clock and runs independently of power events. A hard kill of the supervisor or a device that remains asleep can still require physical intervention.
- **Unresponsive screen:** Let restoration finish and try waking once if the device slept. If Home still fails to return, use the verified physical restart (hold power about 40 seconds, then release). A reboot starts the Kindle normally. After restarting, run Stop or Test NAS Connection. The client can clear an empty legacy `state/active` directory once it sees no older client. New claims in `state/sessions` record boot ID, PID and process start time, so a live process or reused PID can be distinguished. The client preserves uncertain claims and unrecognized files. Set `FULLSCREEN_ENABLED=no` before retrying a failure.
- **NAS unavailable:** A failed initial download leaves the framework running. After startup a failed refresh keeps the last verified image and retries on the configured interval. Each fetch has 5-second connection and 20-second total limits.
- **Logs:** After Home returns, connect USB and copy `extensions\rahat-dashboard\state\dashboard.log` and, if present, `dashboard.log.1`. Include firmware, time of the short press, sleep or wake behavior, and whether Home visibly returned. Look for `KEY_POWER press observed`, `Framework confirmed stop/waiting`, `Supervisor ... terminating`, `Session time limit reached` when testing the timeout, `Dashboard worker group ... is quiescent`, `Pre-start screen clear exit=`, `Framework reports start/running`, power and active-app values, and Home request exit codes. A successful LIPC request and even `App-manager reports Home active` describe software state. Record the visible repaint separately. Keep `last-good.png` private if it contains real dashboard data.

Only the Upstart `framework` job is stopped. Power management, automatic sleep, Wi-Fi and battery and thermal protections retain their stock settings. The supervisor evaluates the deadline when it can run, including after a wake. The extension changes no root filesystem files or startup settings.

The recovery design follows the PW2 references for detaching with `setsid`, drawing after the framework stops, and requesting Home after restoration. The Kindle's exact `initctl` behavior, power handling during takeover, and native full-refresh option remain part of the physical test. [PW2 framework notes](https://github.com/jackwuwei/kindle-dashboard#4-pitfalls-read-before-changing-anything) · [PW2 display and recovery code](https://github.com/ZEUSGMJ/kindle-homelab-dashboard/blob/main/kindle-extension/bin/dash_loop.sh) · [Upstart command reference](https://manpages.debian.org/wheezy/upstart/start.8.en.html)

The PW2 reference clears the old e-ink image before framework startup and waits for application-manager readiness. This release uses the same pre-start clear and polls the PW2's documented read-only `activeApp` and power `state` properties with timed fallback. It keeps the known Home booklet URI. [PW2 native recovery reference](https://github.com/ZEUSGMJ/kindle-homelab-dashboard/blob/main/kindle-extension/bin/dash_loop.sh) · [PW2 LIPC property list](https://wiki.mobileread.com/wiki/Lipc)
