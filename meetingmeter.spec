# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect all pywebview modules, binaries, and data files
webview_datas, webview_binaries, webview_hiddenimports = collect_all('webview')

# Use icon if available (local dev), otherwise skip (CI)
_icns = os.path.join(os.path.dirname(os.path.abspath(SPEC)), 'MeetingMeter.app', 'Contents', 'Resources', 'AppIcon.icns')
_icon = _icns if os.path.exists(_icns) else None

a = Analysis(
    ['meetingmeter_main.py'],
    pathex=[],
    binaries=webview_binaries,
    datas=[('meetingmeter.html', '.')] + webview_datas,
    hiddenimports=webview_hiddenimports + [
        'webview',
        'webview.platforms.cocoa',
        'objc',
        'Foundation',
        'AppKit',
        'WebKit',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MeetingMeter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

app = BUNDLE(
    exe,
    name='MeetingMeter.app',
    icon=_icon,
    bundle_identifier='com.meetingmeter.app',
    info_plist={
        'CFBundleShortVersionString': '1.0',
        'CFBundleVersion': '1.0',
        'NSHighResolutionCapable': True,
        'CFBundleName': 'MeetingMeter',
        'CFBundleDisplayName': 'MeetingMeter',
    },
)
