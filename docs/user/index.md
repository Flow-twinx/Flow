# Flow

Flow is a terminal music player with two modes:

- **Online mode** — search and stream audio from YouTube via `yt-dlp` and VLC, or play JioSaavn tracks.
- **Offline mode** — play local audio files from `~/.flow/downloads/` with search and a liked-songs collection.

Flow picks the mode automatically on startup: it probes for an internet
connection and uses online mode when reachable, offline mode otherwise. The
`switch` command (or `Tab` in the TUI) flips modes on demand.

There are four ways to use it:

| Entry point | What it is |
| ----------- | ---------- |
| `flow` | Interactive shell with commands, tab completion, and playback flags |
| `flow-min` | Plain one-shot commands for scripts, ssh and agents: no colour, no prompts, `--json` on every command |
| `flow-tui` | Full-screen Textual UI with a track list and Now Playing panel |
| `flow-web` | Local web GUI (Flask) served on `127.0.0.1`, ports 5000–5005 |

All four share the same library, playlists, and status files under
`~/.flow/`, so anything you like, download, or configure in one interface is
visible to the others. Playback control works across them too: `flow-min next`
skips a track started by the shell, the TUI or the web GUI.

## Quick start

```bash
# Stream a song from YouTube (foreground; add -bg for background)
flow -pl never gonna give you up

# Search and show results
flow -sh daft punk

# Play from your local library without going online (auto-background)
flow --play-off <song name>

# Shuffle-loop the whole local library
flow --radio-off

# Open the full-screen TUI
flow-tui

# Start the web GUI and open http://127.0.0.1:5000
flow-web

# Same player, script-friendly: prints plain lines, detaches by default
flow-min play "never gonna give you up"
flow-min --json status
```

Running `flow` with no arguments drops you into an interactive shell with a
banner and a `Flow>` prompt. Type `help` for the command list, or `help -i`
for detailed explanations.

## Next steps

- [Installation](installation.md) — requirements and install methods
- [Command line](command-line.md) — flags, commands, and shortcuts
- [Interfaces](interface.md) — TUI and web GUI usage
- [Configuration](configuration.md) — colors, display modes, storage
- [Plugins](plugins.md) — extend Flow with community plugins
