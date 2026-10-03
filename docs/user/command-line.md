# Command line

`flow` has three personalities:

1. **Interactive shell** — run `flow` with no arguments to get a prompt.
2. **One-shot flags** — `flow --play "song"`, `flow --status`, `flow --summary`, control flags, etc.
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
| `--summary` | Play statistics; see [summary](#summary) below |
| `--like` | Like the currently playing song (requires an active player) |
| `--unlike` | Unlike the currently playing song |
| `--download` | Download the currently playing song |
| `--setup-island` | Install the Hyprland music island into `~/.config/quickshell` |
| `--check` | Check all dependencies |

`-bg`, `-s`, `-r`, `-d`, and `-m` are also accepted inline at the end of
shell-mode commands, e.g. `flow play daft punk -s -r 3`. Single-letter flags
combine, so `-dm` is the same as `-d -m` (`-ms`, `-dms` work too).

### Multi-select (`-m`)

`-m` turns the result picker into a checkbox so you can act on several results
at once. Without `questionary` installed the picker falls back to a prompt where
you type `1,3,5-7`, `1-`, `-3`, or `all`.

| Command | Result |
| --- | --- |
| `flow download <query> -m` | download every ticked track |
| `flow search <query> -dm` | download every ticked track |
| `flow play <query> -dm` | download every ticked track, then play |
| `flow search <query> -m` | play the ticked tracks as a queue |
| `flow play <query> -m` | play the ticked tracks as a queue |
| `flow play <query> -m` (offline) | play the ticked songs as a queue |

Queued playback wires up next/prev between the selected tracks, and `-r` still
repeats the queue.

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
| `play <name, index, or liked>` | Play a song by name or search-result number; offline also supports `play liked` and `play all`. `-m` plays a ticked selection as a queue |
| `search <query>` | Search YouTube (online) or the local library (offline); `-dm` downloads a ticked selection |
| `list` | List the local library (offline; alias `ls`) |
| `savan <name>` | Play a song from JioSaavn (online) |
| `savan-s <query>` | Search JioSaavn (online) |
| `radio <name> [index]` | Radio mix (online) or shuffle-loop library (offline). Bare `radio` shuffles everything; a name seeds the loop with that song. `-p` saves as playlist |
| `like` / `unlike` | Like/unlike the current song; liked songs are saved to the library and played with `play liked` |
| `download <query or index>` | Save a streamed song (online; `-f <format>` picks opus/m4a/mp3/webm). Add `-m` to tick and download several |
| `delete <name or index>` | Delete a downloaded song (alias: `dl-d`) |
| `playlist <sub>` | Manage playlists — see below |
| `switch` | Toggle between online and offline mode |
| `config [target [value]]` | Change settings; run bare for an interactive wizard |
| `short` | Show/update command shortcuts |
| `check` | Check all dependencies |
| `summary` | Play statistics and the ranked per-song table — see below |
| `export [-p <path>]` | Copy downloaded songs (tagged) to `~/Downloads`, or to `<path>` |
| `help` / `help -i` | Command list / detailed help |
| `exit` | Leave the interactive shell |

### summary

`summary` reports what you've been playing. Play counts come from
`~/.flow/library.db` and cover **both** online and offline playback; the
online totals come from `~/.flow/history.db`.

```bash
flow summary                          # stats card + a 7-day bar chart
flow summary -l                       # the ranked per-song table
flow summary -l -s artist --top 50    # sort by artist, 50 rows
flow summary -c                       # clear the online play history
```

| Flag | Description |
| ---- | ----------- |
| `-l` | Show the per-song table instead of the stats card |
| `-s <sort>` | Table sort: `plays` (default), `recent`, `name`, `artist` |
| `--top <N>` | Rows to show in the table (default: 20) |
| `-c` | Clear the logged online plays (`history.db`) |

`-c` only empties the play timeline — the `song_count` totals in
`library.db` are untouched.

In shell mode `flow summary …` takes the same flags. As a one-shot flag,
`flow --summary …` also accepts the long `--sort <key>` and `--top <N>`
spellings:

```bash
flow --summary -l --sort recent --top 10
```

The **web History panel** shows the other half of the data: an online-only
timeline you can sort by *newest*, *oldest*, *most played* or *least played*
and filter to today / 7 days / 30 days. The split is deliberate — the CLI
ranks a per-song table (a terminal is bad at a long event log), the web panel
sorts an event stream (a scrollable column is bad at aggregates).

### export

`export` copies every song in `~/.flow/downloads` somewhere you can reach it
with a file manager, and writes the library's metadata into each copy.

```bash
flow export                    # -> ~/Downloads
flow export -p ~/Music/flow    # -> anywhere else
```

| Flag | Description |
| ---- | ----------- |
| `-p <path>` | Destination directory (created if missing). Defaults to `~/Downloads` |

Each copy is named after the song — `Never Gonna Give You Up.webm`, not
`dQw4w9WgXcQ.webm` — and tagged with the title, artist and album from
`library.db`. A song the library has no title for is tagged with its own file
name. Cover art is attached where the format allows it, and the audio itself
is never re-encoded.

Re-running `export` refreshes the files it already wrote instead of creating
`… (2).webm` copies, so a song that changed in the library gets re-tagged in
place.

Tagging needs `ffmpeg` (`flow check` will tell you if it's missing). Without
it the songs are still copied, just untagged.

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