# Installation

## Requirements

- **Python 3.14+**
- **[VLC](https://www.videolan.org/vlc/)** — Flow uses `python-vlc` for all
  audio playback. If `vlc` cannot be imported, `flow` prints package-manager
  install hints and exits.
- **ffmpeg** (optional) — only needed to download in a format other than
  `webm` (opus, m4a, mp3). If ffmpeg is missing, downloads fall back to webm.
- **git** — used by the plugin system to clone plugin repositories.

Python dependencies (installed automatically by pip/uv): `yt-dlp`,
`python-vlc`, `flask`, `numpy`, `sounddevice`, `textual`, `ytmusicapi`,
`questionary`, `psutil`, `dbus-fast`/`dbus-python`, `pygobject`.

## Install from the repository

```bash
git clone https://github.com/Twinx015/Flow.git
cd Flow
uv sync            # or: pip install .
uv run flow        # or: flow
```

This installs three commands:

- `flow` — interactive CLI shell
- `flow-tui` — full-screen TUI
- `flow-web` — web GUI

## Install from PyPI

```bash
pip install flow-twinx
flow
```

## Verify the install

```bash
flow --check
```

prints a table of core dependencies (ffmpeg, vlc, yt-dlp, psutil, flask,
numpy, sounddevice, ytmusicapi) with pass/fail status.

## First run

Everything is stored under `~/.flow/` and created on demand — there is no
setup step. Run `flow` (or `flow-tui`, or `flow-web`) and start playing.