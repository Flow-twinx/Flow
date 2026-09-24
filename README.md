# Flow

A terminal music player with online streaming and offline library modes.

Flow detects your connection and picks automatically: **online mode**
streams from YouTube (via `yt-dlp` and `python-vlc`) and JioSaavn, **offline
mode** plays your local library under `~/.flow/downloads/`. All state —
downloads, likes, playlists, settings — lives in one folder and is shared
between the CLI shell, the Textual TUI, and the web GUI.

## Features

- **Dual-mode** — automatic offline/online detection with manual `switch`
- **Online mode** — YouTube search/stream, radio mixes, JioSaavn (`savan`)
- **Offline mode** — local library with search, liked songs, and tab completion
- **Downloads** — save tracks from YouTube (`-d`), formats: webm/opus/m4a/mp3
- **Repeat & shuffle** — `-r [n]` loops, `-s` randomizes
- **Playlists** — create, edit, merge, dedupe, reorder, export/import `.m3u`
- **Like/unlike** — favorites in `~/.flow/library.json`, auto-download on like
- **Background play** — play in the background and go back to your shell
- **Visualizer** — audio-reactive spectrum bars (or synced lyrics) while playing
- **Three interfaces** — interactive CLI shell, full-screen [TUI](docs/user/interface.md), and a [web GUI](docs/user/interface.md) on port 5000
- **Plugins** — community plugins run in isolated processes

## Requirements

- Python 3.14+
- [VLC](https://www.videolan.org/vlc/) (for `python-vlc` audio playback)
- ffmpeg (optional, only for non-webm download formats)

## Installation

```bash
git clone https://github.com/Twinx015/Flow.git
cd Flow
uv sync            # or: pip install .
uv run flow
```

Or from PyPI:

```bash
pip install flow-twinx
flow
```

Verify with `flow --check`. See [Installation](docs/user/installation.md)
for details.

## Quick start

```bash
flow -pl "never gonna give you up"   # stream from YouTube (foreground)
flow -pl "never gonna give you up" -bg   # ...in the background
flow -sh "daft punk"                 # search, show results
flow --play-off "my song"            # play from the local library (auto-bg)
flow --radio-off                     # shuffle-loop the whole library (auto-bg)
flow                                 # interactive shell (type `help`)
flow-tui                             # full-screen TUI
flow-web                             # web GUI → http://127.0.0.1:5000
```

Playback control works across interfaces from any terminal:

```bash
flow --status      # show the current track
flow --pause       # play/pause the running player
flow --next        # skip
flow --seek 30     # seek 30s forward
```

## Documentation

- **User guide** — [docs/user/](docs/user/index.md): commands and flags,
  TUI/web usage, configuration and storage, plugins
- **Developer guide** — [docs/dev/](docs/dev/index.md): architecture, mode
  internals, storage schemas, control protocol, interfaces

## License

Use however you want, just mention me for inspiration.