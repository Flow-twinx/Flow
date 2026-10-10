# Contributing to Flow

Thanks for wanting to help. Bug reports, fixes, documentation improvements and
new ideas are all welcome. By taking part you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report a bug** using the [bug report form](https://github.com/flow-twinx/flow/issues/new/choose). Include the output of `flow --check`.
- **Suggest a feature** using the feature request form. Describe the problem first, then the change you have in mind.
- **Fix something or add a feature** by opening a pull request (see below).
- **Improve the docs.** Typos, unclear steps and missing examples all count.
- **Write a plugin.** Plugins live in their own repositories; see the [plugin developer guide](docs/dev/plugins.md).

Found a security problem? Do not open a public issue. Follow
[SECURITY.md](SECURITY.md) instead.

## Development setup

You need Python 3.14+, [uv](https://docs.astral.sh/uv/) and
[VLC](https://www.videolan.org/vlc/) (ffmpeg is optional, for non-webm
downloads).

```bash
git clone https://github.com/flow-twinx/flow.git
cd flow
uv sync                  # install dependencies
uv run flow --check      # verify the environment
```

Try your changes locally:

```bash
uv run flow              # interactive shell
uv run flow-tui          # TUI
uv run flow-web          # web GUI at http://127.0.0.1:5000
uv run flow-min status   # plain CLI
```

Running `config dev true` inside Flow prints more diagnostic information while
you work.

## Running the tests

```bash
uv run pytest                          # everything
uv run pytest tests/test_daemon_rpc.py -v   # one file
uv run pytest -q -k registry           # by keyword
```

The tests set a scratch `HOME` in `tests/conftest.py` before importing the
backend, so they never touch your real `~/.flow/`. Keep it that way: never
assume the real home directory in a test, and remember that subprocesses such
as `flow daemon` inherit the scratch `HOME`.

Add or update tests for any bug fix or behaviour change.

## Project layout

| Path        | Purpose                                                              |
| ----------- | -------------------------------------------------------------------- |
| `backend/`  | Core logic and the source of truth, split into `Online/` and `Offline/` modes |
| `cli/`      | The `flow` interactive shell and one-shot flags                      |
| `minimal/`  | `flow-min`, the plain non-interactive CLI                            |
| `tui/`      | The Textual full-screen interface                                    |
| `web/`      | The Flask web GUI and its templates                                  |
| `docs/`     | User and developer documentation                                     |
| `tests/`    | The pytest suite                                                     |

Start with the [architecture overview](docs/dev/index.md).

## Guidelines

**Respect the module boundaries.**
- `backend/` owns the logic. `cli/`, `tui/`, `web/` and `minimal/` are thin front ends over it.
- Keep the Online/Offline split intact. Modes do not hand off to each other mid-command.
- `minimal/` imports `backend.*`, and nothing in `backend/` imports `minimal`.

**Take care with shared state.** Several Flow processes can run at once and
coordinate through files under `~/.flow/`. Before changing anything that
touches the player registry, the SQLite databases, atomic writes or the daemon
socket, read the relevant module in `backend/` and the
[storage](docs/dev/storage.md) and [control](docs/dev/control.md) docs. Keep
the seek mechanism as it is: the control flags write a delta to
`~/.flow/seek.txt` before signalling the player.

**Keep the `flow-min` output contract.** New `minimal/` commands wrap backend
calls in `out.quiet()` and print only through `out.emit` and `out.fail`, so
standard output stays exactly one line or one JSON document. Details are in
[docs/dev/minimal.md](docs/dev/minimal.md).

**Mind the plugin boundary.** Plugins never import Flow internals. Anything
they can do goes through the typed API in `backend/rpc.py`, and the daemon
validates every call. Do not widen `PLUGIN_SAFE_KEYS` or the `raw_cli`
capability without a clear reason.

**Keep changes focused.**
- Follow the style of the surrounding code and prefer small, targeted edits over rewrites.
- Comments are kept to a minimum: give functions and classes a short one-line docstring instead of inline comments.
- The repository has no linter or type-checker configured. Do not add new tooling as part of an unrelated change.

**Update the docs.** The files in `docs/` are the reference for how Flow works.
If your change alters behaviour, a command, a flag or a file format, update the
matching page in the same pull request.

## Submitting a pull request

1. Fork the repository and create a branch from the default branch.
2. Make your change in small, logical commits with clear messages.
3. Run `uv run pytest` and make sure it passes.
4. Open a pull request and fill in the template. Say what changed and why, and link any related issue.
5. Respond to review comments. Maintainers may ask for changes before merging.

For anything large, such as a new subsystem or a change to the storage or
control protocol, open an issue first so the approach can be agreed before you
spend time on it.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
