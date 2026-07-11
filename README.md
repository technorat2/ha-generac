# Generac Updated Login

Unofficial Home Assistant integration for Generac Mobile Link generators. This
repository is a community fork of [bentekkie/ha-generac](https://github.com/bentekkie/ha-generac)
with the current Mobile Link authentication flow and the original cookie bridge
retained as a fallback.

## Features

- UI-based Home Assistant setup.
- APK-matched Auth0 authorization-code PKCE login as the primary path.
- Automatic access-token refresh without manually copying browser cookies.
- Legacy Mobile Link web-cookie authentication only as an expected fallback.
- Generator status, runtime, protection time, exercise, battery, connectivity,
  warning, maintenance, serial/model, dealer, address, panel, and signal data.
- Numeric signal strength reported as a percentage when Mobile Link provides it.
- Weather and generator image entities when returned by the API.
- Friendly entity names while preserving existing technical entity IDs.
- Redacted diagnostics and targeted debug logging for troubleshooting.

Mobile Link is a private reverse-engineered API and can change without notice.
The integration is not affiliated with or endorsed by Generac.

## Installation With HACS

1. Open **HACS** in Home Assistant.
2. Add `https://github.com/technorat2/ha-generac` as a custom repository in the
   **Integration** category.
3. Download **Generac Updated Login**.
4. Restart Home Assistant.
5. Go to **Settings** > **Devices & services** > **Add Integration**.
6. Search for **Generac Updated Login** and enter your Mobile Link credentials.

## Manual Installation

Copy the contents of `custom_components/generac_auth0_pkce/` into:

```text
<home-assistant-config>/custom_components/generac_auth0_pkce/
```

Restart Home Assistant, then add **Generac Updated Login** through the UI. Do
not install the `legacy/generac_updated` directory; it is retained for
reference and testing only.

## Existing Configurations

The canonical domain is `generac_auth0_pkce`. Its domain and unique IDs are
kept stable so existing installations of this fork retain their entity history.
The original `generac` integration and the older `generac_updated` copy are
separate domains and are not migrated automatically. Remove duplicate entries
only after confirming which integration is providing your entities.

## Authentication

The integration follows the Android application’s Auth0 PKCE flow first. The
bearer tokens and expiry metadata are persisted in the Home Assistant config
entry and refreshed when needed. The web-cookie bridge is used only when the
expected bearer flow or API session cannot be used. A WAF-generated HTML 403 is
reported as a connection problem rather than treated as an expired login.

No APK, captured response, account-specific generator data, or credentials are
required by the published integration.

## Entities

| Platform        | Entities                                                                                                                                                                                                                                                                                                                   |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `binary_sensor` | Is Connected, Is Connecting, Maintenance Alert, Warning                                                                                                                                                                                                                                                                    |
| `sensor`        | Status, Device Type, Runtime, Protection Time, Activation Date, Last Seen, Connection Time, Battery Voltage, Exercise Minutes, Outdoor Temperature, Signal Strength, Device Battery Level, Serial Number, Model Number, Device SSID, Status Label, Status Text, Address, Dealer Name, Dealer Email, Dealer Phone, Panel ID |
| `weather`       | Weather                                                                                                                                                                                                                                                                                                                    |
| `image`         | Hero Image                                                                                                                                                                                                                                                                                                                 |

Signal Strength is exposed as a numeric percentage, for example `8%`, when the
Mobile Link payload contains a value such as `"8%"`.

## Troubleshooting

Enable targeted logging in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.generac_auth0_pkce: debug
```

Restart or reload the integration after changing the logger. When sharing logs,
remove credentials, access tokens, refresh tokens, callback URLs, and personal
generator data.

## Standalone Tests

The repository includes PowerShell checks that do not install anything into
Home Assistant:

```powershell
./scripts/Test-GeneracPkce.ps1 -AutoLogin
```

The older cookie-bridge client can be tested with:

```powershell
./scripts/Test-GeneracIntegration.ps1
```

Credentials can be entered interactively or supplied through `GENERAC_USER` and
`GENERAC_PASS` environment variables. The test scripts use a local ignored
virtual environment.

For repository validation:

```powershell
python -m unittest discover -s tests -v
pre-commit run --all-files
```

## Releases and Updates

Home Assistant does not need an `update` entity for this integration. The
`update` platform is for updates to the connected device or service; HACS
delivers updates to this integration itself.

For each release:

1. Bump the SemVer `version` in `custom_components/generac_auth0_pkce/manifest.json`
   and `const.py`.
2. Update `CHANGELOG.md`.
3. Run the standalone tests, unit tests, pre-commit, HACS validation, and
   Hassfest.
4. Create and push a matching tag such as `v0.3.0`.
5. Publish the GitHub release so HACS can offer it to users.

## Credits and License

This is a fork of [ha-generac](https://github.com/bentekkie/ha-generac) by
`@bentekkie`. The repository remains under the MIT license. The Auth0 client
configuration is based on behavior observed in the Generac Mobile Link Android
application; the APK itself is not redistributed here.
