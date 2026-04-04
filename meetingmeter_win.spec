# -*- mode: python ; coding: utf-8 -*-
# Windows build spec — produces a single MeetingMeter.exe
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect all pywebview modules, binaries, and data files
webview_datas, webview_binaries, webview_hiddenimports = collect_all('webview')

a = Analysis(
    ['meetingmeter_main.py'],
    pathex=[],
    binaries=webview_binaries,
    datas=[('meetingmeter.html', '.')] + webview_datas,
    hiddenimports=webview_hiddenimports + [
        'webview',
        'webview.platforms.edgechromium',
        'webview.platforms.mshtml',
        'clr',
        'System',
        'System.Windows.Forms',
        'System.Threading',
        'System.Threading.Thread',
        'reportlab',
        'reportlab.lib',
        'reportlab.lib.pagesizes',
        'reportlab.lib.styles',
        'reportlab.lib.units',
        'reportlab.lib.colors',
        'reportlab.lib.enums',
        'reportlab.platypus',
        'reportlab.pdfgen',
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
    console=False,          # No black console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # Add a .ico file here if you have one
)
