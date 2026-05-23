import os
import json
import subprocess
import objc
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QColorDialog, QFontDialog, QInputDialog
from PyQt6.QtCore import Qt, QTimer, QTime, QDate, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from AppKit import NSWorkspace, NSProcessInfo

class WeatherThread(QThread):
    data_ready = pyqtSignal(str)
    def __init__(self, city):
        super().__init__()
        self.city = city
        self._alive = True

    def run(self):
        try:
            city_path = f"/{self.city}" if self.city else ""
            url = f"wttr.in{city_path}?format=%c%t"
            res = subprocess.check_output(f"curl -s --connect-timeout 5 '{url}'", shell=True).decode("utf-8").strip()
            if self._alive and res and "Unknown" not in res: 
                self.data_ready.emit(res)
        except: 
            if self._alive: self.data_ready.emit("Weather N/A")

    def stop(self):
        self._alive = False
        self.wait()

class NowPlayingThread(QThread):
    data_ready = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self._alive = True

    def run(self):
        try:
            cmd = "nowplaying-cli get artist title"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode("utf-8").splitlines()
            if self._alive and len(output) >= 2:
                artist, title = output[0].strip(), output[1].strip()
                if artist != "null" and title != "null" and (artist or title):
                    text = f"♪ {artist} - {title}"
                    self.data_ready.emit((text[:57] + '..') if len(text) > 60 else text)
                    return
            if self._alive: self.data_ready.emit("")
        except: 
            if self._alive: self.data_ready.emit("")

    def stop(self):
        self._alive = False
        self.wait()

class ClockWidget(QWidget):
    def __init__(self, ktools, config):
        super().__init__()
        self.ktools, self.config = ktools, config
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.date_label, self.label, self.weather_label, self.music_label = QLabel(), QLabel(), QLabel(), QLabel()
        for lbl in [self.date_label, self.label, self.weather_label, self.music_label]:
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(lbl)
        self.weather_worker = None
        self.music_worker = NowPlayingThread()
        self.music_worker.data_ready.connect(self.music_label.setText)
        self.refresh_visibility()
        self.update_styles()
        self.timer = QTimer(self); self.timer.timeout.connect(self.update_info); self.timer.start(1000)
        self.music_timer = QTimer(self); self.music_timer.timeout.connect(self.fetch_music); self.music_timer.start(2000)
        self.weather_timer = QTimer(self); self.weather_timer.timeout.connect(self.fetch_weather); self.weather_timer.start(900000)
        QTimer.singleShot(3000, self.fetch_weather)
        self.update_info(); self.resize(800, 500)

    def update_styles(self):
        c, cf, of = self.config.get("color", "rgba(255, 255, 255, 200)"), self.config.get("clock_font", "Menlo"), self.config.get("other_font", "Menlo")
        self.date_label.setStyleSheet(f"color: {c}; font-family: '{of}'; font-size: 28px; margin-bottom: -15px; background: transparent;")
        font_size = "100px" if not self.config.get("is_24h", True) else "120px"
        self.label.setStyleSheet(f"color: {c}; font-family: '{cf}'; font-size: {font_size}; font-weight: bold; background: transparent;")
        self.weather_label.setStyleSheet(f"color: {c}; font-family: '{of}'; font-size: 24px; margin-top: -10px; background: transparent;")
        self.music_label.setStyleSheet(f"color: {c}; font-family: '{of}'; font-size: 18px; margin-top: 10px; background: transparent;")

    def refresh_visibility(self):
        self.date_label.setVisible(self.config.get("date_enabled", False))
        self.label.setVisible(self.config.get("clock_enabled", True))
        self.weather_label.setVisible(self.config.get("weather_enabled", False))
        self.music_label.setVisible(self.config.get("now_playing_enabled", False))

    def closeEvent(self, event):
        self.timer.stop()
        self.music_timer.stop()
        self.weather_timer.stop()

        if self.weather_worker:
            try: self.weather_worker.data_ready.disconnect()
            except: pass
            self.weather_worker.stop()
        
        if self.music_worker:
            try: self.music_worker.data_ready.disconnect()
            except: pass
            self.music_worker.stop()
            
        super().closeEvent(event)

    def update_info(self):
        if self.label.isVisible():
            fmt = "HH:mm" if self.config.get("is_24h", True) else "hh:mm AP"
            self.label.setText(QTime.currentTime().toString(fmt))
        
        if self.date_label.isVisible():
            self.date_label.setText(QDate.currentDate().toString("dd.MM.yyyy"))

    def refresh_layout(self):
        for i in reversed(range(self.layout.count())): 
            self.layout.itemAt(i).widget().setParent(None)
        
        self.date_label, self.label, self.weather_label, self.music_label = QLabel(), QLabel(), QLabel(), QLabel()
        for lbl in [self.date_label, self.label, self.weather_label, self.music_label]:
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(lbl)
        
        self.refresh_visibility()
        self.update_styles()

    def fetch_weather(self):
        if self.weather_label.isVisible() and (not self.weather_worker or not self.weather_worker.isRunning()):
            self.weather_worker = WeatherThread(self.config.get("weather_city", "")); self.weather_worker.data_ready.connect(self.weather_label.setText); self.weather_worker.start()

    def fetch_music(self):
        if self.music_label.isVisible() and not self.music_worker.isRunning(): self.music_worker.start()

class Plugin:
    def __init__(self, ktools):
        self.ktools = ktools
        self.path = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.path, "kpaperaddon_kclock.json")
        self.config = self.load_config()
        self.widget = None

        self.workspace_center = NSWorkspace.sharedWorkspace().notificationCenter()
        self.workspace_center.addObserver_selector_name_object_(
            self, "handleSleep:", "NSWorkspaceWillSleepNotification", None
        )
        self.workspace_center.addObserver_selector_name_object_(
            self, "handleWake:", "NSWorkspaceDidWakeNotification", None
        )


        self.activity = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            (1 << 10) | (1 << 40), "Keep clock running"
        )

        QTimer.singleShot(2000, self.check_widget_state)

    def _safe_destroy_widget(self):
        if self.widget:
            self.widget.close() 
            self.widget.deleteLater()
            self.widget = None
            print("kclock: widget destroyed safely")

    def handleSleep_(self, notification):
        print("kclock: system sleep detected, nuking everything")
        if self.widget:
            try:
                self.widget.close()
                self.widget = None
            except:
                pass

    def handleWake_(self, notification):
        print("kclock: system wake detected, performing full plugin re-init")
        QTimer.singleShot(3000, self.hard_refresh_widget)

    def load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding='utf-8') as f: return json.load(f)
            except: pass
        return {
            "color": "rgba(255, 255, 255, 200)", "clock_font": "Menlo", "other_font": "Menlo",
            "clock_enabled": True, "date_enabled": False, "weather_enabled": False,
            "now_playing_enabled": False, "weather_city": "", "is_24h": True
        }

    def save_config(self):
        with open(self.config_path, "w", encoding='utf-8') as f: json.dump(self.config, f, indent=4, ensure_ascii=False)
        self.check_widget_state()
        if self.widget:
            self.widget.refresh_visibility()
            self.widget.update_styles()
            self.widget.update_info()

    def check_widget_state(self):
        active = any([
            self.config.get("clock_enabled"), 
            self.config.get("date_enabled"), 
            self.config.get("weather_enabled"), 
            self.config.get("now_playing_enabled")
        ])

        if active:
            if self.widget is not None:
                try:
                    self.widget.update_info()
                    self.widget.refresh_visibility()
                    self.widget.update_styles()
                    self.widget.show()
                except:
                    self.widget = None
            
            if self.widget is None:
                kp = self.ktools.plugins.get('kpaper')

                if kp and hasattr(kp, 'spawn_widget'):
                    self.widget = kp.spawn_widget(lambda kt: ClockWidget(kt, self.config), interactive=False)
                    if self.widget:
                        screen = self.ktools.app.primaryScreen().geometry()
                        self.widget.move((screen.width() - self.widget.width()) // 2, 
                                    (screen.height() - self.widget.height()) // 2)
        else:
            if self.widget:
                self.widget.close()
                self.widget.deleteLater()
                self.widget = None

    def toggle_clock(self): self.config["clock_enabled"] = not self.config.get("clock_enabled", True); self.save_config()
    def toggle_date(self): self.config["date_enabled"] = not self.config.get("date_enabled", False); self.save_config()
    def toggle_weather(self): self.config["weather_enabled"] = not self.config.get("weather_enabled", False); self.save_config()
    def toggle_now_playing(self): self.config["now_playing_enabled"] = not self.config.get("now_playing_enabled", False); self.save_config()
    def toggle_time_format(self): self.config["is_24h"] = not self.config.get("is_24h", True); self.save_config()

    def change_city(self):
        city, ok = QInputDialog.getText(None, "Weather Settings", "Enter City Name (English):", text=self.config.get("weather_city", ""))
        if ok: self.config["weather_city"] = city.strip(); self.save_config(); 
        if self.widget: self.widget.fetch_weather()

    def change_color(self):
        color = QColorDialog.getColor(QColor(self.config.get("color", "#ffffff")))
        if color.isValid(): self.config["color"] = f"rgba({color.red()}, {color.green()}, {color.blue()}, 255)"; self.save_config()

    def change_clock_font(self):
        font, ok = QFontDialog.getFont(QFont(self.config.get("clock_font", "Menlo")))
        if ok: self.config["clock_font"] = font.family(); self.save_config()

    def change_other_font(self):
        font, ok = QFontDialog.getFont(QFont(self.config.get("other_font", "Menlo")))
        if ok: self.config["other_font"] = font.family(); self.save_config()

    def hard_refresh_widget(self):
        print("kclock: hard refreshing...")
        if self.widget:
            try:
                self.widget.close()
                self.widget.deleteLater()
            except:
                pass
        self.widget = None

        self.check_widget_state()

    def unload(self):
        try:
            self.workspace_center.removeObserver_(self)
        except: pass
        
        if self.widget:
            self.widget.close()
            self.widget.deleteLater()
            self.widget = None

        import gc
        gc.collect()
        print("kclock: unloaded and threads killed")

    def get_actions(self):
        return []