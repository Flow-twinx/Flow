import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys

from backend.config import GREY, RED, Muted, Primary, Reset, Secondary

P = Primary
S = Secondary
M = Muted
R = Reset
G = GREY
E = RED

PLUGINS_DIR = pathlib.Path.home() / ".flow/plugins"
REPO_CACHE = PLUGINS_DIR / "_repo"
OTHER_CACHE = PLUGINS_DIR / "_src"

DEFAULT_REPO = "https://github.com/Twinx015/flow-plugins.git"

API_VERSION = 1

FLOW_API_SOURCE = '''"""Flow Plugin API v1 — read-only, process-isolated interface.

Provided by Flow. Plugins must not import any flow internals; everything a
plugin may do goes through this module.
"""
import json
import os
import pathlib
import subprocess

STATUS_FILE = pathlib.Path.home() / ".flow/status.json"
FLOW_BIN = os.environ.get("FLOW_BIN", "flow")

API_VERSION = 1


def current_track():
    """Return the current track info dict (title/duration/thumbnail/playing/ts),
    or {} if nothing is playing / no status file exists."""
    try:
        return json.loads(STATUS_FILE.read_text())
    except Exception:
        return {}


def control(*flow_args):
    """Run a flow CLI command as a subprocess and return its exit code.

    Examples: control("--pause"), control("--next"), control("--status")
    """
    return subprocess.call([FLOW_BIN, *flow_args])
'''


def _ensure_plugins_dir():
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)


def _repo_key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def _git(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _ensure_repo(url: str) -> pathlib.Path:
    _ensure_plugins_dir()
    cache = REPO_CACHE if url == DEFAULT_REPO else OTHER_CACHE / _repo_key(url)
    if (cache / ".git").exists():
        _git(["-C", str(cache), "pull", "--ff-only", "-q"], timeout=30)
    else:
        cache.mkdir(parents=True, exist_ok=True)
        r = _git(["clone", "--depth", "1", url, str(cache)])
        if r.returncode != 0:
            shutil.rmtree(cache, ignore_errors=True)
            raise RuntimeError(
                f"git clone failed for {url}:\n{(r.stderr or r.stdout).strip()}"
            )
    return cache


def _read_manifest(cache_dir: pathlib.Path):
    manifest_file = cache_dir / "manifest.json"
    if not manifest_file.exists():
        return None
    try:
        return json.loads(manifest_file.read_text())
    except Exception:
        return None


def _find_entry(manifest, name: str):
    if not manifest:
        return None
    for p in manifest.get("plugins", []):
        if p.get("name") == name:
            return p
    return None


def _resolve_ref(ref: str) -> tuple[str, str]:
    select = None
    if "#" in ref:
        ref, _, select = ref.partition("#")
    if ref.startswith(("http://", "https://", "git@")):
        url = ref
        name = ref.rstrip("/").split("/")[-1].removesuffix(".git")
        return url, select or name
    expanded = pathlib.Path(os.path.expanduser(ref))
    if expanded.exists():
        return expanded.resolve().as_posix(), select or expanded.name
    if "/" in ref:
        owner, _, name = ref.partition("/")
        return f"https://github.com/{owner}/{name}.git", select or name
    return DEFAULT_REPO, select or ref


def _write_api(plugin_dir: pathlib.Path):
    (plugin_dir / "flow_api.py").write_text(FLOW_API_SOURCE)


def _write_plugin_json(plugin_dir: pathlib.Path, entry: dict):
    (plugin_dir / "plugin.json").write_text(json.dumps(entry, indent=2) + "\n")


def installed() -> dict[str, dict]:
    """Return {name: plugin.json contents} for installed plugins."""
    _ensure_plugins_dir()
    result = {}
    for child in PLUGINS_DIR.iterdir():
        if not child.is_dir() or child.name.startswith("_"):
            continue
        pj = child / "plugin.json"
        if not pj.exists():
            continue
        try:
            info = json.loads(pj.read_text())
        except Exception:
            continue
        if info.get("name"):
            result[info["name"]] = info
    return result


def cmd_list(extra=None) -> int:
    """flow plugins list — read the cached default-repo catalog (fast, offline)."""
    if not REPO_CACHE.exists():
        try:
            _ensure_repo(DEFAULT_REPO)
        except Exception as exc:
            print(f"{E}Could not fetch plugin repo: {exc}{R}")
            return 1
    manifest = _read_manifest(REPO_CACHE)
    if not manifest:
        print(f"{E}No manifest.json found in cached plugin repo{R}")
        return 1

    inst = installed()
    plugins = manifest.get("plugins") or []
    if not plugins:
        print(f"{M}No plugins available in the repository{R}")
        return 0

    print(f"\n{P}Available plugins:{R}\n")
    for p in plugins:
        name = p.get("name", "?")
        ver = p.get("version", "?")
        desc = p.get("description", "")
        mark = ""
        if name in inst:
            iv = inst[name].get("version")
            mark = (
                f" {S}installed v{iv}{R}"
                if iv == ver
                else f" {S}installed v{iv} → update v{ver}{R}"
            )
        print(f"  {P}{name:<20}{R} {G}v{ver}{R}  {desc}{mark}")
    print()
    return 0


def cmd_install(extra) -> int:
    """flow install <REF> [--force]"""
    force = "--force" in extra
    extra = [x for x in extra if x != "--force"]
    if not extra:
        print(f"{E}Usage: flow install <plugin-name> [--force]{R}")
        print(f"  {G}Examples:{R}")
        print(f"    flow install thumbnail-circle")
        print(f"    flow install Twinx015/harpy")
        print(f"    flow install https://github.com/USER/repo.git")
        return 1

    ref = extra[0]
    repo_url, plugin_name = _resolve_ref(ref)

    print(f"{P}Fetching plugin '{plugin_name}'...{R}")
    try:
        cache = _ensure_repo(repo_url)
    except Exception as exc:
        print(f"{E}Failed to fetch repo: {exc}{R}")
        return 1

    manifest = _read_manifest(cache)
    entry = _find_entry(manifest, plugin_name)
    if not entry:
        names = [
            p.get("name") for p in (manifest or {}).get("plugins", []) if p.get("name")
        ]
        print(f"{E}Plugin '{plugin_name}' not found in the repo{R}")
        if names:
            print(f"{G}Available: {', '.join(names)}{R}")
        return 1

    _ensure_plugins_dir()
    dest = PLUGINS_DIR / plugin_name
    if dest.exists() and not force:
        print(
            f"{M}Plugin '{plugin_name}' is already installed (v{entry.get('version', '?')}){R}"
        )
        print(f"{G}Use --force to reinstall{R}")
        return 0

    src = cache / "plugins" / plugin_name
    if not src.is_dir():
        print(f"{E}Plugin source not found: plugins/{plugin_name}/ in the repo{R}")
        return 1

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    _write_api(dest)
    _write_plugin_json(dest, entry)

    ver = entry.get("version", "?")
    print(f"{P}Installed {plugin_name} v{ver}{R}")
    if entry.get("deps"):
        print(f"{G}Dependencies: pip install {' '.join(entry['deps'])}{R}")
    kind = "GUI plugin — run" if entry.get("gui") else "Run"
    print(f"{G}{kind} it with: flow run {plugin_name}{R}")
    return 0


def cmd_uninstall(extra) -> int:
    """flow uninstall <name>"""
    if not extra:
        print(f"{E}Usage: flow uninstall <plugin-name>{R}")
        return 1
    name = extra[0]
    dest = PLUGINS_DIR / name
    if not dest.exists():
        print(f"{E}Plugin '{name}' is not installed{R}")
        return 1
    shutil.rmtree(dest)
    print(f"{P}Uninstalled plugin '{name}'{R}")
    return 0


def cmd_run(extra) -> int:
    """flow run <name> [args...]"""
    if not extra:
        print(f"{E}Usage: flow run <plugin-name> [args...]{R}")
        return 1
    name = extra[0]
    plugin_args = extra[1:]
    dest = PLUGINS_DIR / name
    if not dest.exists():
        print(f"{E}Plugin '{name}' is not installed{R}")
        return 1

    pj = dest / "plugin.json"
    if not pj.exists():
        print(f"{E}Plugin '{name}' has no plugin.json{R}")
        return 1
    try:
        info = json.loads(pj.read_text())
    except Exception:
        print(f"{E}Plugin '{name}' has a corrupt plugin.json{R}")
        return 1

    entry_name = info.get("entry") or "main.py"
    entry_path = dest / entry_name
    if not entry_path.exists():
        print(f"{E}Plugin entry point not found: {entry_name}{R}")
        return 1

    flow_bin = shutil.which("flow") or f"{sys.executable} -m cli.main"
    env = os.environ.copy()
    env["FLOW_PLUGIN_NAME"] = name
    env["FLOW_PLUGIN_HOME"] = str(dest)
    env["FLOW_BIN"] = flow_bin

    print(f"{P}Running plugin '{name}'{R}")
    try:
        return subprocess.call(
            [sys.executable, str(entry_path), *plugin_args],
            cwd=str(dest),
            env=env,
        )
    except KeyboardInterrupt:
        print(f"{M}\nStopped plugin '{name}'{R}")
        return 130


def cmd_update() -> int:
    """flow plugins update — pull all cached repo clones and report updates."""
    caches = [REPO_CACHE]
    if OTHER_CACHE.exists():
        caches += [d for d in OTHER_CACHE.iterdir() if d.is_dir()]

    updated = 0
    for cache_dir in caches:
        git_dir = cache_dir / ".git"
        if not git_dir.exists():
            continue
        try:
            r = _git(["-C", str(cache_dir), "pull", "--ff-only", "-q"], timeout=30)
            if r.returncode == 0:
                updated += 1
            else:
                print(
                    f"{E}Failed to update {cache_dir}: {(r.stderr or r.stdout).strip()}{R}"
                )
        except Exception as exc:
            print(f"{E}Failed to update {cache_dir}: {exc}{R}")

    print(f"{P}Updated {updated} plugin repo(s){R}")

    inst = installed()
    manifest = _read_manifest(REPO_CACHE)
    diffs = []
    for p in (manifest or {}).get("plugins", []):
        name = p.get("name")
        if name in inst and inst[name].get("version") != p.get("version"):
            diffs.append(f"  {name}: {inst[name].get('version')} → {p.get('version')}")
    if diffs:
        print(f"\n{P}Available updates (run 'flow install <name> --force'):{R}")
        print("\n".join(diffs))
    else:
        print(f"{G}All installed plugins are up to date{R}")
    return 0


PLUGIN_CMDS = {"plugins", "install", "uninstall", "remove", "run", "update"}


def dispatch(cmd: str, extra: list[str], args: argparse.Namespace | None = None):
    if cmd == "plugins":
        subcmd = extra[0] if extra else "list"
        rest = extra[1:] if len(extra) > 1 else []
        if subcmd == "list":
            return cmd_list(rest)
        if subcmd == "install":
            return cmd_install(rest)
        if subcmd in ("uninstall", "remove"):
            return cmd_uninstall(rest)
        if subcmd == "run":
            return cmd_run(rest)
        if subcmd == "update":
            return cmd_update()
        print(f"{E}Unknown plugin subcommand: {subcmd}{R}")
        print(
            f"{G}Usage: {P}plugins {S}list|install <ref>|uninstall <name>|run <name>|update{R}"
        )
        return 1
    if cmd == "install":
        return cmd_install(list(extra))
    if cmd in ("uninstall", "remove"):
        return cmd_uninstall(list(extra))
    if cmd == "run":
        return cmd_run(list(extra))
    if cmd == "update":
        return cmd_update()
    return None
