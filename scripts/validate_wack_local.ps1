param(
    [string]$PackagePath = "dist\OpenAI-TTS.msix",
    [string]$ReportPath = "reports\wack\OpenAI-TTS-WACK.xml"
)

$ErrorActionPreference = "Stop"

function Resolve-AppCert {
    $tool = Get-Command -Name "appcert.exe" -ErrorAction SilentlyContinue
    if ($tool) { return $tool.Source }
    $fallback = "C:\Program Files (x86)\Windows Kits\10\App Certification Kit\appcert.exe"
    if (Test-Path -LiteralPath $fallback) { return $fallback }
    return $null
}

if (-not (Test-Path -LiteralPath $PackagePath)) {
    Write-Error "MSIX package unavailable: $PackagePath. Build it first with scripts/build_msix_local.ps1."
    exit 1
}
$resolvedPackagePath = (Resolve-Path -LiteralPath $PackagePath).Path

$appcert = Resolve-AppCert
if (-not $appcert) {
    Write-Error "appcert.exe not found. Install the Windows SDK App Certification Kit."
    exit 1
}

$reportDirectory = Split-Path -Path $ReportPath -Parent
if ($reportDirectory) { New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null }
$reportDirectoryToResolve = "."
if ($reportDirectory) { $reportDirectoryToResolve = $reportDirectory }
$resolvedReportDirectory = (Resolve-Path -LiteralPath $reportDirectoryToResolve).Path
$resolvedReportPath = Join-Path $resolvedReportDirectory (Split-Path -Path $ReportPath -Leaf)
if (Test-Path -LiteralPath $resolvedReportPath) {
    Remove-Item -LiteralPath $resolvedReportPath -Force
}

& $appcert reset
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $appcert test -appxpackagepath $resolvedPackagePath -reportoutputpath $resolvedReportPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "WACK test failed or was blocked. Inspect the App Certification Kit output."
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $resolvedReportPath)) {
    Write-Error "WACK report unavailable after appcert completed: $resolvedReportPath"
    exit 1
}

& python "scripts/check_wack_report.py" $resolvedReportPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "WACK report is not a parsed pass. Certification is not claimed."
    exit $LASTEXITCODE
}

Write-Host "WACK report parsed as PASS: $resolvedReportPath"
