# Flow Docs

Documentation for Flow, a terminal music player with online and offline modes.

## [User guide](user/index.md)

How to install, configure, and use Flow.

| Document                               | Contents                                        |
| -------------------------------------- | ----------------------------------------------- |
| [Introduction](user/index.md)          | What Flow is and how to get started             |
| [Installation](user/installation.md)   | Requirements, install methods, dependency check |
| [Command line](user/command-line.md)   | Flags, shell mode, commands, shortcuts          |
| [Interfaces](user/interface.md)        | Textual TUI and web GUI                         |
| [Configuration](user/configuration.md) | Settings, storage layout, exports               |
| [Plugins](user/plugins.md)             | Installing and running plugins                  |

## [Developer guide](dev/index.md)

How Flow is built and how its subsystems fit together.

| Document                            | Contents                                                   |
| ----------------------------------- | ---------------------------------------------------------- |
| [Architecture](dev/index.md)        | Package layout, entry points, startup flow                 |
| [Online mode](dev/online-mode.md)   | YouTube/JioSaavn search, streaming, radio, downloads       |
| [Offline mode](dev/offline-mode.md) | Local library scanning, playback, liked songs              |
| [Storage](dev/storage.md)           | Files under `~/.flow` and their schemas                    |
| [Playback control](dev/control.md)  | Signals, pid files, status, MPRIS, web control             |
| [Interfaces](dev/interface.md)      | TUI internals, Flask app, visualizer, lyrics, SponsorBlock |
| [Plugins](dev/plugins.md)           | Plugin process model and API                               |

## Tip for dev: Use `config dev true` in flow to see more info
