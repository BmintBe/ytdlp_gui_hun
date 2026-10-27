import sys
import os
import subprocess
import shutil
import json
import stat
import urllib.request
import urllib.error
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox, QTextEdit,
    QProgressBar, QFileDialog, QGroupBox, QGridLayout, QMessageBox,
    QTabWidget, QScrollArea, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPalette, QColor

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

YTDLP_BIN   = "yt-dlp.exe"    if IS_WIN else "yt-dlp"
FFMPEG_BIN  = "ffmpeg.exe"    if IS_WIN else "ffmpeg"
POPEN_FLAGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WIN else {}
DEFAULT_DL  = Path.home() / "Downloads" / "%(title)s.%(ext)s"

GITHUB_YTDLP_ASSET  = "yt-dlp.exe" if IS_WIN else ("yt-dlp_macos" if IS_MAC else "yt-dlp_linux")
FFMPEG_MAC_URL = "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"

# ── Témák ──────────────────────────────────────────────────────────────────────
DARK_THEME = {
    "BG":   "#1e1e2e", "SURF": "#28283d", "PNL": "#313148",
    "ACC":  "#89b4fa", "TXT":  "#cdd6f4", "RED": "#f38ba8",
    "GRN":  "#a6e3a1", "YEL":  "#f9e2af", "SUB": "#6c7086",
    "BORDER": "#44445a",
}
LIGHT_THEME = {
    "BG":   "#eff1f5", "SURF": "#ffffff", "PNL": "#e6e9ef",
    "ACC":  "#1e66f5", "TXT":  "#4c4f69", "RED": "#d20f39",
    "GRN":  "#40a02b", "YEL":  "#df8e1d", "SUB": "#9ca0b0",
    "BORDER": "#ccd0da",
}


def get_bin_path(name: str) -> str:
    own = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    local = own / name
    if local.exists():
        return str(local)
    found = shutil.which(name.replace(".exe", "") if IS_WIN else name)
    return found or ""


def get_version(path: str) -> str:
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True, **POPEN_FLAGS)
        return r.stdout.strip().splitlines()[0]
    except Exception:
        return "ismeretlen"


# ── Frissítő szál ─────────────────────────────────────────────────────────────
class UpdateThread(QThread):
    log_signal      = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, dest_dir: str, mode: str = "ytdlp"):
        super().__init__()
        self.dest_dir = dest_dir
        self.mode = mode

    def run(self):
        try:
            if self.mode == "ytdlp":
                self._update_ytdlp()
            else:
                self._update_ffmpeg()
        except urllib.error.URLError as e:
            self.finished_signal.emit(False, f"Hálózati hiba: {e.reason}")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

    def _download(self, url, dest_path):
        req = urllib.request.Request(url, headers={"User-Agent": "ytdlp-gui"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest_path, "wb") as f:
                while True:
                    buf = resp.read(65536)
                    if not buf:
                        break
                    f.write(buf)
                    downloaded += len(buf)
                    if total:
                        self.progress_signal.emit(int(downloaded / total * 100))

    def _make_exec(self, path: Path):
        if not IS_WIN:
            path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def _update_ytdlp(self):
        api = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
        self.log_signal.emit("yt-dlp: GitHub API lekérdezése...")
        req = urllib.request.Request(api, headers={"User-Agent": "ytdlp-gui"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        tag = data["tag_name"]
        self.log_signal.emit(f"yt-dlp legújabb verzió: {tag}")
        dl_url = next(
            (a["browser_download_url"] for a in data.get("assets", [])
             if a["name"] == GITHUB_YTDLP_ASSET), None)
        if not dl_url:
            self.finished_signal.emit(False, "yt-dlp bináris nem található")
            return
        dest = Path(self.dest_dir) / YTDLP_BIN
        tmp  = Path(self.dest_dir) / (YTDLP_BIN + ".tmp")
        self.log_signal.emit("yt-dlp letöltése...")
        self._download(dl_url, tmp)
        self._make_exec(tmp)
        tmp.replace(dest)
        self.log_signal.emit(f"yt-dlp frissítve → {dest}")
        self.finished_signal.emit(True, "ytdlp")

    def _update_ffmpeg(self):
        dest_dir = Path(self.dest_dir)
        dest = dest_dir / FFMPEG_BIN
        tmp  = dest_dir / (FFMPEG_BIN + ".tmp")

        if IS_WIN:
            api = "https://api.github.com/repos/BtbN/ffmpeg-builds/releases/latest"
            self.log_signal.emit("ffmpeg: GitHub API lekérdezése...")
            req = urllib.request.Request(api, headers={"User-Agent": "ytdlp-gui"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            dl_url = next(
                (a["browser_download_url"] for a in data.get("assets", [])
                 if "win64" in a["name"] and "lgpl" in a["name"] and a["name"].endswith(".zip")),
                None)
            if not dl_url:
                self.finished_signal.emit(False, "ffmpeg zip nem található")
                return
            self.log_signal.emit("ffmpeg letöltése (zip)...")
            zip_tmp = dest_dir / "ffmpeg.zip"
            self._download(dl_url, zip_tmp)
            self.log_signal.emit("ffmpeg kicsomagolása...")
            import zipfile
            with zipfile.ZipFile(zip_tmp) as z:
                for name in z.namelist():
                    if name.endswith("bin/ffmpeg.exe"):
                        with z.open(name) as src, open(tmp, "wb") as dst:
                            dst.write(src.read())
                        break
            zip_tmp.unlink(missing_ok=True)
        elif IS_MAC:
            self.log_signal.emit("ffmpeg letöltése (macOS)...")
            import zipfile, io
            req = urllib.request.Request(FFMPEG_MAC_URL, headers={"User-Agent": "ytdlp-gui"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                data = b""
                while True:
                    buf = resp.read(65536)
                    if not buf:
                        break
                    data += buf
                    if total:
                        self.progress_signal.emit(int(len(data) / total * 100))
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for name in z.namelist():
                    if name == "ffmpeg":
                        with z.open(name) as src, open(tmp, "wb") as dst:
                            dst.write(src.read())
                        break

        self._make_exec(tmp)
        tmp.replace(dest)
        self.log_signal.emit(f"ffmpeg frissítve → {dest}")
        self.finished_signal.emit(True, "ffmpeg")


# ── Letöltő szál ──────────────────────────────────────────────────────────────
class DownloadThread(QThread):
    log_signal      = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, cmd):
        super().__init__()
        self.cmd   = cmd
        self._proc = None

    def run(self):
        try:
            self._proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                **POPEN_FLAGS,
            )
            for line in self._proc.stdout:
                line = line.rstrip()
                if line:
                    self.log_signal.emit(line)
                    if "[download]" in line and "%" in line:
                        try:
                            pct = float(line.split("%")[0].split()[-1])
                            self.progress_signal.emit(int(pct))
                        except Exception:
                            pass
            self._proc.wait()
            ok = self._proc.returncode == 0
            self.finished_signal.emit(ok, "Letöltés kész!" if ok else f"Hiba (kód: {self._proc.returncode})")
        except FileNotFoundError:
            self.finished_signal.emit(False, "yt-dlp nem található!")
        except Exception as e:
            self.finished_signal.emit(False, f"Kivétel: {e}")

    def stop(self):
        if self._proc:
            self._proc.terminate()


# ── Főablak ───────────────────────────────────────────────────────────────────
class YtDlpGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("yt-dlp Letöltő")
        self.setMinimumWidth(680)
        self.setMinimumHeight(480)
        self._thread      = None
        self._upd_thread  = None
        self._ytdlp       = get_bin_path(YTDLP_BIN)
        self._ffmpeg      = get_bin_path(FFMPEG_BIN)
        self._dark_mode   = True
        self._apply_theme()
        self._build_ui()
        self._refresh_status()

    # ── Témák ─────────────────────────────────────────────────────────────────
    def _apply_theme(self):
        t = DARK_THEME if self._dark_mode else LIGHT_THEME
        app = QApplication.instance()
        app.setStyle("Fusion")
        pal = QPalette()
        for role, key in [
            (QPalette.ColorRole.Window,          "BG"),
            (QPalette.ColorRole.WindowText,      "TXT"),
            (QPalette.ColorRole.Base,            "SURF"),
            (QPalette.ColorRole.AlternateBase,   "PNL"),
            (QPalette.ColorRole.Text,            "TXT"),
            (QPalette.ColorRole.Button,          "PNL"),
            (QPalette.ColorRole.ButtonText,      "TXT"),
            (QPalette.ColorRole.BrightText,      "RED"),
            (QPalette.ColorRole.Highlight,       "ACC"),
            (QPalette.ColorRole.HighlightedText, "BG"),
        ]:
            pal.setColor(role, QColor(t[key]))
        app.setPalette(pal)

        hover_btn = "#3a3a55" if self._dark_mode else "#d4d8e0"
        mono_font = "Menlo" if IS_MAC else "Consolas"

        app.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {t["BG"]}; color: {t["TXT"]};
            }}
            QScrollArea {{
                background: {t["BG"]}; border: none;
            }}
            QScrollBar:vertical {{
                background: {t["PNL"]}; width: 8px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {t["BORDER"]}; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t["ACC"]};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QTabWidget::pane {{
                border: 1px solid {t["BORDER"]}; border-radius: 8px;
                background: {t["BG"]}; top: -1px;
            }}
            QTabBar::tab {{
                background: {t["PNL"]}; color: {t["SUB"]};
                border: 1px solid {t["BORDER"]}; border-bottom: none;
                border-radius: 6px 6px 0 0;
                padding: 7px 20px; margin-right: 3px; font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background: {t["BG"]}; color: {t["ACC"]};
                border-bottom: 1px solid {t["BG"]};
            }}
            QTabBar::tab:hover:!selected {{
                background: {hover_btn};
            }}
            QGroupBox {{
                border: 1px solid {t["BORDER"]}; border-radius: 8px;
                margin-top: 8px; padding: 8px 12px 12px 12px;
                font-weight: bold; color: {t["ACC"]};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; left: 10px; padding: 0 4px;
            }}
            QLineEdit, QComboBox, QTextEdit {{
                background: {t["SURF"]}; border: 1px solid {t["BORDER"]};
                border-radius: 6px; padding: 6px 10px; color: {t["TXT"]};
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 1px solid {t["ACC"]};
            }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {t["SURF"]};
                selection-background-color: {t["ACC"]};
                selection-color: {t["BG"]};
            }}
            QPushButton {{
                background: {t["PNL"]}; border: 1px solid {t["BORDER"]};
                border-radius: 6px; padding: 7px 18px;
                color: {t["TXT"]}; font-weight: bold;
            }}
            QPushButton:hover {{ background: {hover_btn}; border-color: {t["ACC"]}; }}
            QPushButton:pressed {{ background: {t["ACC"]}; color: {t["BG"]}; }}
            QPushButton#btn_download {{
                background: {t["ACC"]}; color: {t["BG"]};
                border: none; font-size: 14px; padding: 10px 24px;
            }}
            QPushButton#btn_download:hover {{ background: {t["ACC"]}cc; }}
            QPushButton#btn_download:disabled {{
                background: {t["PNL"]}; color: {t["SUB"]};
            }}
            QPushButton#btn_stop {{
                background: {t["RED"]}; color: {t["BG"]}; border: none;
            }}
            QPushButton#btn_theme, QPushButton#btn_theme2 {{
                background: {t["PNL"]}; border: 1px solid {t["BORDER"]};
                border-radius: 14px; padding: 4px 14px;
                color: {t["TXT"]}; font-size: 12px;
            }}
            QPushButton#btn_theme:hover, QPushButton#btn_theme2:hover {{
                border-color: {t["ACC"]};
            }}
            QPushButton[cssClass="update_btn"] {{
                background: {t["PNL"]}; border: 1px solid {t["ACC"]};
                color: {t["ACC"]}; padding: 5px 10px;
            }}
            QPushButton[cssClass="update_btn"]:hover {{
                background: {t["ACC"]}; color: {t["BG"]};
            }}
            QPushButton[cssClass="update_btn"]:disabled {{
                border-color: {t["BORDER"]}; color: {t["SUB"]};
            }}
            QProgressBar {{
                background: {t["SURF"]}; border: 1px solid {t["BORDER"]};
                border-radius: 6px; text-align: center;
                color: {t["TXT"]}; height: 18px;
            }}
            QProgressBar::chunk {{ background: {t["ACC"]}; border-radius: 5px; }}
            QCheckBox {{ spacing: 8px; color: {t["TXT"]}; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {t["BORDER"]}; border-radius: 4px;
                background: {t["SURF"]};
            }}
            QCheckBox::indicator:checked {{
                background: {t["ACC"]}; border-color: {t["ACC"]};
            }}
            QTextEdit {{
                font-family: {mono_font}, monospace; font-size: 11px;
            }}
        """)

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self._apply_theme()
        label_dark  = "☀️  Világos mód"
        label_light = "\U0001f319  Sötét mód"
        self.btn_theme.setText(label_dark if self._dark_mode else label_light)
        self.btn_theme2.setText(label_dark if self._dark_mode else label_light)
        self._refresh_status()

    # ── UI építés ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main_lay = QVBoxLayout(root)
        main_lay.setSpacing(10)
        main_lay.setContentsMargins(16, 12, 16, 16)

        # ── Fejléc: cím + témaváltó ──
        header = QHBoxLayout()
        title_lbl = QLabel("yt-dlp Letöltő")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.btn_theme = QPushButton("☀️  Világos mód")
        self.btn_theme.setObjectName("btn_theme")
        self.btn_theme.clicked.connect(self._toggle_theme)
        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(self.btn_theme)
        main_lay.addLayout(header)

        # ── Fülek ──
        self.tabs = QTabWidget()
        main_lay.addWidget(self.tabs)

        # === 1. fül: Letöltés ===
        dl_tab = QWidget()
        dl_lay = QVBoxLayout(dl_tab)
        dl_lay.setSpacing(10)
        dl_lay.setContentsMargins(10, 14, 10, 10)

        # Eszközök állapota
        grp_tools = QGroupBox("  Eszközök")
        tools_lay = QGridLayout(grp_tools)
        tools_lay.setSpacing(6)

        self.lbl_ytdlp_ver  = QLabel("...")
        self.lbl_ytdlp_path = QLabel("")
        self.lbl_ytdlp_path.setStyleSheet("font-size:10px;")
        self.btn_upd_ytdlp  = QPushButton("Frissítés")
        self.btn_upd_ytdlp.setProperty("cssClass", "update_btn")
        self.btn_upd_ytdlp.clicked.connect(lambda: self._start_update("ytdlp"))

        self.lbl_ffmpeg_ver  = QLabel("...")
        self.lbl_ffmpeg_path = QLabel("")
        self.lbl_ffmpeg_path.setStyleSheet("font-size:10px;")
        self.btn_upd_ffmpeg  = QPushButton("Letöltés")
        self.btn_upd_ffmpeg.setProperty("cssClass", "update_btn")
        self.btn_upd_ffmpeg.clicked.connect(lambda: self._start_update("ffmpeg"))

        tools_lay.addWidget(QLabel("yt-dlp:"),          0, 0)
        tools_lay.addWidget(self.lbl_ytdlp_ver,         0, 1)
        tools_lay.addWidget(self.lbl_ytdlp_path,        1, 1)
        tools_lay.addWidget(self.btn_upd_ytdlp,         0, 2, 2, 1)
        tools_lay.addWidget(QLabel("ffmpeg:"),           2, 0)
        tools_lay.addWidget(self.lbl_ffmpeg_ver,        2, 1)
        tools_lay.addWidget(self.lbl_ffmpeg_path,       3, 1)
        tools_lay.addWidget(self.btn_upd_ffmpeg,        2, 2, 2, 1)
        tools_lay.setColumnStretch(1, 1)
        dl_lay.addWidget(grp_tools)

        # URL
        grp_url = QGroupBox("  URL")
        url_lay = QHBoxLayout(grp_url)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_edit.textChanged.connect(self._update_cmd)
        url_lay.addWidget(self.url_edit)
        dl_lay.addWidget(grp_url)

        # Formátum
        grp_fmt = QGroupBox("  Formátum és minőség")
        fmt_lay = QGridLayout(grp_fmt)
        fmt_lay.setSpacing(8)
        fmt_lay.addWidget(QLabel("Tartalom:"), 0, 0)
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(["Videó + hang", "Csak videó", "Csak hang"])
        self.cmb_type.currentIndexChanged.connect(self._on_type_change)
        fmt_lay.addWidget(self.cmb_type, 0, 1)
        fmt_lay.addWidget(QLabel("Minőség:"), 0, 2)
        self.cmb_quality = QComboBox()
        self.cmb_quality.addItems(["Legjobb", "1080p", "720p", "480p", "360p", "Legrosszabb"])
        self.cmb_quality.currentIndexChanged.connect(self._update_cmd)
        fmt_lay.addWidget(self.cmb_quality, 0, 3)
        fmt_lay.addWidget(QLabel("Konvertálás:"), 1, 0)
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(["– eredeti –", "mp4", "mkv", "webm", "mp3", "m4a", "opus", "flac", "wav"])
        self.cmb_format.currentIndexChanged.connect(self._update_cmd)
        fmt_lay.addWidget(self.cmb_format, 1, 1)
        dl_lay.addWidget(grp_fmt)

        # Mentési hely
        grp_out = QGroupBox("  Mentési hely")
        vl = QVBoxLayout(grp_out)
        vl.setSpacing(4)
        row = QHBoxLayout()
        self.out_template = QLineEdit()
        self.out_template.setText(str(DEFAULT_DL))
        self.out_template.textChanged.connect(self._update_cmd)
        btn_browse = QPushButton("Tallózás...")
        btn_browse.clicked.connect(self._browse_dir)
        row.addWidget(self.out_template)
        row.addWidget(btn_browse)
        hint = QLabel("Sablon: %(title)s  %(uploader)s  %(id)s  %(ext)s  %(playlist_index)s")
        hint.setStyleSheet("font-size:11px;")
        vl.addLayout(row)
        vl.addWidget(hint)
        dl_lay.addWidget(grp_out)

        # Generált parancs
        grp_cmd = QGroupBox("  Generált parancs")
        self.cmd_display = QTextEdit()
        self.cmd_display.setReadOnly(True)
        self.cmd_display.setFixedHeight(50)
        QVBoxLayout(grp_cmd).addWidget(self.cmd_display)
        dl_lay.addWidget(grp_cmd)

        # Gombok
        btn_row = QHBoxLayout()
        self.btn_download = QPushButton("⬇  Letöltés")
        self.btn_download.setObjectName("btn_download")
        self.btn_download.clicked.connect(self._start_download)
        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.clicked.connect(self._stop_download)
        self.btn_stop.setEnabled(False)
        btn_row.addWidget(self.btn_download)
        btn_row.addWidget(self.btn_stop)
        dl_lay.addLayout(btn_row)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        dl_lay.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dl_lay.addWidget(self.status_label)

        # Letöltés fül scroll-ba csomagolva
        dl_scroll = QScrollArea()
        dl_scroll.setWidget(dl_tab)
        dl_scroll.setWidgetResizable(True)
        dl_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.tabs.addTab(dl_scroll, "⬇  Letöltés")

        # === 2. fül: Beállítások ===
        set_tab = QWidget()
        set_lay = QVBoxLayout(set_tab)
        set_lay.setSpacing(14)
        set_lay.setContentsMargins(10, 14, 10, 10)

        # Letöltési opciók
        grp_dl_opts = QGroupBox("  Letöltési beállítások")
        dl_opts_lay = QGridLayout(grp_dl_opts)
        dl_opts_lay.setSpacing(10)
        self.chk_subs      = self._chk("Feliratok letöltése",     dl_opts_lay, 0, 0)
        self.chk_thumbnail = self._chk("Borítókép beágyazása",    dl_opts_lay, 0, 1)
        self.chk_playlist  = self._chk("Lejátszólista letöltése", dl_opts_lay, 1, 0)
        self.chk_metadata  = self._chk("Metaadatok beágyazása",   dl_opts_lay, 1, 1)
        self.chk_chapters  = self._chk("Fejezetek beágyazása",    dl_opts_lay, 2, 0)
        self.chk_sponsor   = self._chk("SponsorBlock jelölés",    dl_opts_lay, 2, 1)
        set_lay.addWidget(grp_dl_opts)

        # Adatvédelem és hibakeresés
        grp_priv = QGroupBox("  Adatvédelem és hibakeresés")
        priv_lay = QGridLayout(grp_priv)
        priv_lay.setSpacing(10)
        self.chk_cookies = self._chk("Sütik (böngészőből)", priv_lay, 0, 0)
        self.chk_verbose = self._chk("Részletes kimenet (-v)", priv_lay, 0, 1)
        browser_note = QLabel(f"Böngésző: {'Safari' if IS_MAC else 'Firefox'}")
        browser_note.setStyleSheet("font-size:11px;")
        priv_lay.addWidget(browser_note, 1, 0, 1, 2)
        set_lay.addWidget(grp_priv)

        # Megjelenés
        grp_appear = QGroupBox("  Megjelenés")
        appear_lay = QVBoxLayout(grp_appear)
        appear_lay.setSpacing(10)
        theme_row = QHBoxLayout()
        theme_lbl = QLabel("Téma:")
        self.btn_theme2 = QPushButton("☀️  Váltás világos módra")
        self.btn_theme2.setObjectName("btn_theme2")
        self.btn_theme2.clicked.connect(self._toggle_theme)
        theme_row.addWidget(theme_lbl)
        theme_row.addWidget(self.btn_theme2)
        theme_row.addStretch()
        appear_lay.addLayout(theme_row)
        set_lay.addWidget(grp_appear)

        set_lay.addStretch()

        # Beállítások fül scroll-ba csomagolva
        set_scroll = QScrollArea()
        set_scroll.setWidget(set_tab)
        set_scroll.setWidgetResizable(True)
        set_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.tabs.addTab(set_scroll, "⚙  Beállítások")

        # === 3. fül: Napló ===
        log_tab = QWidget()
        log_lay = QVBoxLayout(log_tab)
        log_lay.setSpacing(8)
        log_lay.setContentsMargins(10, 14, 10, 10)

        log_btn_row = QHBoxLayout()
        btn_clear = QPushButton("🗑  Napló törlése")
        btn_clear.clicked.connect(self._clear_log)
        log_btn_row.addStretch()
        log_btn_row.addWidget(btn_clear)
        log_lay.addLayout(log_btn_row)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        log_lay.addWidget(self.log_box)

        self.tabs.addTab(log_tab, "📋  Napló")

        self._update_cmd()

    def _chk(self, text, grid, row, col):
        cb = QCheckBox(text)
        cb.stateChanged.connect(self._update_cmd)
        grid.addWidget(cb, row, col)
        return cb

    # ── Állapot frissítés ─────────────────────────────────────────────────────
    def _refresh_status(self):
        self._ytdlp  = get_bin_path(YTDLP_BIN)
        self._ffmpeg = get_bin_path(FFMPEG_BIN)
        t = DARK_THEME if self._dark_mode else LIGHT_THEME

        if self._ytdlp:
            ver = get_version(self._ytdlp)
            self.lbl_ytdlp_ver.setText(f"✔  {ver}")
            self.lbl_ytdlp_ver.setStyleSheet(f"color:{t['GRN']};font-weight:bold;")
            self.lbl_ytdlp_path.setText(self._ytdlp)
            self.lbl_ytdlp_path.setStyleSheet(f"color:{t['SUB']};font-size:10px;")
            self.btn_upd_ytdlp.setText("Frissítés")
        else:
            self.lbl_ytdlp_ver.setText("✘  Nincs telepítve")
            self.lbl_ytdlp_ver.setStyleSheet(f"color:{t['RED']};font-weight:bold;")
            self.lbl_ytdlp_path.setText("")
            self.btn_upd_ytdlp.setText("Letöltés")

        if self._ffmpeg:
            ver = get_version(self._ffmpeg)
            self.lbl_ffmpeg_ver.setText(f"✔  {ver}")
            self.lbl_ffmpeg_ver.setStyleSheet(f"color:{t['GRN']};font-weight:bold;")
            self.lbl_ffmpeg_path.setText(self._ffmpeg)
            self.lbl_ffmpeg_path.setStyleSheet(f"color:{t['SUB']};font-size:10px;")
            self.btn_upd_ffmpeg.setText("Frissítés")
        else:
            self.lbl_ffmpeg_ver.setText("✘  Nincs – videó+hang összefűzés nem működik!")
            self.lbl_ffmpeg_ver.setStyleSheet(f"color:{t['YEL']};font-weight:bold;")
            self.lbl_ffmpeg_path.setText("")
            self.btn_upd_ffmpeg.setText("Letöltés")

        self._update_cmd()

    def _start_update(self, mode: str):
        dest_dir = (Path(sys.executable).parent if getattr(sys, "frozen", False)
                    else Path(__file__).parent)
        self._set_buttons_enabled(False)
        self.progress.setValue(0)
        t = DARK_THEME if self._dark_mode else LIGHT_THEME
        self._set_status(f"{'yt-dlp' if mode == 'ytdlp' else 'ffmpeg'} letöltése...", t["ACC"])
        self._upd_thread = UpdateThread(str(dest_dir), mode)
        self._upd_thread.log_signal.connect(self._log)
        self._upd_thread.progress_signal.connect(self.progress.setValue)
        self._upd_thread.finished_signal.connect(self._on_update_finished)
        self._upd_thread.start()

    def _on_update_finished(self, ok, msg):
        self._set_buttons_enabled(True)
        t = DARK_THEME if self._dark_mode else LIGHT_THEME
        self._set_status("Frissítve!" if ok else f"Hiba: {msg}", t["GRN"] if ok else t["RED"])
        if ok:
            self._refresh_status()

    def _on_type_change(self):
        audio = self.cmb_type.currentIndex() == 2
        self.cmb_quality.setEnabled(not audio)
        items = (["– eredeti –", "mp3", "m4a", "opus", "flac", "wav"] if audio
                 else ["– eredeti –", "mp4", "mkv", "webm", "mp3", "m4a", "opus", "flac", "wav"])
        self.cmb_format.blockSignals(True)
        self.cmb_format.clear()
        self.cmb_format.addItems(items)
        self.cmb_format.blockSignals(False)
        self._update_cmd()

    def _build_args(self):
        ytdlp = self._ytdlp or "yt-dlp"
        args  = [ytdlp]

        if self._ffmpeg:
            args += ["--ffmpeg-location", self._ffmpeg]

        # YouTube kliens - tv_embedded nem igényel JS-t és elkerüli a SABR-t
        args += ["--extractor-args", "youtube:player_client=tv_embedded"]

        t = self.cmb_type.currentIndex()
        qi = self.cmb_quality.currentIndex()
        fmt = self.cmb_format.currentText()
        q_map = {
            0: "bestvideo+bestaudio/best",
            1: "bestvideo[height<=1080]+bestaudio/best",
            2: "bestvideo[height<=720]+bestaudio/best",
            3: "bestvideo[height<=480]+bestaudio/best",
            4: "bestvideo[height<=360]+bestaudio/best",
            5: "worstvideo+worstaudio/worst",
        }

        if t == 2:
            args += ["-x", "--audio-format", fmt if fmt != "– eredeti –" else "mp3", "--audio-quality", "0"]
        elif t == 1:
            args += ["-f", "bestvideo[height<=1080]/bestvideo"]
            if fmt not in ("– eredeti –", "mp3", "m4a", "opus", "flac", "wav"):
                args += ["--recode-video", fmt]
        else:
            args += ["-f", q_map.get(qi, "bestvideo+bestaudio/best")]
            if fmt != "– eredeti –":
                args += ["--merge-output-format", fmt]

        if self.chk_subs.isChecked():      args += ["--write-subs", "--write-auto-subs", "--sub-langs", "hu,en"]
        if self.chk_thumbnail.isChecked(): args += ["--embed-thumbnail"]
        if self.chk_playlist.isChecked():  args += ["--yes-playlist"]
        else:                              args += ["--no-playlist"]
        if self.chk_metadata.isChecked():  args += ["--add-metadata"]
        if self.chk_chapters.isChecked():  args += ["--embed-chapters"]
        if self.chk_sponsor.isChecked():   args += ["--sponsorblock-mark", "sponsor"]
        if self.chk_cookies.isChecked():
            browser = "safari" if IS_MAC else "firefox"
            args += ["--cookies-from-browser", browser]
        if self.chk_verbose.isChecked():   args += ["-v"]

        out = self.out_template.text().strip()
        if out:
            args += ["-o", out]
        args.append(self.url_edit.text().strip() or "URL")
        return args

    def _update_cmd(self):
        self.cmd_display.setPlainText(" ".join(self._build_args()))

    def _browse_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Válassz mappát")
        if folder:
            self.out_template.setText(os.path.join(folder, "%(title)s.%(ext)s"))

    def _start_download(self):
        if not self._ytdlp:
            QMessageBox.warning(self, "Hiba", "yt-dlp nem található!")
            return
        if not self.url_edit.text().strip():
            t = DARK_THEME if self._dark_mode else LIGHT_THEME
            self._set_status("Adj meg egy URL-t!", t["RED"])
            return
        if not self._ffmpeg and self.cmb_type.currentIndex() != 2:
            self._log("⚠ ffmpeg nincs telepítve – a videó és hang külön fájlként töltődik le!")
        args = self._build_args()
        self.tabs.setCurrentIndex(2)  # Napló fülre vált
        self._log("\n" + " ".join(args))
        self.progress.setValue(0)
        t = DARK_THEME if self._dark_mode else LIGHT_THEME
        self._set_status("Letöltés...", t["ACC"])
        self.btn_download.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._thread = DownloadThread(args)
        self._thread.log_signal.connect(self._log)
        self._thread.progress_signal.connect(self.progress.setValue)
        self._thread.finished_signal.connect(self._on_dl_finished)
        self._thread.start()

    def _stop_download(self):
        if self._thread:
            self._thread.stop()
        self._log("Leállítva.")
        self._reset_buttons()

    def _on_dl_finished(self, ok, msg):
        self.progress.setValue(100 if ok else self.progress.value())
        t = DARK_THEME if self._dark_mode else LIGHT_THEME
        self._set_status(msg, t["GRN"] if ok else t["RED"])
        self._log(msg)
        self._reset_buttons()

    def _set_buttons_enabled(self, enabled: bool):
        self.btn_download.setEnabled(enabled)
        self.btn_upd_ytdlp.setEnabled(enabled)
        self.btn_upd_ffmpeg.setEnabled(enabled)

    def _reset_buttons(self):
        self.btn_download.setEnabled(True)
        self.btn_stop.setEnabled(False)

    def _set_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color:{color};font-weight:bold;")

    def _clear_log(self):
        self.log_box.clear()

    def _log(self, text):
        self.log_box.append(text)
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("yt-dlp GUI")
    win = YtDlpGUI()
    win.show()
    sys.exit(app.exec())
