<#
.SYNOPSIS
Tests the Generac Home Assistant integration API client before installation.

.DESCRIPTION
Runs the integration's GeneracApiClient directly from this repository without
copying files into Home Assistant. The script prompts for credentials when they
are not supplied and installs only the minimal API-client dependencies into a
local test environment.

.EXAMPLE
.\scripts\Test-GeneracIntegration.ps1

.EXAMPLE
$env:GENERAC_USER = "name@example.com"
$env:GENERAC_PASS = "password"
.\scripts\Test-GeneracIntegration.ps1 -RawJson
#>

[CmdletBinding()]
param(
    [string]$Username = $env:GENERAC_USER,
    [securestring]$Password,
    [switch]$RawJson,
    [switch]$UnsafeCookieJar,
    [switch]$SkipDependencyInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$testVenv = Join-Path $repoRoot ".venv-generac-test"
$testScript = Join-Path $repoRoot ".generac_api_test.py"
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

if ([string]::IsNullOrWhiteSpace($Username)) {
    $Username = Read-Host "Generac Mobile Link username"
}

$passwordWasFromEnv = $false
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

$pythonCode = @'
import asyncio
import dataclasses
import importlib.util
import json
import os
from pathlib import Path
import sys
import types

import aiohttp


REPO_ROOT = Path(__file__).resolve().parent
GENERAC_DIR = REPO_ROOT / "legacy" / "generac_updated"

custom_components_pkg = types.ModuleType("custom_components")
custom_components_pkg.__path__ = [str(REPO_ROOT / "custom_components")]
generac_pkg = types.ModuleType("custom_components.generac_updated")
generac_pkg.__path__ = [str(GENERAC_DIR)]
sys.modules["custom_components"] = custom_components_pkg
sys.modules["custom_components.generac_updated"] = generac_pkg

api_spec = importlib.util.spec_from_file_location(
    "custom_components.generac_updated.api",
    GENERAC_DIR / "api.py",
)
api_module = importlib.util.module_from_spec(api_spec)
sys.modules["custom_components.generac_updated.api"] = api_module
api_spec.loader.exec_module(api_module)

GeneracApiClient = api_module.GeneracApiClient
InvalidCredentialsException = api_module.InvalidCredentialsException
CannotConnectException = api_module.CannotConnectException


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, value):
        if dataclasses.is_dataclass(value):
            return dataclasses.asdict(value)
        return super().default(value)


async def main():
    username = os.environ["GENERAC_USER"]
    password = os.environ["GENERAC_PASS"]
    raw_json = os.environ.get("GENERAC_RAW_JSON") == "1"

    jar = aiohttp.CookieJar(unsafe=os.environ.get("GENERAC_UNSAFE_COOKIE_JAR") == "1")
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        client = GeneracApiClient(username, password, session)
        data = await client.async_get_data()

    if data is None:
        print("Connected, but the API returned no generator data.")
        return 2

    if raw_json:
        print(json.dumps(data, cls=EnhancedJSONEncoder, indent=2, sort_keys=True))
        return 0

    print(f"Connected to Generac Mobile Link. Found {len(data)} generator(s).")
    for generator_id, item in data.items():
        apparatus = item.apparatus
        detail = item.apparatusDetail
        print("")
        print(f"- {apparatus.name or detail.name or generator_id}")
        print(f"  id: {generator_id}")
        print(f"  serial: {apparatus.serialNumber or detail.serialNumber or 'unknown'}")
        print(f"  model: {apparatus.modelNumber or 'unknown'}")
        print(f"  status: {detail.statusLabel or detail.statusText or detail.apparatusStatus or 'unknown'}")
        print(f"  connected: {detail.isConnected}")
        print(f"  last seen: {detail.lastSeen or 'unknown'}")

    return 0


try:
    raise SystemExit(asyncio.run(main()))
except InvalidCredentialsException:
    print("Authentication failed: username or password was rejected.", file=sys.stderr)
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
    $env:GENERAC_USER = $Username
    $env:GENERAC_PASS = $plainPassword
    $env:GENERAC_RAW_JSON = if ($RawJson) { "1" } else { "0" }
    $env:GENERAC_UNSAFE_COOKIE_JAR = if ($UnsafeCookieJar) { "1" } else { "0" }

    $pythonToRun = Get-PythonCommand
    & $pythonToRun $testScript
    exit $LASTEXITCODE
}
finally {
    Remove-Item -LiteralPath $testScript -Force -ErrorAction SilentlyContinue
    if (-not $passwordWasFromEnv) {
        Remove-Item Env:\GENERAC_PASS -ErrorAction SilentlyContinue
    }
    Remove-Item Env:\GENERAC_RAW_JSON -ErrorAction SilentlyContinue
    Remove-Item Env:\GENERAC_UNSAFE_COOKIE_JAR -ErrorAction SilentlyContinue
    Pop-Location
}
