# Copyright (c) Microsoft Corporation. Licensed under the MIT License.
# MIT License
#
# Copyright (c) Microsoft Corporation.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE

[CmdletBinding(PositionalBinding=$false)]
param(
    [switch]$Uninstall,
    [switch]$Help
)
& {
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$ExtensionName = 'aigateway'
$ExpectedApiVersion = '2025-09-01-preview'
$PublicWheelUrl = 'https://github.com/Azure/ai-gateway/releases/download/cli-v1.0.0b22/aigateway-1.0.0b22-py3-none-any.whl'
$ExpectedSha256 = '3363ee0efde6ec22f445fd11f2b6b625867c1ab49b8ab76108f6e1bfa920060a'

if ($Help) {
    Write-Host 'Usage: install.ps1 [-Uninstall] [-Help]'
    Write-Host 'Installs the pinned public aigateway 1.0.0b22 wheel; no source overrides.'
    return
}

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

function Invoke-NativeText {
    param(
        [string]$Command,
        [string[]]$Arguments
    )
    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()
    try {
        & $Command @Arguments 1>$stdoutPath 2>$stderrPath
        $exitCode = $LASTEXITCODE
        $stdout = [System.IO.File]::ReadAllText($stdoutPath).Trim()
        $stderr = [System.IO.File]::ReadAllText($stderrPath).Trim()
        if ($exitCode -ne 0) {
            $details = @(
                @($stderr, $stdout) |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
            )
            throw (
                "$Command failed with exit code $exitCode." +
                $(if ($details.Count) {
                    [Environment]::NewLine + ($details -join [Environment]::NewLine)
                } else {
                    ''
                })
            )
        }

        return $stdout
    } finally {
        Remove-Item -LiteralPath $stdoutPath, $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Confirm-Sha256 {
    param(
        [string]$AssetName,
        [string]$Path,
        [string]$ExpectedDigest
    )
    if ($ExpectedDigest -notmatch '^[0-9A-Fa-f]{64}$') {
        throw "Invalid expected SHA-256 digest for '$AssetName'."
    }
    $actualDigest = (
        Get-FileHash -LiteralPath $Path -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($actualDigest -ne $ExpectedDigest.ToLowerInvariant()) {
        throw "SHA-256 verification failed for '$AssetName'."
    }
}

function Save-HttpsWheel {
    param(
        [System.Uri]$Uri,
        [string]$OutFile
    )

    Add-Type -AssemblyName System.Net.Http
    $desktop = $PSVersionTable.PSEdition -eq 'Desktop'
    $originalProtocol = [System.Net.ServicePointManager]::SecurityProtocol
    try {
        if ($desktop) {
            [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        }
        for ($redirectCount = 0; $redirectCount -le 10; $redirectCount++) {
            if (-not $Uri.IsAbsoluteUri -or $Uri.Scheme -ne 'https' -or $Uri.UserInfo) {
                throw 'Public wheel download requires HTTPS URLs without embedded credentials.'
            }
            $request = @{
                Uri = $Uri
                OutFile = $OutFile
                UseBasicParsing = $true
                MaximumRedirection = 0
                ErrorAction = 'Stop'
            }
            if (-not $desktop) {
                $request.SslProtocol = 'Tls12'
            }
            try {
                Invoke-WebRequest @request
                return
            } catch [System.Net.WebException], [System.Net.Http.HttpRequestException] {
                $responseProperty = $_.Exception.PSObject.Properties['Response']
                if ($null -eq $responseProperty -or $null -eq $responseProperty.Value) {
                    throw
                }
                $response = $responseProperty.Value
                try {
                    if ([int]$response.StatusCode -notin @(301, 302, 303, 307, 308)) {
                        throw
                    }
                    if ($redirectCount -eq 10) {
                        throw 'Public wheel download exceeded 10 redirects.'
                    }
                    if ($response -is [System.Net.Http.HttpResponseMessage]) {
                        $location = [string]$response.Headers.Location
                    } else {
                        $location = [string]$response.Headers['Location']
                    }
                    if ([string]::IsNullOrWhiteSpace($location)) {
                        throw 'Public wheel redirect has no Location header.'
                    }
                    # Disable automatic redirects so every next URL is checked before use.
                    $Uri = [System.Uri]::new($Uri, $location)
                } finally {
                    $response.Dispose()
                }
            }
        }
    } finally {
        if ($desktop) {
            [System.Net.ServicePointManager]::SecurityProtocol = $originalProtocol
        }
    }
}

Require-Command 'az'

if ($Uninstall) {
    $installedName = Invoke-NativeText 'az' @(
        'extension', 'list', '--query', "[?name=='$ExtensionName'].name",
        '--output', 'tsv'
    )
    if ($installedName -eq $ExtensionName) {
        Invoke-NativeText 'az' @(
            'extension', 'remove', '--name', $ExtensionName
        ) | Out-Null
        Write-Host "Uninstalled '$ExtensionName'."
    } elseif ([string]::IsNullOrEmpty($installedName)) {
        Write-Host "'$ExtensionName' is not installed; nothing to do."
    } else {
        throw 'Unexpected extension list response; refusing to uninstall.'
    }
    return
}


if (-not $PublicWheelUrl -or -not $ExpectedSha256) {
    throw 'Public release is not activated; no approved wheel URL/SHA-256 pair is embedded.'
}
if (@(Get-ChildItem Env:AIGATEWAY_INSTALL_*).Count -gt 0) {
    throw 'AIGATEWAY_INSTALL_* overrides are not supported by this pinned public installer.'
}
$publicUri = [System.Uri]$PublicWheelUrl
$wheelName = [System.IO.Path]::GetFileName($publicUri.AbsolutePath)
if ($wheelName -notmatch '^aigateway-[A-Za-z0-9.+_-]+-py3-none-any\.whl$') {
    throw (
        'Public wheel URL must end with an exact aigateway wheel ' +
        'filename.'
    )
}
$tempDir = Join-Path (
    [System.IO.Path]::GetTempPath()
) ("aigateway-install-" + [System.Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempDir | Out-Null
try {
    $downloadDir = Join-Path $tempDir 'artifact'
    New-Item -ItemType Directory -Path $downloadDir | Out-Null
    $wheelPath = Join-Path $downloadDir $wheelName
    Save-HttpsWheel -Uri $publicUri -OutFile $wheelPath

    $wheels = @(
        Get-ChildItem -LiteralPath $downloadDir -Filter 'aigateway-*.whl' -File
    )
    if ($wheels.Count -ne 1) {
        throw 'Expected exactly one aigateway-*.whl in public URL.'
    }
    $wheel = $wheels[0]
    if ($wheel.Name -notmatch '^aigateway-(?<Version>[A-Za-z0-9.+_-]+)-py3-none-any\.whl$') {
        throw "Unexpected wheel filename '$($wheel.Name)'."
    }
    $expectedVersion = $Matches.Version

    $bytes = [System.IO.File]::ReadAllBytes($wheel.FullName)
    if ($bytes.Length -eq 0) {
        throw 'Public wheel download is empty.'
    }
    $prefixLength = [Math]::Min(512, $bytes.Length)
    $prefix = [System.Text.Encoding]::ASCII.GetString(
        $bytes,
        0,
        $prefixLength
    )
    if ($prefix -match '(?i)<html|<!doctype') {
        throw 'Public wheel download looks like an HTML page, not a wheel.'
    }
    Confirm-Sha256 $wheel.Name $wheel.FullName $ExpectedSha256

    # Azure CLI skips --upgrade for an equal version, even if its bytes differ.
    $installedVersion = Invoke-NativeText 'az' @(
        'extension', 'list', '--query', "[?name=='$ExtensionName'].version",
        '--output', 'tsv'
    )
    if ($installedVersion -eq $expectedVersion) {
        Invoke-NativeText 'az' @(
            'extension', 'remove', '--name', $ExtensionName
        ) | Out-Null
    }

    Invoke-NativeText 'az' @(
        'extension', 'add', '--upgrade', '--yes',
        '--source', $wheel.FullName, '--output', 'none'
    ) | Out-Null

    $installed = (
        Invoke-NativeText 'az' @(
            'aigateway', 'version', '--output', 'json'
        ) | ConvertFrom-Json
    )
    if ($installed.extensionName -ne $ExtensionName) {
        throw "Installed extension name '$($installed.extensionName)' is not '$ExtensionName'."
    }
    if ($installed.extensionVersion -ne $expectedVersion) {
        throw "Installed version '$($installed.extensionVersion)' does not match wheel '$expectedVersion'."
    }
    if ($installed.apiVersion -ne $ExpectedApiVersion) {
        throw "Supported API '$($installed.apiVersion)' does not match '$ExpectedApiVersion'."
    }

    Write-Host "Installed '$ExtensionName' $expectedVersion successfully."
    Write-Host 'Verify with: az aigateway version'
} finally {
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
}
