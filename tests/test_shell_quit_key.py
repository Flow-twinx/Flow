"""Tests for `cli.tui.install_quit_key` — making Ctrl+Q leave the shell.

Ctrl+Q was never wired up: on a stock terminal it is XON (resume output), so it
either gets eaten by flow control or arrives as a plain byte, and the shell's
QUIT character is still Ctrl+\\. Only radio mode remapped VQUIT, so Ctrl+Q quit
nothing while Ctrl+C did. These tests pin the remap (and that it is undone) on a
real pty slave rather than a mock, because the whole bug lives in termios.

Uses the scratch `HOME` from `conftest.py` like the rest of the suite.
"""

import os
import pty
import signal
import termios

import pytest

from cli import tui


@pytest.fixture
def tty_fd():
    """A pty slave to point `install_quit_key` at, closed afterwards."""
    master, slave = pty.openpty()
    yield slave
    for fd in (master, slave):
        try:
            os.close(fd)
        except OSError:
            pass


def _vquit(fd):
    """The QUIT character, normalised: Linux hands it back as bytes."""
    value = termios.tcgetattr(fd)[6][termios.VQUIT]
    return value[0] if isinstance(value, bytes) else value


def test_ctrl_q_becomes_the_terminals_quit_character(tty_fd):
    """The kernel only raises SIGQUIT for Ctrl+Q if VQUIT is remapped to it."""
    assert _vquit(tty_fd) != tui._CTRL_Q, "pty slave should not start out as Ctrl+Q"
    restore = tui.install_quit_key(tty_fd)
    try:
        assert _vquit(tty_fd) == tui._CTRL_Q
    finally:
        restore()


def test_ctrl_q_is_taken_away_from_flow_control(tty_fd):
    """Left on, IXON swallows Ctrl+Q as XON before VQUIT is ever consulted."""
    termios.tcsetattr(tty_fd, termios.TCSANOW, termios.tcgetattr(tty_fd))
    restore = tui.install_quit_key(tty_fd)
    try:
        iflag = termios.tcgetattr(tty_fd)[0]
        assert not iflag & termios.IXON
    finally:
        restore()


def test_sigquit_becomes_the_same_interrupt_ctrl_c_raises(tty_fd):
    """The REPL loop already leaves on KeyboardInterrupt; reuse that path."""
    before = signal.getsignal(signal.SIGQUIT)
    restore = tui.install_quit_key(tty_fd)
    try:
        handler = signal.getsignal(signal.SIGQUIT)
        assert handler is not before
        with pytest.raises(KeyboardInterrupt):
            handler(signal.SIGQUIT, None)
    finally:
        restore()


def test_restore_puts_the_terminal_and_handler_back(tty_fd):
    """Radio mode nests inside the shell, so both layers must be undoable."""
    before_term = termios.tcgetattr(tty_fd)
    before_handler = signal.getsignal(signal.SIGQUIT)
    restore = tui.install_quit_key(tty_fd)
    restore()
    assert termios.tcgetattr(tty_fd) == before_term
    assert signal.getsignal(signal.SIGQUIT) is before_handler


def test_restore_is_idempotent_and_safe_to_call_twice(tty_fd):
    """The shell unwinds through a `finally`, which may run after radio's own."""
    before_term = termios.tcgetattr(tty_fd)
    restore = tui.install_quit_key(tty_fd)
    restore()
    restore()
    assert termios.tcgetattr(tty_fd) == before_term


def test_nothing_happens_without_a_terminal(tmp_path):
    """Piped stdin must not have its termios poked at, and must still be safe."""
    path = tmp_path / "not-a-tty"
    path.write_bytes(b"")
    with path.open("rb") as handle:
        before = signal.getsignal(signal.SIGQUIT)
        restore = tui.install_quit_key(handle.fileno())
        assert signal.getsignal(signal.SIGQUIT) is before
        restore()  # must not raise
