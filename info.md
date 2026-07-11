# Generac Updated Login

Unofficial Home Assistant integration for Generac Mobile Link generators. The
Auth0 authorization-code PKCE flow is primary, with the legacy Mobile Link
web-cookie bridge retained as an authentication fallback.

## Installation

1. Add `https://github.com/technorat2/ha-generac` to HACS as a custom
   **Integration** repository.
2. Download **Generac Updated Login**.
3. Restart Home Assistant.
4. Add **Generac Updated Login** from **Settings** > **Devices & services**.

Manual installation uses:

```text
custom_components/generac/
```

Configuration is completed in the Home Assistant UI. No manual cookie
extraction is required.

The integration uses Generac's private Mobile Link API and may need updates if
Generac changes its service or authentication behavior.

---

[HACS](https://hacs.xyz)
