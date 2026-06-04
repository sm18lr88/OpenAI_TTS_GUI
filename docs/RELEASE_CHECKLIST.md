# Release Checklist

Run this checklist before publishing a public release.

## Source Gates

- `uv run ruff check`
- `uv run ruff format --check .`
- `uv run ty check`
- `uv run pytest --ignore=tests/perf`
- Confirm `pyproject.toml`, `settings.py`, `__init__.py`, `installer.nsi`, release notes, and artifact names use the same version.

## Packaging Gates

- `uv run pyinstaller --noconfirm openai_tts.spec`
- Run the packaged executable with `--self-check` and `--gui-smoke`.
- Build `OpenAI-TTS-Setup.exe` with NSIS.
- Verify the portable zip, installer, and macOS zip are non-empty.
- Generate and verify `SHA256SUMS.txt`.

## Optional Local MSIX/WACK Gates

- Optional local MSIX packaging is documented in `docs/MSIX_LOCAL.md`; NSIS remains the recommended current release artifact.
- If locally testing MSIX, run `scripts\build_msix_local.ps1` after the PyInstaller output exists and confirm `MakeAppx` creates `dist\OpenAI-TTS.msix`.
- If locally validating WACK, run `scripts\validate_wack_local.ps1` with the Windows SDK App Certification Kit and keep the actual report under `reports\wack`.
- Store certification is not claimed unless a real report is parsed as passing for the package being claimed.

## Windows Installer Gates

- Install as a standard user.
- Confirm Start Menu shortcuts launch the app and uninstaller.
- Confirm uninstall refuses unsafe paths and removes only installed app files.
- Confirm user data under the app data directory is preserved unless explicitly removed by the user.

## Trust and Certification Notes

- Confirm README support, privacy, license, and ffmpeg requirements match the release.
- Scan release artifacts with Microsoft Defender or equivalent before publishing.
- For Microsoft Store MSI/EXE submission, provide a secure versioned package URL, silent installer parameters, privacy policy URL if required, and certification notes.
- Windows App Certification Kit or Store certification is not claimed unless a real report passes for the submitted package.
