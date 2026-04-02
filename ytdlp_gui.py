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
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPalette, QColor

# ── Platform ──────────────────────────────────────────────────────────────────
IS_WIN  = sys.platform == "win32"
IS_MAC  = sys.platform == "darwin"
IS_LIN  = sys.platform.startswith("linux")

YTDLP_BIN   = "yt-dlp.exe" if IS_WIN else "yt-dlp"
GITHUB_ASSET = "yt-dlp.exe" if IS_WIN else ("yt-dlp_macos" if IS_MAC else "yt-dlp_linux")

POPEN_FLAGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WIN else {}

DEFAULT_DL = (
    Path.home() / "Downloads" / "%(title)s.%(ext)s"
)

# ── yt-dlp útvonal meghatározás ───────────────────────────────────────────────
def get_ytdlp_path() -> str:
    own_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    local = own_dir / YTDLP_BIN
    if local.exists():
        return str(local)
    found = shutil.which("yt-dlp")
    return found or ""


def get_ytdlp_version(ytdlp_path: str) -> str:
    try:
        r = subprocess.run([ytdlp_path, "--version"],
                           capture_output=True, text=True, **POPEN_FLAGS)
        return r.stdout.strip()
    except Exception:
        return "ismeretlen"


# ── Frissítő szál ─────────────────────────────────────────────────────────────
class UpdateThread(QThread):
    log_signal      = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, dest_dir: str):
        super().__init__()
        self.dest_dir = dest_dir

    def run(self):
        api = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
        try:
            self.log_signal.emit("GitHub API lekérdezése...")
            req = urllib.request.Request(api, headers={"User-Agent": "ytdlp-gui"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            tag = data["tag_name"]
            self.log_signal.emit(f"Legújabb verzió: {tag}")

            dl_url = next(
                (a["browser_download_url"] for a in data.get("assets", [])
                 if a["name"] == GITHUB_ASSET),
                None
            )
            if not dl_url:
                self.finished_signal.emit(False, f"{GITHUB_ASSET} nem található a release-ben")
                return

            dest = Path(self.dest_dir) / YTDLP_BIN
            tmp  = Path(self.dest_dir) / (YTDLP_BIN + ".tmp")

            self.log_signal.emit(f"Letöltés: {dl_url}")
            req2 = urllib.request.Request(dl_url, headers={"User-Agent": "ytdlp-gui"})
            with urllib.request.urlopen(req2, timeout=120) as resp2:
                total = int(resp2.headers.get("Content-Length", 0))
                downloaded = 0
                with open(tmp, "wb") as f:
                    while True:
                        buf = resp2.read(65536)
                        if not buf:
                            break
                        f.write(buf)
                        downloaded += len(buf)
                        if total:
                            self.progress_signal.emit(int(downloaded / total * 100))

            # macOS / Linux: futtatási jog beállítása
            if not IS_WIN:
                tmp.chmod(tmp.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

            tmp.replace(dest)
            self.log_signal.emit(f"Frissítve -> {dest}")
            self.finished_signal.emit(True, str(dest))

        except urllib.error.URLError as e:
            self.finished_signal.emit(False, f"Hálózati hiba: {e.reason}")
        except Exception as e:
            self.finished_signal.emit(False, str(e))


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
        self.setMinimumWidth(740)
        self.setMinimumHeight(680)
        self._thread     = None
        self._upd_thread = None
        self._ytdlp      = get_ytdlp_path()
        self._apply_dark_theme()
        self._build_ui()
        self._refresh_ytdlp_status()

    def _apply_dark_theme(self):
        app = QApplication.instance()
        app.setStyle("Fusion")
        pal = QPalette()
        BG  = QColor("#1e1e2e"); SURF = QColor("#28283d")
        PNL = QColor("#313148"); ACC  = QColor("#89b4fa")
        TXT = QColor("#cdd6f4"); RED  = QColor("#f38ba8")
        for role, color in [
            (QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TXT),
            (QPalette.ColorRole.Base, SURF), (QPalette.ColorRole.AlternateBase, PNL),
            (QPalette.ColorRole.Text, TXT),  (QPalette.ColorRole.Button, PNL),
            (QPalette.ColorRole.ButtonText, TXT), (QPalette.ColorRole.BrightText, RED),
            (QPalette.ColorRole.Highlight, ACC), (QPalette.ColorRole.HighlightedText, BG),
        ]:
            pal.setColor(role, color)
        app.setPalette(pal)
        app.setStyleSheet(f"""
            QMainWindow,QWidget{{background:{BG.name()};color:{TXT.name()};}}
            QGroupBox{{border:1px solid {PNL.name()};border-radius:8px;margin-top:8px;
                padding:8px 12px 12px 12px;font-weight:bold;color:{ACC.name()};}}
            QGroupBox::title{{subcontrol-origin:margin;left:10px;padding:0 4px;}}
            QLineEdit,QComboBox,QTextEdit{{background:{SURF.name()};border:1px solid {PNL.name()};
                border-radius:6px;padding:6px 10px;color:{TXT.name()};}}
            QLineEdit:focus,QComboBox:focus{{border:1px solid {ACC.name()};}}
            QComboBox::drop-down{{border:none;width:24px;}}
            QComboBox QAbstractItemView{{background:{SURF.name()};
                selection-background-color:{ACC.name()};selection-color:{BG.name()};}}
            QPushButton{{background:{PNL.name()};border:1px solid #44445a;border-radius:6px;
                padding:7px 18px;color:{TXT.name()};font-weight:bold;}}
            QPushButton:hover{{background:#3a3a55;border-color:{ACC.name()};}}
            QPushButton:pressed{{background:{ACC.name()};color:{BG.name()};}}
            QPushButton#btn_download{{background:{ACC.name()};color:{BG.name()};
                border:none;font-size:14px;padding:10px 24px;}}
            QPushButton#btn_download:hover{{background:#74a8f5;}}
            QPushButton#btn_download:disabled{{background:{PNL.name()};color:#6c7086;}}
            QPushButton#btn_stop{{background:{RED.name()};color:{BG.name()};border:none;}}
            QPushButton#btn_update{{background:#313148;border:1px solid {ACC.name()};color:{ACC.name()};}}
            QPushButton#btn_update:hover{{background:{ACC.name()};color:{BG.name()};}}
            QPushButton#btn_update:disabled{{border-color:#44445a;color:#6c7086;}}
            QProgressBar{{background:{SURF.name()};border:1px solid {PNL.name()};
                border-radius:6px;text-align:center;color:{TXT.name()};height:18px;}}
            QProgressBar::chunk{{background:{ACC.name()};border-radius:5px;}}
            QCheckBox{{spacing:8px;color:{TXT.name()};}}
            QCheckBox::indicator{{width:16px;height:16px;border:1px solid #44445a;
                border-radius:4px;background:{SURF.name()};}}
            QCheckBox::indicator:checked{{background:{ACC.name()};border-color:{ACC.name()};}}
            QTextEdit{{font-family:{'Menlo' if IS_MAC else 'Consolas'},monospace;font-size:11px;}}
        """)

    def _build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        lay = QVBoxLayout(root); lay.setSpacing(10); lay.setContentsMargins(16,16,16,16)

        # ── yt-dlp állapot ──
        grp_ytdlp = QGroupBox("  yt-dlp")
        yd_lay = QHBoxLayout(grp_ytdlp)
        self.lbl_ytdlp_ver  = QLabel("...")
        self.lbl_ytdlp_path = QLabel("")
        self.lbl_ytdlp_path.setStyleSheet("color:#6c7086;font-size:11px;")
        info_col = QVBoxLayout(); info_col.setSpacing(2)
        info_col.addWidget(self.lbl_ytdlp_ver); info_col.addWidget(self.lbl_ytdlp_path)
        yd_lay.addLayout(info_col); yd_lay.addStretch()
        self.btn_update = QPushButton("Frissítés (GitHub)")
        self.btn_update.setObjectName("btn_update")
        self.btn_update.clicked.connect(self._start_update)
        yd_lay.addWidget(self.btn_update)
        lay.addWidget(grp_ytdlp)

        # ── URL ──
        grp_url = QGroupBox("  URL")
        url_lay = QHBoxLayout(grp_url)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        self.url_edit.textChanged.connect(self._update_cmd)
        url_lay.addWidget(self.url_edit)
        lay.addWidget(grp_url)

        # ── Formátum ──
        grp_fmt = QGroupBox("  Formátum és minőség")
        fmt_lay = QGridLayout(grp_fmt); fmt_lay.setSpacing(8)
        fmt_lay.addWidget(QLabel("Tartalom:"), 0, 0)
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(["Videó + hang","Csak videó","Csak hang"])
        self.cmb_type.currentIndexChanged.connect(self._on_type_change)
        fmt_lay.addWidget(self.cmb_type, 0, 1)
        fmt_lay.addWidget(QLabel("Minőség:"), 0, 2)
        self.cmb_quality = QComboBox()
        self.cmb_quality.addItems(["Legjobb","1080p","720p","480p","360p","Legrosszabb"])
        self.cmb_quality.currentIndexChanged.connect(self._update_cmd)
        fmt_lay.addWidget(self.cmb_quality, 0, 3)
        fmt_lay.addWidget(QLabel("Konvertálás:"), 1, 0)
        self.cmb_format = QComboBox()
        self.cmb_format.addItems(["– eredeti –","mp4","mkv","webm","mp3","m4a","opus","flac","wav"])
        self.cmb_format.currentIndexChanged.connect(self._update_cmd)
        fmt_lay.addWidget(self.cmb_format, 1, 1)
        lay.addWidget(grp_fmt)

        # ── Opciók ──
        grp_opt = QGroupBox("  Beállítások")
        opt_lay = QGridLayout(grp_opt); opt_lay.setSpacing(6)
        self.chk_subs      = self._chk("Feliratok letöltése",     opt_lay, 0, 0)
        self.chk_thumbnail = self._chk("Borítókép beágyazása",    opt_lay, 0, 1)
        self.chk_playlist  = self._chk("Lejátszólista letöltése", opt_lay, 1, 0)
        self.chk_metadata  = self._chk("Metaadatok beágyazása",   opt_lay, 1, 1)
        self.chk_chapters  = self._chk("Fejezetek beágyazása",    opt_lay, 2, 0)
        self.chk_sponsor   = self._chk("SponsorBlock jelölés",    opt_lay, 2, 1)
        self.chk_cookies   = self._chk("Sütik (böngészőből)",     opt_lay, 3, 0)
        self.chk_verbose   = self._chk("Részletes kimenet (-v)",  opt_lay, 3, 1)
        lay.addWidget(grp_opt)

        # ── Mentési hely ──
        grp_out = QGroupBox("  Mentési hely")
        vl = QVBoxLayout(grp_out); vl.setSpacing(4)
        row = QHBoxLayout()
        self.out_template = QLineEdit()
        self.out_template.setText(str(DEFAULT_DL))
        self.out_template.textChanged.connect(self._update_cmd)
        btn_browse = QPushButton("Tallózás...")
        btn_browse.clicked.connect(self._browse_dir)
        row.addWidget(self.out_template); row.addWidget(btn_browse)
        hint = QLabel("Sablon: %(title)s  %(uploader)s  %(id)s  %(ext)s  %(playlist_index)s")
        hint.setStyleSheet("color:#6c7086;font-size:11px;")
        vl.addLayout(row); vl.addWidget(hint)
        lay.addWidget(grp_out)

        # ── Parancs előnézet ──
        grp_cmd = QGroupBox("  Generált parancs")
        cmd_lay = QVBoxLayout(grp_cmd)
        self.cmd_display = QTextEdit(); self.cmd_display.setReadOnly(True); self.cmd_display.setFixedHeight(52)
        cmd_lay.addWidget(self.cmd_display)
        lay.addWidget(grp_cmd)

        # ── Gombok ──
        btn_row = QHBoxLayout()
        self.btn_download = QPushButton("Letöltés")
        self.btn_download.setObjectName("btn_download")
        self.btn_download.clicked.connect(self._start_download)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.clicked.connect(self._stop_download)
        self.btn_stop.setEnabled(False)
        btn_clear = QPushButton("Napló törlése")
        btn_clear.clicked.connect(lambda: self.log_box.clear())
        btn_row.addWidget(self.btn_download); btn_row.addWidget(self.btn_stop)
        btn_row.addStretch(); btn_row.addWidget(btn_clear)
        lay.addLayout(btn_row)

        self.progress = QProgressBar(); self.progress.setValue(0)
        lay.addWidget(self.progress)
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.status_label)
        self.log_box = QTextEdit(); self.log_box.setReadOnly(True); self.log_box.setMinimumHeight(110)
        lay.addWidget(self.log_box)
        self._update_cmd()

    def _chk(self, text, grid, row, col):
        cb = QCheckBox(text); cb.stateChanged.connect(self._update_cmd)
        grid.addWidget(cb, row, col); return cb

    def _refresh_ytdlp_status(self):
        self._ytdlp = get_ytdlp_path()
        if self._ytdlp:
            ver = get_ytdlp_version(self._ytdlp)
            self.lbl_ytdlp_ver.setText(f"yt-dlp  {ver}")
            self.lbl_ytdlp_ver.setStyleSheet("color:#a6e3a1;font-weight:bold;")
            self.lbl_ytdlp_path.setText(self._ytdlp)
        else:
            self.lbl_ytdlp_ver.setText("yt-dlp nem talalhato – kattints a Frissites gombra!")
            self.lbl_ytdlp_ver.setStyleSheet("color:#f38ba8;font-weight:bold;")
            self.lbl_ytdlp_path.setText("")
        self._update_cmd()

    def _start_update(self):
        dest_dir = (Path(sys.executable).parent if getattr(sys, "frozen", False)
                    else Path(__file__).parent)
        self.btn_update.setEnabled(False); self.btn_download.setEnabled(False)
        self.progress.setValue(0)
        self._set_status("yt-dlp letöltése...", "#89b4fa")
        self._log("Frissítés indítása...")
        self._upd_thread = UpdateThread(str(dest_dir))
        self._upd_thread.log_signal.connect(self._log)
        self._upd_thread.progress_signal.connect(self.progress.setValue)
        self._upd_thread.finished_signal.connect(self._on_update_finished)
        self._upd_thread.start()

    def _on_update_finished(self, ok, msg):
        self.btn_update.setEnabled(True); self.btn_download.setEnabled(True)
        self._set_status("Frissítve!" if ok else f"Hiba: {msg}", "#a6e3a1" if ok else "#f38ba8")
        self._log(msg)
        if ok:
            self._refresh_ytdlp_status()

    def _on_type_change(self):
        audio = self.cmb_type.currentIndex() == 2
        self.cmb_quality.setEnabled(not audio)
        items = (["– eredeti –","mp3","m4a","opus","flac","wav"] if audio
                 else ["– eredeti –","mp4","mkv","webm","mp3","m4a","opus","flac","wav"])
        self.cmb_format.blockSignals(True)
        self.cmb_format.clear(); self.cmb_format.addItems(items)
        self.cmb_format.blockSignals(False)
        self._update_cmd()

    def _build_args(self):
        ytdlp = self._ytdlp or "yt-dlp"
        args  = [ytdlp]
        t = self.cmb_type.currentIndex(); qi = self.cmb_quality.currentIndex()
        fmt = self.cmb_format.currentText()
        q_map = {0:"bestvideo+bestaudio/best", 1:"bestvideo[height<=1080]+bestaudio/best",
                 2:"bestvideo[height<=720]+bestaudio/best",  3:"bestvideo[height<=480]+bestaudio/best",
                 4:"bestvideo[height<=360]+bestaudio/best",  5:"worstvideo+worstaudio/worst"}
        if t == 2:
            args += ["-x","--audio-format", fmt if fmt != "– eredeti –" else "mp3","--audio-quality","0"]
        elif t == 1:
            args += ["-f","bestvideo[height<=1080]/bestvideo"]
            if fmt not in ("– eredeti –","mp3","m4a","opus","flac","wav"):
                args += ["--recode-video", fmt]
        else:
            args += ["-f", q_map.get(qi,"bestvideo+bestaudio/best")]
            if fmt != "– eredeti –": args += ["--merge-output-format", fmt]

        if self.chk_subs.isChecked():      args += ["--write-subs","--write-auto-subs","--sub-langs","hu,en"]
        if self.chk_thumbnail.isChecked(): args += ["--embed-thumbnail"]
        if self.chk_playlist.isChecked():  args += ["--yes-playlist"]
        else:                              args += ["--no-playlist"]
        if self.chk_metadata.isChecked():  args += ["--add-metadata"]
        if self.chk_chapters.isChecked():  args += ["--embed-chapters"]
        if self.chk_sponsor.isChecked():   args += ["--sponsorblock-mark","sponsor"]
        if self.chk_cookies.isChecked():
            browser = "safari" if IS_MAC else "firefox"
            args += ["--cookies-from-browser", browser]
        if self.chk_verbose.isChecked():   args += ["-v"]

        out = self.out_template.text().strip()
        if out: args += ["-o", out]
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
            QMessageBox.warning(self, "Hiba", "yt-dlp nem talalhato!\nKattints a Frissites gombra.")
            return
        if not self.url_edit.text().strip():
            self._set_status("Adj meg egy URL-t!", "#f38ba8"); return
        args = self._build_args()
        self._log("\n" + " ".join(args))
        self.progress.setValue(0); self._set_status("Letöltés...", "#89b4fa")
        self.btn_download.setEnabled(False); self.btn_stop.setEnabled(True)
        self._thread = DownloadThread(args)
        self._thread.log_signal.connect(self._log)
        self._thread.progress_signal.connect(self.progress.setValue)
        self._thread.finished_signal.connect(self._on_dl_finished)
        self._thread.start()

    def _stop_download(self):
        if self._thread: self._thread.stop()
        self._log("Leállítva."); self._reset_buttons()

    def _on_dl_finished(self, ok, msg):
        self.progress.setValue(100 if ok else self.progress.value())
        self._set_status(msg, "#a6e3a1" if ok else "#f38ba8")
        self._log(msg); self._reset_buttons()

    def _reset_buttons(self):
        self.btn_download.setEnabled(True); self.btn_stop.setEnabled(False)

    def _set_status(self, text, color):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color:{color};font-weight:bold;")

    def _log(self, text):
        self.log_box.append(text)
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("yt-dlp GUI")
    win = YtDlpGUI()
    win.show()
    sys.exit(app.exec())
