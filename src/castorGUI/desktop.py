"""
Desktop build: the web frontend in a native window.

There is no second UI here. This starts the same FastAPI host the browser build
uses on a loopback port and points an OS webview at it, so the desktop app and the
page mounted inside Kinder are the same HTML, CSS and JavaScript. Anything else
would recreate the very duplication frontend/ exists to end.

pywebview uses the platform's own engine (WKWebView on macOS, WebView2 on Windows,
WebKitGTK on Linux) rather than shipping a browser, which is why the desktop build
needs no Node or Rust toolchain — the project has neither and should not grow one
just to get a window.

    python src/castorGUI/desktop.py

To package it, the assets have to be carried along (see _asset_root in server.py):

    pyinstaller --onefile --windowed --name "CASTOR ETC" \
        --add-data "src/castorGUI/frontend:frontend" \
        --add-data "src/castorGUI/data:data" \
        src/castorGUI/desktop.py
"""
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn
import webview

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from server import app  # noqa: E402

WINDOW_TITLE = "CASTOR"
STARTUP_TIMEOUT_SECONDS = 15


def _free_port() -> int:
    """Asks the OS for an unused loopback port.

    Binding to port 0 and reading back the assignment leaves a brief window in which
    something else could claim it before uvicorn binds. That is tolerable here: this
    is a single desktop process on a loopback interface, and the alternative — a
    fixed port — fails outright whenever a second copy is already running.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def start_server() -> tuple[uvicorn.Server, int]:
    """Runs the API host on a background thread and returns once it is accepting
    connections, so the window never opens onto a page that isn't being served yet.

    Split out from main() because it is the half that can be exercised without a
    display.
    """
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError(f"API host failed to start on port {port} within {STARTUP_TIMEOUT_SECONDS}s")
        time.sleep(0.05)
    return server, port


def main() -> None:
    server, port = start_server()
    webview.create_window(WINDOW_TITLE, f"http://127.0.0.1:{port}", width=1440, height=920)
    # Blocks until the user closes the window; the daemon thread would die with the
    # process anyway, but asking the server to stop first lets it close cleanly.
    webview.start()
    server.should_exit = True


if __name__ == "__main__":
    main()
