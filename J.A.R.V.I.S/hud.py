import sys
import math
import os
import random
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtGui import QPainter, QPen, QColor, QRadialGradient, QFont, QBrush, QPolygonF, QLinearGradient
from PyQt5.QtCore import QTimer, Qt, QPointF

VOICE_FILE = "voice_level.txt"
STATUS_FILE = "hud_status.txt"
COMMAND_FILE = "hud_command.txt"
RESULT_FILE = "hud_result.txt"

PROJECT_FILE = "hud_project.txt"
CURRENT_FILE = "hud_current_file.txt"
ACTION_FILE = "hud_action.txt"
AI_STATUS_FILE = "hud_ai_status.txt"

SECURITY_SCORE_FILE = "hud_security_score.txt"
PROJECT_SCORE_FILE = "hud_project_score.txt"
MEMORY_STATUS_FILE = "hud_memory_status.txt"
VISION_STATUS_FILE = "hud_vision_status.txt"
OLLAMA_STATUS_FILE = "hud_ollama_status.txt"

# Step 14 - Enterprise Dashboard extra context files
NEXT_TASK_FILE = "hud_next_task.txt"
ROADMAP_STATUS_FILE = "hud_roadmap_status.txt"
SPRINT_STATUS_FILE = "hud_sprint_status.txt"
RELEASE_STATUS_FILE = "hud_release_status.txt"
DEPLOYMENT_STATUS_FILE = "hud_deployment_status.txt"
PRODUCTION_STATUS_FILE = "hud_production_status.txt"
COMMANDER_MODE_FILE = "hud_commander_mode.txt"


class JarvisHUD(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("JARVIS HUD - Enterprise Commander Dashboard")
        self.setGeometry(40, 25, 1540, 920)
        self.setStyleSheet("background-color: black;")
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint
        )

        self.t = 0.0
        self.voice_raw = 0.0
        self.voice_smooth = 0.0

        self.status = "STANDBY"
        self.command = "Waiting for command..."
        self.result = "System ready."

        self.project_name = "No Project"
        self.current_file = "No File"
        self.current_action = "Idle"
        self.ai_status = "READY"

        self.security_score = "N/A"
        self.project_score = "N/A"
        self.memory_status = "SYNC"
        self.vision_status = "ACTIVE"
        self.ollama_status = "LOCAL"

        # Step 14 - Project Commander / Enterprise HUD
        self.next_task = "Waiting for next task"
        self.roadmap_status = "N/A"
        self.sprint_status = "N/A"
        self.release_status = "N/A"
        self.deployment_status = "N/A"
        self.production_status = "N/A"
        self.commander_mode = "STANDBY"

        # Extra J.A.R.V.I.S OS visual layer state.
        # This does not replace your old HUD logic; it only adds animated panels,
        # radar, graphs and sci-fi background around the existing core.
        self.jarvis_graph_values = [random.random() for _ in range(52)]
        self.jarvis_cpu_values = [random.random() for _ in range(48)]
        self.jarvis_net_values = [random.random() for _ in range(58)]
        self.jarvis_disk_values = [random.random() for _ in range(44)]
        self.jarvis_radar_blips = [
            (random.random() * 360, 0.22 + random.random() * 0.70)
            for _ in range(22)
        ]

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16)

    def read_file_safe(self, path, default=""):
        try:
            if not os.path.exists(path):
                return default

            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                value = f.read().strip()

            return value if value else default

        except Exception:
            return default

    def animate(self):
        self.t += 0.012

        try:
            self.voice_raw = float(
                self.read_file_safe(VOICE_FILE, "0.0")
            )
        except Exception:
            self.voice_raw = 0.0

        self.status = self.read_file_safe(
            STATUS_FILE,
            "STANDBY"
        ).upper()

        self.command = self.read_file_safe(
            COMMAND_FILE,
            "Waiting for command..."
        )

        self.result = self.read_file_safe(
            RESULT_FILE,
            "System ready."
        )

        self.project_name = self.read_file_safe(
            PROJECT_FILE,
            "No Project"
        )

        self.current_file = self.read_file_safe(
            CURRENT_FILE,
            "No File"
        )

        self.current_action = self.read_file_safe(
            ACTION_FILE,
            "Idle"
        )

        self.ai_status = self.read_file_safe(
            AI_STATUS_FILE,
            "READY"
        ).upper()

        self.security_score = self.read_file_safe(
            SECURITY_SCORE_FILE,
            "N/A"
        )

        self.project_score = self.read_file_safe(
            PROJECT_SCORE_FILE,
            "N/A"
        )

        self.memory_status = self.read_file_safe(
            MEMORY_STATUS_FILE,
            "SYNC"
        ).upper()

        self.vision_status = self.read_file_safe(
            VISION_STATUS_FILE,
            "ACTIVE"
        ).upper()

        self.ollama_status = self.read_file_safe(
            OLLAMA_STATUS_FILE,
            "LOCAL"
        ).upper()

        self.next_task = self.read_file_safe(
            NEXT_TASK_FILE,
            "Waiting for next task"
        )

        self.roadmap_status = self.read_file_safe(
            ROADMAP_STATUS_FILE,
            "N/A"
        ).upper()

        self.sprint_status = self.read_file_safe(
            SPRINT_STATUS_FILE,
            "N/A"
        ).upper()

        self.release_status = self.read_file_safe(
            RELEASE_STATUS_FILE,
            "N/A"
        ).upper()

        self.deployment_status = self.read_file_safe(
            DEPLOYMENT_STATUS_FILE,
            "N/A"
        ).upper()

        self.production_status = self.read_file_safe(
            PRODUCTION_STATUS_FILE,
            "N/A"
        ).upper()

        self.commander_mode = self.read_file_safe(
            COMMANDER_MODE_FILE,
            "STANDBY"
        ).upper()

        self.voice_smooth += (
            self.voice_raw - self.voice_smooth
        ) * 0.35

        # Extra animated pseudo-telemetry for the J.A.R.V.I.S OS background.
        # Real project state still comes from your existing hud_*.txt files.
        if int(self.t * 10) % 2 == 0:
            self.jarvis_graph_values.pop(0)
            self.jarvis_graph_values.append(
                max(
                    0.05,
                    min(
                        1.0,
                        0.35 + random.random() * 0.55 + self.voice_smooth * 0.25
                    )
                )
            )

            self.jarvis_cpu_values.pop(0)
            self.jarvis_cpu_values.append(
                max(
                    0.05,
                    min(
                        1.0,
                        0.25 + random.random() * 0.55
                    )
                )
            )

            self.jarvis_net_values.pop(0)
            self.jarvis_net_values.append(
                max(
                    0.04,
                    min(
                        1.0,
                        0.20 + random.random() * 0.72
                    )
                )
            )

            self.jarvis_disk_values.pop(0)
            self.jarvis_disk_values.append(
                max(
                    0.04,
                    min(
                        1.0,
                        0.30 + random.random() * 0.50
                    )
                )
            )

        self.update()

    def status_color(self):
        status = self.status.lower()

        if "listening" in status:
            return QColor(0, 220, 255, 235)

        if "processing" in status:
            return QColor(255, 190, 0, 235)

        if "success" in status or "done" in status:
            return QColor(0, 255, 120, 235)

        if "error" in status or "cancel" in status:
            return QColor(255, 70, 70, 235)

        return QColor(0, 180, 255, 210)

    def ai_color(self):
        status = self.ai_status.lower()

        if "thinking" in status or "processing" in status:
            return QColor(255, 190, 0, 235)

        if "error" in status:
            return QColor(255, 70, 70, 235)

        if "ready" in status:
            return QColor(0, 255, 120, 235)

        return QColor(0, 220, 255, 220)

    def commander_color(self):
        text = (
            self.commander_mode + " " +
            self.roadmap_status + " " +
            self.sprint_status + " " +
            self.release_status + " " +
            self.deployment_status + " " +
            self.production_status
        ).lower()

        if "error" in text or "failed" in text:
            return QColor(255, 70, 70, 235)

        if "thinking" in text or "processing" in text or "active" in text:
            return QColor(255, 190, 0, 235)

        if "ready" in text or "done" in text or "success" in text or "completed" in text:
            return QColor(0, 255, 120, 235)

        return QColor(0, 220, 255, 220)

    def health_color(self, value):
        lower = str(value).lower()

        if lower in {"n/a", "unknown", "none", ""}:
            return QColor(150, 180, 190, 200)

        if "high" in lower or "error" in lower or "low" in lower:
            return QColor(255, 70, 70, 230)

        if "medium" in lower or "processing" in lower or "thinking" in lower:
            return QColor(255, 190, 0, 230)

        if "ready" in lower or "done" in lower or "success" in lower or "active" in lower:
            return QColor(0, 255, 120, 230)

        return QColor(0, 220, 255, 220)

    def draw_wrapped_text(self, painter, x, y, text, color, max_chars=72, line_height=18, max_lines=3):
        painter.setFont(QFont("Consolas", 9))
        painter.setPen(color)

        text = str(text).strip()
        if not text:
            return y

        words = text.split()
        lines = []
        current = ""

        for word in words:
            candidate = (current + " " + word).strip()

            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word

            if len(lines) >= max_lines:
                break

        if current and len(lines) < max_lines:
            lines.append(current)

        for index, line in enumerate(lines[:max_lines]):
            if index == max_lines - 1 and len(lines) == max_lines and len(" ".join(words)) > len(" ".join(lines)):
                line = line[:max_chars - 3] + "..."

            painter.drawText(x, y + index * line_height, line)

        return y + len(lines[:max_lines]) * line_height

    def draw_panel(self, painter, x, y, w, h, title, color):
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(QColor(0, 18, 28, 110)))
        painter.drawRoundedRect(x, y, w, h, 16, 16)

        painter.setFont(QFont("Consolas", 11, QFont.Bold))
        painter.setPen(color)
        painter.drawText(x + 14, y + 24, title)

    def draw_text_line(self, painter, x, y, label, value, color, limit=70):
        painter.setFont(QFont("Consolas", 10))
        painter.setPen(color)
        painter.drawText(
            x,
            y,
            f"{label}: {str(value)[:limit]}"
        )

    def draw_main_info_panel(self, painter):
        color = self.status_color()

        x = 315
        y = self.height() - 175
        w = self.width() - 630
        h = 135

        self.draw_panel(
            painter,
            x,
            y,
            w,
            h,
            "JARVIS COMMAND STREAM",
            color
        )

        self.draw_text_line(
            painter,
            x + 18,
            y + 44,
            "STATUS",
            self.status,
            color,
            60
        )

        self.draw_text_line(
            painter,
            x + 18,
            y + 68,
            "COMMAND",
            self.command,
            QColor(180, 240, 255, 230),
            95
        )

        self.draw_text_line(
            painter,
            x + 18,
            y + 92,
            "RESULT",
            self.result,
            QColor(160, 255, 210, 230),
            100
        )

        self.draw_text_line(
            painter,
            x + 18,
            y + 116,
            "PROJECT",
            self.project_name,
            QColor(255, 210, 120, 235),
            92
        )

        self.draw_text_line(
            painter,
            x + 480,
            y + 44,
            "FILE",
            self.current_file,
            QColor(255, 255, 150, 235),
            98
        )

        self.draw_text_line(
            painter,
            x + 480,
            y + 68,
            "ACTION",
            self.current_action,
            QColor(150, 255, 255, 235),
            95
        )

        self.draw_text_line(
            painter,
            x + 480,
            y + 92,
            "AI STATUS",
            self.ai_status,
            self.ai_color(),
            60
        )

    def draw_left_system_panel(self, painter):
        x = 35
        y = 95
        w = 210
        h = 205

        self.draw_panel(
            painter,
            x,
            y,
            w,
            h,
            "SYSTEM CORE",
            QColor(0, 220, 255, 210)
        )

        items = [
            ("VOICE", f"{self.voice_smooth:.2f}", QColor(0, 220, 255, 220)),
            ("AI", self.ai_status[:18], self.ai_color()),
            ("VISION", self.vision_status[:18], QColor(0, 255, 180, 220)),
            ("MEMORY", self.memory_status[:18], QColor(255, 210, 120, 220)),
            ("OLLAMA", self.ollama_status[:18], QColor(180, 240, 255, 220)),
        ]

        for i, (label, value, color) in enumerate(items):
            yy = y + 58 + i * 28
            self.draw_text_line(
                painter,
                x + 16,
                yy,
                label,
                value,
                color,
                20
            )

    def draw_right_score_panel(self, painter):
        x = self.width() - 245
        y = 95
        w = 210
        h = 205

        self.draw_panel(
            painter,
            x,
            y,
            w,
            h,
            "PROJECT MATRIX",
            QColor(0, 255, 160, 210)
        )

        items = [
            ("PROJECT", self.project_name[:20], QColor(255, 210, 120, 220)),
            ("SECURITY", self.security_score, QColor(0, 255, 120, 220)),
            ("SCORE", self.project_score, QColor(0, 220, 255, 220)),
            ("FILE", self.current_file[:20], QColor(255, 255, 150, 220)),
            ("MODE", self.status[:18], self.status_color()),
        ]

        for i, (label, value, color) in enumerate(items):
            yy = y + 58 + i * 28
            self.draw_text_line(
                painter,
                x + 16,
                yy,
                label,
                value,
                color,
                22
            )

    def draw_enterprise_commander_panel(self, painter):
        color = self.commander_color()

        x = 35
        y = 320
        w = 265
        h = 275

        self.draw_panel(
            painter,
            x,
            y,
            w,
            h,
            "PROJECT COMMANDER",
            color
        )

        rows = [
            ("MODE", self.commander_mode, self.health_color(self.commander_mode)),
            ("ROADMAP", self.roadmap_status, self.health_color(self.roadmap_status)),
            ("SPRINT", self.sprint_status, self.health_color(self.sprint_status)),
            ("RELEASE", self.release_status, self.health_color(self.release_status)),
            ("DEPLOY", self.deployment_status, self.health_color(self.deployment_status)),
            ("PROD", self.production_status, self.health_color(self.production_status)),
        ]

        for i, (label, value, row_color) in enumerate(rows):
            yy = y + 55 + i * 27
            self.draw_text_line(
                painter,
                x + 16,
                yy,
                label,
                value,
                row_color,
                24
            )

        painter.setPen(QColor(180, 240, 255, 220))
        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.drawText(x + 16, y + 226, "NEXT TASK:")

        self.draw_wrapped_text(
            painter,
            x + 16,
            y + 248,
            self.next_task,
            QColor(255, 230, 150, 230),
            max_chars=32,
            line_height=17,
            max_lines=2
        )

    def draw_enterprise_status_strip(self, painter):
        return

    def draw_mini_score_orbits(self, painter, cx, cy):
        metrics = [
            ("SEC", self.security_score, 92, 0.0),
            ("PRJ", self.project_score, 92, math.pi),
            ("MEM", self.memory_status, 118, math.pi / 2),
            ("CMD", self.commander_mode, 118, -math.pi / 2),
        ]

        painter.setFont(QFont("Consolas", 8, QFont.Bold))

        for label, value, radius, offset in metrics:
            angle = self.t * 1.4 + offset
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)

            color = self.health_color(value)

            painter.setPen(QPen(color, 2))
            painter.setBrush(QBrush(QColor(0, 20, 32, 180)))
            painter.drawEllipse(int(x - 22), int(y - 22), 44, 44)

            painter.setPen(color)
            painter.drawText(
                int(x - 20),
                int(y - 5),
                40,
                12,
                Qt.AlignCenter,
                label
            )

            painter.setFont(QFont("Consolas", 7))
            painter.drawText(
                int(x - 20),
                int(y + 8),
                40,
                12,
                Qt.AlignCenter,
                str(value)[:8]
            )
            painter.setFont(QFont("Consolas", 8, QFont.Bold))

    def draw_status_bars(self, painter, cx, cy):
        color = self.status_color()

        painter.setPen(QPen(color, 4))

        for i in range(24):
            height = 16 + 22 * abs(
                math.sin(self.t * 3 + i * 0.65)
            )

            if self.status.lower() == "listening":
                height += 20 * self.voice_smooth

            if self.ai_status.lower() == "thinking":
                height += 14 * abs(math.sin(self.t * 6 + i))

            x_left = 290 + i * 8
            x_right = self.width() - 290 - i * 8
            y = 78

            painter.drawLine(
                int(x_left),
                int(y),
                int(x_left),
                int(y + height)
            )

            painter.drawLine(
                int(x_right),
                int(y),
                int(x_right),
                int(y + height)
            )

    def draw_radar_points(self, painter, cx, cy):
        color = self.status_color()
        painter.setPen(QPen(color, 3))

        for i in range(56):
            angle = self.t * 2 + i * (2 * math.pi / 56)
            radius = 125 + 28 * math.sin(self.t * 3 + i)

            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            painter.drawPoint(int(x), int(y))

    def draw_scan_lines(self, painter):
        painter.setPen(QPen(QColor(0, 170, 255, 45), 1))

        for i in range(0, self.height(), 28):
            offset = int((self.t * 80) % 28)
            painter.drawLine(
                0,
                i + offset,
                self.width(),
                i + offset
            )


    # ==========================
    # EXTRA J.A.R.V.I.S OS VISUAL LAYER
    # Added on top of your existing HUD.
    # Existing HUD panels and state logic remain intact.
    # ==========================
    def jarvis_cyan(self, alpha=230):
        return QColor(0, 220, 255, alpha)

    def jarvis_dark_panel(self, alpha=125):
        return QColor(0, 18, 32, alpha)

    def draw_jarvis_os_background(self, painter):
        w = self.width()
        h = self.height()

        gradient = QLinearGradient(0, 0, w, h)
        gradient.setColorAt(0.0, QColor(0, 6, 12))
        gradient.setColorAt(0.45, QColor(0, 18, 30))
        gradient.setColorAt(1.0, QColor(0, 4, 10))

        painter.fillRect(0, 0, w, h, gradient)

        # Animated sci-fi grid.
        grid_step = 38
        offset = int((self.t * 24) % grid_step)

        painter.setPen(QPen(QColor(0, 180, 255, 25), 1))

        for x in range(-grid_step, w + grid_step, grid_step):
            painter.drawLine(
                x + offset,
                0,
                x + offset,
                h
            )

        for y in range(-grid_step, h + grid_step, grid_step):
            painter.drawLine(
                0,
                y + offset,
                w,
                y + offset
            )

        # Scan-line effect.
        painter.setPen(QPen(QColor(0, 220, 255, 35), 1))

        for y in range(0, h, 26):
            line_y = y + int((self.t * 85) % 26)
            painter.drawLine(
                0,
                line_y,
                w,
                line_y
            )

        # Neon border.
        painter.setPen(QPen(QColor(0, 220, 255, 175), 2))
        painter.drawLine(20, 28, w - 20, 28)
        painter.drawLine(20, h - 28, w - 20, h - 28)

        # Decorative circuit segments.
        painter.setPen(QPen(QColor(0, 220, 255, 75), 2))

        for i in range(10):
            x = 40 + i * 150
            y = 28 + (i % 2) * 18
            painter.drawLine(x, y, x + 70, y)
            painter.drawLine(x + 70, y, x + 92, y + 18)

    def draw_jarvis_panel(self, painter, x, y, w, h, title, color=None):
        color = color or self.jarvis_cyan()

        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(self.jarvis_dark_panel()))
        painter.drawRoundedRect(
            x,
            y,
            w,
            h,
            14,
            14
        )

        corner = 26

        # Angular HUD corners.
        painter.drawLine(x, y + corner, x, y + 8)
        painter.drawLine(x + 8, y, x + corner, y)
        painter.drawLine(x + w - corner, y, x + w - 8, y)
        painter.drawLine(x + w, y + 8, x + w, y + corner)

        painter.drawLine(x, y + h - corner, x, y + h - 8)
        painter.drawLine(x + 8, y + h, x + corner, y + h)
        painter.drawLine(x + w - corner, y + h, x + w - 8, y + h)
        painter.drawLine(x + w, y + h - corner, x + w, y + h - 8)

        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.setPen(color)
        painter.drawText(
            x + 14,
            y + 24,
            title
        )

    def draw_jarvis_small_graph(self, painter, x, y, w, h, values, color=None):
        color = color or self.jarvis_cyan()

        painter.setPen(QPen(QColor(0, 220, 255, 55), 1))
        painter.drawRect(
            x,
            y,
            w,
            h
        )

        if len(values) < 2:
            return

        painter.setPen(QPen(color, 1))
        step = w / (len(values) - 1)

        last_x = x
        last_y = y + h - int(values[0] * h)

        for index, value in enumerate(values[1:], start=1):
            px = x + int(index * step)
            py = y + h - int(value * h)

            painter.drawLine(
                last_x,
                last_y,
                px,
                py
            )

            last_x = px
            last_y = py

    def draw_jarvis_bar(self, painter, x, y, w, h, value, color=None):
        color = color or self.jarvis_cyan()

        try:
            value = float(value)
        except Exception:
            value = 0.0

        value = max(0.0, min(1.0, value))

        painter.setPen(QPen(QColor(0, 160, 220, 110), 1))
        painter.setBrush(QBrush(QColor(0, 40, 60, 120)))
        painter.drawRect(
            x,
            y,
            w,
            h
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRect(
            x,
            y,
            int(w * value),
            h
        )

    def draw_jarvis_header_overlay(self, painter):
        return

    def draw_jarvis_side_telemetry_left(self, painter):
        # Clean layout: compact extra telemetry placed where it does not cover your original panels.
        x = 315
        y = 590
        w = 250

        self.draw_jarvis_panel(
            painter,
            x,
            y,
            w,
            82,
            "LIVE TELEMETRY"
        )

        painter.setFont(QFont("Consolas", 8))
        painter.setPen(self.jarvis_cyan())

        painter.drawText(x + 15, y + 45, "CPU")
        self.draw_jarvis_small_graph(
            painter,
            x + 52,
            y + 32,
            80,
            28,
            self.jarvis_cpu_values
        )

        painter.drawText(x + 145, y + 45, "RAM")
        self.draw_jarvis_small_graph(
            painter,
            x + 182,
            y + 32,
            52,
            28,
            self.jarvis_graph_values
        )

        x2 = 575
        self.draw_jarvis_panel(
            painter,
            x2,
            y,
            245,
            82,
            "NETWORK PULSE"
        )

        painter.drawText(x2 + 15, y + 45, "DL")
        self.draw_jarvis_small_graph(
            painter,
            x2 + 52,
            y + 32,
            170,
            28,
            self.jarvis_net_values
        )


    def draw_jarvis_app_launcher_overlay(self, painter):
        # Compact launcher: avoids overlapping your original left HUD panels.
        x = 305
        y = 150
        w = 170
        h = 240

        self.draw_jarvis_panel(
            painter,
            x,
            y,
            w,
            h,
            "APP LAUNCHER"
        )

        apps = [
            "CHROME",
            "YOUTUBE",
            "SPOTIFY",
            "NOTEPAD",
            "CALCULATOR",
            "VS CODE",
        ]

        painter.setFont(QFont("Consolas", 8))

        for index, app in enumerate(apps):
            yy = y + 58 + index * 28

            painter.setPen(self.jarvis_cyan())
            painter.drawEllipse(
                x + 16,
                yy - 10,
                12,
                12
            )

            painter.drawText(
                x + 40,
                yy + 1,
                app
            )


    def draw_jarvis_radar_widget(self, painter, cx, cy, radius):
        painter.setPen(QPen(QColor(0, 220, 255, 170), 2))
        painter.setBrush(Qt.NoBrush)

        for rr in [
            radius,
            int(radius * 0.75),
            int(radius * 0.50),
            int(radius * 0.25)
        ]:
            painter.drawEllipse(
                cx - rr,
                cy - rr,
                rr * 2,
                rr * 2
            )

        for angle_degrees in range(0, 360, 30):
            angle = math.radians(angle_degrees)

            painter.drawLine(
                cx,
                cy,
                int(cx + radius * math.cos(angle)),
                int(cy + radius * math.sin(angle))
            )

        sweep = self.t * 2.7
        sx = cx + radius * math.cos(sweep)
        sy = cy + radius * math.sin(sweep)

        painter.setPen(QPen(QColor(0, 255, 255, 230), 3))
        painter.drawLine(
            cx,
            cy,
            int(sx),
            int(sy)
        )

        painter.setPen(QPen(QColor(0, 255, 255, 230), 4))

        for angle_degrees, distance in self.jarvis_radar_blips:
            angle = math.radians(angle_degrees + self.t * 14)
            bx = cx + radius * distance * math.cos(angle)
            by = cy + radius * distance * math.sin(angle)

            painter.drawPoint(
                int(bx),
                int(by)
            )

    def draw_jarvis_right_panels_overlay(self, painter):
        # Clean right-side overlays: placed below the original PROJECT MATRIX panel.
        x = self.width() - 305
        y = 330
        w = 270

        self.draw_jarvis_panel(
            painter,
            x,
            y,
            w,
            180,
            "RADAR"
        )

        self.draw_jarvis_radar_widget(
            painter,
            x + w // 2,
            y + 98,
            66
        )

        y += 200

        self.draw_jarvis_panel(
            painter,
            x,
            y,
            w,
            145,
            "PROJECTS"
        )

        projects = [
            ("J.A.R.V.I.S", 1.0),
            ("CYBERSHIELD", 0.82),
            ("HUD INTERFACE", 0.96),
            ("VOICE CORE", 0.78),
        ]

        for index, (name, value) in enumerate(projects):
            yy = y + 55 + index * 23

            painter.setPen(self.jarvis_cyan())
            painter.drawText(
                x + 15,
                yy,
                name
            )

            self.draw_jarvis_bar(
                painter,
                x + 150,
                yy - 10,
                90,
                7,
                value
            )


    def draw_jarvis_weather_news_overlay(self, painter):
        # Compact weather/news area placed between center and right column.
        x = self.width() - 610
        y = 150
        w = 255

        self.draw_jarvis_panel(
            painter,
            x,
            y,
            w,
            150,
            "WEATHER"
        )

        painter.setFont(QFont("Consolas", 22, QFont.Bold))
        painter.setPen(self.jarvis_cyan())
        painter.drawText(
            x + 150,
            y + 68,
            "13°C"
        )

        painter.setFont(QFont("Consolas", 8))

        weather_lines = [
            "Condition: Clear",
            "Humidity: 72%",
            "Wind: 22 km/h",
            "AI Weather: Stable"
        ]

        for index, line in enumerate(weather_lines):
            painter.drawText(
                x + 18,
                y + 55 + index * 18,
                line
            )

        y += 165

        self.draw_jarvis_panel(
            painter,
            x,
            y,
            w,
            150,
            "NEWS FEED"
        )

        news = [
            "JARVIS systems online",
            "Project index synchronized",
            "Security scanner ready",
            "Release pack available"
        ]

        for index, item in enumerate(news):
            painter.drawText(
                x + 18,
                y + 55 + index * 22,
                item
            )


    def draw_jarvis_extra_reactor_skin(self, painter):
        cx = self.width() // 2
        cy = self.height() // 2 - 110
        color = self.status_color()

        # Extra large reactor skin around your existing original core.
        for radius, alpha in [
            (310, 45),
            (275, 65),
            (242, 90),
            (205, 115)
        ]:
            painter.setPen(QPen(QColor(0, 210, 255, alpha), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(
                cx - radius,
                cy - radius,
                radius * 2,
                radius * 2
            )

        # Segmented rotating rings.
        for ring_index, radius in enumerate([
            292,
            258,
            224,
            186,
            150
        ]):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(
                (self.t * 38 * (1 if ring_index % 2 == 0 else -1))
                + ring_index * 11
            )
            painter.translate(-cx, -cy)

            painter.setPen(
                QPen(
                    QColor(0, 220, 255, 125),
                    4 if ring_index < 2 else 2
                )
            )

            for i in range(36):
                if i % 3 != 1:
                    painter.drawArc(
                        cx - radius,
                        cy - radius,
                        radius * 2,
                        radius * 2,
                        i * 10 * 16,
                        5 * 16
                    )

            painter.restore()

        # Arc reactor triangle over the original center.
        energy = min(self.voice_smooth, 1.0)

        if self.status.lower() == "processing":
            energy = max(
                energy,
                0.45 + 0.25 * abs(math.sin(self.t * 6))
            )

        if self.ai_status.lower() == "thinking":
            energy = max(
                energy,
                0.58 + 0.32 * abs(math.sin(self.t * 7))
            )

        reactor_r = int(82 + 18 * energy)

        gradient = QRadialGradient(cx, cy, reactor_r)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 245))
        gradient.setColorAt(0.25, QColor(120, 240, 255, 235))
        gradient.setColorAt(0.65, QColor(0, 160, 255, 205))
        gradient.setColorAt(1.0, QColor(0, 45, 90, 145))

        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(color, 3))
        painter.drawEllipse(
            cx - reactor_r,
            cy - reactor_r,
            reactor_r * 2,
            reactor_r * 2
        )

        points = []

        for i in range(3):
            angle = -math.pi / 2 + i * 2 * math.pi / 3 + self.t * 0.3
            points.append(
                QPointF(
                    cx + reactor_r * 0.95 * math.cos(angle),
                    cy + reactor_r * 0.95 * math.sin(angle)
                )
            )

        painter.setPen(QPen(QColor(0, 240, 255, 230), 4))
        painter.setBrush(QBrush(QColor(0, 130, 255, 95)))
        painter.drawPolygon(QPolygonF(points))

        painter.setFont(QFont("Consolas", 20, QFont.Bold))
        painter.setPen(color)
        painter.drawText(
            cx - 160,
            cy - 188,
            320,
            30,
            Qt.AlignCenter,
            "JARVIS"
        )

        painter.setFont(QFont("Consolas", 9))
        painter.drawText(
            cx - 210,
            cy - 158,
            420,
            22,
            Qt.AlignCenter,
            f"ONLINE  |  {self.status}  |  AI {self.ai_status}"
        )


    def draw_jarvis_background_orbit_skin(self, painter):
        """
        Decorative background rings only.
        It does NOT draw the extra triangle/core, so your original center remains clean.
        """
        cx = self.width() // 2
        cy = self.height() // 2 - 110

        for radius, alpha in [
            (340, 30),
            (305, 45),
            (270, 60),
            (235, 75)
        ]:
            painter.setPen(QPen(QColor(0, 210, 255, alpha), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(
                cx - radius,
                cy - radius,
                radius * 2,
                radius * 2
            )

        for ring_index, radius in enumerate([322, 288, 252]):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(
                (self.t * 26 * (1 if ring_index % 2 == 0 else -1))
                + ring_index * 9
            )
            painter.translate(-cx, -cy)

            painter.setPen(QPen(QColor(0, 220, 255, 80), 2))

            for i in range(36):
                if i % 4 == 0:
                    painter.drawArc(
                        cx - radius,
                        cy - radius,
                        radius * 2,
                        radius * 2,
                        i * 10 * 16,
                        4 * 16
                    )

            painter.restore()

        painter.setFont(QFont("Consolas", 18, QFont.Bold))
        painter.setPen(QColor(0, 220, 255, 160))
        painter.drawText(
            cx - 160,
            cy - 205,
            320,
            30,
            Qt.AlignCenter,
            "JARVIS"
        )

        painter.setFont(QFont("Consolas", 9))
        painter.setPen(QColor(0, 220, 255, 135))
        painter.drawText(
            cx - 230,
            cy - 178,
            460,
            22,
            Qt.AlignCenter,
            f"ONLINE  |  {self.status}  |  AI {self.ai_status}"
        )


    def draw_jarvis_bottom_icon_row(self, painter):
        cx = self.width() // 2
        y = self.height() - 315

        labels = [
            "SYS",
            "CORE",
            "MEM",
            "SEC",
            "TIME",
            "DEL"
        ]

        for index, label in enumerate(labels):
            x = cx - 225 + index * 90
            self.draw_jarvis_hex_icon(
                painter,
                x,
                y,
                label
            )

    def draw_jarvis_hex_icon(self, painter, cx, cy, label):
        radius = 28
        points = []

        for i in range(6):
            angle = math.pi / 6 + i * math.pi / 3
            points.append(
                QPointF(
                    cx + radius * math.cos(angle),
                    cy + radius * math.sin(angle)
                )
            )

        painter.setPen(QPen(self.jarvis_cyan(210), 2))
        painter.setBrush(QBrush(QColor(0, 30, 48, 150)))
        painter.drawPolygon(QPolygonF(points))

        painter.setFont(QFont("Consolas", 8, QFont.Bold))
        painter.setPen(self.jarvis_cyan())
        painter.drawText(
            cx - 25,
            cy + 4,
            50,
            12,
            Qt.AlignCenter,
            label
        )

    def draw_jarvis_os_layer_before_original(self, painter):
        self.draw_jarvis_os_background(painter)
        self.draw_jarvis_side_telemetry_left(painter)
        self.draw_jarvis_app_launcher_overlay(painter)
        self.draw_jarvis_weather_news_overlay(painter)
        self.draw_jarvis_right_panels_overlay(painter)
        # Keep your original center/core. The extra overlay reactor/triangle is disabled
        # so the HUD does not draw two centers on top of each other.
        self.draw_jarvis_background_orbit_skin(painter)
        self.draw_jarvis_bottom_icon_row(painter)



    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        self.draw_jarvis_os_layer_before_original(painter)

        # Original HUD rendering continues below.
        # The previous black background is intentionally no longer visible,
        # because the new J.A.R.V.I.S OS layer is drawn first.
        self.draw_scan_lines(painter)

        cx, cy = self.width() // 2, self.height() // 2 - 110

        status_color = self.status_color()

        # Background halo
        halo_r = int(310 + 12 * math.sin(self.t * 1.5))
        painter.setPen(QPen(QColor(0, 120, 200, 120), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(
            cx - halo_r,
            cy - halo_r,
            halo_r * 2,
            halo_r * 2
        )

        # Main outer ring
        painter.setPen(QPen(status_color, 3))
        outer_r = int(265 + 8 * math.sin(self.t * 2))
        painter.drawEllipse(
            cx - outer_r,
            cy - outer_r,
            outer_r * 2,
            outer_r * 2
        )

        # Extra segmented ring effect
        painter.setPen(QPen(QColor(0, 220, 255, 130), 2))
        for i in range(28):
            if i % 3 == 0:
                angle = self.t + i * (2 * math.pi / 28)
                r = outer_r + 18
                x = cx + r * math.cos(angle)
                y = cy + r * math.sin(angle)
                painter.drawPoint(int(x), int(y))

        # Atomic rings
        atomic_rings = [
            (225, 35, (1.0, 0.75)),
            (188, -55, (0.85, 1.0)),
            (155, 75, (0.7, 1.0)),
            (118, -95, (1.0, 0.55)),
        ]

        for r, speed, scale in atomic_rings:
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(self.t * speed)
            painter.scale(scale[0], scale[1])
            painter.translate(-cx, -cy)

            painter.setPen(QPen(QColor(0, 200, 255, 135), 2))
            painter.drawEllipse(
                cx - r,
                cy - r,
                r * 2,
                r * 2
            )
            painter.restore()

        self.draw_radar_points(painter, cx, cy)

        # Central energy core
        energy = min(self.voice_smooth, 1.0)

        if self.status.lower() == "processing":
            energy = max(
                energy,
                0.45 + 0.25 * abs(math.sin(self.t * 6))
            )

        if self.ai_status.lower() == "thinking":
            energy = max(
                energy,
                0.58 + 0.32 * abs(math.sin(self.t * 7))
            )

        core_r = int(58 + 30 * energy)

        gradient = QRadialGradient(cx - 12, cy - 12, core_r)
        gradient.setColorAt(0.0, QColor(255, 255, 255))
        gradient.setColorAt(0.3, QColor(160, 240, 255))
        gradient.setColorAt(0.6, QColor(0, 170, 255))
        gradient.setColorAt(1.0, QColor(0, 60, 120))

        painter.setBrush(gradient)
        painter.setPen(QPen(status_color, 2))
        painter.drawEllipse(
            cx - core_r,
            cy - core_r,
            core_r * 2,
            core_r * 2
        )

        # Central label
        painter.setFont(QFont("Consolas", 18, QFont.Bold))
        painter.setPen(status_color)
        painter.drawText(
            0,
            cy + core_r + 46,
            self.width(),
            35,
            Qt.AlignCenter,
            self.status
        )

        painter.setFont(QFont("Consolas", 10))
        painter.setPen(self.ai_color())
        painter.drawText(
            0,
            cy + core_r + 72,
            self.width(),
            24,
            Qt.AlignCenter,
            "AI CORE: " + self.ai_status
        )

        self.draw_status_bars(painter, cx, cy)
        self.draw_mini_score_orbits(painter, cx, cy)
        self.draw_left_system_panel(painter)
        self.draw_right_score_panel(painter)
        self.draw_enterprise_commander_panel(painter)
        self.draw_main_info_panel(painter)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    hud = JarvisHUD()
    hud.show()
    sys.exit(app.exec_())
