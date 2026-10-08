import os
import socket
import sys
import threading
import time
import webbrowser

import uvicorn


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    # windowed PyInstaller builds have no stdout/stderr; uvicorn's logging would crash on them
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    from .server import app

    port = int(os.environ.get("NQ_KLINE_PORT") or _free_port())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}/"

    if "--browser" in sys.argv:  # dev / fallback: use the default browser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
    try:
        import webview

        webview.create_window("那斯達克 NQ K線分析", url, width=1500, height=950, min_size=(1000, 650))
        webview.start()
    except Exception:
        webbrowser.open(url)
        while True:
            time.sleep(1)
    server.should_exit = True
