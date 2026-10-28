# Development

Use Windows with Python 3.12 (64-bit). From the project root:

Clone with Git for development. If you extracted a source ZIP instead, run
`git init` once before using the Git-based release and archive checks.

```powershell
./Setup-Capri.ps1 -Development
$env:TEMP = Join-Path $PWD 'data/tmp'
$env:TMP = $env:TEMP
$env:PYTHONDONTWRITEBYTECODE = '1'
./.venv/Scripts/python.exe -m unittest discover -s tests -q
./.venv/Scripts/python.exe tools/check_release.py
```

The setup script creates the temp directory. Tests use temporary profiles and
mocked model responses; they do not need Ollama or access your actual memories.
Two-monitor integration tests skip when only one display is available. The GitHub
workflow uses Qt's offscreen backend, with generated data in the runner temp folder.

An optional application smoke check uses a separate profile and exits automatically:

```powershell
./.venv/Scripts/python.exe -m capri.companion.app --profile evidence/smoke --smoke 8
```

This command displays a temporary pet unless `QT_QPA_PLATFORM=offscreen` is set.
It does not use the regular `data/` profile. Error logs are in that smoke profile.
The workflow checks that no runtime errors were logged.

`tools/preview_animation_library.py` renders Capri's own widget to `evidence/`;
it does not capture the desktop. Pillow is only needed for this development tool.
Runtime dependencies are pinned in `requirements.txt`.

## Layout

```text
capri/companion/          Desktop renderer, behavior, local model and memory
assets/companion/         Active animation manifests and prepared frames
assets/library/           Original library timing/provenance metadata
docs/                    Setup details, customization, privacy and previews
tests/                   Unit and native Qt integration tests
tools/                   Activity launcher, preview and release checks
persona.template.txt     Empty public seed template
data/                    Private local profile; ignored
.venv/                   Local Python environment; ignored
```

## Before publishing

Run tests and `tools/check_release.py`. Review new assets and confirm their
attribution/licensing in `ASSETS.md`. Confirm no local profile, journal export,
personal prompt, secret, machine-specific shortcut or private evidence is staged.
Do not copy `.git` from a personal working directory: use a fresh repository.
Add the intended remote yourself; this folder has no preconfigured remote.

Create a ZIP containing only checked public files:

```powershell
./.venv/Scripts/python.exe tools/make_source_archive.py
```

The archive is written beside the project folder; an existing archive is never
overwritten. It excludes Git history, environments, caches, local profiles and
ignored evidence. Use `--output` to choose another new filename.

The release checker examines tracked files plus non-ignored candidates, requires
an empty template, validates animation paths/hold times and rejects common local
state paths. It cannot recognize every secret or establish artwork permissions.
