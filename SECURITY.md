# Security Policy

## Supported versions

Only the latest release of Flow receives security fixes. Please update to the
newest version before reporting a problem.

## Reporting a vulnerability

Please do not report security vulnerabilities in public issues, pull requests
or discussions.

Report them privately by either:

- using the **Report a vulnerability** button on the repository's **Security**
  tab, if it is available, or
- emailing **twinzler@proton.me** with the subject line `Flow security report`.

Please include:

- a description of the issue and its impact
- the Flow version, operating system and Python version
- steps to reproduce, or a proof of concept
- any suggested fix, if you have one

You can expect an acknowledgement within a few days. After that we will work
with you to confirm the issue, prepare a fix and agree a time to disclose it.
We are happy to credit you in the release notes unless you prefer to stay
anonymous.

## Scope

Flow is a local, single-user application. Reports are most useful when they
concern:

- the plugin system: escaping the process isolation, bypassing the
  capability checks in the daemon (`raw_cli`, `PLUGIN_SAFE_KEYS`), or reaching
  data a plugin was not granted
- the daemon's local socket (`~/.flow/flow.sock`) and its permissions
- the local web GUI and its control API
- unsafe handling of files, paths or data under `~/.flow/`
- unsafe handling of untrusted input such as playlist imports, metadata from
  online sources or downloaded filenames

The following are out of scope:

- vulnerabilities in third-party plugins. Report those to the plugin's author.
- vulnerabilities in dependencies such as yt-dlp, VLC or Flask. Report those
  upstream, though we would appreciate a heads-up if Flow needs a version bump.
- issues that need an attacker to already have full control of your account
  or machine
- questions about the content or licensing of music you stream or download

## A note on plugins

Plugins are third-party code. Flow runs them in separate processes and limits
what they can do through a typed, host-validated API, but you should still
only install plugins from authors you trust.
