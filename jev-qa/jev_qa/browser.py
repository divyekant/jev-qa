"""Own a disposable Chrome profile and a private Browser Harness daemon."""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


class RunDeadline(BaseException):
    """Abort the whole run; dependency Exception handlers must not swallow this."""


class BrowserSetupError(ValueError):
    """A safe, actionable browser setup failure for the command-line boundary."""


class BrowserCleanupError(RuntimeError):
    """A recorded browser target could not be closed after the run."""


_REMOTE_DEBUG_HINT = (
    "enable chrome://inspect/#remote-debugging and accept Chrome's remote debugging prompt"
)
_CLEANUP_INCOMPLETE_MESSAGE = "Browser cleanup incomplete."
_ACTIVE_PORT_NAME = "DevToolsActivePort"
_BROWSER_ENDPOINT = re.compile(r"\A/devtools/browser/[A-Za-z0-9._~-]+\Z")


def _active_port_ws(path):
    """Build a loopback browser WebSocket from a Chrome-owned active-port file."""
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError) as exc:
        raise BrowserSetupError(f"{_ACTIVE_PORT_NAME} was not found; {_REMOTE_DEBUG_HINT}.") from exc
    if len(lines) < 2:
        raise BrowserSetupError(f"{_ACTIVE_PORT_NAME} is incomplete; {_REMOTE_DEBUG_HINT}.")
    port_text, endpoint = lines[0].strip(), lines[1].strip()
    if not re.fullmatch(r"[0-9]+", port_text):
        raise BrowserSetupError(f"{_ACTIVE_PORT_NAME} contains an invalid port; {_REMOTE_DEBUG_HINT}.")
    port = int(port_text)
    if not 1 <= port <= 65535 or not _BROWSER_ENDPOINT.fullmatch(endpoint):
        raise BrowserSetupError(
            f"{_ACTIVE_PORT_NAME} contains an invalid browser endpoint; {_REMOTE_DEBUG_HINT}."
        )
    return f"ws://127.0.0.1:{port}{endpoint}"


def _validate_cdp_ws(ws_url, timeout=5):
    """Confirm that the discovered endpoint accepts a current browser connection."""
    try:
        from websockets.sync.client import connect

        with connect(ws_url, open_timeout=timeout, close_timeout=1):
            return
    except Exception as exc:
        raise BrowserSetupError(
            f"Existing Chrome remote debugging is unreachable; {_REMOTE_DEBUG_HINT}."
        ) from exc


class _DirectCdp:
    """Small independent browser-level CDP connection used for owned-tab cleanup."""

    def __init__(self, ws_url, *, timeout=5):
        from websockets.sync.client import connect

        self._socket = connect(ws_url, open_timeout=timeout, close_timeout=1)
        self._timeout = timeout
        self._next_id = 0

    def call(self, method, **params):
        if self._socket is None:
            raise RuntimeError("direct CDP connection is closed")
        self._next_id += 1
        request_id = self._next_id
        self._socket.send(json.dumps({"id": request_id, "method": method, "params": params}))
        deadline = time.monotonic() + self._timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"direct CDP {method} timed out")
            message = json.loads(self._socket.recv(timeout=remaining))
            if not isinstance(message, dict) or message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(str(message["error"]))
            return message.get("result", {})

    def close(self):
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            finally:
                self._socket = None


def _discover_existing_chrome_ws(active_port=None, *, validate=True, timeout=5):
    """Return the validated WebSocket for the running macOS default Chrome profile."""
    if sys.platform != "darwin":
        raise BrowserSetupError("existing-chrome is supported only on macOS.")
    path = active_port or (
        Path.home() / "Library/Application Support/Google/Chrome" / _ACTIVE_PORT_NAME
    )
    ws_url = _active_port_ws(path)
    if validate:
        _validate_cdp_ws(ws_url, timeout=timeout)
    return ws_url


def existing_chrome_ws(active_port=None, *, validate=True, timeout=5):
    return _discover_existing_chrome_ws(active_port, validate=validate, timeout=timeout)


def chrome_path():
    candidates = [
        os.environ.get("JEV_QA_CHROME"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError("Chrome was not found. Set JEV_QA_CHROME to its executable.")


@contextmanager
def isolated_runtime():
    # Upstream captures these settings at import time. One CLI invocation owns one runtime.
    if "browser_harness.helpers" in sys.modules:
        raise RuntimeError("Start each QA run in a fresh process before importing Browser Harness.")
    with tempfile.TemporaryDirectory(prefix="jevqa-", dir="/tmp") as directory:
        root = Path(directory)
        settings = {
            "BH_HOME": str(root / "harness"),
            "BH_RUNTIME_DIR": str(root / "ipc"),
            "BH_TMP_DIR": str(root / "tmp"),
            "BH_AGENT_WORKSPACE": str(root / "workspace"),
            "BH_TAB_MARKER": "0",
            "BU_NAME": f"jevqa-{os.getpid()}",
            "BU_BROWSER_ID": None,
            "BU_CDP_URL": None,
            "BU_CDP_WS": None,
        }
        previous = {key: os.environ.get(key) for key in settings}
        for key, value in settings.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        try:
            yield root
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def _load_harness():
    # Import only after isolated_runtime has set the private IPC environment.
    from browser_harness import admin
    from jev_ultrafast.browser import Browser

    return admin, Browser


def _close_target(target):
    from browser_harness.helpers import cdp

    cdp("Target.closeTarget", targetId=target)


def _remember_target(owned_targets, target):
    if isinstance(target, str) and target and target not in owned_targets:
        owned_targets.append(target)


def _daemon_target():
    from browser_harness import helpers

    response = helpers._send({"meta": "current_tab"}, response_timeout=5)
    target = response.get("targetId") if isinstance(response, dict) else None
    if not isinstance(target, str) or not target:
        raise RuntimeError("Private browser daemon did not report its dedicated tab.")
    return target


def _new_browser(browser_class, url, owned_targets=None):
    """Construct Browser while retaining a target for cleanup on partial failure."""
    owned_targets = owned_targets if owned_targets is not None else []
    browser = browser_class.__new__(browser_class)
    browser.target = None
    try:
        browser_class.__init__(browser, url)
    except BaseException:
        target = getattr(browser, "target", None)
        if target:
            _remember_target(owned_targets, target)
            try:
                _close_target(target)
            except Exception:
                pass
        raise
    _remember_target(owned_targets, getattr(browser, "target", None))
    return browser


def _close_owned_targets(connection, ws_url, owned_targets):
    """Close only explicitly recorded targets through the independent browser connection."""
    targets = [target for target in owned_targets if isinstance(target, str) and target]
    if not targets:
        return
    owned_connection = connection is None
    direct = connection
    try:
        if direct is None:
            direct = _DirectCdp(ws_url)
        failures = []
        for target in targets:
            try:
                result = direct.call("Target.closeTarget", targetId=target)
                if isinstance(result, dict) and result.get("success") is False:
                    raise RuntimeError("Target.closeTarget returned success=false")
            except Exception as exc:
                message = str(exc).lower()
                if "target" in message and ("not found" in message or "no target" in message):
                    continue
                failures.append(exc)
        if failures:
            raise BrowserCleanupError(
                "Browser cleanup incomplete: Chrome did not close all recorded owned tabs."
            ) from failures[0]
        remaining = set(targets)
        deadline = time.monotonic() + 5
        while remaining:
            if time.monotonic() >= deadline:
                raise BrowserCleanupError(
                    "Browser cleanup incomplete: recorded owned tabs remained open."
                )
            result = direct.call("Target.getTargets")
            infos = result.get("targetInfos") if isinstance(result, dict) else None
            if not isinstance(infos, list):
                raise RuntimeError("Target.getTargets returned an invalid result")
            live = {
                item.get("targetId")
                for item in infos
                if isinstance(item, dict) and isinstance(item.get("targetId"), str)
            }
            remaining.intersection_update(live)
            if remaining:
                time.sleep(0.05)
    except BrowserCleanupError:
        raise
    except Exception as exc:
        raise BrowserCleanupError(
            "Browser cleanup incomplete: the Chrome CDP connection became unreachable."
        ) from exc
    finally:
        if owned_connection and direct is not None:
            direct.close()


def _surface_cleanup_error(active_error, cleanup_error):
    """Mark cleanup failure without changing the original exception text or type."""
    try:
        active_error.jev_qa_cleanup_incomplete = True
        active_error.jev_qa_cleanup_message = _CLEANUP_INCOMPLETE_MESSAGE
        active_error.add_note(_CLEANUP_INCOMPLETE_MESSAGE)
    except Exception:
        pass


def _stop_daemon(daemon, _admin):
    """Ask the private daemon to close its dedicated tab before process fallback."""
    if daemon is None:
        return
    if daemon.poll() is None:
        try:
            from browser_harness import helpers

            response = helpers._send({"meta": "shutdown"}, response_timeout=5)
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise RuntimeError("daemon did not confirm clean shutdown")
        except Exception:
            pass
    if daemon.poll() is None:
        try:
            daemon.wait(timeout=5)
        except subprocess.TimeoutExpired:
            daemon.terminate()
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait(timeout=5)


@contextmanager
def browser_session(url, *, existing=False):
    if not os.environ.get("BU_NAME", "").startswith("jevqa-"):
        raise RuntimeError("A private runtime is required before opening Chrome.")
    root = Path(os.environ["BH_HOME"]).parent
    profile = root / "chrome"
    process = None
    browser = None
    daemon = None
    admin = None
    direct = None
    owned_targets = []
    previous_ws = os.environ.get("BU_CDP_WS")
    ws_url = None
    active_error = None
    daemon_started = False
    daemon_target_recorded = False
    try:
        if existing:
            ws_url = existing_chrome_ws()
            os.environ["BU_CDP_WS"] = ws_url
        else:
            process = subprocess.Popen(
                [
                    chrome_path(),
                    "--headless=new",
                    "--remote-debugging-port=0",
                    "--remote-debugging-address=127.0.0.1",
                    f"--user-data-dir={profile}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-sync",
                    "--disable-background-networking",
                    "about:blank",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 15
            port_file = profile / _ACTIVE_PORT_NAME
            while not port_file.exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Private Chrome did not start within 15 seconds.")
                time.sleep(0.05)
            ws_url = _active_port_ws(port_file)
            os.environ["BU_CDP_WS"] = ws_url
        try:
            direct = _DirectCdp(ws_url)
        except Exception as exc:
            if existing:
                raise BrowserSetupError(
                    f"Existing Chrome remote debugging is unreachable; {_REMOTE_DEBUG_HINT}."
                ) from exc
            raise RuntimeError("Private Chrome remote debugging did not accept a connection.") from exc
        admin, Browser = _load_harness()

        daemon = subprocess.Popen(
            [sys.executable, "-m", "browser_harness.daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        daemon_started = True
        deadline = time.monotonic() + 15
        while True:
            if daemon.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Private browser connection did not start within 15 seconds.")
            if (root / "ipc" / "bu.sock").exists():
                try:
                    if admin.daemon_browser_ready():
                        break
                except Exception:
                    pass
            time.sleep(0.05)
        _remember_target(owned_targets, _daemon_target())
        daemon_target_recorded = True
        browser = _new_browser(Browser, url, owned_targets)
        browser._jevqa_owned_target_ids = tuple(owned_targets)
        try:
            yield browser
        except BaseException as exc:
            active_error = exc
            raise
    except BaseException as exc:
        if active_error is None:
            active_error = exc
        raise
    finally:
        # The execution budget ends here. Teardown has its own bounded waits.
        signal.setitimer(signal.ITIMER_REAL, 0)
        cleanup_errors = []
        try:
            if browser is not None and (daemon is None or daemon.poll() is None):
                try:
                    browser.close()
                except Exception:
                    # Direct CDP cleanup below handles a crashed daemon.
                    pass
        finally:
            try:
                _stop_daemon(daemon, admin)
            except BaseException as exc:
                cleanup_errors.append(exc)
            try:
                _close_owned_targets(direct, ws_url, owned_targets)
            except BaseException as exc:
                cleanup_errors.append(exc)
            if daemon_started and not daemon_target_recorded:
                cleanup_errors.append(
                    BrowserCleanupError(
                        "Browser cleanup incomplete: the daemon started but did not report its owned tab."
                    )
                )
            try:
                if direct is not None:
                    direct.close()
            except BaseException as exc:
                cleanup_errors.append(exc)
            try:
                if process is not None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            except BaseException as exc:
                cleanup_errors.append(exc)
            finally:
                if previous_ws is None:
                    os.environ.pop("BU_CDP_WS", None)
                else:
                    os.environ["BU_CDP_WS"] = previous_ws
        if cleanup_errors:
            cleanup_error = cleanup_errors[0]
            if not isinstance(cleanup_error, BrowserCleanupError):
                cleanup_error = BrowserCleanupError("Browser cleanup incomplete.")
                cleanup_errors[0] = cleanup_error
            if active_error is not None:
                _surface_cleanup_error(active_error, cleanup_error)
            else:
                raise cleanup_error
