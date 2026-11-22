# Kindle Paperwhite 2 compatibility

The target is the Amazon Kindle Paperwhite 2, sixth generation (2013), with firmware 5.12.2. Its six-inch e-ink touchscreen has a native portrait resolution of 758 × 1024 pixels and 16 grayscale levels. It uses Wi-Fi and Amazon’s experimental browser.

Phase 1 uses a basic HTML image page, a high-contrast grayscale PNG, and manual reload. Browser viewport scaling, PNG display, cache behavior, automatic refresh, screen sleep, continuous-awake behavior and standard touchscreen forms all need verification on the physical device. Browser chrome may reduce the usable screen area. Timer accuracy will eventually come from server-side timestamps independently of display refreshes.

## Physical tests

1. Bind the application to Dashboard NAS’s trusted LAN IPv4 address and connect the Kindle to that network.
2. Open `http://<Dashboard NAS-LAN-IP>:8765/kindle` in the experimental browser. Verify load, orientation, scaling, contrast, readability and browser chrome. Open `/api/kindle/image.png` directly if needed.
3. Reload manually and confirm the displayed time changes. Observe Wi-Fi reconnect, wake recovery, caching and idle/sleep behavior.
4. In a later phase, measure 30-second Pomodoro refreshes across active, paused and resumed states. Check background, sleep and wake behavior and e-ink ghosting.
5. Verify ordinary HTML form buttons, touch target sizing, duplicate submissions, and the supported TLS/cookie behavior before releasing authenticated device controls.
6. Evaluate a native client if the browser cannot meet the requirements. Any path involving device modification requires a separate decision. No jailbreak, firmware change or device modification is part of this project phase.
