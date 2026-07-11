<#
.SYNOPSIS
Tests the Generac Auth0 authorization-code PKCE flow.

.DESCRIPTION
Run once without arguments to generate and save an Auth0 login URL. Open the URL,
sign in, and copy the final custom-scheme callback URL. Run again with
-CallbackUrl to exchange the code for tokens and call the Mobile Link API.

.EXAMPLE
.\scripts\Test-GeneracPkce.ps1

.EXAMPLE
.\scripts\Test-GeneracPkce.ps1 -OpenBrowser

.EXAMPLE
.\scripts\Test-GeneracPkce.ps1 -CallbackUrl "com.generac.standbystatus.auth0://..."

.EXAMPLE
$env:GENERAC_USER = "name@example.com"
$env:GENERAC_PASS = "password"
.\scripts\Test-GeneracPkce.ps1 -AutoLogin
#>

[CmdletBinding()]
param(
    [string]$Username = $env:GENERAC_USER,
    [securestring]$Password,
    [switch]$AutoLogin,
    [string]$CallbackUrl,
    [switch]$OpenBrowser,
    [switch]$SkipDependencyInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$testVenv = Join-Path $repoRoot ".venv-generac-test"
$testScript = Join-Path $repoRoot ".generac_pkce_test.py"
$stateFile = Join-Path $repoRoot ".generac_pkce_state.json"
$testPythonVersion = "3.12"

function ConvertFrom-SecureStringToPlainText {
    param([securestring]$SecureString)

    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

function Get-PythonCommand {
    $candidates = @(
        (Join-Path $testVenv "Scripts\python.exe"),
        "python",
        "python3",
        "py"
    )

    foreach ($candidate in $candidates) {
        $resolved = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $resolved) {
            return $resolved.Source
        }
    }

    throw "Python was not found. Install Python or uv, then rerun this script."
}

function Get-PythonVersion {
    param([string]$Python)

    $version = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return $version.Trim()
}

function Invoke-Native {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
    }
}

$passwordWasFromEnv = $false
$plainPassword = ""
if ($AutoLogin) {
    if ([string]::IsNullOrWhiteSpace($Username)) {
        $Username = Read-Host "Generac Mobile Link username"
    }

    if ($null -eq $Password) {
        if (-not [string]::IsNullOrEmpty($env:GENERAC_PASS)) {
            $plainPassword = $env:GENERAC_PASS
            $passwordWasFromEnv = $true
        }
        else {
            $Password = Read-Host "Generac Mobile Link password" -AsSecureString
            $plainPassword = ConvertFrom-SecureStringToPlainText $Password
        }
    }
    else {
        $plainPassword = ConvertFrom-SecureStringToPlainText $Password
    }
}

$pythonCode = @'
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup


REPO_ROOT = Path(__file__).resolve().parent
GENERAC_DIR = REPO_ROOT / "custom_components" / "generac"
STATE_FILE = REPO_ROOT / ".generac_pkce_state.json"

custom_components_pkg = types.ModuleType("custom_components")
custom_components_pkg.__path__ = [str(REPO_ROOT / "custom_components")]
generac_pkg = types.ModuleType("custom_components.generac")
generac_pkg.__path__ = [str(GENERAC_DIR)]
sys.modules["custom_components"] = custom_components_pkg
sys.modules["custom_components.generac"] = generac_pkg

api_spec = importlib.util.spec_from_file_location(
    "custom_components.generac.api",
    GENERAC_DIR / "api.py",
)
api_module = importlib.util.module_from_spec(api_spec)
sys.modules["custom_components.generac.api"] = api_module
api_spec.loader.exec_module(api_module)

Auth0PkceSession = api_module.Auth0PkceSession
GeneracApiClient = api_module.GeneracApiClient
InvalidCredentialsException = api_module.InvalidCredentialsException
CannotConnectException = api_module.CannotConnectException


async def submit_hosted_login(session, auth_url, username, password):
    response = await session.get(auth_url, allow_redirects=True)
    for _ in range(8):
        page = await response.text()
        form = BeautifulSoup(page, "html.parser").select_one("form")
        if form is None:
            raise CannotConnectException(f"Auth0 hosted login form not found at {response.url}")

        form_data = []
        for input_element in form.select("input[name]"):
            name = input_element.attrs["name"]
            field_type = input_element.attrs.get("type", "").lower()
            lower_name = name.lower()
            value = input_element.attrs.get("value", "")
            if field_type == "password" or "password" in lower_name:
                value = password
            elif (
                lower_name in ("username", "email", "login", "signinname")
                or "username" in lower_name
                or "email" in lower_name
            ):
                value = username
            form_data.append((name, value))

        response = await session.post(
            urljoin(str(response.url), form.attrs.get("action") or str(response.url)),
            data=form_data,
            allow_redirects=False,
        )
        while response.status in (301, 302, 303, 307, 308):
            location = response.headers.get("location", "")
            if location.startswith("com.generac."):
                return location
            response = await session.get(
                urljoin(str(response.url), location), allow_redirects=False
            )

    raise CannotConnectException("Auth0 hosted login did not return a callback URL")


async def main():
    callback_url = os.environ.get("GENERAC_CALLBACK_URL", "")
    auto_login = os.environ.get("GENERAC_AUTO_LOGIN") == "1"

    if not callback_url and not auto_login:
        state = Auth0PkceSession.create()
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print("PKCE state saved to .generac_pkce_state.json")
        print("")
        print(state["auth_url"])
        return 0

    if auto_login:
        state = Auth0PkceSession.create()
    elif not STATE_FILE.exists():
        print("Missing .generac_pkce_state.json. Run without -CallbackUrl first.", file=sys.stderr)
        return 2
    else:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))

    async with aiohttp.ClientSession() as session:
        if auto_login:
            callback_url = await submit_hosted_login(
                session,
                state["auth_url"],
                os.environ["GENERAC_USER"],
                os.environ["GENERAC_PASS"],
            )
        token_data = await Auth0PkceSession.exchange_callback(
            session,
            callback_url,
            state["code_verifier"],
            state["state"],
        )
        client = GeneracApiClient(
            "",
            "",
            session,
            access_token=token_data.get("access_token", ""),
            refresh_token=token_data.get("refresh_token", ""),
            expires_at=token_data.get("expires_at", 0),
        )
        data = await client.async_get_data()

    if not client.auth_method.startswith("auth0"):
        print(
            "The PKCE token was accepted, but the client used the cookie fallback."
        )
        return 4

    if data is None:
        print("PKCE token exchange succeeded, but the API returned no generator data.")
        return 3

    print(
        f"PKCE bearer login worked via {client.auth_method}. "
        f"Found {len(data)} generator(s)."
    )
    for generator_id, item in data.items():
        apparatus = item.apparatus
        detail = item.apparatusDetail
        print("")
        print(f"- {apparatus.name or detail.name or generator_id}")
        print(f"  id: {generator_id}")
        print(f"  serial: {apparatus.serialNumber or detail.serialNumber or 'unknown'}")
        print(f"  status: {detail.statusLabel or detail.statusText or detail.apparatusStatus or 'unknown'}")

    return 0


try:
    raise SystemExit(asyncio.run(main()))
except InvalidCredentialsException as err:
    print(f"Authentication failed: {err}", file=sys.stderr)
    raise SystemExit(10)
except CannotConnectException as err:
    print(f"Connection failed: {err}", file=sys.stderr)
    raise SystemExit(11)
'@

Push-Location $repoRoot
try {
    if (-not $SkipDependencyInstall) {
        $uv = Get-Command "uv" -ErrorAction SilentlyContinue
        if ($null -ne $uv) {
            $testPython = Join-Path $testVenv "Scripts\python.exe"
            if (Test-Path $testPython) {
                $existingVersion = Get-PythonVersion $testPython
                if ($existingVersion -ne $testPythonVersion) {
                    Remove-Item -LiteralPath $testVenv -Recurse -Force
                }
            }
            if (-not (Test-Path $testPython)) {
                Invoke-Native $uv.Source @("venv", "--python", $testPythonVersion, $testVenv)
            }
            Invoke-Native $uv.Source @(
                "pip",
                "install",
                "--python",
                $testPython,
                "aiohttp==3.11.11",
                "beautifulsoup4==4.12.3",
                "dacite==1.8.1"
            )
        }
        else {
            $python = Get-PythonCommand
            if (-not (Test-Path $testVenv)) {
                Invoke-Native $python @("-m", "venv", $testVenv)
            }
            $python = Get-PythonCommand
            Invoke-Native $python @(
                "-m",
                "pip",
                "install",
                "aiohttp==3.11.11",
                "beautifulsoup4==4.12.3",
                "dacite==1.8.1"
            )
        }
    }

    Set-Content -LiteralPath $testScript -Value $pythonCode -Encoding UTF8
    $env:GENERAC_CALLBACK_URL = $CallbackUrl
    $env:GENERAC_AUTO_LOGIN = if ($AutoLogin) { "1" } else { "0" }
    if ($AutoLogin) {
        $env:GENERAC_USER = $Username
        $env:GENERAC_PASS = $plainPassword
    }

    $pythonToRun = Get-PythonCommand
    & $pythonToRun $testScript
    $exitCode = $LASTEXITCODE

    if ($OpenBrowser -and [string]::IsNullOrWhiteSpace($CallbackUrl) -and (Test-Path $stateFile)) {
        $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
        Start-Process $state.auth_url
    }

    exit $exitCode
}
finally {
    Remove-Item -LiteralPath $testScript -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\GENERAC_CALLBACK_URL -ErrorAction SilentlyContinue
    Remove-Item Env:\GENERAC_AUTO_LOGIN -ErrorAction SilentlyContinue
    if ($AutoLogin -and -not $passwordWasFromEnv) {
        Remove-Item Env:\GENERAC_PASS -ErrorAction SilentlyContinue
    }
    Pop-Location
}
