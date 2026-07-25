# Optional Local MSIX and WACK Workflow

The supported release artifact remains the PyInstaller bundle packaged by NSIS as `OpenAI-TTS-Setup.exe`. The MSIX path is optional and local-only for developers who want to inspect a packaged desktop/full-trust app with Windows SDK tooling.

## Required Local Tools

- Windows SDK `MakeAppx` (`makeappx.exe`) to create `dist\OpenAI-TTS.msix`.
- Windows SDK `SignTool` (`signtool.exe`) when signing is requested.
- Windows SDK App Certification Kit (`appcert.exe`) to run local WACK validation.
- Python/uv project environment for the existing PyInstaller build.

## Build the MSIX Locally

Build the normal PyInstaller output first:

```powershell
uv run pyinstaller --noconfirm packaging/pyinstaller/openai_tts.spec
```

Then stage and pack the MSIX:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_msix_local.ps1
```

The script reads the project version from `pyproject.toml`, converts it to the four-part MSIX version form, stages files from `dist\OpenAI-TTS`, materializes `packaging\msix\AppxManifest.xml.in`, and runs `makeappx pack` to create `dist\OpenAI-TTS.msix`.

Optional signing examples. When signing is enabled, the script signs staged
`.exe`, `.dll`, and `.pyd` payload files before packing, then signs the MSIX.
This is needed for the WACK signed-file requirement, but it requires your own
local test certificate or production code-signing certificate.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_msix_local.ps1 -CertThumbprint "<certificate sha1 thumbprint>"
powershell -ExecutionPolicy Bypass -File scripts\build_msix_local.ps1 -PfxPath ".\local-msix.pfx" -PfxPassword "<password>"
```

Example local test certificate creation:

```powershell
$cert = New-SelfSignedCertificate -Type Custom -Subject "CN=OpenAI TTS GUI Local" -KeyUsage DigitalSignature -FriendlyName "OpenAI TTS GUI Local MSIX" -CertStoreLocation "Cert:\CurrentUser\My" -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3")
Export-PfxCertificate -Cert $cert -FilePath .\local-msix.pfx -Password (Read-Host -AsSecureString "PFX password")
```

## Validate with WACK Locally

After building and signing as needed, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate_wack_local.ps1
```

Defaults:

- Package: `dist\OpenAI-TTS.msix`
- Report: `reports\wack\OpenAI-TTS-WACK.xml`

The validation script locates `appcert.exe`, runs `appcert reset`, runs `appcert test -appxpackagepath <package> -reportoutputpath <report>`, and then parses the report with `scripts\check_wack_report.py`.

## Caveats

- This workflow does not claim Store certification.
- A local pass is not claimed unless a real report from the App Certification Kit exists and parses as `PASS`.
- The MSIX staging script removes redundant unsigned root Visual C++ runtime copies and unused Qt PDF/software-OpenGL payloads before packing. Keep `--self-check` and `--gui-smoke` passing after any future staging trim.
- PyInstaller/PyQt payloads can still trigger WACK blocked-executable checks because required runtime files reference process-launch APIs or contain blocked command strings. If only required runtime files remain in that failure, fixing it requires a packaging/runtime change or Microsoft review/waiver, not a repository-only metadata tweak.
- Store submission can still require additional review, identity, policy, and metadata outside this repository.
- NSIS remains the recommended and current release artifact for public releases.
