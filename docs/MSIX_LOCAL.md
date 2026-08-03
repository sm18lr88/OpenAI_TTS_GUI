# Optional Local MSIX and WACK Workflow

The supported release artifact remains the PyInstaller bundle that NSIS packages as
`OpenAI-TTS-Setup.exe`. The MSIX path is optional and local only. It lets developers inspect a
packaged desktop/full-trust app with Windows SDK tooling.

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

The script reads the project version from `pyproject.toml`. It converts the version to the
four-part MSIX form. It stages files from `dist\OpenAI-TTS`. It materializes
`packaging\msix\AppxManifest.xml.in`. It runs `makeappx pack` to create `dist\OpenAI-TTS.msix`.

These are optional signing examples. When signing is enabled, the script signs staged
`.exe`, `.dll`, and `.pyd` payload files before packing. It then signs the MSIX.
The WACK signed-file requirement needs this. It also requires your own local test certificate
or production code-signing certificate.

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

The validation script finds `appcert.exe` and runs `appcert reset`. It then runs
`appcert test -appxpackagepath <package> -reportoutputpath <report>`. It parses the report with
`scripts\check_wack_report.py`.

## Caveats

- This workflow does not claim Store certification.
- Do not claim a local pass unless a real App Certification Kit report exists and parses as `PASS`.
- The MSIX staging script removes redundant unsigned root Visual C++ runtime copies and unused Qt PDF/software-OpenGL payloads before packing. After any future staging trim, keep `--self-check` and `--gui-smoke` passing.
- PyInstaller/PyQt payloads can still trigger WACK blocked-executable checks. Required runtime files can reference process-launch APIs or contain blocked command strings. If only required runtime files remain in that failure, a packaging/runtime change or Microsoft review/waiver is required. A repository-only metadata tweak cannot fix it.
- Store submission can still require additional review, identity, policy, and metadata outside this repository.
- NSIS remains the recommended and current release artifact for public releases.
