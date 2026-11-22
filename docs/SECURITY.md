# Security architecture

## Administrator

Create the initial account from a trusted terminal with `app.setup_admin`. The command prompts for a unique password. Passwords are salted and hashed with scrypt. The app stores only hashes of random session tokens, expires them server-side, and revokes them on logout. Keep the SQLite database and backups private.

Administrator data routes require a valid session. Mutations also require the session's CSRF token in a custom header. Login requires a same-origin browser request with its own custom header. The application sets no cross-origin permissions. The sign-in endpoint allows five attempts per client address and 15 in total per minute, with at most two simultaneous password checks. These counters live in the single app process and reset on restart. A trusted reverse proxy may cause clients to share one rate-limit identity.

Session cookies are HttpOnly and SameSite=Strict. They default to Secure for HTTPS. `ADMIN_COOKIE_SECURE=false` is an explicit trusted-LAN HTTP override. Plain HTTP leaves the password and cookie exposed to anyone able to observe or interfere with local traffic. Bind locally by default, prefer HTTPS for remote administration, and keep the app off public interfaces and proxies.

## Kindle

The optional shared display exposes only a read-only PNG to clients that can reach Dashboard NAS on the trusted LAN. Sharing is disabled by default. If enabled, open tasks and active deadlines appear only when individually marked Kindle-visible and permitted by their widget. Keep sensitive entries hidden. The diagnostic records only its own in-memory timestamp and serves the synthetic test image.

Device registration remains planned. Pairing will issue revocable device-specific credentials and scope them to assigned display data and explicitly authorized timer or display actions. Physical TLS and cookie compatibility must be verified before selecting a credential transport.
