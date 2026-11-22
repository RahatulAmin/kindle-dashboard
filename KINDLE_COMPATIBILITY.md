# Kindle Paperwhite 2 compatibility

The target is the Amazon Kindle Paperwhite 2, sixth generation (2013), with firmware 5.12.2. Its six-inch e-ink touchscreen has a native portrait resolution of 758 × 1024 pixels and 16 grayscale levels. It uses Wi-Fi and Amazon’s experimental browser.

## Physical observations

- The Kindle reached Dashboard NAS over the local network and loaded `/kindle` in the experimental browser.
- The server-rendered 758 × 1024 grayscale PNG displayed with readable text.
- The browser toolbar reduced the usable height and the page required vertical scrolling.
- The Kindle toolbar and the server-rendered clock showed different times. The cause is unverified. The diagnostic labels the server time with its timezone abbreviation and UTC offset for comparison.

## Browser diagnostic

Open `http://<Dashboard NAS-LAN-IP>:8765/kindle/test` on the trusted LAN. The shared last-press timestamp lives only in the running app's memory and resets on restart. Tap **Test Touch** to POST the timestamp, then the browser should follow a redirect back to the page. **Refresh Now** and the 30-second meta refresh use GET and leave the last press unchanged.

1. Open the diagnostic in portrait with the toolbar visible. Check that the timestamp, both buttons, and the complete image are visible without scrolling. Record any clipping, scaling, or toolbar-dependent behavior.
2. Compare the displayed server timestamp and UTC offset with the toolbar clock and a known local clock. Record the difference and each device's timezone if available.
3. Leave the page open without touching it for at least 70 seconds. Record whether the timestamp advances about every 30 seconds and whether the image updates. Repeat across sleep, wake, and Wi-Fi reconnect. Continuous-awake behavior is still unknown.
4. Tap **Test Touch**. Verify that a new last-press timestamp appears after the redirect. Tap **Refresh Now** and confirm that server time advances and last press remains unchanged. Check that subsequent automatic refreshes preserve last press and do not ask to resubmit the form.

Headless Firefox displayed the full image and both buttons without scrolling at 758 × 860 and 360 × 520 window sizes. The POST redirect, manual refresh and 30-second meta refresh worked, and reloads preserved the last press. The physical PW2 on firmware 5.12.2 subsequently passed screen fitting, 30-second automatic refresh, the touchscreen HTML POST form, and manual refresh on the diagnostic.

## Phase 2 dashboard

Enable Kindle sharing in **Settings** and open `/kindle` to see the data-backed Pillow image. The page uses the same simple viewport sizing and HTML refresh approach. It defaults to 30 seconds and the 758 × 1024 grayscale image contains bounded, single-line entries. Confirm the complete populated image fits beneath the toolbar on the physical Kindle. Check long entries, widget changes, stale weather, and readable text when the image is scaled.

The diagnostic at `/kindle/test` remains separate. It can still be used to compare the toolbar clock against the server timestamp and test touch, wake, or reconnect behavior.

## Phase 2.5A native KUAL preview

The Paperwhite 2 is already jailbroken and has KUAL installed. The packaged `rahat-dashboard` extension downloads and validates the test image, then can draw it once with the device's `eips -g` utility while Amazon's interface continues running. An Amazon repaint may cover the image. The NAS test verified the real PNG endpoint and a packaged BusyBox shell download.

KUAL launch, the available native utilities, physical image rendering, and Home/power-button recovery still need a device test. The [extension guide](kindle-native/rahat-dashboard/README.md) includes exact USB paths, test steps, and log collection. Framework takeover, refresh loops, and boot startup are outside this package.

## Later physical tests

During Pomodoro development, measure refresh behavior across active, paused and resumed states and look for e-ink ghosting. The timer will use server timestamps independently of display refreshes. Verify TLS and cookie support before releasing authenticated device controls. If the browser cannot meet the requirements, evaluate an optional native client. Any device modification requires a separate decision.
