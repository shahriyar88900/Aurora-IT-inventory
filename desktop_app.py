#!/usr/bin/env python3
"""Aurora Plant IT Inventory - Desktop Edition.

Runs the existing server (server.py) in a background thread and shows it
inside a native window using pywebview, instead of opening a browser tab.
Nothing about server.py itself changes: this file only wraps it, so the
original browser/LAN launcher (Start_Aurora_Inventory.bat) keeps working
exactly as before.
"""

import os
import socket
import sys
import threading

import webview

import server as app_server

# pywebview disables in-window downloads by default. This app relies on
# "Export CSV" and "Download Excel template" triggering real file downloads,
# so this must be enabled before the window is created.
webview.settings["ALLOW_DOWNLOADS"] = True

HOST = "127.0.0.1"
PORT = int(os.environ.get("APS_PORT", "8090"))
WINDOW_TITLE = f"Aurora Plant IT Inventory v{app_server.APP_VERSION}"


def port_is_free(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) != 0


def start_backend():
    """Initialize the database and start the HTTP server on a daemon thread."""
    app_server.initialize()
    try:
        httpd = app_server.ThreadingHTTPServer((HOST, PORT), app_server.Handler)
    except OSError as exc:
        print(f"ERROR: Cannot start Aurora Plant IT Inventory on port {PORT}.")
        print("Another copy of the app may already be running.")
        print(f"Detail: {exc}")
        sys.exit(1)

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def main():
    if not port_is_free(HOST, PORT):
        webview.create_window(
            WINDOW_TITLE,
            html=(
                "<body style='font-family:sans-serif;padding:40px;text-align:center'>"
                "<h2>Aurora Plant IT Inventory is already running</h2>"
                "<p>Close the other window first, then start this app again.</p>"
                "</body>"
            ),
            width=480,
            height=220,
        )
        webview.start()
        return

    httpd = start_backend()
    try:
        window = webview.create_window(
            WINDOW_TITLE,
            f"http://{HOST}:{PORT}/login?release={app_server.APP_VERSION}",
            width=1280,
            height=820,
            min_size=(1000, 650),
        )
        webview.start()
    finally:
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()
