"""Standalone launcher for the pixel-palette web app.

Starts the Flask server, opens the default browser, and keeps running until
the server is shut down (e.g. via the "Close app" button in the UI). If the
port is already in use, it simply opens the browser to the running instance.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.request
import webbrowser

from werkzeug.serving import make_server

from app import app

HOST = "127.0.0.1"
PORT = 5000
URL = f"http://{HOST}:{PORT}"


def _port_in_use(host: str, port: int) -> bool:
    s = socket.socket()
    try:
        s.bind((host, port))
        return False
    except OSError:
        return True
    finally:
        s.close()


def _up(timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(URL, timeout=1):
                return True
        except Exception:
            time.sleep(0.15)
    return False


def _open_browser() -> None:
    if _up():
        webbrowser.open(URL)
    else:
        print(f"Could not reach the server at {URL}")


if __name__ == "__main__":
    if _port_in_use(HOST, PORT):
        # A Pixel Palette instance is already running: just open the browser.
        print(f"A Pixel Palette instance is already running at {URL}")
        webbrowser.open(URL)
        raise SystemExit(0)

    server = make_server(HOST, PORT, app, threaded=True)
    app.config["ENABLE_SHUTDOWN"] = True
    app.config["_server"] = server
    threading.Thread(target=_open_browser, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()