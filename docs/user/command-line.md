# Command line

`flow` has three personalities:

1. **Interactive shell** — run `flow` with no arguments to get a prompt.
2. **One-shot flags** — `flow --play "song"`, `flow --status`, control flags, etc.
3. **Shell-mode commands** — `flow <command> <args>` runs a single command and exits.

## One-shot flags

| Flag | Description |
| ---- | ----------- |
| `-bg` | Play in the background and return to the shell |
| `-s` | Shuffle (used with play/radio) |
| `-r [n]` | Repeat `n` times, or repeat forever when no number is given |
| `-d` | Download the played song |
| `--play <name>` | Play a song from YouTube |
| `--play-off <name>` | Play from the local library without going online (auto-background) |
| `--rd <name>` | Radio mix from YouTube (auto-background) |
| `--radio-off` | Radio over the shuffled local library (auto-background) |
| `--resume` | Resume the last played track from `~/.flow/status.json` (auto-background) |
| `--pause` | Toggle play/pause in the running player (VLC, TUI, or web) |
| `--next` | Skip to the next track in the running player |
| `--previous` | Go back to the previous track in the running player |
| `--seek SEC` | Seek SEC seconds forward in the running player |
| `--seekb SEC` | Seek SEC seconds backward in the running player |
| `--status` | Print the playback status card and exit |
| `--like` | Like the currently playing song (requires an active player) |
| `--unlike` | Unlike the currently playing song |
| `--download` | Download the currently playing song |
| `--setup-island` | Install the Hyprland music island into `~/.config/quickshell` |
| `--check` | Check all dependencies |

`-bg`, `-s`, `-r`, and `-d` are also accepted inline at the end of shell-mode
commands, e.g. `flow play daft punk -s -r 3`.

## Shell mode

Run a command from your shell without entering interactive mode. When the
command plays music it stays in the foreground — like the interactive shell —
unless it backgrounds itself:

- `radio`, `savan`, `--rd`, `--radio-off`, `--play-off`, and `--resume`
  automatically spawn a background player and return to the shell.
- Everything else (`play`, `--play`, `-pl ...`) plays in the foreground;
  add `-bg` to background it, e.g. `flow play daft punk -bg`.

```bash
flow play never gonna give you up     # foreground playback
flow play never gonna give you up -bg # background playback
flow search daft punk          # print results, exit
flow radio daft punk           # radio mix (auto-bg)
flow playlist list
flow plist list                 # plist is the playlist alias
```

The control flags above (`--pause`, `--next`, `--previous`, `--seek`,
`--seekb`, `--like`, `--unlike`, `--download`, `--status`) talk to whatever
player is currently running — a background VLC, the TUI, or the web player —
and work whether or not a `flow` session is active.

### Shortcuts

Shell-mode and interactive commands accept your user-defined shortcuts as
aliases, with a `-` prefix:

```bash
flow -pl never gonna give you up    # pl -> play (foreground; add -bg for background)
flow -rd daft punk                  # rd -> radio (auto-bg)
flow -sh daft punk                  # sh -> search
flow -svn hello                     # svn -> savan (auto-bg)
flow -dl never gonna give you up    # dl -> download
```

Built-in aliases (overridable/extendable via `~/.flow/shortcuts.json`):

`pl` play · `sh` search · `ls` list · `lk` like · `ul` unlike · `dl` download
· `dl-d` delete · `rd` radio · `sw` switch · `hl` help · `cf` config ·
`ex` exit · `svn` savan · `svn-s` savan-s · `plist` playlist

Manage them inside Flow with the `short` command:

```bash
short                     # list all shortcuts
short add <key> <cmd>     # add or update an alias
short remove <idx>        # remove by list index
short <idx> <new_cmd>     # update by index
```

## Commands

These work in both the interactive prompt and shell mode. `search` shows
results with indices; `play <index>` plays a result by number, and after a
download the matching index can be used the same way.

| Command | Description |
| ------- | ----------- |
| `play <name, index, or liked>` | Play a song by name or search-result number; offline also supports `play liked` and `play all` |
| `search <query>` | Search YouTube (online) or the local library (offline) |
| `list` | List the local library (offline; alias `ls`) |
| `savan <name>` | Play a song from JioSaavn (online) |
| `savan-s <query>` | Search JioSaavn (online) |
| `radio <name> [index]` | Radio mix (online) or shuffle-loop library (offline); `-p` saves as playlist |
| `like` / `unlike` | Like/unlike the current song; liked songs are saved to the library and played with `play liked` |
| `download <query or index>` | Save a streamed song (online; `-f <format>` picks opus/m4a/mp3/webm) |
| `delete <name or index>` | Delete a downloaded song (alias: `dl-d`) |
| `playlist <sub>` | Manage playlists — see below |
| `switch` | Toggle between online and offline mode |
| `config [target [value]]` | Change settings; run bare for an interactive wizard |
| `short` | Show/update command shortcuts |
| `check` | Check all dependencies |
| `export` | Back up `~/.flow` to `~/Downloads/flow_backup.zip` |
| `help` / `help -i` | Command list / detailed help |
| `exit` | Leave the interactive shell |

### Playlist subcommands

`playlist` (alias `plist`): `create` · `add` · `remove` · `list` · `play` ·
`rename` · `move` · `duplicate` · `merge` · `sort` · `clear` · `dedupe` ·
`info` · `export` · `import` · `download`

```bash
flow playlist create roadtrip
flow playlist add roadtrip "some song"
flow playlist list
flow playlist play roadtrip
flow playlist export roadtrip   # writes roadtrip.m3u to ~/Downloads
flow playlist import songs.m3u  # name defaults to the file name
flow playlist download roadtrip # download all YouTube tracks in it
```

`liked` is a reserved playlist name.