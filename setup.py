from setuptools import setup

APP = ['ytdlp_gui.py']
OPTIONS = {
    'argv_emulation': False,
    'packages': ['PyQt6'],
    'iconfile': None,
    'plist': {
        'CFBundleName': 'yt-dlp GUI',
        'CFBundleDisplayName': 'yt-dlp GUI',
        'CFBundleIdentifier': 'com.ytdlp.gui',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
    },
}

setup(
    app=APP,
    name='yt-dlp GUI',
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
