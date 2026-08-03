# Release Checklist

Run this checklist before publishing a public release.

## Source Gates

- `uv run ruff check`
- `uv run ruff format --check .`
- `uv run ty check`
- `uv run pytest --ignore=tests/perf`
- `make coverage`
- Confirm `pyproject.toml`, `settings.py`, `__init__.py`, `packaging/windows/installer.nsi`, release notes, and artifact names use the same version.

## Packaging Gates

- `uv run pyinstaller --noconfirm packaging/pyinstaller/openai_tts.spec`
- Run the packaged executable with `--self-check` and `--gui-smoke`.
- Build `OpenAI-TTS-Setup.exe` with NSIS.
- Verify the portable zip, installer, and macOS zip are non-empty.
- Generate and verify `SHA256SUMS.txt`.

## Optional Local MSIX/WACK Gates

- `docs/MSIX_LOCAL.md` documents optional local MSIX packaging. NSIS remains the recommended release artifact.
- If you test MSIX locally, run `scripts\build_msix_local.ps1` after the PyInstaller output exists. Confirm that `MakeAppx` creates `dist\OpenAI-TTS.msix`.
- If you validate WACK locally, run `scripts\validate_wack_local.ps1` with the Windows SDK App Certification Kit. Keep the actual report under `reports\wack`.
- Do not claim Store certification unless a real report parses as passing for the package you claim.

## Windows Installer Gates

- Install as a standard user.
- Confirm Start Menu shortcuts launch the app and uninstaller.
- Confirm uninstall refuses unsafe paths and removes only installed app files.
- Confirm user data under the app data directory is preserved unless explicitly removed by the user.

## Trust and Certification Notes

- Confirm README support, privacy, license, and ffmpeg requirements match the release.
- Scan release artifacts with Microsoft Defender or equivalent before publishing.
- For Microsoft Store MSI/EXE submission, provide a secure versioned package URL and silent installer parameters. Provide a privacy policy URL if required. Provide certification notes.
- Windows App Certification Kit or Store certification is not claimed unless a real report passes for the submitted package.
