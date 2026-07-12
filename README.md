# Generac MobileLink

Unofficial Home Assistant integration for Generac MobileLink generators and
propane tank monitors. This repository is a fork of
[pjordanandrsn/ha-generac](https://github.com/pjordanandrsn/ha-generac) with
friendly entity names, diagnostics, branding, additional sensors, and focused
repository tests.

## Features

- UI-based Home Assistant setup.
- Auth0 authorization-code PKCE with a persisted DPoP key.
- Access-token refresh without storing the account password or copying cookies.
- Home Assistant reauthentication when the refresh credential is rejected.
- MFA code handling for SMS, authenticator-app, and email factors.
- Auth0 custom-prompt handling for consent and account-update screens.
- Configurable cloud polling, defaulting to 15 minutes.
- Generator status, runtime, protection time, exercise, battery, connectivity,
  warning, maintenance, serial/model, dealer, address, panel, and signal data.
- Propane tank monitor entities when returned by the account.
- Numeric signal strength reported as a percentage.
- Weather and generator image entities when returned by the API.
- Friendly entity names while preserving stable technical entity IDs.
- Redacted diagnostics and targeted debug logging.

Mobile Link is a private reverse-engineered API and can change without notice.
The integration is not affiliated with or endorsed by Generac.

## Installation With HACS

1. Open **HACS** in Home Assistant.
2. Add `https://github.com/technorat2/ha-generac` as a custom repository in the
   **Integration** category.
3. Download **Generac MobileLink**.
4. Restart Home Assistant.
5. Go to **Settings** > **Devices & services** > **Add Integration**.
6. Search for **Generac MobileLink** and enter your Mobile Link credentials.

## Manual Installation

Copy `custom_components/generac/` into:

```text
<home-assistant-config>/custom_components/generac/
```

Restart Home Assistant, then add **Generac MobileLink** through the UI.

## Authentication

The integration uses Auth0 authorization-code PKCE with a DPoP-bound refresh
credential. Mobile Link resource requests use the bearer access token issued by
Auth0; DPoP proofs are used for the Auth0 token exchange and refresh operations.
The private DPoP key and refresh token are persisted in the Home Assistant
config entry. Passwords and web cookies are not persisted. Invalid credentials
surface as Home Assistant reauthentication.

Accounts with SMS, authenticator-app, or email MFA receive a second setup step
for the verification code. Unsupported interactive factors are reported with
an actionable setup error.

## Entities

| Platform | Entities |
| --- | --- |
| `binary_sensor` | Is Connected, Is Connecting, Maintenance Alert, Warning |
| `sensor` | Status, Device Type, Runtime, Protection Time, Activation Date, Last Seen, Connection Time, Battery Voltage, Exercise Minutes, Outdoor Temperature, Signal Strength, Device Battery Level, Serial Number, Model Number, Device SSID, Status Label, Status Text, Address, Dealer Name, Dealer Email, Dealer Phone, Panel ID, tank capacity/fuel/orientation sensors |
| `weather` | Weather |
| `image` | Hero Image |

## Troubleshooting

Enable targeted logging in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.generac: debug
```

When sharing logs, remove credentials, access tokens, refresh tokens, callback
URLs, cookies, addresses, serial numbers, and other personal generator data.

## Standalone Test

The repository includes a PowerShell check that exercises the Auth0/DPoP login
and a live API read without installing anything into Home Assistant:

```powershell
./scripts/Test-GeneracDpop.ps1
```

Credentials can be entered interactively or supplied through `GENERAC_USER` and
`GENERAC_PASS` environment variables.

For repository validation:

```powershell
python -m unittest discover -s tests -v
pre-commit run --all-files
```

## Credits and License

This project is distributed under the MIT license. It builds on the work in
[pjordanandrsn/ha-generac](https://github.com/pjordanandrsn/ha-generac) and the
upstream [ha-generac](https://github.com/binarydev/ha-generac) project.
