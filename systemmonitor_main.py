#!/usr/bin/env python3
"""SystemMonitor — native desktop app using pywebview."""

import sys
import os
import time
import threading
from http.server import HTTPServer

# Resolve monitor.html path (works both dev and bundled)
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Patch monitor_server to find monitor.html from the correct location
os.chdir(BASE_DIR)

from monitor_server import Handler, get_stats
import psutil
import webview

PORT = 8765


def start_server():
    psutil.cpu_percent(interval=None, percpu=True)
    time.sleep(0.2)
    server = HTTPServer(("localhost", PORT), Handler)
    server.serve_forever()


def main():
    # Start HTTP server in background thread
    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    # Wait briefly for server to be ready
    time.sleep(0.8)

    # Open native window
    window = webview.create_window(
        title="System Monitor",
        url=f"http://localhost:{PORT}",
        width=1100,
        height=780,
        min_size=(800, 600),
        resizable=True,
        text_select=False,
        background_color="#0d1117",
    )
    webview.start()


if __name__ == "__main__":
    main()
