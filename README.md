# Flow

A terminal-based music player with online streaming and offline library modes.

## Features

- **Dual-mode operation** — It will automatically detect internet and switch between online streaming and offline playback.
- **Online mode** — Search and stream audio from YouTube via `yt-dlp` and `python-vlc`
- **Offline mode** — Play local audio files with album support, search, and a liked-songs collection
- **Download** — Save tracks from YouTube to your local library with the `-d` flag
- **Repeat & shuffle** — Loop tracks n times or play in random order
- **Like/unlike** — Toggle favorites on/off, stored in `~/.flow/library.json`
- **Playlist play** — Create playlists and play them with `playlist play <name>`
- **Tab completion** — Auto-complete commands and song names in offline mode
- **Colored TUI** — Cyan theme for online, magenta for offline, with borders and banners
- **Background play** — Play music in background and return to your shell
- **Audio-reactive bars** — Real-time spectrum analyzer with configurable width, height, and spacing
- **Synced lyrics** — Display color-coded lyrics that scroll with the song
- **Gui for GUI lovers** - Get a gui in web using flask for you to enjoy

## Requirements

- Python 3
- [VLC](https://www.videolan.org/vlc/) media player (for `python-vlc` bindings)

## Installation

```bash
git clone https://github.com/Philast-015/Flow.git
cd flow
uv run flow_twinx/main.py
```

Or through pip:

```bash
pip install flow-twinx
flow
```

### Note: Make sure vlc is installed.

## Project structure

```
flow/
├── backend/          # Engine: config, library, playlists, players, web API
│   ├── Online/       # Online mode (youtube, savan, streaming player)
│   ├── Offline/      # Offline mode (local files, offline player)
│   └── web/          # Flask app + templates (GUI mode)
├── cli/       # CLI launcher shell that links to backend
│   ├── main.py       # entry point (`flow`)
│   └── tui.py        # banner + prompt chrome
└── tui/   # Full-screen Textual UI
    └── main.py       # entry point (`flowt`)
```

The backend holds all the logic; `flow_twinx` is the thin CLI shell that imports it.

## Usage

```bash
flow
```

OR if you cloned the repo:

```bash
cd flow_twinx
uv run main.py
```

### Flags

| Flag          | Description                                                           |
| ------------- | --------------------------------------------------------------------- |
| `-bg`         | Play in background and exit to shell                                  |
| `flow-web --stop-all` | Stop all background processes (web servers + VLC)              |
| `-i`          | Use it in help command to show detailed help                          |
| `-s`          | Use it shuffle or play random songs                                   |
| `-r`          | Use it to repeat songs no of time [ -r n ] [ -r ] ( n = no of times ) |
| `-d`          | Use it to download songs                                              |
| `--play-off`  | Play a song from the local library without going online               |
| `--radio-off` | Radio from the local library (shuffled, looped) without going online  |
| `--resume`    | Resume the last played track from `~/.flow/status.json`               |
| `--pause`     | Toggle play/pause in the running player (VLC or flowt TUI)            |
| `--next`      | Skip to the next track in the running player                          |
| `--previous`  | Go back to the previous track in the running player                   |
| `--status`    | Show the playback status card                                         |
| `--seek SEC`  | Seek SEC seconds forward in the running player (VLC or web player)    |
| `--seekb SEC` | Seek SEC seconds backward in the running player (VLC or web player)   |

### Shell Mode

Run commands directly from your shell without entering interactive mode.
Play-like commands (`-pl`, `-rd`) automatically run in background.

```bash
flow -pl never gonna give you up    # play (auto-bg)
flow -rd daft punk                  # radio (auto-bg)
flow -sh daft punk                  # search (show results, exit)
flow -kill                          # kill VLC
flow --play-off draft punk                 # play a local song (offline, auto-bg)
flow --radio-off                    # radio over shuffled local library (auto-bg)
flow --resume                       # replay last track from status.json (auto-bg)
```

Also works with positional commands:

```bash
flow play never gonna give you up
flow radio daft punk
flow search daft punk
```

Shell shortcuts use your user-defined shortcuts with `-` prefix:

```bash
flow -svn hello                     # svn → savan
flow -dl never gonna give you up    # dl → download
```

### Gui Mode:

To launch gui mode just type :

```bash
flow-web
```

The dedicated `flow-web` command picks the first free port starting at 5000
(5000, then 5001, ...) and daemonizes.

| Command | Action |
| ------- | ------ |
| `flow-web` | Start the web server (prompts to restart if one is already running) |
| `flow-web --new` | Start another instance on the next free port |
| `flow-web --port 8080` | Start on a specific port |
| `flow-web --stop [PORT]` | Stop one web server (defaults to the running port) |
| `flow-web --stop-all` | Stop all web servers and VLC |

### TUI Mode:

Launch the full-screen Textual interface with:

```bash
flowt
```

It shows the local (or online) library on the left and the Now Playing panel on
the right, including a live progress bar, time, mode, repeat/shuffle state and
volume.

| Key             | Action                                       |
| --------------- | -------------------------------------------- |
| `Enter` / click | Play the selected track (starts immediately) |
| `space`         | Play / pause                                 |
| `n` / `p`       | Next / previous track                        |
| `s` / `r`       | Toggle shuffle / repeat                      |
| `S`             | Focus the search box (works in both modes)    |
| `d`             | Download current track (online mode only)     |
| `+` / `-`       | Volume up / down                             |
| `Tab`           | Switch online/offline mode                   |
| `q`             | Quit                                         |

`flowt` also accepts the control flags:

| Flag         | Description                                                         |
| ------------ | ------------------------------------------------------------------- |
| `--status`   | Print the playback status card and exit                             |
| `--pause`    | Toggle play/pause in a running Flow session (TUI or background VLC) |
| `--next`     | Skip to the next track in a running Flow session                    |
| `--previous` | Go back to the previous track in a running Flow session             |
| `--repeat`   | Toggle repeat in a running TUI, or start the TUI with repeat on     |
| `--shuffle`  | Toggle shuffle in a running TUI, or start the TUI with shuffle on   |

While playing, the TUI publishes its state to `~/.flow/status.json`, so
`flow --status` (and `flow --pause` / `--next` / `--previous`) work against a
running TUI. Its pid is tracked in `~/.flow/tui.pid`.

### Commands

| Command                | Description                                          |
| ---------------------- | ---------------------------------------------------- |
| `play <name or #>`     | Play a song by name or search result number          |
| `search <query>`       | Search YouTube (online) or library (offline)         |
| `list`                 | Show all songs, albums, or liked tracks              |
| `like`                 | Like/unlike the currently playing song               |
| `download <name or #>` | Save a streamed song to the local library            |
| `delete <name or #>`   | Delete a downloaded song (alias: `dl-d`)             |
| `radio <name> [#]`     | Radio mix (online) or shuffle-loop library (offline) |
| `playlist <sub>`       | Manage playlists (create/add/remove/play)            |
| `export`               | Backup ~/.flow config to ~/Downloads                 |
| `plugins list`         | List available plugins (fast, offline)               |
| `install <ref>`        | Install a plugin: `name`, `owner/name`, or git URL   |
| `run <name>`           | Run an installed plugin                              |
| `uninstall <name>`     | Remove an installed plugin                           |
| `plugins update`       | Pull latest plugin repo and show available updates   |
| `switch`               | Toggle between online and offline mode               |
| `help`                 | Show available commands                              |
| `help -i`              | Show available commands with detailed explanation    |

### Config Options

| Target       | Description                  | Range              |
| ------------ | ---------------------------- | ------------------ |
| `primary`    | Color for online songs       | Any color          |
| `secondary`  | Color for offline songs      | Any color          |
| `tertiary`   | Color for labels             | Any color          |
| `display`    | Playback display mode        | none, bars, lyrics |
| `barwidth`   | Number of bars in visualizer | 4-80               |
| `barheight`  | Height of bars               | 2-16               |
| `barspacing` | Space between bars           | 0-4                |

Usage: `config <target> <value>`

## Configuration

- Downloads are stored in `~/.flow/downloads/` (named by video id, e.g. `TucWbkH5WX0.opus`)
- All per-song data (liked/downloaded/title/paths) lives in the single file `~/.flow/library.json`, keyed by video id
- Thumbnails are downloaded on like/download to `~/.flow/downloads/.cache/<video_id>.jpg`
- User shortcuts are stored in `~/.flow/shortcuts.json`
- Config file: `~/.flow/config.json`
- Downloaded plugins live in `~/.flow/plugins/`

## Plugins

Flow can install and run plugins from git repositories. Plugins are small
packages that live in `~/.flow/plugins/<name>/` and are run as **external
processes** — a plugin can only read the current-track status and invoke the
`flow` CLI itself, so Flow internals stay isolated.

```bash
flow plugins list
flow install thumbnail-circle
flow install Twinx015/harpy
flow install <git-url>
flow run thumbnail-circle
flow uninstall thumbnail-circle
flow plugins update            # pull latest repos + show available updates
```

- `flow install <name> --force` reinstalls an already-installed plugin.
- A plugin's dependencies are printed at install time (e.g. `pip install pyside6`).
- The bundled `~/.flow/plugins/<name>/flow_api.py` is the entire API surface:
  `current_track()` (read `~/.flow/status.json`) and `control("--pause", ...)`
  (run a `flow` CLI command).
- The community plugin repo is https://github.com/Twinx015/flow-plugins.

## License

Use however you want just mention me for inspiration.
