import os
from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

block_cipher = None

_icns = os.path.join(os.path.dirname(SPECPATH), "SystemMonitorIcon.icns")
_icon = _icns if os.path.exists(_icns) else None

webview_datas, webview_binaries, webview_hiddenimports = collect_all("webview")

a = Analysis(
    ["systemmonitor_main.py"],
    pathex=["."],
    binaries=webview_binaries,
    datas=webview_datas + [("monitor.html", "."), ("monitor_server.py", ".")],
    hiddenimports=webview_hiddenimports + [
        "webview",
        "webview.platforms.cocoa",
        "objc",
        "Foundation",
        "AppKit",
        "WebKit",
        "psutil",
        "_psutil_osx",
        "_psutil_posix",
    ],
    excludes=["tkinter"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SystemMonitor",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False,
    upx=False,
    name="SystemMonitor",
)

app = BUNDLE(
    coll,
    name="SystemMonitor.app",
    icon=_icon,
    bundle_identifier="com.aqadil.systemmonitor",
    info_plist={
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleName": "System Monitor",
        "NSHighResolutionCapable": True,
    },
)
