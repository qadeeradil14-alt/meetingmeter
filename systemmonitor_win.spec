import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

webview_datas, webview_binaries, webview_hiddenimports = collect_all("webview")

a = Analysis(
    ["systemmonitor_main.py"],
    pathex=["."],
    binaries=webview_binaries,
    datas=webview_datas + [("monitor.html", "."), ("monitor_server.py", ".")],
    hiddenimports=webview_hiddenimports + [
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.mshtml",
        "psutil",
    ],
    excludes=["tkinter"],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="SystemMonitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)
