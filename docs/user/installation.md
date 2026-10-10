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

This installs four commands:

- `flow` — interactive CLI shell
- `flow-min` — plain non-interactive CLI (scripts, ssh, agents)
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

## Installing VLC

Flow plays audio through libvlc via `python-vlc`. `python-vlc` resolves the
library at `import vlc` time, so VLC must be installed *before* Flow imports
it. Flow's startup bootstrap (`backend.platform.bootstrap_vlc`) picks up a
standard install automatically on each OS.

### Linux

```bash
sudo apt install vlc        # Debian / Ubuntu
sudo dnf install vlc        # Fedora
sudo pacman -S vlc          # Arch
```

libvlc is resolved through ldconfig and its plugins are found next to it —
nothing to configure.

### macOS

```bash
brew install --cask vlc
```

Flow points `python-vlc` at `/Applications/VLC.app` automatically (plugin
dir: `/Applications/VLC.app/Contents/MacOS/plugins`). If you keep VLC
somewhere non-standard, export the plugin path before starting Flow:

```bash
export VLC_PLUGIN_PATH="/path/to/VLC.app/Contents/MacOS/plugins"
```

### Windows

Install the official [VLC installer](https://www.videolan.org/vlc/), or use
the portable zip (same 64-bit build, no installer):

```
https://get.videolan.org/vlc/3.0.21/win64/vlc-3.0.21-win64.zip
```

Flow finds `libvlc.dll` in the standard `VideoLAN\VLC` install locations
automatically. When running from a portable/extracted copy, point python-vlc
at it before starting Flow (PowerShell):

```powershell
$env:PYTHON_VLC_LIB_PATH = "C:\path\to\vlc\libvlc.dll"
$env:VLC_PLUGIN_PATH = "C:\path\to\vlc\plugins"
```

`flow --check` reports whether VLC resolved correctly on every OS.

## First run

Everything is stored under `~/.flow/` and created on demand — there is no
setup step. Run `flow` (or `flow-tui`, or `flow-web`) and start playing.