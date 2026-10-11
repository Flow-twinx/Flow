import pathlib
import threading

from backend import config, logger

e = config.RED
s = config.GREEN
r = config.Reset
w = config.ORANGE

LOGS_DIR = pathlib.Path.home() / ".flow/LOGS"
_emit_lock = threading.Lock()


def setup_werkzeug_handler():
    """Setup werkzeug logging to use new logger system."""
    try:
        import logging

        for name in ("werkzeug", "werkzeug.serving"):
            wlog = logging.getLogger(name)
            wlog.handlers.clear()
            # Let it propagate to root, but we handle via our logger
            wlog.setLevel(logging.WARNING)
    except Exception:
        pass


def _emit(level, msg):
    if not config.DEV_MODE:
        return
    with _emit_lock:
        try:
            if level == logging.ERROR:
                logger.error("web", "request", msg)
            elif level == logging.WARNING:
                logger.warn("web", "request", msg)
            else:
                logger.info("web", "request", msg)
        except Exception:
            pass
        print(msg, flush=True)


def log_error(method, status, route, source="", message=""):
    try:
        import logging

        full_msg = f"{e}[ERROR] [{source}] {method} {status} {route} - {message}{r}"
        _emit(logging.ERROR, full_msg)
        logger.error("web", "http", f"{method} {status} {route}", {"method": method, "status": status, "route": route, "source": source, "message": message})
    except Exception:
        pass


def log_success(method, status, route, source="", message=""):
    try:
        import logging

        full_msg = f"{s}[OK] [{source}] {method} {status} {route} - {message}{r}"
        _emit(logging.INFO, full_msg)
        logger.info("web", "http", f"{method} {status} {route}", {"method": method, "status": status, "route": route, "source": source, "message": message})
    except Exception:
        pass


def log_info(method, status, route, source="", message=""):
    try:
        if route == "/api/control/poll":
            # Still log to file but maybe skip console spam? But keep as requested - log everything
            logger.debug("web", "http_poll", f"{method} {status} {route}", {"method": method, "status": status, "route": route})
            return
        import logging

        full_msg = f"[INFO] [{source}] {method} {status} {route} - {message}"
        _emit(logging.INFO, full_msg)
        logger.info("web", "http", f"{method} {status} {route}", {"method": method, "status": status, "route": route, "source": source, "message": message})
    except Exception:
        pass


def log_warn(method, status, route, source="", message=""):
    try:
        import logging

        full_msg = f"{w}[WARN] [{source}] {method} {status} {route} - {message}{r}"
        _emit(logging.WARNING, full_msg)
        logger.warn("web", "http", f"{method} {status} {route}", {"method": method, "status": status, "route": route, "source": source, "message": message})
    except Exception:
        pass
