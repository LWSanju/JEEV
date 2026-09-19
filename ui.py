"""JEEV MARK I - Ultimate Dynamic Island + Smooth Chat UI.

Complete replacement for ui.py.

Visual upgrades:
- Minimal collapsed Dynamic Island: J + status + live visualizer only.
- Smooth pill -> panel morph with geometry, opacity and slide motion.
- Tighter spacing and cleaner proportions.
- Real message bubbles with individual fade/slide entrance.
- Cleaner input bar with rounded field and compact send button.
- Hover/press micro-interactions.
- Breathing status indicator.
- Animated audio visualizer.
- Clicking the Dynamic Island toggles the expanded panel.
- Existing JarvisUI compatibility API and plugin-manager flow retained.
"""

from __future__ import annotations

import math
import sys
import threading
from pathlib import Path

from PyQt6.QtCore import (
    Qt,
    pyqtSignal,
    QRectF,
    QPoint,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QAbstractAnimation,
    QUrl,
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPixmap, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QWidget,
    QGraphicsOpacityEffect,
    QFileDialog,
)

try:
    from plugin_manager import get_plugin_manager
except Exception:
    get_plugin_manager = None


class Theme:
    BLACK = QColor("#050507")
    PANEL = QColor("#0A0A0D")
    PANEL2 = QColor("#111116")
    INPUT = QColor("#15161B")
    EDGE = QColor("#282B34")
    EDGE_SOFT = QColor("#1C1E25")
    WHITE = QColor("#F5F7FA")
    TEXT = QColor("#D9DCE3")
    DIM = QColor("#777C88")
    GREEN = QColor("#65F6A5")
    BLUE = QColor("#78A7FF")
    RED = QColor("#FF6576")
    USER_BUBBLE = "#171A22"
    JEEV_BUBBLE = "#10141D"
    ERROR_BUBBLE = "#1B1014"
    PLUGIN_BUBBLE = "#101A16"


C = Theme


def clamp(value, low, high):
    return max(low, min(high, value))


def ui_font(size: int, bold: bool = False) -> QFont:
    f = QFont("Segoe UI", size)
    f.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return f


class AgentAudioVisualizerBar(QFrame):
    """Animated equalizer used inside the island."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.0
        self._active = False
        self._state = "idle"
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._animate_bars)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent; border: none;")

    def set_state(self, state: str):
        self._state = str(state or "idle").lower()
        self._active = self._state in {
            "speaking", "listening", "thinking",
            "connecting", "connected", "processing",
        }
        if self._active:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._level = 0.0
            self._phase = 0.0
        self.update()

    def _animate_bars(self):
        if not self._active:
            self._timer.stop()
            return
        self._phase = (self._phase + 0.23) % 10000
        # The parent draws the visualizer. One parent repaint at ~30 FPS is
        # enough for a smooth HUD without consuming the CPU with 50 FPS paints.
        parent = self.parent()
        if parent is not None:
            parent.update()

    def set_level(self, level: float):
        try:
            self._level = clamp(float(level), 0.0, 1.0)
        except Exception:
            self._level = 0.0
        self.update()

    def tick(self):
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if not self._active:
            painter.end()
            return

        bar_count = 5
        bar_width = 3.5
        gap = 3.5
        total = bar_count * bar_width + (bar_count - 1) * gap
        start_x = (self.width() - total) / 2.0
        multipliers = (0.48, 0.76, 1.0, 0.76, 0.48)

        if self._state == "speaking":
            base = 0.10
        elif self._state == "listening":
            base = 0.075
        elif self._state == "thinking":
            base = 0.07
        else:
            base = 0.05

        for i in range(bar_count):
            if self._state == "speaking":
                motion = (
                    0.18 * math.sin(self._phase + i * 0.95)
                    + 0.08 * math.sin(self._phase * 1.7 + i * 1.35)
                )
            elif self._state == "thinking":
                motion = 0.10 + 0.08 * math.sin(self._phase * 1.4 + i * 0.7)
            else:
                motion = 0.035 * math.sin(self._phase + i * 0.8)

            response = max(0.0, base + motion + self._level * multipliers[i])
            bar_h = clamp(
                4.5 + response * (self.height() - 7.0),
                4.0,
                max(4.0, self.height() - 2.0),
            )
            x = start_x + i * (bar_width + gap)
            y = (self.height() - bar_h) / 2.0

            if self._state == "listening":
                color = C.GREEN
            elif self._state in {
                "thinking", "processing", "connecting", "connected"
            }:
                color = C.BLUE
            else:
                color = C.WHITE

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(
                QRectF(x, y, bar_width, bar_h), 2.2, 2.2
            )

        painter.end()


class MessageBubble(QFrame):
    """Compact chat bubble with a soft slide/fade entrance."""

    def __init__(self, role: str, text: str, parent=None):
        super().__init__(parent)
        self.role = role
        self.setObjectName("messageBubble")
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Minimum,
        )

        if role == "you":
            bg = C.USER_BUBBLE
            border = "#262A35"
            accent = "#DDE3F0"
            name = "YOU"
        elif role == "error":
            bg = C.ERROR_BUBBLE
            border = "#402027"
            accent = C.RED
            name = "ERROR"
        elif role == "plugin":
            bg = C.PLUGIN_BUBBLE
            border = "#233A2E"
            accent = C.GREEN
            name = "PLUGIN"
        else:
            bg = C.JEEV_BUBBLE
            border = "#202A3A"
            accent = C.BLUE
            name = "JEEV"

        self.setStyleSheet(
            f"""
            QFrame#messageBubble {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 16px;
            }}
            QLabel#messageName {{
                color: {accent};
                background: transparent;
                font-family: "Segoe UI"; font-size: 8pt; font-weight: bold;
            }}
            QLabel#messageText {{
                color: #D9DCE3;
                background: transparent;
                font-family: "Segoe UI"; font-size: 9pt;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 10)
        layout.setSpacing(3)

        name_label = QLabel(name)
        name_label.setObjectName("messageName")
        layout.addWidget(name_label)

        body = QLabel(str(text))
        body.setObjectName("messageText")
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        body.setMaximumWidth(470)
        layout.addWidget(body)

        # Keep chat bubbles lightweight. A single position animation is much
        # cheaper than a QGraphicsOpacityEffect per message, especially on an
        # 8 GB / integrated-graphics machine.
        self._slide = None
        self._anim_group = None

    def animate_in(self, delay: int = 0):
        def start():
            start_pos = self.pos()
            end_pos = QPoint(start_pos.x(), start_pos.y())
            self.move(start_pos.x(), start_pos.y() + 7)

            self._slide = QPropertyAnimation(self, b"pos", self)
            self._slide.setDuration(180)
            self._slide.setStartValue(QPoint(start_pos.x(), start_pos.y() + 7))
            self._slide.setEndValue(end_pos)
            self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim_group = self._slide
            self._slide.start(QAbstractAnimation.DeletionPolicy.KeepWhenStopped)

        if delay:
            QTimer.singleShot(delay, start)
        else:
            start()


class GeneratedImageCard(QFrame):
    """Compact generated-image card shown inside the expanded Dynamic Island."""

    def __init__(self, image_path: str, caption: str = "", parent=None):
        super().__init__(parent)
        self.image_path = str(image_path)
        self.setObjectName("generatedImageCard")
        self.setStyleSheet("""
            QFrame#generatedImageCard {
                background: #0D1016;
                border: 1px solid #252B37;
                border-radius: 18px;
            }
            QLabel#generatedImageTitle {
                color: #78A7FF;
                background: transparent;
                font-family: "Segoe UI";
                font-size: 8pt;
                font-weight: 700;
            }
            QLabel#generatedImageCaption {
                color: #AEB4C0;
                background: transparent;
                font-family: "Segoe UI";
                font-size: 8pt;
            }
            QLabel#generatedImage {
                background: #07080B;
                border: 1px solid #1E232D;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(7)

        title = QLabel("JEEV • GENERATED IMAGE")
        title.setObjectName("generatedImageTitle")
        layout.addWidget(title)

        self.image = QLabel()
        self.image.setObjectName("generatedImage")
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(260, 150)
        self.image.setMaximumHeight(300)
        self.image.setCursor(Qt.CursorShape.PointingHandCursor)
        self.image.setToolTip("Click to open the full-size image")
        self.image.mousePressEvent = self._open_image
        layout.addWidget(self.image)

        if caption:
            cap = QLabel(str(caption))
            cap.setObjectName("generatedImageCaption")
            cap.setWordWrap(True)
            layout.addWidget(cap)

        self._pixmap = QPixmap()
        self._load_image()

    def _load_image(self):
        pixmap = QPixmap(self.image_path)
        if pixmap.isNull():
            self.image.setText("Unable to load generated image.")
            return
        self._pixmap = pixmap
        self._fit_image()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_image()

    def _fit_image(self):
        if self._pixmap.isNull():
            return
        target = self.image.size()
        if target.width() < 10 or target.height() < 10:
            return
        scaled = self._pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.image.setPixmap(scaled)

    def _open_image(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            try:
                QDesktopServices.openUrl(QUrl.fromLocalFile(self.image_path))
            except Exception:
                pass
            event.accept()
        else:
            event.ignore()



class JarvisUI(QFrame):
    WINDOW_W = 440
    WINDOW_H = 90
    EXPANDED_W = 680
    EXPANDED_H = 540

    state_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str)
    command_signal = pyqtSignal(str)
    file_signal = pyqtSignal(str)
    mute_signal = pyqtSignal(bool)
    plugin_status_signal = pyqtSignal(str)
    generated_image_signal = pyqtSignal(str, str)

    def __init__(self, face_path: str | None = None, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        super().__init__(None)

        self._state = "IDLE"
        self._level = 0.0
        self._muted = False
        self._current_file = None
        self._history = []
        self._action_text = ""
        self._ready = True
        self._expanded = False
        self._animating = False
        self._pressed = False
        self._hovered = False
        self.on_text_command = None
        self._generated_image_paths = set()
        self._image_cards = []

        self._root_bg = None
        self.root = self._RootShim(self._app)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(self.WINDOW_W, self.WINDOW_H)
        self.resize(self.WINDOW_W, self.WINDOW_H)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # The visualizer is a child of the root so it can sit above the pill.
        self._visualizer = AgentAudioVisualizerBar(self)
        self._visualizer.setGeometry(0, 0, 1, 1)
        self._visualizer.hide()

        # Expanded panel.
        self._panel = QFrame(self)
        self._panel.setObjectName("chatPanel")
        self._panel.setVisible(False)
        self._panel.setMouseTracking(True)
        self._panel.setStyleSheet(
            """
            QFrame#chatPanel {
                background: #0A0A0D;
                border: 1px solid #292C35;
                border-radius: 24px;
            }
            QScrollArea {
                background: transparent;
                border: none;
            }
            QWidget#chatViewport {
                background: transparent;
            }
            QLineEdit#chatInput {
                background: #15161B;
                border: 1px solid #2B2E38;
                border-radius: 17px;
                color: #F5F7FA;
                padding: 8px 13px;
                font-family: "Segoe UI"; font-size: 9pt;
                selection-background-color: #29354B;
            }
            QLineEdit#chatInput:focus {
                border: 1px solid #5879B3;
                background: #171920;
            }
            QPushButton#attachButton {
                background: #15161B;
                border: 1px solid #2B2E38;
                border-radius: 18px;
                color: #DDE3F0;
                font-family: "Segoe UI";
                font-size: 17pt;
                font-weight: 500;
                padding: 0px 0px 2px 0px;
            }
            QPushButton#attachButton:hover {
                background: #1B1F28;
                border: 1px solid #435879;
                color: #F5F7FA;
            }
            QPushButton#attachButton:pressed {
                background: #10131A;
            }

            QPushButton#sendButton {
                background: #1A202C;
                border: 1px solid #313846;
                border-radius: 17px;
                color: #E9EDF5;
                font-family: "Segoe UI"; font-size: 9pt; font-weight: 700;
                padding: 0px;
            }
            QPushButton#sendButton:hover {
                background: #222B3A;
                border: 1px solid #435879;
            }
            QPushButton#sendButton:pressed {
                background: #12161E;
            }
            """
        )

        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(18, 47, 18, 14)
        panel_layout.setSpacing(8)

        # Compact header.
        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 2, 0)
        header.setSpacing(7)

        title = QLabel("JEEV")
        title.setStyleSheet(
            "color:#F5F7FA; font-family:'Segoe UI'; font-size:11pt; font-weight:700; background:transparent;"
        )

        subtitle = QLabel("Chat")
        subtitle.setStyleSheet(
            "color:#707580; font-family:'Segoe UI'; font-size:9pt; background:transparent;"
        )

        dot = QLabel("•")
        dot.setStyleSheet(
            "color:#353944; font-family:'Segoe UI'; font-size:9pt; background:transparent;"
        )

        plugins = QLabel("Plugins")
        plugins.setStyleSheet(
            "color:#707580; font-family:'Segoe UI'; font-size:9pt; background:transparent;"
        )

        header.addWidget(title)
        header.addWidget(subtitle)
        header.addWidget(dot)
        header.addWidget(plugins)
        header.addStretch(1)
        panel_layout.addLayout(header)

        # Scrollable bubble area.
        self._scroll = QScrollArea(self._panel)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(
            """
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 4px 0 4px 0;
            }
            QScrollBar::handle:vertical {
                background: #30343E;
                border-radius: 2px;
                min-height: 28px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )

        self._chat_view = QWidget()
        self._chat_view.setObjectName("chatViewport")
        self._chat_layout = QVBoxLayout(self._chat_view)
        self._chat_layout.setContentsMargins(2, 2, 2, 4)
        self._chat_layout.setSpacing(7)
        self._chat_layout.addStretch(1)

        self._scroll.setWidget(self._chat_view)
        panel_layout.addWidget(self._scroll, 1)

        # Generated-image display. The watcher is intentionally isolated from
        # the backend so image generation can keep working without changes to
        # Gmail, WhatsApp, Spotify, browser, coding-agent, or other tools.
        self.generated_image_signal.connect(self._show_generated_image)
        self._image_watch_dir = Path(__file__).resolve().parent / "generated_images"
        self._image_watch_dir.mkdir(parents=True, exist_ok=True)
        self._remember_existing_generated_images()
        self._image_watch_timer = QTimer(self)
        self._image_watch_timer.setInterval(1500)
        self._image_watch_timer.timeout.connect(self._poll_generated_images)
        self._image_watch_timer.start()

        # Cleaner input dock with a real attachment button.
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 2, 0, 0)
        input_row.setSpacing(7)

        self._attach_button = QPushButton("+", self._panel)
        self._attach_button.setObjectName("attachButton")
        self._attach_button.setFixedSize(36, 36)
        self._attach_button.setToolTip("Attach an image, PDF, document, or file")
        self._attach_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._attach_button.clicked.connect(self._browse_file)

        self._input = QLineEdit(self._panel)
        self._input.setObjectName("chatInput")
        self._input.setPlaceholderText("Message JEEV…")
        self._input.setMinimumHeight(36)
        self._input.returnPressed.connect(self._send)

        self._send_button = QPushButton("↑", self._panel)
        self._send_button.setObjectName("sendButton")
        self._send_button.setFixedSize(36, 36)
        self._send_button.setToolTip("Send")
        self._send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send_button.clicked.connect(self._send)

        input_row.addWidget(self._attach_button)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(self._send_button)
        panel_layout.addLayout(input_row)

        # Opacity effects let the panel fade independently from the island.
        self._panel_opacity = QGraphicsOpacityEffect(self._panel)
        self._panel_opacity.setOpacity(0.0)
        self._panel.setGraphicsEffect(self._panel_opacity)

        self._panel_anim = None
        self._panel_fade = None
        self._chat_fade = None

        # Signals remain compatible with the existing backend.
        self.state_signal.connect(self._apply_state)
        self.log_signal.connect(self._add_log)
        self.command_signal.connect(self._send_command)
        self.file_signal.connect(self._on_file_selected)
        self.mute_signal.connect(self._apply_mute)
        self.plugin_status_signal.connect(self._show_plugin_status)

        self._position_once()

    class _RootShim:
        def __init__(self, app):
            self._app = app

        def mainloop(self):
            return self._app.exec()

        def protocol(self, *_args, **_kwargs):
            return None

    def _screen_area(self):
        screen = self.screen() or QApplication.primaryScreen()
        return screen.availableGeometry() if screen else None

    def _position_for_size(self, width: int, height: int):
        area = self._screen_area()
        if not area:
            return
        x = area.left() + (area.width() - width) // 2
        y = area.top() + 6
        self.move(x, y)

    def _position_once(self):
        self._position_for_size(self.width(), self.height())
        self.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Child layout changes happen here, never inside paintEvent().
        self._sync_visualizer_geometry()

    def showEvent(self, event):
        super().showEvent(event)
        self._position_once()
        self._sync_visualizer_geometry()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._point_on_island(event.position().toPoint()):
                self._pressed = True
                self.update()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was_pressed = self._pressed
            self._pressed = False
            self.update()

            if was_pressed and self._point_on_island(
                event.position().toPoint()
            ):
                if self._expanded:
                    self.collapse_chat()
                else:
                    self.expand_chat()

            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _point_on_island(self, point: QPoint) -> bool:
        # QRectF.contains in Qt6 accepts x/y floats.
        return self._pill_rect().contains(
            float(point.x()), float(point.y())
        )

    def _pill_rect(self) -> QRectF:
        if self._expanded:
            return QRectF(
                (self.width() - 400) / 2,
                7,
                400,
                40,
            )

        state = self._state
        if state == "LISTENING":
            width, height = 235, 38
        elif state in {"THINKING", "PROCESSING"}:
            width, height = 250, 38
        elif state == "SPEAKING":
            width, height = 235, 38
        elif state == "MUTED":
            width, height = 190, 36
        else:
            width, height = 215, 36

        return QRectF(
            (self.width() - width) / 2,
            0,
            width,
            height,
        )

    def _draw_shadow(self, painter, rect, hover=False):
        layers = (
            ((2, 34), (4, 22), (7, 12), (10, 5))
            if hover
            else ((2, 28), (4, 18), (7, 10))
        )
        for amount, alpha in layers:
            r = rect.adjusted(-amount, -amount, amount, amount)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(
                r, r.height() / 2, r.height() / 2
            )

    def _draw_text(
        self,
        painter,
        text,
        rect,
        size,
        color,
        bold=False,
        align=Qt.AlignmentFlag.AlignLeft,
    ):
        painter.setFont(ui_font(size, bold))
        painter.setPen(color)
        painter.drawText(rect, align, str(text))

    def paintEvent(self, event):
        painter = QPainter()
        if not painter.begin(self):
            return
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pill = self._pill_rect()
            if self._pressed:
                pill.translate(0, 1)
            self._draw_shadow(painter, pill, self._hovered)
            edge = QColor("#4D6DAB") if self._hovered and self._expanded else C.EDGE
            painter.setPen(QPen(edge, 1))
            painter.setBrush(C.BLACK)
            painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            self._draw_content(painter, pill)
        finally:
            painter.end()

    def _draw_visualizer(self, painter, rect):
        if not self._visualizer._active or self._expanded:
            return
        bar_count, bar_width, gap = 5, 3.5, 3.5
        total = bar_count * bar_width + (bar_count - 1) * gap
        start_x = rect.right() - total - 11
        multipliers = (0.48, 0.76, 1.0, 0.76, 0.48)
        state = self._visualizer._state
        base = 0.10 if state == "speaking" else 0.075 if state == "listening" else 0.07 if state == "thinking" else 0.05
        for i in range(bar_count):
            if state == "speaking":
                motion = 0.18 * math.sin(self._visualizer._phase + i * 0.95) + 0.08 * math.sin(self._visualizer._phase * 1.7 + i * 1.35)
            elif state == "thinking":
                motion = 0.10 + 0.08 * math.sin(self._visualizer._phase * 1.4 + i * 0.7)
            else:
                motion = 0.035 * math.sin(self._visualizer._phase + i * 0.8)
            response = max(0.0, base + motion + self._visualizer._level * multipliers[i])
            bar_h = clamp(4.5 + response * (rect.height() - 7.0), 4.0, max(4.0, rect.height() - 2.0))
            x = start_x + i * (bar_width + gap)
            y = rect.center().y() - bar_h / 2.0
            color = C.GREEN if state == "listening" else C.BLUE if state in {"thinking", "processing", "connecting", "connected"} else C.WHITE
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, y, bar_width, bar_h), 2.2, 2.2)

    def _draw_content(self, painter, rect):
        state = self._state

        if state == "LISTENING":
            status_color, status = C.GREEN, "LISTENING"
        elif state in {"THINKING", "PROCESSING"}:
            status_color, status = C.BLUE, "THINKING"
        elif state == "SPEAKING":
            status_color, status = C.WHITE, "JEEV"
        elif state == "MUTED":
            status_color, status = C.RED, "MUTED"
        else:
            status_color, status = C.WHITE, "JEEV"

        if self._expanded:
            self._draw_text(
                painter,
                "‹",
                QRectF(
                    rect.left() + 9,
                    rect.top(),
                    28,
                    rect.height(),
                ),
                21,
                C.WHITE,
                False,
                Qt.AlignmentFlag.AlignCenter,
            )
            self._draw_text(
                painter,
                "JEEV",
                QRectF(
                    rect.left() + 37,
                    rect.top(),
                    48,
                    rect.height(),
                ),
                9,
                C.WHITE,
                True,
                Qt.AlignmentFlag.AlignVCenter
                | Qt.AlignmentFlag.AlignLeft,
            )
            dot_x = rect.left() + 93
            status_x = rect.left() + 105
        else:
            self._draw_text(
                painter,
                "J",
                QRectF(
                    rect.left() + 11,
                    rect.top(),
                    31,
                    rect.height(),
                ),
                17,
                C.WHITE,
                True,
                Qt.AlignmentFlag.AlignCenter,
            )
            dot_x = rect.left() + 46
            status_x = rect.left() + 58

        # Breathing status dot.
        pulse = 0.5 + 0.5 * math.sin(
            self._visualizer._phase * 1.5
        )
        radius = (
            2.5
            + (0.75 * pulse if self._state != "IDLE" else 0.0)
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(status_color)
        painter.drawEllipse(
            QRectF(
                dot_x - radius + 3,
                rect.center().y() - radius,
                radius * 2,
                radius * 2,
            )
        )

        self._draw_text(
            painter,
            status,
            QRectF(
                status_x,
                rect.top(),
                82,
                rect.height(),
            ),
            7,
            C.TEXT if state != "MUTED" else C.RED,
            True,
            Qt.AlignmentFlag.AlignVCenter
            | Qt.AlignmentFlag.AlignLeft,
        )

        self._draw_visualizer(painter, rect)

        # IMPORTANT: action/message text is deliberately never drawn
        # in the collapsed island.
        #
        # Do NOT move/reconfigure child widgets from inside paintEvent().
        # Doing so can schedule a nested child repaint while this widget's
        # QPainter is still active, which causes:
        #   QPainter::begin: A paint device can only be painted by one painter
        # Keep all child geometry updates outside the painting pass.

    def _sync_visualizer_geometry(self):
        """Position the child visualizer without doing it during paintEvent."""
        try:
            rect = self._pill_rect()
            self._visualizer.setGeometry(0, 0, 1, 1)
        except RuntimeError:
            # The widget may be shutting down.
            pass

    def _make_geometry_animation(
        self, start, end, duration, curve
    ):
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(duration)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(curve)
        return anim

    def _stop_current_animation(self):
        for animation in (
            self._panel_anim,
            self._panel_fade,
            self._chat_fade,
        ):
            if animation is not None:
                try:
                    animation.stop()
                except Exception:
                    pass

    def _set_panel_geometry_for_window(self):
        # Panel begins directly underneath the island, leaving the pill
        # visually floating above it while the window itself expands.
        self._panel.setGeometry(
            0,
            40,
            self.width(),
            max(1, self.height() - 40),
        )

    def expand_chat(self):
        if self._expanded:
            return
        if self._animating:
            self._stop_current_animation()
            self._animating = False

        area = self._screen_area()
        if not area:
            return

        self._stop_current_animation()
        self._animating = True
        self._expanded = True

        start = self.geometry()
        end = start
        end.setX(
            area.left()
            + (area.width() - self.EXPANDED_W) // 2
        )
        end.setY(area.top() + 6)
        end.setWidth(self.EXPANDED_W)
        end.setHeight(self.EXPANDED_H)

        # Start with a small panel directly below the compact pill.
        self._panel.setGeometry(
            (self.width() - 460) // 2,
            39,
            460,
            50,
        )
        self._panel_opacity.setOpacity(0.0)
        self._panel.setVisible(True)
        self._panel.raise_()
        self._visualizer.raise_()

        geometry = self._make_geometry_animation(
            start,
            end,
            500,
            QEasingCurve.Type.OutBack,
        )

        self._panel_fade = QPropertyAnimation(
            self._panel_opacity, b"opacity", self
        )
        self._panel_fade.setDuration(360)
        self._panel_fade.setStartValue(0.0)
        self._panel_fade.setEndValue(1.0)
        self._panel_fade.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )

        group = QParallelAnimationGroup(self)
        group.addAnimation(geometry)
        group.addAnimation(self._panel_fade)
        self._panel_anim = group

        geometry.valueChanged.connect(
            lambda _value: self._set_panel_geometry_for_window()
        )
        group.finished.connect(self._expand_finished)
        group.start()

        self.update()

    def _expand_finished(self):
        self._animating = False
        self._set_panel_geometry_for_window()
        self._sync_visualizer_geometry()
        self._panel_opacity.setOpacity(1.0)
        self._input.setFocus(Qt.FocusReason.MouseFocusReason)
        self._scroll_to_bottom()
        self.update()

    def collapse_chat(self):
        if not self._expanded:
            return
        if self._animating:
            self._stop_current_animation()
            self._animating = False

        area = self._screen_area()
        if not area:
            return

        self._stop_current_animation()
        self._animating = True

        start = self.geometry()
        end = start
        end.setX(
            area.left()
            + (area.width() - self.WINDOW_W) // 2
        )
        end.setY(area.top() + 6)
        end.setWidth(self.WINDOW_W)
        end.setHeight(self.WINDOW_H)

        panel_fade = QPropertyAnimation(
            self._panel_opacity, b"opacity", self
        )
        panel_fade.setDuration(190)
        panel_fade.setStartValue(
            self._panel_opacity.opacity()
        )
        panel_fade.setEndValue(0.0)
        panel_fade.setEasingCurve(
            QEasingCurve.Type.InCubic
        )
        self._panel_fade = panel_fade

        geometry = self._make_geometry_animation(
            start,
            end,
            410,
            QEasingCurve.Type.InOutCubic,
        )

        group = QParallelAnimationGroup(self)
        group.addAnimation(geometry)
        group.addAnimation(panel_fade)
        self._panel_anim = group
        geometry.valueChanged.connect(
            lambda _value: self._set_panel_geometry_for_window()
        )
        group.finished.connect(self._collapse_finished)
        group.start()

    def _collapse_finished(self):
        self._expanded = False
        self._animating = False
        self._panel.setVisible(False)
        self._panel_opacity.setOpacity(0.0)
        self._panel.setGeometry(
            0, 40, self.WINDOW_W, self.WINDOW_H - 40
        )
        self._position_for_size(
            self.WINDOW_W, self.WINDOW_H
        )
        self._sync_visualizer_geometry()
        self.update()

    def set_state(self, state: str):
        normalized = str(state).upper().strip() or "IDLE"
        # Audio streaming can report the same state many times per second.
        # Do not enqueue duplicate Qt signals/repaints.
        if normalized == self._state:
            return
        self.state_signal.emit(normalized)

    def _apply_state(self, state: str):
        normalized = str(state).upper().strip() or "IDLE"
        if normalized == self._state:
            return
        self._state = normalized
        self._visualizer.set_state(self._state.lower())
        self._sync_visualizer_geometry()
        self.update()

    def set_speaking_level(self, level: float):
        try:
            value = clamp(float(level), 0.0, 1.0)
        except Exception:
            value = 0.0
        if abs(value - self._level) < 0.015:
            return
        self._level = value
        self._visualizer.set_level(self._level)
        self.update()

    def set_audio_level(self, level: float):
        self.set_speaking_level(level)

    def update_speaking_level(self, level: float):
        self.set_speaking_level(level)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self._muted:
            self.set_state("LISTENING")

    def write_log(self, text: str):
        self.log_signal.emit(str(text))

    def _add_log(self, text: str):
        text = str(text).strip()
        if not text:
            return

        self._history.append(text)
        if len(self._history) > 100:
            self._history = self._history[-100:]

        if text.startswith("You:"):
            message = text[4:].strip()
            self._action_text = message[:42]
            self._add_bubble("you", message)

        elif text.startswith("Jeev:"):
            message = text[5:].strip()
            self._action_text = message[:42]
            self._add_bubble("jeev", message)

        elif text.startswith("ERR:"):
            message = text[4:].strip()
            self._action_text = "Error"
            self._add_bubble("error", message)

        elif text.startswith("FILE:"):
            self._action_text = "File ready"
            self._add_bubble("jeev", text)

        else:
            self._add_bubble("jeev", text)

        self.update()


    def _remember_existing_generated_images(self):
        try:
            for path in self._image_watch_dir.iterdir():
                if path.is_file() and path.suffix.lower() in {
                    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"
                }:
                    self._generated_image_paths.add(str(path.resolve()))
        except Exception:
            pass

    def _poll_generated_images(self):
        """Pick up newly created images without touching the backend thread."""
        try:
            files = [
                p for p in self._image_watch_dir.iterdir()
                if p.is_file() and p.suffix.lower() in {
                    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"
                }
            ]
            files.sort(key=lambda p: p.stat().st_mtime)
            for path in files:
                resolved = str(path.resolve())
                if resolved in self._generated_image_paths:
                    continue
                # Ignore files that are still being written.
                try:
                    if path.stat().st_size < 1024:
                        continue
                except OSError:
                    continue
                self._generated_image_paths.add(resolved)
                self.generated_image_signal.emit(
                    resolved,
                    f"Saved to generated_images\\{path.name}",
                )
        except Exception:
            pass

    def show_generated_image(self, image_path: str, caption: str = ""):
        """Public, thread-safe API for main.py or any image tool to use."""
        self.generated_image_signal.emit(str(image_path), str(caption or ""))

    def _show_generated_image(self, image_path: str, caption: str = ""):
        path = Path(str(image_path))
        if not path.exists() or not path.is_file():
            return
        if not self._expanded:
            self.expand_chat()

        # Avoid duplicate cards if main.py also explicitly calls this API.
        resolved = str(path.resolve())
        self._generated_image_paths.add(resolved)

        card = GeneratedImageCard(resolved, caption, self._chat_view)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(card)
        row.addStretch(1)

        index = max(0, self._chat_layout.count() - 1)
        self._chat_layout.insertLayout(index, row)
        self._image_cards.append(card)

        # Do not attach a QGraphicsOpacityEffect to every generated image.
        # The card is intentionally static so image arrival never stutters
        # the assistant's live HUD.
        card.show()
        card.adjustSize()
        QTimer.singleShot(80, self._scroll_to_bottom)


    def _add_bubble(self, role: str, text: str):
        bubble = MessageBubble(role, str(text), self._chat_view)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        if role == "you":
            row.addStretch(1)
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch(1)

        # Insert before the permanent bottom stretch.
        index = max(0, self._chat_layout.count() - 1)
        self._chat_layout.insertLayout(index, row)

        bubble.show()
        bubble.adjustSize()
        bubble.animate_in(0)

        QTimer.singleShot(35, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        try:
            bar = self._scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
        except Exception:
            pass

    @staticmethod
    def _escape(text):
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )

    def _show_action(self, text: str, duration: int = 0):
        self._action_text = str(text).strip()[:42]
        self.update()

    def _finish_action(self):
        self._action_text = ""
        self.update()

    def _animate_size(self, width, height):
        self.update()

    def _set_size(self, width, height):
        self.update()

    def _tick_animation(self):
        return None

    @property
    def muted(self):
        return bool(self._muted)

    @muted.setter
    def muted(self, value):
        self.set_muted(value)

    def set_muted(self, value: bool):
        self.mute_signal.emit(bool(value))

    def _apply_mute(self, value: bool):
        self._muted = bool(value)
        self.set_state(
            "MUTED" if self._muted else "LISTENING"
        )

    def _toggle_mute(self):
        self.set_muted(not self._muted)

    @property
    def current_file(self):
        return self._current_file

    def _browse_file(self):
        """Open the native file picker for JEEV's analyzer."""
        try:
            start_dir = str(Path.home())
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Attach file to JEEV",
                start_dir,
                (
                    "Supported files (*.png *.jpg *.jpeg *.webp *.gif *.bmp "
                    "*.tif *.tiff *.pdf *.txt *.md *.csv *.json *.xml *.docx "
                    "*.xlsx *.xlsm *.xls *.py *.js *.ts *.html *.css *.java "
                    "*.cpp *.c *.h *.hpp);;"
                    "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.tif *.tiff);;"
                    "Documents (*.pdf *.txt *.md *.csv *.json *.xml *.docx *.xlsx *.xlsm *.xls);;"
                    "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.c *.h *.hpp);;"
                    "All files (*.*)"
                ),
            )
            if path:
                self.file_signal.emit(path)
        except Exception as exc:
            self._show_plugin_status(f"File picker error: {exc}")

    def _on_file_selected(self, path: str):
        self._current_file = path

        if path:
            name = Path(path).name
            self._action_text = f"File: {name}"[:42]
            self._add_bubble(
                "you",
                f"Attached: {name}",
            )
            self._input.setFocus()
            self.update()

            callback = self.on_text_command
            if callback:
                threading.Thread(
                    target=callback,
                    args=(f"[FILE_UPLOADED] path={path}",),
                    daemon=True,
                ).start()

    def _send(self):
        text = self._input.text().strip()
        if not text:
            return

        self._input.clear()
        self._add_log(f"You: {text}")

        manager = None
        if get_plugin_manager is not None:
            try:
                manager = get_plugin_manager()
            except Exception as exc:
                self._show_plugin_status(
                    f"Plugin manager unavailable: {exc}"
                )

        is_github = bool(
            manager
            and manager.extract_url(text)
            and "github.com/" in text.lower()
        )
        plugin_words = any(
            w in text.lower()
            for w in (
                "plugin",
                "install",
                "add this",
                "github",
            )
        )

        if (
            manager
            and is_github
            and (
                plugin_words
                or text.lower().strip().startswith("http")
            )
        ):
            threading.Thread(
                target=self._install_plugin_worker,
                args=(manager, text),
                daemon=True,
                name="JEEV-PluginInstall",
            ).start()
            return

        callback = self.on_text_command
        if callback:
            threading.Thread(
                target=callback,
                args=(text,),
                daemon=True,
            ).start()

    def _install_plugin_worker(self, manager, text):
        self.plugin_status_signal.emit(
            "Plugin Manager: inspecting GitHub repository…"
        )

        try:
            result = manager.install_from_text(
                text, allow_high_risk=False
            )

            if result.get("ok"):
                p = result.get("plugin", {})
                msg = (
                    f"✓ Plugin installed: "
                    f"{p.get('name', p.get('id', 'plugin'))} "
                    f"v{p.get('version', '')}\n"
                    f"Capabilities: "
                    f"{', '.join(p.get('capabilities', [])) or 'none declared'}"
                )

                if result.get("warnings"):
                    msg += (
                        "\nWarnings: "
                        + "; ".join(result["warnings"])
                    )

                self.plugin_status_signal.emit(msg)

            else:
                self.plugin_status_signal.emit(
                    "Plugin install failed: "
                    + str(result.get("error", "unknown error"))
                )

        except PermissionError as exc:
            self.plugin_status_signal.emit(
                "Plugin needs approval before activation: "
                + str(exc)
            )
        except Exception as exc:
            self.plugin_status_signal.emit(
                "Plugin install failed: " + str(exc)
            )

    def _show_plugin_status(self, text):
        text = str(text)
        self._action_text = text.splitlines()[0][:42]
        self._add_bubble("plugin", text)
        self.update()

    def _send_command(self, text: str):
        self._input.setText(str(text))
        self._send()

    def wait_for_api_key(self):
        return True

    def process_events(self):
        self._app.processEvents()

    def run(self):
        return self._app.exec()

    def closeEvent(self, event):
        event.accept()


if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    ui = JarvisUI()
    ui.show()
    ui.set_state("LISTENING")
    sys.exit(ui.run())
