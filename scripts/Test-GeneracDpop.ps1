<#
.SYNOPSIS
Tests the Generac Auth0/DPoP login and Mobile Link API before installation.

.DESCRIPTION
Runs the maintained authentication and API modules directly from this
repository. MFA accounts must be completed through the Home Assistant config
flow because this non-interactive check does not hold a browser session open.
#>

[CmdletBinding()]
param(
    [string]$Username = $env:GENERAC_USER,
    [securestring]$Password,
    [switch]$SkipDependencyInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$venv = Join-Path $repoRoot ".venv-generac-test"
$pythonFile = Join-Path $repoRoot ".generac_dpop_test.py"

function Get-PythonPath {
    $venvPython = Join-Path $venv "Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        return $venvPython
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $python) {
        throw "Python 3 is required."
    }
    return $python.Source
}

function ConvertTo-PlainText([securestring]$Value) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

if ([string]::IsNullOrWhiteSpace($Username)) {
    $Username = Read-Host "Generac email"
}
if ($null -eq $Password) {
    if ([string]::IsNullOrWhiteSpace($env:GENERAC_PASS)) {
        $Password = Read-Host "Generac password" -AsSecureString
    }
    else {
        $Password = ConvertTo-SecureString $env:GENERAC_PASS -AsPlainText -Force
    }
}

$plainPassword = ConvertTo-PlainText $Password
$pythonCode = @'
import asyncio
import dataclasses
import json
import os
import sys
import types
from pathlib import Path

import aiohttp

REPO_ROOT = Path(__file__).resolve().parent
GENERAC_DIR = REPO_ROOT / "custom_components" / "generac"
components = types.ModuleType("custom_components")
components.__path__ = [str(REPO_ROOT / "custom_components")]
package = types.ModuleType("custom_components.generac")
package.__path__ = [str(GENERAC_DIR)]
sys.modules["custom_components"] = components
sys.modules["custom_components.generac"] = package

from custom_components.generac.api import GeneracApiClient
from custom_components.generac.auth import GeneracAuth
from custom_components.generac.auth import MfaRequiredError


async def main():
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True, quote_cookie=False)
    ) as session:
        try:
            auth = await GeneracAuth.login(
                session, os.environ["GENERAC_USER"], os.environ["GENERAC_PASS"]
            )
        except MfaRequiredError as error:
            print(f"MFA is required ({error.flow.mfa_type}); use the HA config flow.")
            return 2

        data = await GeneracApiClient(session, auth).async_get_data()

    print(f"Auth0/DPoP login succeeded. Found {len(data or {})} device(s).")
    for device_id, item in (data or {}).items():
        print(f"- {item.apparatus.name or item.apparatusDetail.name or device_id}")
        print(f"  id: {device_id}")
        print(f"  type: {item.apparatus.type}")
    return 0


try:
    raise SystemExit(asyncio.run(main()))
except Exception as error:
    print(f"Generac test failed: {type(error).__name__}: {error}", file=sys.stderr)
    raise SystemExit(1)
'@

Push-Location $repoRoot
try {
    if (-not $SkipDependencyInstall) {
        $python = Get-PythonPath
        if (-not (Test-Path -LiteralPath (Join-Path $venv "Scripts\python.exe"))) {
            & $python -m venv $venv
            if ($LASTEXITCODE -ne 0) { throw "Could not create the test virtual environment." }
        }
        $python = Join-Path $venv "Scripts\python.exe"
        & $python -m pip install "aiohttp==3.11.11" "dacite==1.9.2" "cryptography>=41"
        if ($LASTEXITCODE -ne 0) { throw "Could not install test dependencies." }
    }
    else {
        $python = Get-PythonPath
    }

    Set-Content -LiteralPath $pythonFile -Value $pythonCode -Encoding UTF8
    $env:GENERAC_USER = $Username
    $env:GENERAC_PASS = $plainPassword
    & $python $pythonFile
    exit $LASTEXITCODE
}
finally {
    Remove-Item -LiteralPath $pythonFile -Force -ErrorAction SilentlyContinue
    Remove-Item Env:\GENERAC_PASS -ErrorAction SilentlyContinue
    Pop-Location
}
