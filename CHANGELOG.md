# Changelog

## 0.3.2 - 2026-07-11

- Fix the options flow for current Home Assistant versions by initializing the
  base `OptionsFlow` class instead of assigning its read-only `config_entry`.

## 0.3.1 - 2026-07-11

- Align Auth0 token expiry and refresh recovery with the Mobile Link APK.
- Retry Auth0 PKCE login before using the legacy cookie bridge after a 401.
- Serialize refresh requests and harden diagnostics for failed setup entries.

## 0.3.0 - 2026-07-11

- Use the APK-matched Auth0 PKCE flow as the primary authentication path.
- Preserve the Mobile Link web-cookie bridge as a fallback.
- Persist and refresh bearer tokens in the Home Assistant config entry.
- Report signal strength as a numeric percentage.
- Add friendly entity names without changing existing unique IDs.
- Add the Mobile Link APK launcher icon as integration branding.
- Move the older cookie-only component under `legacy/` so the public package has
  one installable integration.
