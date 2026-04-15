param(
    [switch]$PersistToUser = $true,
    [switch]$WriteDotEnv = $false
)

$ErrorActionPreference = "Stop"

function Convert-SecureStringToPlainText {
    param([Security.SecureString]$SecureString)
    if (-not $SecureString) { return "" }
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

Write-Host ""
Write-Host "Paste your OpenAI API key and press Enter." -ForegroundColor Cyan
Write-Host "Input is hidden for safety." -ForegroundColor DarkGray
$secureKey = Read-Host "OPENAI_API_KEY" -AsSecureString
$plainKey = Convert-SecureStringToPlainText -SecureString $secureKey
$plainKey = ($plainKey -replace '[\u200B-\u200D\uFEFF]', '').Trim()
if (
    ($plainKey.StartsWith('"') -and $plainKey.EndsWith('"')) -or
    ($plainKey.StartsWith("'") -and $plainKey.EndsWith("'"))
) {
    $plainKey = $plainKey.Substring(1, $plainKey.Length - 2).Trim()
}

if ([string]::IsNullOrWhiteSpace($plainKey)) {
    Write-Host "No key entered. Nothing changed." -ForegroundColor Yellow
    exit 1
}

if (-not $plainKey.StartsWith("sk-")) {
    Write-Host "Key does not look valid after sanitizing input. Make sure you paste only the key value (starts with 'sk-')." -ForegroundColor Red
    exit 1
}

# Set for this process/session.
$env:OPENAI_API_KEY = $plainKey
Write-Host "Set OPENAI_API_KEY for current PowerShell session." -ForegroundColor Green

if ($PersistToUser) {
    [Environment]::SetEnvironmentVariable("OPENAI_API_KEY", $plainKey, "User")
    Write-Host "Persisted OPENAI_API_KEY to User environment variables." -ForegroundColor Green
}

if ($WriteDotEnv) {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $dotenvPath = Join-Path $repoRoot ".env"
    "OPENAI_API_KEY=$plainKey" | Set-Content -Path $dotenvPath -Encoding UTF8
    Write-Host "Wrote key to .env at $dotenvPath" -ForegroundColor Green
}

Write-Host ""
Write-Host "Done. You can now run:" -ForegroundColor Cyan
Write-Host "  py -c ""from fastapi.testclient import TestClient; from api.main import app; c=TestClient(app); print(c.get('/debug/ai-status').json())""" -ForegroundColor DarkCyan
