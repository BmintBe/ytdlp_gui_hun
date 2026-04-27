from setuptools import setup

APP = ['ytdlp_gui.py']
OPTIONS = {
    'argv_emulation': False,
    'packages': ['PyQt6'],
    'includes': [
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtNetwork',
        'PyQt6.sip',
    ],
    'excludes': ['tkinter', 'matplotlib', 'numpy'],
    'no_zip': True,
    'site_packages': True,
    'plist': {
        'CFBundleName': 'yt-dlp GUI',
        'CFBundleDisplayName': 'yt-dlp GUI',
        'CFBundleIdentifier': 'com.ytdlp.gui',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'LSMinimumSystemVersion': '12.0',
    },
}

setup(
    app=APP,
    name='yt-dlp GUI',
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
