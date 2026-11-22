# Rahat Dashboard for KUAL

Phase 2.5A is a manual, one-shot test for a jailbroken Kindle Paperwhite 2 with KUAL already installed. It uses the Kindle's POSIX shell, curl, and `eips -g` to fetch and display a server-rendered 758 × 1024 8-bit grayscale PNG. The Amazon framework stays running and may quickly repaint part or all of the native image. Phase 2.5A does not control the framework, input devices, power settings, or boot behavior.

## Server and connection

The extension ships with `http://192.0.2.10:8765` as its requested default. Dashboard NAS was configured at **192.0.2.10:8765** when this package was prepared. Verify its current LAN address and use it in `config.sh`. The FastAPI app must be running on that address for the test.

- `/api/kindle/image.png` serves the synthetic test image and is the starting endpoint.
- `/api/kindle/dashboard.png` serves real data after an administrator enables Kindle sharing in **Settings**. Trusted-LAN clients can read this image while sharing is enabled. Leave sharing off for the initial test.
- The extension sends no administrator credentials or session cookies. The synthetic read-only endpoint needs no credential. For real data on an untrusted network, private device authentication would need a separate design.

On Dashboard NAS, start the project in a foreground terminal. Use the current LAN IPv4 address.

```sh
cd /srv/kindle-dashboard/project
umask 077
bash scripts/prepare-storage.sh && APP_HOST=192.0.2.10 PYTHONPATH=backend .venv/bin/python -m app
```

From Windows, open `http://192.0.2.10:8765/api/kindle/image.png` in a browser before testing the Kindle. Use Ctrl+C on the NAS to stop that foreground instance when finished.

## Install over USB from Windows

1. Save `rahat-dashboard.zip` to Windows from the project. If you already use SSH on Dashboard NAS, PowerShell can copy it with `scp user@192.0.2.10:/srv/kindle-dashboard/project/kindle-native/rahat-dashboard.zip .`.
2. Right-click the ZIP and select **Extract All**. Inside the extracted folder, open `extensions`.
3. Plug the Kindle into Windows using a USB data cable and open the Kindle drive in File Explorer. Create `extensions` at the drive root if needed. Copy the extracted `rahat-dashboard` folder into it.
4. Verify the final path is `E:\extensions\rahat-dashboard\config.xml`, substituting the actual drive letter. On the Kindle this is `/mnt/us/extensions/rahat-dashboard/config.xml`.
5. In that same folder, copy `config.sh.example` to `config.sh`. Enable **View → Show → File name extensions** in File Explorer so the file does not accidentally end in `.txt`. Edit `SERVER_URL` in an editor that preserves Unix LF and UTF-8 without a BOM, such as VS Code. For this NAS, use `SERVER_URL='http://192.0.2.10:8765'` if that address is still current. Leave `IMAGE_PATH` on the synthetic endpoint.
6. Use **Eject** in Windows and unplug USB before launching KUAL. Keep the Kindle on the same Wi-Fi network as the NAS.

## First physical test

1. Open **KUAL → Rahat Dashboard → Test NAS Connection**. Allow up to 20 seconds for the request. It downloads and validates the image without drawing it. Reconnect USB and verify that `state/dashboard.log` contains `Download verified` and `state/last-good.png` opens as a 758 × 1024 image on Windows.
2. Eject and disconnect USB. Run **Test Native Image Display** and watch the screen as KUAL exits its menu. It sends the validated cached PNG to the installed `eips` utility. A success entry records the utility's exit status. Seeing a readable image, noting whether it covers the expected area, and observing how quickly the Amazon UI repaints are physical checks.
3. Reopen KUAL and select **Start Dashboard**. It downloads and displays a fresh image once. Compare its time with the cached image. Select **Stop / Restore Kindle**, then return Home or sleep and wake to confirm a normal repaint.
4. With airplane mode enabled or the NAS app stopped, repeat **Test NAS Connection**. Verify the log reports failure and the previous PNG still opens. Then restore connectivity. The cached image can still be displayed manually from **Test Native Image Display**.

## Logs and recovery

After an action completes, connect USB and copy `extensions\rahat-dashboard\state\dashboard.log` from the Kindle drive. Include the firmware and the KUAL action you ran. The file's date comes from the Kindle clock. Keep `last-good.png` private if it contains dashboard data. The connection test checks the HTTP status, PNG signature, dimensions, grayscale and interlace flags, first data chunk and closing marker. It does not decode every pixel or verify all chunk checksums. The display action asks the installed `eips` to read the actual PNG.

- **Normal exit:** Each action completes after one attempt. Return Home or press the power button once to sleep and again to wake if the image is still visible.
- **Stop during a download:** **Stop / Restore Kindle** requests cancellation. The fetch can take up to 20 seconds to return. The script checks cancellation before saving or drawing and leaves the existing cache available. A draw that already began may finish.
- **App cannot reach Dashboard NAS:** Confirm Wi-Fi, the LAN address and endpoint. HTTP 404 on the real endpoint commonly means sharing is off. Use the synthetic endpoint to retest. The last verified image remains available.
- **Crash or stuck test:** Restart the Kindle normally if its UI is responsive. If the screen is unresponsive, first wait for the bounded download, then try one power-button sleep/wake cycle. As a last resort, hold the power button for about 40 seconds and release to restart. [Amazon Kindle restart instructions](https://digprjsurvey.amazon.com/csad/help/node/G9WDGDTCSDQMSU7Z) Once restarted, you can remove a leftover `state/active` directory via USB if the log reports a stale marker. Leave `last-good.png` in place if you want to retain the cache.
- **Remove the extension:** After any action finishes, remove `extensions\rahat-dashboard` over USB. Copy out the log first if needed.

## Framework takeover design for a later phase

Before any separately approved takeover, verify a valid frame and the power-button exit path on physical hardware with the framework still running. A future worker and recovery supervisor must detach from KUAL's framework process tree with a separate session, such as `setsid`, before requesting framework shutdown. The worker would draw only after shutdown finishes because the framework can blank the display as it exits. Recovery should track whether this app stopped the framework, restore it on shutdown or crash, wait for the application manager, and request a Home repaint. A single power press should request recovery and allow time for Home to return. Keep a physical restart fallback and test it before enabling takeover. The power-event layout and restoration timing in the references are device-specific. [jackwuwei Paperwhite reference](https://github.com/jackwuwei/kindle-dashboard#4-pitfalls-read-before-changing-anything) · [ZEUSGMJ PW2 recovery reference](https://github.com/ZEUSGMJ/kindle-homelab-dashboard#exit-behavior)

KUAL metadata follows the published menu structure. The initial renderer uses the references' PNG drawing approach with the system UI running. [KUAL config and menu examples](https://github.com/ZEUSGMJ/kindle-homelab-dashboard/tree/main/kindle-extension) · [Native PNG reference](https://github.com/ZEUSGMJ/kindle-homelab-dashboard/blob/main/kindle-extension/bin/dash_loop.sh)
