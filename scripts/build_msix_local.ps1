param(
    [string]$Version,
    [string]$Publisher = "CN=OpenAI TTS GUI Local",
    [string]$PyInstallerOutput = "dist\OpenAI-TTS",
    [string]$ManifestTemplate = "packaging\msix\AppxManifest.xml.in",
    [string]$StagePath = "dist\msix-stage",
    [string]$PackagePath = "dist\OpenAI-TTS.msix",
    [string]$CertThumbprint,
    [string]$PfxPath,
    [string]$PfxPassword
)

$ErrorActionPreference = "Stop"

function Resolve-Tool($Name) {
    $tool = Get-Command -Name $Name -ErrorAction SilentlyContinue
    if ($tool) { return $tool.Source }
    return $null
}

function Get-ProjectVersion {
    if ($Version) { return $Version }
    $pyproject = Get-Content -LiteralPath "pyproject.toml" -Raw
    if ($pyproject -match '(?m)^version\s*=\s*"([^"]+)"') { return $Matches[1] }
    throw "Version was not provided and pyproject.toml does not contain a project version."
}

function Convert-ToMsixVersion([string]$InputVersion) {
    $parts = $InputVersion -split '[^0-9]+' | Where-Object { $_ -ne "" }
    if ($parts.Count -eq 0) { throw "Version '$InputVersion' cannot be converted to MSIX numeric form." }
    while ($parts.Count -lt 4) { $parts += "0" }
    return ($parts[0..3] -join ".")
}

function Write-PlaceholderPng([string]$Path, [int]$Width, [int]$Height) {
    Add-Type -AssemblyName System.Drawing
    $bitmap = New-Object System.Drawing.Bitmap $Width, $Height
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.Clear([System.Drawing.Color]::FromArgb(32, 33, 36))
        } finally {
            $graphics.Dispose()
        }
        $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $bitmap.Dispose()
    }
}

function Invoke-SignTarget([string]$SignTool, [string]$Target) {
    if ($CertThumbprint) {
        & $SignTool sign /fd SHA256 /sha1 $CertThumbprint $Target
    } elseif ($PfxPath) {
        $args = @("sign", "/fd", "SHA256", "/f", $PfxPath)
        if ($PfxPassword) { $args += @("/p", $PfxPassword) }
        $args += $Target
        & $SignTool @args
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Remove-StagedPath([string]$RelativePath) {
    $path = Join-Path $StagePath $RelativePath
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

if (-not (Test-Path -LiteralPath $PyInstallerOutput)) {
    throw "PyInstaller output not found at '$PyInstallerOutput'. Run: uv run pyinstaller --noconfirm openai_tts.spec"
}
if (-not (Test-Path -LiteralPath (Join-Path $PyInstallerOutput "openai_tts_bin.exe"))) {
    throw "Packaged executable not found: '$PyInstallerOutput\openai_tts_bin.exe'."
}

$makeappx = Resolve-Tool "makeappx.exe"
if (-not $makeappx) { throw "makeappx.exe is unavailable. Install the Windows SDK and add MakeAppx to PATH." }

if (Test-Path -LiteralPath $StagePath) { Remove-Item -LiteralPath $StagePath -Recurse -Force }
New-Item -ItemType Directory -Path $StagePath | Out-Null
Copy-Item -Path (Join-Path $PyInstallerOutput "*") -Destination $StagePath -Recurse -Force
Remove-StagedPath "_internal\PyQt6\Qt6\translations"
Remove-StagedPath "_internal\VCRUNTIME140.dll"
Remove-StagedPath "_internal\VCRUNTIME140_1.dll"
Remove-StagedPath "_internal\PyQt6\Qt6\plugins\imageformats\qpdf.dll"
Remove-StagedPath "_internal\PyQt6\Qt6\plugins\imageformats\qtga.dll"
Remove-StagedPath "_internal\PyQt6\Qt6\plugins\imageformats\qtiff.dll"
Remove-StagedPath "_internal\PyQt6\Qt6\plugins\imageformats\qwbmp.dll"
Remove-StagedPath "_internal\PyQt6\Qt6\bin\Qt6Pdf.dll"
Remove-StagedPath "_internal\PyQt6\Qt6\bin\opengl32sw.dll"

$assetsPath = Join-Path $StagePath "Assets"
New-Item -ItemType Directory -Path $assetsPath -Force | Out-Null
Write-PlaceholderPng (Join-Path $assetsPath "Square44x44Logo.png") 44 44
Write-PlaceholderPng (Join-Path $assetsPath "Square150x150Logo.png") 150 150
Write-PlaceholderPng (Join-Path $assetsPath "Wide310x150Logo.png") 310 150
Write-PlaceholderPng (Join-Path $assetsPath "StoreLogo.png") 50 50

$msixVersion = Convert-ToMsixVersion (Get-ProjectVersion)
$manifest = Get-Content -LiteralPath $ManifestTemplate -Raw
$manifest = $manifest.Replace("{{VERSION}}", $msixVersion).Replace("{{PUBLISHER}}", $Publisher)
Set-Content -LiteralPath (Join-Path $StagePath "AppxManifest.xml") -Value $manifest -Encoding UTF8

$signtool = $null
if ($CertThumbprint -or $PfxPath) {
    $signtool = Resolve-Tool "signtool.exe"
    if (-not $signtool) { throw "signtool.exe is unavailable. Install the Windows SDK or skip signing." }
    Get-ChildItem -LiteralPath $StagePath -Recurse -File |
        Where-Object { $_.Extension -in @(".exe", ".dll", ".pyd") } |
        ForEach-Object { Invoke-SignTarget $signtool $_.FullName }
}

if (Test-Path -LiteralPath $PackagePath) { Remove-Item -LiteralPath $PackagePath -Force }
& $makeappx pack /d $StagePath /p $PackagePath /o
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($signtool) {
    Invoke-SignTarget $signtool $PackagePath
}

Write-Host "Created $PackagePath"
