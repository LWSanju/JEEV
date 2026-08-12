from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from PyQt6.QtCore import (
    QMimeData,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontDatabase,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QLinearGradient,
    QPixmap,
    QRadialGradient,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# ============================================================
# BASE DIRECTORY
# ============================================================

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE = CONFIG_DIR / "api_keys.json"

# ============================================================
# JEEV IDENTITY FONT
# ============================================================

_JEEV_FONT_FILE = BASE_DIR / "Zaslia.otf"
_JEEV_FONT_FAMILY = "Zaslia"


def _load_jeev_font() -> str:
    """Load the bundled Zaslia font and return its Qt family name."""
    if not _JEEV_FONT_FILE.exists():
        print(
            f"[JEEV] ⚠️ Zaslia font not found: {_JEEV_FONT_FILE}"
        )
        return _JEEV_FONT_FAMILY

    font_id = QFontDatabase.addApplicationFont(
        str(_JEEV_FONT_FILE)
    )

    if font_id == -1:
        print("[JEEV] ⚠️ Failed to load Zaslia.otf")
        return _JEEV_FONT_FAMILY

    families = QFontDatabase.applicationFontFamilies(font_id)

    if families:
        print(f"[JEEV] ✨ Loaded identity font: {families[0]}")
        return families[0]

    return _JEEV_FONT_FAMILY



_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W, _MIN_H = 820, 580
_LEFT_W = 280
_RIGHT_W = 420

_OS = platform.system()


# ============================================================
# JEEV — STELLAR CORE THEME
# ============================================================

class C:
    # Deep space
    BG = "#010207"
    DARK = "#05070d"

    # Panels
    PANEL = "#080b12"
    PANEL2 = "#0c1018"

    # Borders
    BORDER = "#202633"
    BORDER_A = "#303847"
    BORDER_B = "#596579"

    # Primary stellar amber
    PRI = "#ff9d32"
    PRI_DIM = "#b86620"
    PRI_GHO = "#241205"

    # Gold
    ACC = "#ffc15a"
    ACC2 = "#ffe0a3"

    # Status
    GREEN = "#39ff9a"
    GREEN_D = "#16a866"
    RED = "#ff4966"

    # Text
    TEXT = "#f6dfc3"
    TEXT_DIM = "#8d7b69"
    TEXT_MED = "#b9a58e"
    WHITE = "#fff7ed"

    BAR_BG = "#151821"

    # Stellar core
    CORE_WHITE = "#ffffff"
    CORE_HOT = "#fff4c7"
    CORE_GOLD = "#ffc34d"
    CORE_ORANGE = "#ff7a18"
    CORE_DEEP = "#8a2608"

    # Orbit colours
    ORBIT = "#ffad45"
    ORBIT_B = "#ffcc70"
    ORBIT_DIM = "#8d4d19"

    # Electron
    ELECTRON = "#fff0b5"
    ELECTRON_GLOW = "#ff9d32"

    # Stars
    STAR = "#ffd58a"


def qcol(h: str, a: int = 255) -> QColor:
    c = QColor(h)
    c.setAlpha(max(0, min(255, a)))
    return c


# ============================================================
# SYSTEM METRICS
# ============================================================

class _SysMetrics:
    def __init__(self):
        self.cpu = 0.0
        self.mem = 0.0
        self.net = 0.0
        self.gpu = -1.0
        self.tmp = -1.0

        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True

        t = threading.Thread(
            target=self._loop,
            daemon=True,
        )

        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass

            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc = psutil.net_io_counters()

        now = time.time()
        dt = now - self._last_net_t

        if dt > 0:
            sent = (
                nc.bytes_sent
                - self._last_net.bytes_sent
            ) / dt

            recv = (
                nc.bytes_recv
                - self._last_net.bytes_recv
            ) / dt

            net = (
                (sent + recv)
                / (1024 * 1024)
            )

        else:
            net = 0.0

        self._last_net = nc
        self._last_net_t = now

        gpu = self._get_gpu()
        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # NVIDIA
        try:
            r = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if r.returncode == 0:
                vals = [
                    float(v.strip())
                    for v in r.stdout.strip().split("\n")
                    if v.strip()
                ]

                if vals:
                    return sum(vals) / len(vals)

        except Exception:
            pass

        # AMD / Intel Linux
        if _OS == "Linux":
            try:
                r = subprocess.run(
                    [
                        "rocm-smi",
                        "--showuse",
                        "--csv",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )

                if r.returncode == 0:
                    for line in r.stdout.strip().split("\n"):
                        parts = line.split(",")

                        if len(parts) >= 2:
                            try:
                                return float(
                                    parts[1]
                                    .strip()
                                    .replace("%", "")
                                )
                            except ValueError:
                                pass

            except Exception:
                pass

            try:
                r = subprocess.run(
                    [
                        "intel_gpu_top",
                        "-J",
                        "-s",
                        "500",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=1,
                )

                if (
                    r.returncode == 0
                    and "Render/3D" in r.stdout
                ):
                    import re

                    m = re.search(
                        r'"busy":\s*([\d.]+)',
                        r.stdout,
                    )

                    if m:
                        return float(
                            m.group(1)
                        )

            except Exception:
                pass

        # macOS
        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    [
                        "sudo",
                        "-n",
                        "powermetrics",
                        "-n",
                        "1",
                        "-i",
                        "500",
                        "--samplers",
                        "gpu_power",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )

                if (
                    r.returncode == 0
                    and "GPU" in r.stdout
                ):
                    import re

                    m = re.search(
                        r"GPU\s+Active:\s+([\d.]+)%",
                        r.stdout,
                    )

                    if m:
                        return float(
                            m.group(1)
                        )

            except Exception:
                pass

        return -1.0

    def _get_temp(self) -> float:
        try:
            temps = psutil.sensors_temperatures()

            candidates = [
                "coretemp",
                "k10temp",
                "cpu_thermal",
                "acpitz",
                "cpu-thermal",
                "zenpower",
                "it8688",
            ]

            for name in candidates:
                if name in temps:
                    entries = temps[name]

                    if entries:
                        return entries[0].current

            for entries in temps.values():
                if entries:
                    return entries[0].current

        except Exception:
            pass

        if _OS == "Darwin":
            try:
                r = subprocess.run(
                    ["osx-cpu-temp"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )

                if r.returncode == 0:
                    import re

                    m = re.search(
                        r"([\d.]+)",
                        r.stdout,
                    )

                    if m:
                        return float(
                            m.group(1)
                        )

            except Exception:
                pass

        if _OS == "Windows":
            try:
                r = subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "(Get-WmiObject "
                        "MSAcpi_ThermalZoneTemperature "
                        "-Namespace root/wmi).CurrentTemperature",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )

                if (
                    r.returncode == 0
                    and r.stdout.strip()
                ):
                    raw = float(
                        r.stdout.strip()
                        .split("\n")[0]
                    )

                    return (
                        raw / 10.0
                    ) - 273.15

            except Exception:
                pass

        return -1.0

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()


# ============================================================
# STELLAR / ATOMIC CORE HUD
# ============================================================

class HudCanvas(QWidget):
    """
    JEEV central visual core.

    This version intentionally does NOT use a Saturn/planet design.

    The centre is a glowing stellar energy core.
    Multiple orbital planes cross around it like an atom.
    Electrons travel along those paths.
    """

    def __init__(
        self,
        face_path: str,
        parent=None,
    ):
        super().__init__(parent)

        self.setAttribute(
            Qt.WidgetAttribute.WA_OpaquePaintEvent
        )

        self.setMinimumSize(300, 300)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        self.muted = False
        self.speaking = False
        self.state = "INITIALISING"

        self._tick = 0

        self._scale = 1.0
        self._tgt_scale = 1.0

        self._halo = 55.0
        self._tgt_halo = 55.0

        self._last_t = time.time()

        # HUD scanner
        self._scan = 0.0
        self._scan2 = 180.0

        # ====================================================
        # ATOMIC ORBIT SYSTEM
        # ====================================================

        # Three independent orbital planes.
        self._orbit_angle_1 = 0.0
        self._orbit_angle_2 = math.pi / 2
        self._orbit_angle_3 = math.pi
        self._orbit_angle_4 = math.pi * 0.35

        self._orbit_speed_1 = 0.020
        self._orbit_speed_2 = -0.014
        self._orbit_speed_3 = 0.010
        self._orbit_speed_4 = -0.008

        # Electron positions.
        self._electron_phase_1 = 0.0
        self._electron_phase_2 = math.pi * 0.72
        self._electron_phase_3 = math.pi * 1.45
        self._electron_phase_4 = math.pi * 0.20
        self._electron_phase_5 = math.pi * 1.10

        # Stellar core breathing.
        self._core_phase = 0.0

        # Energy sparks.
        self._energy_phase = 0.0

        # Expanding energy pulses.
        self._pulses = [
            0.0,
            75.0,
            150.0,
        ]

        # Particles coming from the core.
        self._particles: list[list[float]] = []

        # Background stars.
        self._stars: list[list[float]] = []

        # Nebula particles.
        self._nebula: list[list[float]] = []

        self._blink = True
        self._blink_tick = 0

        self._face_px: QPixmap | None = None

        self._load_face(face_path)
        self._generate_stars()
        self._generate_nebula()

        self._tmr = QTimer(self)

        self._tmr.timeout.connect(
            self._step
        )

        self._tmr.start(16)

    # --------------------------------------------------------
    # FACE
    # --------------------------------------------------------

    def _load_face(self, path: str):
        try:
            from PIL import Image, ImageDraw
            import io

            img = Image.open(path).convert(
                "RGBA"
            )

            sz = min(img.size)

            img = img.resize(
                (sz, sz),
                Image.LANCZOS,
            )

            mask = Image.new(
                "L",
                (sz, sz),
                0,
            )

            ImageDraw.Draw(mask).ellipse(
                (2, 2, sz - 2, sz - 2),
                fill=255,
            )

            img.putalpha(mask)

            buf = io.BytesIO()

            img.save(
                buf,
                format="PNG",
            )

            px = QPixmap()

            px.loadFromData(
                buf.getvalue()
            )

            self._face_px = px

        except Exception:
            self._face_px = None

    # --------------------------------------------------------
    # STARS
    # --------------------------------------------------------

    def _generate_stars(self):
        self._stars.clear()

        for _ in range(280):
            self._stars.append(
                [
                    random.random(),
                    random.random(),
                    random.uniform(
                        0.4,
                        1.9,
                    ),
                    random.uniform(
                        0.15,
                        0.9,
                    ),
                ]
            )

    # --------------------------------------------------------
    # NEBULA
    # --------------------------------------------------------

    def _generate_nebula(self):
        self._nebula.clear()

        for _ in range(45):
            self._nebula.append(
                [
                    random.uniform(
                        0.15,
                        0.85,
                    ),
                    random.uniform(
                        0.10,
                        0.90,
                    ),
                    random.uniform(
                        20,
                        90,
                    ),
                    random.uniform(
                        0.02,
                        0.09,
                    ),
                ]
            )

    # --------------------------------------------------------
    # ANIMATION UPDATE
    # --------------------------------------------------------

    def _step(self):
        self._tick += 1

        now = time.time()

        if now - self._last_t > (
            0.12
            if self.speaking
            else 0.5
        ):
            if self.speaking:
                self._tgt_scale = random.uniform(
                    1.06,
                    1.14,
                )

                self._tgt_halo = random.uniform(
                    145,
                    190,
                )

            elif self.muted:
                self._tgt_scale = random.uniform(
                    0.998,
                    1.002,
                )

                self._tgt_halo = random.uniform(
                    15,
                    28,
                )

            else:
                self._tgt_scale = random.uniform(
                    1.001,
                    1.008,
                )

                self._tgt_halo = random.uniform(
                    48,
                    68,
                )

            self._last_t = now

        smoothing = (
            0.38
            if self.speaking
            else 0.15
        )

        self._scale += (
            self._tgt_scale
            - self._scale
        ) * smoothing

        self._halo += (
            self._tgt_halo
            - self._halo
        ) * smoothing

        # ====================================================
        # ATOMIC ORBIT ROTATION
        # ====================================================

        speed_multiplier = (
            2.7
            if self.speaking
            else 1.0
        )

        if self.muted:
            speed_multiplier *= 0.55

        self._orbit_angle_1 = (
            self._orbit_angle_1
            + self._orbit_speed_1
            * speed_multiplier
        ) % (math.pi * 2)

        self._orbit_angle_2 = (
            self._orbit_angle_2
            + self._orbit_speed_2
            * speed_multiplier
        ) % (math.pi * 2)

        self._orbit_angle_3 = (
            self._orbit_angle_3
            + self._orbit_speed_3
            * speed_multiplier
        ) % (math.pi * 2)

        self._orbit_angle_4 = (
            self._orbit_angle_4
            + self._orbit_speed_4
            * speed_multiplier
        ) % (math.pi * 2)

        # ====================================================
        # ELECTRONS
        # ====================================================

        electron_speed = (
            0.055
            if self.speaking
            else 0.026
        )

        self._electron_phase_1 = (
            self._electron_phase_1
            + electron_speed
        ) % (math.pi * 2)

        self._electron_phase_2 = (
            self._electron_phase_2
            - electron_speed * 1.25
        ) % (math.pi * 2)

        self._electron_phase_3 = (
            self._electron_phase_3
            + electron_speed * 0.72
        ) % (math.pi * 2)

        self._electron_phase_4 = (
            self._electron_phase_4
            - electron_speed * 0.88
        ) % (math.pi * 2)

        self._electron_phase_5 = (
            self._electron_phase_5
            + electron_speed * 0.61
        ) % (math.pi * 2)

        # Core energy.
        self._core_phase += (
            0.070
            if self.speaking
            else 0.035
        )

        self._energy_phase += 0.08

        # HUD scanners.
        self._scan = (
            self._scan
            + (
                3.0
                if self.speaking
                else 1.3
            )
        ) % 360

        self._scan2 = (
            self._scan2
            + (
                -2.0
                if self.speaking
                else -0.75
            )
        ) % 360

        # ====================================================
        # PULSE RINGS
        # ====================================================

        fw = min(
            self.width(),
            self.height(),
        )

        limit = fw * 0.74

        pulse_speed = (
            4.2
            if self.speaking
            else 2.0
        )

        self._pulses = [
            r + pulse_speed
            for r in self._pulses
            if r + pulse_speed < limit
        ]

        if len(self._pulses) < 3:
            if random.random() < (
                0.07
                if self.speaking
                else 0.025
            ):
                self._pulses.append(0.0)

        # ====================================================
        # ENERGY PARTICLES
        # ====================================================

        if random.random() < (0.34 if self.speaking else 0.10):
            cx = self.width() / 2
            cy = self.height() / 2

            ang = random.uniform(
                0,
                2 * math.pi,
            )

            radius = fw * 0.13

            self._particles.append(
                [
                    cx
                    + math.cos(ang)
                    * radius,

                    cy
                    + math.sin(ang)
                    * radius,

                    math.cos(ang)
                    * random.uniform(
                        0.8,
                        2.6,
                    ),

                    math.sin(ang)
                    * random.uniform(
                        0.8,
                        2.6,
                    ),

                    1.0,
                ]
            )

        self._particles = [
            [
                pt[0] + pt[2],
                pt[1] + pt[3],
                pt[2] * 0.97,
                pt[3] * 0.97,
                pt[4] - 0.028,
            ]
            for pt in self._particles
            if pt[4] > 0
        ]

        # ====================================================
        # BLINK
        # ====================================================

        self._blink_tick += 1

        if self._blink_tick >= 38:
            self._blink = not self._blink
            self._blink_tick = 0

        self.update()

    # --------------------------------------------------------
    # ORBIT POINT GENERATOR
    # --------------------------------------------------------

    def _orbit_point(
        self,
        cx: float,
        cy: float,
        radius: float,
        t: float,
        rotation: float,
        plane: int,
    ) -> QPointF:
        """
        Generates a projected 3D atom orbit.

        Each plane is tilted differently.
        """

        x = math.cos(t) * radius
        y = math.sin(t) * radius

        if plane == 0:
            # Horizontal / diagonal orbital plane.
            px = (
                x * math.cos(rotation)
                - y
                * math.sin(rotation)
            )

            py = (
                x * math.sin(rotation)
                + y
                * math.cos(rotation)
            )

            py *= 0.30

        elif plane == 1:
            # Strong crossing orbital plane.
            px = (
                x
                * math.cos(rotation)
            )

            py = (
                y
                * math.cos(rotation)
                + x
                * math.sin(rotation)
            )

            px *= 0.34

        else:
            # Third tilted plane.
            px = (
                x
                * math.cos(rotation)
                - y
                * math.sin(rotation)
                * 0.55
            )

            py = (
                x
                * math.sin(rotation)
                * 0.55
                + y
                * math.cos(rotation)
            )

            py *= 0.56

        return QPointF(
            cx + px,
            cy + py,
        )

    # --------------------------------------------------------
    # DRAW ORBIT
    # --------------------------------------------------------

    def _draw_orbit(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        radius: float,
        rotation: float,
        plane: int,
        alpha: int,
        width: float,
    ):
        points = []

        count = 180

        for i in range(count + 1):
            t = (
                i
                / count
                * math.pi
                * 2
            )

            points.append(
                self._orbit_point(
                    cx,
                    cy,
                    radius,
                    t,
                    rotation,
                    plane,
                )
            )

        if len(points) < 2:
            return

        path = QPainterPath()

        path.moveTo(points[0])

        for point in points[1:]:
            path.lineTo(point)

        # Slightly different spectral tones make the four planes read as
        # separate living paths rather than duplicated circles.
        orbit_color = {
            0: C.ORBIT_B,
            1: "#d7c7ff",
            2: C.ORBIT,
            3: "#9bc7ff",
        }.get(plane, C.ORBIT)

        # Glow.
        p.setPen(
            QPen(
                qcol(
                    orbit_color,
                    max(
                        5,
                        int(alpha * 0.18),
                    ),
                ),
                width * 4.0,
            )
        )

        p.setBrush(
            Qt.BrushStyle.NoBrush
        )

        p.drawPath(path)

        # Main orbital line.
        p.setPen(
            QPen(
                qcol(
                    orbit_color,
                    alpha,
                ),
                width,
            )
        )

        p.drawPath(path)

    # --------------------------------------------------------
    # DRAW ELECTRON
    # --------------------------------------------------------

    def _draw_electron(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        radius: float,
        phase: float,
        rotation: float,
        plane: int,
        size: float = 3.5,
    ):
        point = self._orbit_point(
            cx,
            cy,
            radius,
            phase,
            rotation,
            plane,
        )

        ex = point.x()
        ey = point.y()

        electron_color = {
            0: C.ELECTRON_GLOW,
            1: "#9e8cff",
            2: C.ELECTRON_GLOW,
            3: "#69b5ff",
        }.get(plane, C.ELECTRON_GLOW)

        # Short luminous trail: gives the electrons the moving-photon feel
        # visible in the reference instead of static dots on an ellipse.
        for j in range(7, 0, -1):
            trail_phase = phase - j * 0.045
            tp = self._orbit_point(cx, cy, radius, trail_phase, rotation, plane)
            ta = int(105 * (1.0 - j / 8.0))
            tr = max(0.7, size * (1.0 - j * 0.075))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(electron_color, ta)))
            p.drawEllipse(QPointF(tp.x(), tp.y()), tr, tr)

        # Electron glow.
        glow_r = size * 5.5

        grad = QRadialGradient(
            QPointF(ex, ey),
            glow_r,
        )

        grad.setColorAt(
            0.0,
            qcol(
                C.ELECTRON,
                230,
            ),
        )

        grad.setColorAt(
            0.22,
            qcol(
                electron_color,
                190,
            ),
        )

        grad.setColorAt(
            0.55,
            qcol(
                electron_color,
                70,
            ),
        )

        grad.setColorAt(
            1.0,
            qcol(
                C.ELECTRON_GLOW,
                0,
            ),
        )

        p.setPen(
            Qt.PenStyle.NoPen
        )

        p.setBrush(
            QBrush(grad)
        )

        p.drawEllipse(
            QRectF(
                ex - glow_r,
                ey - glow_r,
                glow_r * 2,
                glow_r * 2,
            )
        )

        # Actual electron.
        p.setBrush(
            QBrush(
                qcol(
                    C.ELECTRON,
                    255,
                )
            )
        )

        p.drawEllipse(
            QRectF(
                ex - size,
                ey - size,
                size * 2,
                size * 2,
            )
        )

    # --------------------------------------------------------
    # DRAW STELLAR CORE
    # --------------------------------------------------------

    def _draw_core(
        self,
        p: QPainter,
        cx: float,
        cy: float,
        radius: float,
    ):
        pulse = (
            math.sin(
                self._core_phase
            )
            + 1.0
        ) * 0.5

        # ====================================================
        # MASSIVE OUTER GLOW
        # ====================================================

        glow_radius = radius * (
            3.0
            + pulse * 0.65
        )

        grad = QRadialGradient(
            QPointF(cx, cy),
            glow_radius,
        )

        grad.setColorAt(
            0.0,
            qcol(
                C.CORE_WHITE,
                int(
                    135
                    + pulse * 80
                ),
            ),
        )

        grad.setColorAt(
            0.12,
            qcol(
                C.CORE_HOT,
                int(
                    155
                    + pulse * 65
                ),
            ),
        )

        grad.setColorAt(
            0.28,
            qcol(
                C.CORE_GOLD,
                int(
                    120
                    + pulse * 50
                ),
            ),
        )

        grad.setColorAt(
            0.52,
            qcol(
                C.CORE_ORANGE,
                int(
                    65
                    + pulse * 35
                ),
            ),
        )

        grad.setColorAt(
            0.78,
            qcol(
                C.CORE_DEEP,
                int(
                    25
                    + pulse * 20
                ),
            ),
        )

        grad.setColorAt(
            1.0,
            qcol(
                C.CORE_DEEP,
                0,
            ),
        )

        p.setPen(
            Qt.PenStyle.NoPen
        )

        p.setBrush(
            QBrush(grad)
        )

        p.drawEllipse(
            QRectF(
                cx - glow_radius,
                cy - glow_radius,
                glow_radius * 2,
                glow_radius * 2,
            )
        )

        # ====================================================
        # INNER ENERGY SHELL
        # ====================================================

        shell_r = radius * (
            1.45
            + pulse * 0.08
        )

        shell_grad = QRadialGradient(
            QPointF(cx, cy),
            shell_r,
        )

        shell_grad.setColorAt(
            0.0,
            qcol(
                C.CORE_WHITE,
                255,
            ),
        )

        shell_grad.setColorAt(
            0.22,
            qcol(
                C.CORE_HOT,
                255,
            ),
        )

        shell_grad.setColorAt(
            0.50,
            qcol(
                C.CORE_GOLD,
                245,
            ),
        )

        shell_grad.setColorAt(
            0.75,
            qcol(
                C.CORE_ORANGE,
                210,
            ),
        )

        shell_grad.setColorAt(
            1.0,
            qcol(
                C.CORE_DEEP,
                80,
            ),
        )

        p.setBrush(
            QBrush(shell_grad)
        )

        p.drawEllipse(
            QRectF(
                cx - shell_r,
                cy - shell_r,
                shell_r * 2,
                shell_r * 2,
            )
        )

        # ====================================================
        # CORE SURFACE
        # ====================================================

        core_r = radius * (
            0.78
            + pulse * 0.04
        )

        core_grad = QRadialGradient(
            QPointF(
                cx
                - core_r * 0.28,
                cy
                - core_r * 0.30,
            ),
            core_r * 1.2,
        )

        core_grad.setColorAt(
            0.0,
            qcol(
                "#ffffff",
                255,
            ),
        )

        core_grad.setColorAt(
            0.20,
            qcol(
                "#fff2bf",
                255,
            ),
        )

        core_grad.setColorAt(
            0.48,
            qcol(
                "#ffc04b",
                255,
            ),
        )

        core_grad.setColorAt(
            0.75,
            qcol(
                "#ff7519",
                255,
            ),
        )

        core_grad.setColorAt(
            1.0,
            qcol(
                "#9e2808",
                255,
            ),
        )

        p.setBrush(
            QBrush(core_grad)
        )

        p.drawEllipse(
            QRectF(
                cx - core_r,
                cy - core_r,
                core_r * 2,
                core_r * 2,
            )
        )

        # ====================================================
        # ENERGY CONTOURS
        # ====================================================

        p.setBrush(
            Qt.BrushStyle.NoBrush
        )

        for i in range(4):
            rr = (
                core_r
                * (
                    1.15
                    + i * 0.17
                )
            )

            alpha = int(
                110
                * (
                    1
                    - i / 5
                )
                * (
                    0.7
                    + pulse * 0.3
                )
            )

            p.setPen(
                QPen(
                    qcol(
                        C.CORE_HOT,
                        alpha,
                    ),
                    1.0,
                )
            )

            p.drawEllipse(
                QRectF(
                    cx - rr,
                    cy - rr,
                    rr * 2,
                    rr * 2,
                )
            )

        # ====================================================
        # FINE ENERGY RAYS + SURFACE PARTICLES
        # ====================================================
        ray_count = 18
        ray_phase = self._core_phase * 0.17
        for i in range(ray_count):
            ang = i * (math.tau / ray_count) + ray_phase
            inner = core_r * 1.05
            outer = core_r * (1.45 + 0.20 * math.sin(self._core_phase * 1.7 + i))
            alpha = int(35 + 35 * pulse + 18 * math.sin(i * 1.7 + self._core_phase))
            p.setPen(QPen(qcol(C.CORE_HOT, max(12, alpha)), 1.0))
            p.drawLine(
                QPointF(cx + math.cos(ang) * inner, cy + math.sin(ang) * inner),
                QPointF(cx + math.cos(ang) * outer, cy + math.sin(ang) * outer),
            )

        for i in range(12):
            a = self._core_phase * 1.15 + i * 0.73
            rr = core_r * (0.84 + 0.18 * math.sin(a * 2.3))
            px = cx + math.cos(a) * rr
            py = cy + math.sin(a) * rr
            pr = 0.8 + 0.8 * ((math.sin(a * 3.1) + 1.0) * 0.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(qcol(C.CORE_WHITE, int(135 + 80 * pulse))))
            p.drawEllipse(QPointF(px, py), pr, pr)

        # ====================================================
        # CENTRAL WHITE STAR POINT
        # ====================================================

        point_r = radius * (
            0.12
            + pulse * 0.025
        )

        p.setBrush(
            QBrush(
                qcol(
                    "#ffffff",
                    255,
                )
            )
        )

        p.setPen(
            Qt.PenStyle.NoPen
        )

        p.drawEllipse(
            QRectF(
                cx - point_r,
                cy - point_r,
                point_r * 2,
                point_r * 2,
            )
        )

    # --------------------------------------------------------
    # PAINT EVENT
    # --------------------------------------------------------

    def paintEvent(self, _):
        p = QPainter(self)

        p.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        p.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform
        )

        p.fillRect(
            self.rect(),
            qcol(C.BG),
        )

        W = self.width()
        H = self.height()

        cx = W / 2
        cy = H / 2

        fw = min(W, H)

        # ====================================================
        # DEEP SPACE BACKGROUND
        # ====================================================

        # Subtle central nebula.
        nebula_grad = QRadialGradient(
            QPointF(cx, cy),
            fw * 0.70,
        )

        nebula_grad.setColorAt(
            0.0,
            qcol(
                "#1b0d04",
                100,
            ),
        )

        nebula_grad.setColorAt(
            0.30,
            qcol(
                "#100a08",
                70,
            ),
        )

        nebula_grad.setColorAt(
            0.65,
            qcol(
                "#05060b",
                40,
            ),
        )

        nebula_grad.setColorAt(
            1.0,
            qcol(
                C.BG,
                0,
            ),
        )

        p.setPen(
            Qt.PenStyle.NoPen
        )

        p.setBrush(
            QBrush(nebula_grad)
        )

        p.drawRect(
            self.rect()
        )

        # ====================================================
        # NEBULA CLOUDS
        # ====================================================

        for nx, ny, radius, opacity in self._nebula:
            grad = QRadialGradient(
                QPointF(
                    nx * W,
                    ny * H,
                ),
                radius,
            )

            grad.setColorAt(
                0.0,
                qcol(
                    C.CORE_ORANGE,
                    int(
                        opacity * 255
                    ),
                ),
            )

            grad.setColorAt(
                1.0,
                qcol(
                    C.CORE_ORANGE,
                    0,
                ),
            )

            p.setBrush(
                QBrush(grad)
            )

            p.drawEllipse(
                QRectF(
                    nx * W - radius,
                    ny * H - radius,
                    radius * 2,
                    radius * 2,
                )
            )

        # ====================================================
        # STARS
        # ====================================================

        p.setPen(
            Qt.PenStyle.NoPen
        )

        for sx, sy, size, opacity in self._stars:
            twinkle = (
                math.sin(
                    self._tick * 0.025
                    + sx * 20
                )
                + 1
            ) * 0.5

            alpha = int(
                35
                + opacity * 110
                + twinkle * 30
            )

            p.setBrush(
                QBrush(
                    qcol(
                        C.STAR,
                        min(
                            190,
                            alpha,
                        ),
                    )
                )
            )

            p.drawEllipse(
                QPointF(
                    sx * W,
                    sy * H,
                ),
                size,
                size,
            )

        # ====================================================
        # CLEAN STARFIELD
        # ====================================================
        # No dashboard grid. The depth comes from stars, nebula, and
        # the very faint orbital geometry.

        # ====================================================
        # FAR-FIELD DUST / ENERGY SPECKS
        # ====================================================
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(34):
            a = self._tick * 0.0012 + i * 1.913
            rr = fw * (0.24 + 0.22 * ((i * 37) % 17) / 17.0)
            px = cx + math.cos(a * 1.7 + i) * rr
            py = cy + math.sin(a + i * 0.4) * rr * 0.62
            pr = 0.45 + (i % 3) * 0.22
            alpha = 18 + (i % 5) * 7
            p.setBrush(QBrush(qcol(C.ACC, alpha)))
            p.drawEllipse(QPointF(px, py), pr, pr)

        # ====================================================
        # CORE SIZE
        # ====================================================

        core_r = fw * 0.108

        # ====================================================
        # OUTER ENERGY HALOS
        # ====================================================

        for i in range(12):
            r = (
                core_r
                * (
                    2.0
                    + i * 0.16
                )
            )

            factor = (
                1.0
                - i / 12
            )

            alpha = max(
                0,
                min(
                    255,
                    int(
                        self._halo
                        * 0.06
                        * factor
                    ),
                ),
            )

            p.setPen(
                QPen(
                    qcol(
                        C.PRI,
                        alpha,
                    ),
                    1.0,
                )
            )

            p.setBrush(
                Qt.BrushStyle.NoBrush
            )

            p.drawEllipse(
                QRectF(
                    cx - r,
                    cy - r,
                    r * 2,
                    r * 2,
                )
            )

        # ====================================================
        # EXPANDING ENERGY PULSES
        # ====================================================

        for pulse_radius in self._pulses:
            alpha = max(
                0,
                int(
                    190
                    * (
                        1.0
                        - pulse_radius
                        / (
                            fw * 0.74
                        )
                    )
                ),
            )

            p.setPen(
                QPen(
                    qcol(
                        C.PRI,
                        alpha,
                    ),
                    1.2,
                )
            )

            p.setBrush(
                Qt.BrushStyle.NoBrush
            )

            p.drawEllipse(
                QRectF(
                    cx - pulse_radius,
                    cy - pulse_radius,
                    pulse_radius * 2,
                    pulse_radius * 2,
                )
            )

        # ====================================================
        # ATOMIC ORBIT SYSTEM
        # ====================================================

        orbit_radius_1 = fw * 0.255
        orbit_radius_2 = fw * 0.275
        orbit_radius_3 = fw * 0.235

        # Back orbital planes first.
        self._draw_orbit(
            p,
            cx,
            cy,
            orbit_radius_2,
            self._orbit_angle_2,
            1,
            125
            if not self.muted
            else 55,
            1.7,
        )

        self._draw_orbit(
            p,
            cx,
            cy,
            orbit_radius_3,
            self._orbit_angle_3,
            2,
            110
            if not self.muted
            else 45,
            1.5,
        )

        self._draw_orbit(
            p,
            cx,
            cy,
            fw * 0.30,
            self._orbit_angle_4,
            3,
            92
            if not self.muted
            else 40,
            1.35,
        )

        # Main orbital plane.
        self._draw_orbit(
            p,
            cx,
            cy,
            orbit_radius_1,
            self._orbit_angle_1,
            0,
            185
            if not self.muted
            else 70,
            2.0,
        )

        # ====================================================
        # ELECTRONS
        # ====================================================

        self._draw_electron(
            p,
            cx,
            cy,
            orbit_radius_1,
            self._electron_phase_1,
            self._orbit_angle_1,
            0,
            4.0,
        )

        self._draw_electron(
            p,
            cx,
            cy,
            orbit_radius_2,
            self._electron_phase_2,
            self._orbit_angle_2,
            1,
            3.6,
        )

        self._draw_electron(
            p,
            cx,
            cy,
            orbit_radius_3,
            self._electron_phase_3,
            self._orbit_angle_3,
            2,
            3.4,
        )

        self._draw_electron(
            p,
            cx,
            cy,
            orbit_radius_1 * 0.82,
            self._electron_phase_4,
            -self._orbit_angle_1 * 0.65,
            2,
            3.0,
        )

        self._draw_electron(
            p,
            cx,
            cy,
            fw * 0.30,
            self._electron_phase_5,
            self._orbit_angle_4,
            3,
            3.2,
        )

        # ====================================================
        # INNER ATOMIC SHELL
        # ====================================================

        inner_r = fw * 0.17

        p.setPen(
            QPen(
                qcol(
                    C.ORBIT_B,
                    75,
                ),
                1.0,
            )
        )

        p.setBrush(
            Qt.BrushStyle.NoBrush
        )

        p.drawEllipse(
            QRectF(
                cx - inner_r,
                cy - inner_r * 0.38,
                inner_r * 2,
                inner_r * 0.76,
            )
        )

        # ====================================================
        # STELLAR CORE
        # ====================================================

        self._draw_core(
            p,
            cx,
            cy,
            core_r * self._scale,
        )

        # ====================================================
        # OLD HUD SCANNING ARCS
        # ====================================================

        for idx, (
            r_frac,
            width,
            arc_length,
            gap,
        ) in enumerate(
            [
                (
                    0.48,
                    2.5,
                    115,
                    78,
                ),
                (
                    0.40,
                    1.5,
                    78,
                    55,
                ),
                (
                    0.32,
                    1.0,
                    56,
                    40,
                ),
            ]
        ):
            ring_r = fw * r_frac

            base = (
                self._scan
                if idx == 0
                else (
                    self._scan2
                    if idx == 1
                    else self._scan * 0.45
                )
            )

            alpha = max(
                0,
                min(
                    255,
                    int(
                        self._halo
                        * (
                            0.70
                            - idx * 0.12
                        )
                    ),
                ),
            )

            p.setPen(
                QPen(
                    qcol(
                        C.MUTED_C
                        if self.muted
                        else C.PRI,
                        alpha,
                    ),
                    width,
                )
            )

            p.setBrush(
                Qt.BrushStyle.NoBrush
            )

            angle = base

            rect = QRectF(
                cx - ring_r,
                cy - ring_r,
                ring_r * 2,
                ring_r * 2,
            )

            while angle < base + 360:
                p.drawArc(
                    rect,
                    int(angle * 16),
                    int(
                        arc_length * 16
                    ),
                )

                angle += (
                    arc_length
                    + gap
                )

        # ====================================================
        # PARTICLE BURST
        # ====================================================

        for pt in self._particles:
            alpha = max(
                0,
                min(
                    255,
                    int(
                        pt[4] * 255
                    ),
                ),
            )

            p.setPen(
                Qt.PenStyle.NoPen
            )

            p.setBrush(
                QBrush(
                    qcol(
                        C.PRI,
                        alpha,
                    )
                )
            )

            p.drawEllipse(
                QPointF(
                    pt[0],
                    pt[1],
                ),
                2.5,
                2.5,
            )

        # ====================================================
        # OUTER SCANNER
        # ====================================================

        scanner_r = fw * 0.50

        scanner_alpha = min(
            255,
            int(
                self._halo * 1.5
            ),
        )

        p.setPen(
            QPen(
                qcol(
                    C.MUTED_C
                    if self.muted
                    else C.PRI,
                    scanner_alpha,
                ),
                2.0,
            )
        )

        p.setBrush(
            Qt.BrushStyle.NoBrush
        )

        scanner_rect = QRectF(
            cx - scanner_r,
            cy - scanner_r,
            scanner_r * 2,
            scanner_r * 2,
        )

        extension = (
            75
            if self.speaking
            else 44
        )

        p.drawArc(
            scanner_rect,
            int(
                self._scan * 16
            ),
            int(
                extension * 16
            ),
        )

        p.setPen(
            QPen(
                qcol(
                    C.ACC,
                    scanner_alpha // 2,
                ),
                1.2,
            )
        )

        p.drawArc(
            scanner_rect,
            int(
                self._scan2 * 16
            ),
            int(
                extension * 16
            ),
        )

        # ====================================================
        # TICK MARKS
        # ====================================================

        tick_outer = fw * 0.46
        tick_inner = fw * 0.445

        p.setPen(
            QPen(
                qcol(
                    C.PRI,
                    120,
                ),
                1,
            )
        )

        for degree in range(
            0,
            360,
            10,
        ):
            rad = math.radians(
                degree
            )

            inner = (
                tick_inner
                if degree % 30 == 0
                else tick_inner + 6
            )

            p.drawLine(
                QPointF(
                    cx
                    + tick_outer
                    * math.cos(rad),
                    cy
                    - tick_outer
                    * math.sin(rad),
                ),
                QPointF(
                    cx
                    + inner
                    * math.cos(rad),
                    cy
                    - inner
                    * math.sin(rad),
                ),
            )

        # ====================================================
        # CLEAN CORE FIELD
        # ====================================================
        # No targeting crosshair and no corner-crop brackets. The reference
        # uses a clean cinematic field around the living stellar core.

        # ====================================================
        # CENTER IDENTITY
        # ====================================================
        # The reference does not place a face/image over the star. Keep the
        # centre purely energetic; the JEEV identity is already in the header.

        # ====================================================
        # STATUS TEXT
        # ====================================================

        status_y = (
            cy
            + fw * 0.40
        )

        if self.muted:
            text = "⊘  MUTED"
            color = qcol(
                C.MUTED_C
            )

        elif self.speaking:
            text = "●  SPEAKING"
            color = qcol(
                C.ACC
            )

        elif self.state == "THINKING":
            symbol = (
                "◈"
                if self._blink
                else "◇"
            )

            text = (
                f"{symbol}  THINKING"
            )

            color = qcol(
                C.ACC2
            )

        elif self.state == "PROCESSING":
            symbol = (
                "▷"
                if self._blink
                else "▶"
            )

            text = (
                f"{symbol}  PROCESSING"
            )

            color = qcol(
                C.ACC2
            )

        elif self.state == "LISTENING":
            symbol = (
                "●"
                if self._blink
                else "○"
            )

            text = (
                f"{symbol}  LISTENING"
            )

            color = qcol(
                C.GREEN
            )

        else:
            symbol = (
                "●"
                if self._blink
                else "○"
            )

            text = (
                f"{symbol}  {self.state}"
            )

            color = qcol(
                C.PRI
            )

        p.setPen(
            QPen(
                color,
                1,
            )
        )

        p.setFont(
            QFont(
                "Courier New",
                11,
                QFont.Weight.Bold,
            )
        )

        p.drawText(
            QRectF(
                0,
                status_y,
                W,
                26,
            ),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )

        # ====================================================
        # WAVEFORM
        # ====================================================

        wave_y = status_y + 30

        count = 36
        bar_width = 8

        wave_x = (
            W
            - count * bar_width
        ) / 2

        for i in range(count):
            if self.muted:
                height = 2
                color = qcol(
                    C.MUTED_C
                )

            elif self.speaking:
                height = random.randint(
                    3,
                    20,
                )

                color = (
                    qcol(C.PRI)
                    if height > 12
                    else qcol(
                        C.PRI_DIM
                    )
                )

            else:
                height = int(
                    3
                    + 2
                    * math.sin(
                        self._tick
                        * 0.09
                        + i
                        * 0.6
                    )
                )

                color = qcol(
                    C.BORDER_B
                )

            p.fillRect(
                QRectF(
                    wave_x
                    + i * bar_width,
                    wave_y
                    + 20
                    - height,
                    bar_width - 1,
                    height,
                ),
                color,
            )


# ============================================================
# METRIC BAR
# ============================================================

class MetricBar(QWidget):
    """Minimal metric row used inside the floating SYS MONITOR glass card."""

    def __init__(
        self,
        label: str,
        color: str = C.PRI,
        parent=None,
    ):
        super().__init__(parent)

        self._label = label
        self._color = color
        self._value = 0.0
        self._text = "--"
        self.setFixedHeight(48)
        self.setMinimumWidth(130)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        if self._value > 85:
            bar_color = qcol(C.RED)
        elif self._value > 65:
            bar_color = qcol(C.ACC)
        else:
            bar_color = qcol(self._color)

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT_MED, 235), 1))
        p.drawText(QRectF(10, 3, 70, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._label)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(bar_color if self._text != "--" else qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(82, 2, W - 92, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._text)

        track = QRectF(10, 25, W - 20, 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(qcol("#070b12", 220)))
        p.drawRoundedRect(track, 2, 2)

        fill_w = track.width() * self._value / 100.0
        if fill_w > 0:
            p.setBrush(QBrush(bar_color))
            p.drawRoundedRect(QRectF(track.x(), track.y(), fill_w, track.height()), 2, 2)
            # small luminous head, like the reference widgets
            p.setBrush(QBrush(qcol("#ffffff", 120)))
            p.drawEllipse(QPointF(track.x() + fill_w, track.y() + track.height() / 2), 2.0, 2.0)


# ============================================================
# ACTIVITY LOG
# ============================================================

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        self.setReadOnly(True)

        self.setFont(
            QFont(
                "Courier New",
                9,
            )
        )

        self.setStyleSheet(
            f"""
            QTextEdit {{
                background: transparent;
                color: {C.TEXT};
                border: none;
                border-radius: 0px;
                padding: 0px;
                selection-background-color: rgba(255,157,50,35);
            }}

            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}

            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
            """
        )

        self._queue: list[str] = []
        self._typing = False
        self._text = ""
        self._pos = 0
        self._tag = "sys"

        self._tmr = QTimer(self)

        self._tmr.timeout.connect(
            self._step
        )

        self._sig.connect(
            self._enqueue
        )

    def append_log(
        self,
        text: str,
    ):
        self._sig.emit(text)

    def _enqueue(
        self,
        text: str,
    ):
        self._queue.append(text)

        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return

        self._typing = True

        self._text = self._queue.pop(0)
        self._pos = 0

        lower = self._text.lower()

        if lower.startswith("you:"):
            self._tag = "you"

        elif lower.startswith("jeev:"):
            self._tag = "ai"

        elif lower.startswith("jarvis:"):
            self._tag = "ai"

        elif lower.startswith("file:"):
            self._tag = "file"

        elif "err" in lower:
            self._tag = "err"

        else:
            self._tag = "sys"

        self._tmr.start(6)

    def _step(self):
        if self._pos < len(
            self._text
        ):
            ch = self._text[
                self._pos
            ]

            cursor = self.textCursor()
            fmt = cursor.charFormat()

            color = {
                "you": qcol(C.WHITE),
                "ai": qcol(C.PRI),
                "err": qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys": qcol(C.ACC2),
            }.get(
                self._tag,
                qcol(C.TEXT),
            )

            fmt.setForeground(
                QBrush(color)
            )

            cursor.movePosition(
                cursor.MoveOperation.End
            )

            cursor.insertText(
                ch,
                fmt,
            )

            self.setTextCursor(
                cursor
            )

            self.ensureCursorVisible()

            self._pos += 1

        else:
            self._tmr.stop()

            cursor = self.textCursor()

            cursor.movePosition(
                cursor.MoveOperation.End
            )

            cursor.insertText(
                "\n"
            )

            self.setTextCursor(
                cursor
            )

            self.ensureCursorVisible()

            QTimer.singleShot(
                20,
                self._next,
            )


# ============================================================
# FILE SYSTEM
# ============================================================

_FILE_ICONS = {
    "image": ("🖼", "#00d4ff"),
    "video": ("🎬", "#ff8c32"),
    "audio": ("🎵", "#cc88ff"),
    "pdf": ("📄", "#ff6677"),
    "word": ("📝", "#6699ff"),
    "excel": ("📊", "#55cc88"),
    "code": ("💻", "#ffcc55"),
    "archive": ("📦", "#ff9944"),
    "pptx": ("📊", "#ff7755"),
    "text": ("📃", "#aaaaaa"),
    "data": ("🔧", "#88ddff"),
    "unknown": ("📎", "#888888"),
}


_EXT_TO_CAT = {
    **dict.fromkeys(
        [
            "jpg",
            "jpeg",
            "png",
            "gif",
            "webp",
            "bmp",
            "tiff",
            "svg",
            "ico",
        ],
        "image",
    ),

    **dict.fromkeys(
        [
            "mp4",
            "avi",
            "mov",
            "mkv",
            "wmv",
            "flv",
            "webm",
            "m4v",
        ],
        "video",
    ),

    **dict.fromkeys(
        [
            "mp3",
            "wav",
            "ogg",
            "m4a",
            "aac",
            "flac",
            "wma",
            "opus",
        ],
        "audio",
    ),

    **dict.fromkeys(
        ["pdf"],
        "pdf",
    ),

    **dict.fromkeys(
        [
            "doc",
            "docx",
        ],
        "word",
    ),

    **dict.fromkeys(
        [
            "xls",
            "xlsx",
            "ods",
        ],
        "excel",
    ),

    **dict.fromkeys(
        [
            "ppt",
            "pptx",
        ],
        "pptx",
    ),

    **dict.fromkeys(
        [
            "py",
            "js",
            "ts",
            "jsx",
            "tsx",
            "html",
            "css",
            "java",
            "c",
            "cpp",
            "cs",
            "go",
            "rs",
            "rb",
            "php",
            "swift",
            "kt",
            "sh",
            "sql",
            "lua",
        ],
        "code",
    ),

    **dict.fromkeys(
        [
            "zip",
            "rar",
            "tar",
            "gz",
            "7z",
            "bz2",
            "xz",
        ],
        "archive",
    ),

    **dict.fromkeys(
        [
            "txt",
            "md",
            "rst",
            "log",
        ],
        "text",
    ),

    **dict.fromkeys(
        [
            "csv",
            "tsv",
            "json",
            "xml",
        ],
        "data",
    ),
}


def _file_category(
    path: Path,
) -> str:
    return _EXT_TO_CAT.get(
        path.suffix.lower().lstrip("."),
        "unknown",
    )


def _fmt_size(
    size: int,
) -> str:
    if size < 1024:
        return f"{size} B"

    elif size < 1024**2:
        return f"{size / 1024:.1f} KB"

    elif size < 1024**3:
        return f"{size / 1024**2:.1f} MB"

    else:
        return f"{size / 1024**3:.1f} GB"


# ============================================================
# FILE DROP ZONE
# ============================================================

class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        self.setAcceptDrops(True)

        self.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.setFixedHeight(128)

        self._current_file: str | None = None
        self._hovering = False
        self._drag_over = False
        self._dash_offset = 0.0

        self._anim_tmr = QTimer(self)

        self._anim_tmr.timeout.connect(
            self._animate
        )

        self._anim_tmr.start(40)

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        layout.setSpacing(0)

        self._canvas = _DropCanvas(
            self
        )

        layout.addWidget(
            self._canvas
        )

    def _animate(self):
        self._dash_offset = (
            self._dash_offset
            + 0.8
        ) % 20

        self._canvas.update()

    def dragEnterEvent(
        self,
        event: QDragEnterEvent,
    ):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

            self._drag_over = True

            self._canvas.update()

    def dragLeaveEvent(self, event):
        self._drag_over = False
        self._canvas.update()

    def dropEvent(
        self,
        event: QDropEvent,
    ):
        self._drag_over = False

        urls = event.mimeData().urls()

        if urls:
            path = urls[0].toLocalFile()

            if Path(path).is_file():
                self._set_file(path)

        self._canvas.update()

    def mousePressEvent(self, event):
        if (
            event.button()
            == Qt.MouseButton.LeftButton
        ):
            self._browse()

    def enterEvent(self, event):
        self._hovering = True
        self._canvas.update()

    def leaveEvent(self, event):
        self._hovering = False
        self._canvas.update()

    def current_file(
        self,
    ) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None
        self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a file for JEEV",
            str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )

        if path:
            self._set_file(path)

    def _set_file(
        self,
        path: str,
    ):
        self._current_file = path

        self._canvas.update()

        self.file_selected.emit(path)


# ============================================================
# DROP CANVAS
# ============================================================

class _DropCanvas(QWidget):
    """Floating glass file capsule; intentionally no dashboard-style box."""

    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        r = QRectF(3, 4, W - 6, H - 8)

        # Glass body
        grad = QLinearGradient(0, r.top(), 0, r.bottom())
        if self._z._drag_over:
            grad.setColorAt(0, qcol("#24170a", 105))
            grad.setColorAt(1, qcol("#0a0d14", 105))
            edge = qcol(C.PRI, 235)
        elif self._z._current_file:
            grad.setColorAt(0, qcol("#071d17", 100))
            grad.setColorAt(1, qcol("#080f15", 100))
            edge = qcol(C.GREEN, 190)
        elif self._z._hovering:
            grad.setColorAt(0, qcol("#131b25", 105))
            grad.setColorAt(1, qcol("#080d15", 105))
            edge = qcol(C.PRI, 175)
        else:
            grad.setColorAt(0, qcol("#101721", 88))
            grad.setColorAt(1, qcol("#070b12", 108))
            edge = qcol(C.BORDER_B, 135)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(r, 18, 18)

        # Outer/inner glass contours
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(edge, 1.0))
        p.drawRoundedRect(r, 18, 18)
        p.setPen(QPen(qcol("#ffffff", 25), 1.0))
        p.drawRoundedRect(QRectF(r.x() + 5, r.y() + 5, r.width() - 10, r.height() - 10), 14, 14)

        if self._z._current_file:
            self._paint_file(p, W, H)
        elif self._z._drag_over:
            self._paint_drag_over(p, W, H)
        else:
            self._paint_idle(p, W, H, self._z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        c = qcol(C.PRI if hover else C.PRI_DIM)
        p.setPen(QPen(c, 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 19), QPointF(cx, cy + 2))
        p.drawLine(QPointF(cx - 9, cy - 9), QPointF(cx, cy - 19))
        p.drawLine(QPointF(cx + 9, cy - 9), QPointF(cx, cy - 19))
        p.drawLine(QPointF(cx - 16, cy + 3), QPointF(cx + 16, cy + 3))

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.TEXT if hover else C.PRI_DIM), 1))
        p.drawText(QRectF(0, cy + 10, W, 17), Qt.AlignmentFlag.AlignCenter, "Drop file here or Click to Browse")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol(C.TEXT_DIM, 210), 1))
        p.drawText(QRectF(0, cy + 28, W, 14), Qt.AlignmentFlag.AlignCenter, "Images · Videos · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 25, W, 30), Qt.AlignmentFlag.AlignCenter, "↑")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.drawText(QRectF(0, cy + 8, W, 18), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        category = _file_category(path)
        icon, icon_color = _FILE_ICONS.get(category, _FILE_ICONS["unknown"])
        try:
            size_string = _fmt_size(path.stat().st_size)
        except Exception:
            size_string = "--"
        extension = path.suffix.upper().lstrip(".") or "FILE"

        p.setFont(QFont("Segoe UI Emoji" if _OS == "Windows" else "Arial", 21))
        p.setPen(QPen(qcol(icon_color), 1))
        p.drawText(QRectF(14, 0, 50, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = 70
        tw = W - tx - 46
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 32 else path.name[:29] + "..."
        p.drawText(QRectF(tx, 18, tw, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, 37, tw, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{extension}  ·  {size_string}")

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 190), 1))
        p.drawText(QRectF(W - 38, 0, 25, H), Qt.AlignmentFlag.AlignCenter, "×")

    def mousePressEvent(self, event):
        zone = self._z
        if zone._current_file and event.pos().x() > self.width() - 44:
            zone.clear_file()
        else:
            zone.mousePressEvent(event)


# ============================================================
# SETUP OVERLAY
# ============================================================

class SetupOverlay(QWidget):
    done = pyqtSignal(
        str,
        str,
        str,
    )

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        self.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )

        self.setStyleSheet(
            f"""
            SetupOverlay {{
                background: rgba(2, 3, 6, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 12px;
            }}
            """
        )

        detected = {
            "darwin": "mac",
            "windows": "windows",
        }.get(
            _OS.lower(),
            "linux",
        )

        self._sel_os = detected

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            30,
            22,
            30,
            22,
        )

        layout.setSpacing(8)

        def label(
            text,
            font_size=9,
            bold=False,
            color=C.PRI,
            align=Qt.AlignmentFlag.AlignCenter,
        ):
            widget = QLabel(text)

            widget.setAlignment(
                align
            )

            widget.setFont(
                QFont(
                    "Courier New",
                    font_size,
                    QFont.Weight.Bold
                    if bold
                    else QFont.Weight.Normal,
                )
            )

            widget.setStyleSheet(
                f"color: {color}; background: transparent;"
            )

            return widget

        layout.addWidget(
            label(
                "◈  INITIALISATION REQUIRED",
                13,
                True,
            )
        )

        layout.addWidget(
            label(
                "Configure JEEV before first boot.",
                9,
                color=C.PRI_DIM,
            )
        )

        layout.addSpacing(6)

        separator = QFrame()

        separator.setFrameShape(
            QFrame.Shape.HLine
        )

        separator.setStyleSheet(
            f"color: {C.BORDER};"
        )

        layout.addWidget(
            separator
        )

        layout.addSpacing(4)

        layout.addWidget(
            label(
                "GEMINI API KEY",
                8,
                color=C.TEXT_DIM,
                align=Qt.AlignmentFlag.AlignLeft,
            )
        )

        self._key_input = QLineEdit()

        self._key_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        self._key_input.setPlaceholderText(
            "AIza…"
        )

        self._key_input.setFont(
            QFont(
                "Courier New",
                10,
            )
        )

        self._key_input.setFixedHeight(
            32
        )

        self._key_input.setStyleSheet(
            f"""
            QLineEdit {{
                background: #0d0a08;
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 7px;
                padding: 4px 8px;
            }}

            QLineEdit:focus {{
                border: 1px solid {C.PRI};
            }}
            """
        )

        layout.addWidget(
            self._key_input
        )

        layout.addSpacing(8)

        layout.addWidget(
            label(
                "OPENROUTER API KEY",
                8,
                color=C.TEXT_DIM,
                align=Qt.AlignmentFlag.AlignLeft,
            )
        )

        self._or_input = QLineEdit()

        self._or_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        self._or_input.setPlaceholderText(
            "sk-or-…"
        )

        self._or_input.setFont(
            QFont(
                "Courier New",
                10,
            )
        )

        self._or_input.setFixedHeight(
            32
        )

        self._or_input.setStyleSheet(
            f"""
            QLineEdit {{
                background: #0d0a08;
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 7px;
                padding: 4px 8px;
            }}

            QLineEdit:focus {{
                border: 1px solid {C.ACC2};
            }}
            """
        )

        layout.addWidget(
            self._or_input
        )

        layout.addSpacing(12)

        separator2 = QFrame()

        separator2.setFrameShape(
            QFrame.Shape.HLine
        )

        separator2.setStyleSheet(
            f"color: {C.BORDER};"
        )

        layout.addWidget(
            separator2
        )

        layout.addSpacing(4)

        layout.addWidget(
            label(
                "OPERATING SYSTEM",
                8,
                color=C.TEXT_DIM,
                align=Qt.AlignmentFlag.AlignLeft,
            )
        )

        detected_name = {
            "windows": "Windows",
            "mac": "macOS",
            "linux": "Linux",
        }[detected]

        layout.addWidget(
            label(
                f"Auto-detected: {detected_name}",
                8,
                color=C.ACC2,
                align=Qt.AlignmentFlag.AlignLeft,
            )
        )

        os_row = QHBoxLayout()

        os_row.setSpacing(6)

        self._os_btns: dict[
            str,
            QPushButton,
        ] = {}

        for key, text in [
            (
                "windows",
                "⊞  Windows",
            ),
            (
                "mac",
                "  macOS",
            ),
            (
                "linux",
                "🐧  Linux",
            ),
        ]:
            button = QPushButton(text)

            button.setFont(
                QFont(
                    "Courier New",
                    9,
                    QFont.Weight.Bold,
                )
            )

            button.setFixedHeight(
                32
            )

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            button.clicked.connect(
                lambda _, k=key:
                self._sel(k)
            )

            os_row.addWidget(
                button
            )

            self._os_btns[key] = button

        layout.addLayout(
            os_row
        )

        self._sel(detected)

        layout.addSpacing(12)

        initialise = QPushButton(
            "▸  INITIALISE SYSTEMS"
        )

        initialise.setFont(
            QFont(
                "Courier New",
                10,
                QFont.Weight.Bold,
            )
        )

        initialise.setFixedHeight(
            36
        )

        initialise.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        initialise.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {C.PRI};
                border: 1px solid {C.PRI_DIM};
                border-radius: 7px;
            }}

            QPushButton:hover {{
                background: {C.PRI_GHO};
                border: 1px solid {C.PRI};
            }}
            """
        )

        initialise.clicked.connect(
            self._submit
        )

        layout.addWidget(
            initialise
        )

    def _sel(
        self,
        key: str,
    ):
        self._sel_os = key

        palette = {
            "windows": (
                C.PRI,
                "#140b03",
            ),
            "mac": (
                C.ACC2,
                "#161205",
            ),
            "linux": (
                C.GREEN,
                "#03150d",
            ),
        }

        for current, button in self._os_btns.items():
            if current == key:
                foreground, background = palette[
                    current
                ]

                button.setStyleSheet(
                    f"""
                    QPushButton {{
                        background: {foreground};
                        color: {background};
                        border: none;
                        border-radius: 7px;
                        font-weight: bold;
                    }}
                    """
                )

            else:
                button.setStyleSheet(
                    f"""
                    QPushButton {{
                        background: #0d0a08;
                        color: {C.TEXT_DIM};
                        border: 1px solid {C.BORDER};
                        border-radius: 7px;
                    }}

                    QPushButton:hover {{
                        color: {C.TEXT};
                        border: 1px solid {C.BORDER_B};
                    }}
                    """
                )

    def _submit(self):
        key = self._key_input.text().strip()
        openrouter_key = (
            self._or_input.text().strip()
        )

        if not key:
            self._key_input.setStyleSheet(
                self._key_input.styleSheet()
                + f"""
                QLineEdit {{
                    border: 1px solid {C.RED};
                }}
                """
            )

            return

        if not openrouter_key:
            self._or_input.setStyleSheet(
                self._or_input.styleSheet()
                + f"""
                QLineEdit {{
                    border: 1px solid {C.RED};
                }}
                """
            )

            return

        self.done.emit(
            key,
            openrouter_key,
            self._sel_os,
        )


# ============================================================
# MAIN WINDOW
# ============================================================

class MainWindow(QMainWindow):
    _log_sig = pyqtSignal(str)
    _state_sig = pyqtSignal(str)

    def __init__(
        self,
        face_path: str,
    ):
        super().__init__()

        self.setWindowTitle(
            "JEEV — MARK I"
        )

        self.setMinimumSize(
            _MIN_W,
            _MIN_H,
        )

        self.resize(
            _DEFAULT_W,
            _DEFAULT_H,
        )

        screen = (
            QApplication.primaryScreen()
            .availableGeometry()
        )

        self.move(
            (
                screen.width()
                - _DEFAULT_W
            ) // 2,
            (
                screen.height()
                - _DEFAULT_H
            ) // 2,
        )

        self.on_text_command = None

        self._muted = False

        self._current_file: str | None = None

        central = QWidget()

        central.setStyleSheet(
            f"""
            background: {C.BG};
            """
        )

        self.setCentralWidget(
            central
        )

        root = QVBoxLayout(
            central
        )

        root.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        root.setSpacing(0)

        root.addWidget(self._build_header())

        # ----------------------------------------------------
        # FULL-SPACE HUD + FLOATING UI LAYER
        # ----------------------------------------------------
        # The side controls deliberately overlay the starfield instead
        # of reserving dashboard columns. This is the key visual change.
        self._space = QWidget()
        self._space.setStyleSheet("background: transparent;")
        root.addWidget(self._space, stretch=1)

        self.hud = HudCanvas(face_path, self._space)
        self.hud.setGeometry(self._space.rect())

        self._left_panel = self._build_left_panel()
        self._left_panel.setParent(self._space)

        self._right_panel = self._build_right_panel()
        self._right_panel.setParent(self._space)

        self._float_phase = 0.0
        self._float_tmr = QTimer(self)
        self._float_tmr.timeout.connect(self._animate_floating_ui)
        self._float_tmr.start(35)

        root.addWidget(self._build_footer())

        self._position_floating_ui()

        self._clock_tmr = QTimer(
            self
        )

        self._clock_tmr.timeout.connect(
            self._tick_clock
        )

        self._clock_tmr.start(1000)

        self._tick_clock()

        self._metric_tmr = QTimer(
            self
        )

        self._metric_tmr.timeout.connect(
            self._update_metrics
        )

        self._metric_tmr.start(2000)

        self._update_metrics()

        self._log_sig.connect(
            self._log.append_log
        )

        self._state_sig.connect(
            self._apply_state
        )

        self._overlay: SetupOverlay | None = None

        self._ready = (
            self._check_config()
        )

        if not self._ready:
            self._show_setup()

        mute_shortcut = QShortcut(
            QKeySequence("F4"),
            self,
        )

        mute_shortcut.activated.connect(
            self._toggle_mute
        )

        fullscreen_shortcut = QShortcut(
            QKeySequence("F11"),
            self,
        )

        fullscreen_shortcut.activated.connect(
            self._toggle_fullscreen
        )

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_floating_ui()

        if getattr(self, "_overlay", None) and self._overlay.isVisible():
            overlay_width = 460
            overlay_height = 430
            central = self.centralWidget()
            self._overlay.setGeometry(
                (central.width() - overlay_width) // 2,
                (central.height() - overlay_height) // 2,
                overlay_width,
                overlay_height,
            )

    def _position_floating_ui(self):
        if not hasattr(self, "_space"):
            return
        r = self._space.rect()
        if r.width() <= 0 or r.height() <= 0:
            return
        self.hud.setGeometry(r)

        phase = getattr(self, "_float_phase", 0.0)
        # Scale the floating widgets so the same composition survives window
        # resizing while remaining close to the supplied 1614x974 reference.
        if r.width() >= 1250:
            self._left_panel.setFixedWidth(280)
            self._right_panel.setFixedWidth(420)
        elif r.width() >= 1050:
            self._left_panel.setFixedWidth(245)
            self._right_panel.setFixedWidth(380)
        else:
            self._left_panel.setFixedWidth(205)
            self._right_panel.setFixedWidth(330)

        left_y = 25 + int(math.sin(phase * 0.85) * 2)
        right_y = 55 + int(math.sin(phase * 0.72 + 1.8) * 3)
        # Keep both floating panels inside the HUD bounds.
        left_x = max(10, min(40, r.width() - self._left_panel.width() - 10))
        left_x += int(math.sin(phase * 0.55) * 2)
        right_x = max(10, r.width() - self._right_panel.width() - 18)
        right_x += int(math.sin(phase * 0.62 + 0.8) * 2)
        right_x = min(right_x, max(10, r.width() - self._right_panel.width() - 10))

        self._left_panel.move(left_x, left_y)
        self._right_panel.move(right_x, right_y)
        self._left_panel.raise_()
        self._right_panel.raise_()

    def _animate_floating_ui(self):
        self._float_phase += 0.035
        self._position_floating_ui()

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    def _update_metrics(self):
        snapshot = _metrics.snapshot()

        cpu = snapshot["cpu"]

        self._bar_cpu.set_value(
            cpu,
            f"{cpu:.0f}%",
        )

        memory = snapshot["mem"]

        self._bar_mem.set_value(
            memory,
            f"{memory:.0f}%",
        )

        network = snapshot["net"]

        if network < 1.0:
            network_text = (
                f"{network * 1024:.0f}KB/s"
            )
        else:
            network_text = (
                f"{network:.1f}MB/s"
            )

        network_pct = min(
            100,
            network * 10,
        )

        self._bar_net.set_value(
            network_pct,
            network_text,
        )

        gpu = snapshot["gpu"]

        if gpu >= 0:
            self._bar_gpu.set_value(
                gpu,
                f"{gpu:.0f}%",
            )
        else:
            self._bar_gpu.set_value(
                0,
                "N/A",
            )

        temperature = snapshot["tmp"]

        if temperature >= 0:
            temperature_pct = min(
                100,
                temperature,
            )

            self._bar_tmp.set_value(
                temperature_pct,
                f"{temperature:.0f}°C",
            )

        else:
            self._bar_tmp.set_value(
                0,
                "N/A",
            )

        try:
            boot_time = psutil.boot_time()

            elapsed = (
                time.time()
                - boot_time
            )

            hours = int(
                elapsed // 3600
            )

            minutes = int(
                (
                    elapsed
                    % 3600
                )
                // 60
            )

            self._uptime_lbl.setText(
                f"UP  {hours:02d}:{minutes:02d}"
            )

        except Exception:
            self._uptime_lbl.setText(
                "UP  --:--"
            )

        try:
            process_count = len(
                psutil.pids()
            )

            self._proc_lbl.setText(
                f"PROC  {process_count}"
            )

        except Exception:
            self._proc_lbl.setText(
                "PROC  --"
            )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    def _build_header(
        self,
    ) -> QWidget:
        widget = QWidget()

        widget.setFixedHeight(58)

        widget.setStyleSheet(
            f"""
            background: transparent;
            border: none;
            """
        )

        layout = QHBoxLayout(widget)

        layout.setContentsMargins(
            16,
            0,
            16,
            0,
        )

        def badge(
            text,
            color=C.TEXT_MED,
        ):
            label = QLabel(text)

            label.setFont(
                QFont(
                    "Courier New",
                    8,
                )
            )

            label.setStyleSheet(
                f"""
                color: {color};
                background: transparent;
                """
            )

            return label

        layout.addWidget(
            badge(
                "",
                C.PRI_DIM,
            )
        )

        layout.addStretch()

        middle = QVBoxLayout()

        middle.setSpacing(1)

        title = QLabel(
            "JEEV"
        )

        title.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        title.setFont(
            QFont(
                _JEEV_FONT_FAMILY,
                28,
                QFont.Weight.Normal,
            )
        )

        title.setStyleSheet(
            f"""
            color: {C.PRI};
            background: transparent;
            """
        )

        middle.addWidget(
            title
        )

        subtitle = QLabel(
            "Just a rather very intelligent system"
        )

        subtitle.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        subtitle.setFont(
            QFont(
                "Courier New",
                7,
            )
        )

        subtitle.setStyleSheet(
            f"""
            color: {C.PRI_DIM};
            background: transparent;
            """
        )

        middle.addWidget(
            subtitle
        )

        layout.addLayout(
            middle
        )

        layout.addStretch()

        right = QVBoxLayout()

        right.setSpacing(2)

        self._clock_lbl = QLabel(
            "00:00:00"
        )

        self._clock_lbl.setFont(
            QFont(
                "Georgia",
                20,
                QFont.Weight.Bold,
            )
        )

        self._clock_lbl.setStyleSheet(
            f"""
            color: {C.PRI};
            background: transparent;
            """
        )

        self._clock_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        right.addWidget(
            self._clock_lbl
        )

        self._date_lbl = QLabel("")

        self._date_lbl.setFont(
            QFont(
                "Courier New",
                7,
            )
        )

        self._date_lbl.setStyleSheet(
            f"""
            color: {C.TEXT_DIM};
            background: transparent;
            """
        )

        self._date_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )

        right.addWidget(
            self._date_lbl
        )

        layout.addLayout(
            right
        )

        return widget

    def _tick_clock(self):
        self._clock_lbl.setText(
            time.strftime("%H:%M:%S")
        )

        self._date_lbl.setText(
            time.strftime(
                "%a %d %b %Y"
            )
        )

    # --------------------------------------------------------
    # FLOATING GLASS HELPERS
    # --------------------------------------------------------

    def _glass_effect(self, widget, blur=28, alpha=115):
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(blur)
        effect.setOffset(0, 5)
        effect.setColor(qcol("#000000", int(alpha * 0.72)))
        widget.setGraphicsEffect(effect)
        return widget

    def _glass_style(self, accent=None, radius=22):
        accent = accent or C.BORDER_B
        # Deliberately translucent: the starfield remains visible through the
        # panels, matching the liquid-glass reference instead of opaque cards.
        return f"""
            QWidget {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 rgba(20, 31, 44, 92),
                    stop: 0.48 rgba(7, 14, 24, 72),
                    stop: 1 rgba(3, 8, 15, 112)
                );
                border: 1px solid rgba(150, 181, 208, 82);
                border-radius: {radius}px;
            }}
        """

    # --------------------------------------------------------
    # LEFT FLOATING WIDGETS
    # --------------------------------------------------------

    def _build_left_panel(self) -> QWidget:
        widget = QWidget()
        widget.setFixedWidth(_LEFT_W)
        widget.setMinimumHeight(0)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Main SYS MONITOR glass widget.
        # Compact enough to remain fully visible at the minimum window size.
        metrics_card = QWidget()
        metrics_card.setFixedHeight(238)
        metrics_card.setStyleSheet(self._glass_style())
        self._glass_effect(metrics_card, 32, 145)
        mlay = QVBoxLayout(metrics_card)
        mlay.setContentsMargins(8, 8, 8, 6)
        mlay.setSpacing(0)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 2)
        header = QLabel("✦SYS MONITOR")
        header.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        header_row.addWidget(header)
        header_row.addStretch()
        dots = QLabel("⋮")
        dots.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        dots.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        header_row.addWidget(dots)
        mlay.addLayout(header_row)

        self._bar_cpu = MetricBar("CPU", C.PRI, metrics_card)
        self._bar_mem = MetricBar("RAM", C.RED, metrics_card)
        self._bar_net = MetricBar("NET", C.GREEN, metrics_card)
        self._bar_gpu = MetricBar("GPU", C.ACC, metrics_card)
        self._bar_tmp = MetricBar("TEMP", "#ff6688", metrics_card)
        for bar in [self._bar_cpu, self._bar_mem, self._bar_net, self._bar_gpu, self._bar_tmp]:
            mlay.addWidget(bar)

        layout.addWidget(metrics_card)

        # Compact uptime/process glass widget.
        info_panel = QWidget()
        info_panel.setFixedHeight(72)
        info_panel.setStyleSheet(self._glass_style())
        self._glass_effect(info_panel, 26, 125)
        info_layout = QVBoxLayout(info_panel)
        info_layout.setContentsMargins(10, 6, 10, 5)
        info_layout.setSpacing(0)

        self._uptime_lbl = QLabel("◷  --:--")
        self._uptime_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._uptime_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent; border: none;")
        info_layout.addWidget(self._uptime_lbl)

        self._proc_lbl = QLabel("PROC  --")
        self._proc_lbl.setFont(QFont("Courier New", 8))
        self._proc_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        info_layout.addWidget(self._proc_lbl)

        os_name = {"Windows": "WIN", "Darwin": "macOS", "Linux": "LINUX"}.get(_OS, _OS.upper())
        os_label = QLabel(f"OS  {os_name}")
        os_label.setFont(QFont("Courier New", 8))
        os_label.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        info_layout.addWidget(os_label)
        layout.addWidget(info_panel)

        # Three individual mini-widgets, matching the reference composition.
        status_specs = [("AI CORE", "ACTIVE", C.GREEN), ("SEC", "CLEARANCE", C.ACC), ("PROTOCOL", "NORMAL", "#76a9ff")]
        for title, value, color in status_specs:
            card = QWidget()
            card.setFixedHeight(52)
            card.setStyleSheet(self._glass_style())
            self._glass_effect(card, 22, 115)
            row = QHBoxLayout(card)
            row.setContentsMargins(9, 4, 7, 4)
            text = QLabel(f"{title}\n{value}")
            text.setFont(QFont("Courier New", 6, QFont.Weight.Bold))
            text.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            row.addWidget(text)
            row.addStretch()
            dot = QLabel("●" if title == "AI CORE" else "›")
            dot.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
            dot.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            row.addWidget(dot)
            layout.addWidget(card)

        layout.addStretch()
        return widget

    # --------------------------------------------------------
    # RIGHT FLOATING HUD
    # --------------------------------------------------------

    def _build_right_panel(self) -> QWidget:
        widget = QWidget()
        widget.setFixedWidth(_RIGHT_W)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        widget.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Activity log: the log itself owns the SYS/JEEV messages.
        # Do not add a second static "SYS: JEEV online." header here.
        section = QLabel("ACTIVITY LOG")
        section.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        section.setStyleSheet(f"color: {C.ACC2}; background: transparent; border: none;")
        layout.addWidget(section)

        self._log = LogWidget(widget)
        self._log.setMinimumHeight(235)
        self._log.setMaximumHeight(265)
        layout.addWidget(self._log)

        layout.addStretch(1)

        # File upload is a single floating glass capsule.
        self._drop_zone = FileDropZone(widget)
        self._drop_zone.file_selected.connect(self._on_file_selected)
        self._glass_effect(self._drop_zone, 30, 145)
        layout.addWidget(self._drop_zone)

        self._file_hint = QLabel("No file loaded — drop or click above to upload")
        self._file_hint.setFont(QFont("Courier New", 6))
        self._file_hint.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none;")
        self._file_hint.setWordWrap(True)
        self._file_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._file_hint)

        # Command capsule.
        command_card = QWidget()
        command_card.setFixedHeight(214)
        command_card.setStyleSheet(self._glass_style())
        self._glass_effect(command_card, 30, 145)
        cl = QVBoxLayout(command_card)
        cl.setContentsMargins(10, 10, 10, 9)
        cl.setSpacing(8)
        cl.addLayout(self._build_input_row())

        self._mute_btn = QPushButton("♟  MICROPHONE ACTIVE")
        self._mute_btn.setFixedHeight(58)
        self._mute_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        cl.addWidget(self._mute_btn)

        fullscreen = QLabel("⌗  FULLSCREEN   |   [F11]")
        fullscreen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fullscreen.setFont(QFont("Courier New", 7))
        fullscreen.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        cl.addWidget(fullscreen)

        # Keep click-to-fullscreen behavior without reintroducing a button box.
        fullscreen.mousePressEvent = lambda e: self._toggle_fullscreen()
        layout.addWidget(command_card)

        layout.addSpacing(6)
        return widget

    # --------------------------------------------------------
    # INPUT
    # --------------------------------------------------------

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(7)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or question...")
        self._input.setFont(QFont("Courier New", 8))
        self._input.setFixedHeight(44)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(4, 9, 16, 210);
                color: {C.WHITE};
                border: 1px solid rgba(116, 135, 160, 115);
                border-radius: 11px;
                padding: 3px 10px;
            }}
            QLineEdit:focus {{
                border: 1px solid rgba(255,157,50,190);
                background: rgba(7, 12, 20, 225);
            }}
        """)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input, stretch=1)

        send = QPushButton("›")
        send.setFixedSize(44, 44)
        send.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.setStyleSheet(f"""
            QPushButton {{
                background: rgba(25, 15, 7, 215);
                color: {C.PRI};
                border: 1px solid rgba(255,157,50,120);
                border-radius: 11px;
            }}
            QPushButton:hover {{
                background: rgba(255,157,50,35);
                border: 1px solid {C.PRI};
            }}
        """)
        send.clicked.connect(self._send)
        row.addWidget(send)
        return row

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    def _build_footer(self) -> QWidget:
        widget = QWidget()
        widget.setFixedHeight(30)
        widget.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(18, 0, 18, 4)

        def footer_label(text, color=C.TEXT_DIM):
            label = QLabel(text)
            label.setFont(QFont("Courier New", 6))
            label.setStyleSheet(f"color: {color}; background: transparent; border: none;")
            return label

        layout.addWidget(footer_label("F4 MUTE  ·  F11 FULLSCREEN"))
        layout.addStretch()
        layout.addWidget(footer_label("SANJAY ADHITYAN  ·  JEEV MARK I  ·  CLASSIFIED", C.PRI_DIM))
        layout.addStretch()
        layout.addWidget(footer_label("© SANJAY ADHITYAN™", C.PRI_DIM))
        return widget

    # --------------------------------------------------------
    # FILE SELECTED
    # --------------------------------------------------------

    def _on_file_selected(
        self,
        path: str,
    ):
        self._current_file = path

        file_path = Path(path)

        category = _file_category(
            file_path
        )

        icon, _ = _FILE_ICONS.get(
            category,
            _FILE_ICONS["unknown"],
        )

        try:
            size = _fmt_size(
                file_path.stat().st_size
            )
        except Exception:
            size = "--"

        self._file_hint.setText(
            f"{icon}  {file_path.name}  ·  {size}  ·  "
            "Tell JEEV what to do with it"
        )

        self._log.append_log(
            f"FILE: {file_path.name} ({size}) loaded"
        )

        if self.on_text_command:
            message = (
                f"[FILE_UPLOADED] "
                f"path={path} | "
                f"name={file_path.name} | "
                f"type={file_path.suffix.lstrip('.')} | "
                f"size={size} | "
                f"Briefly tell the user you can see "
                f"the file '{file_path.name}' ({size}) "
                f"has been uploaded and ask what "
                f"they'd like to do with it."
            )

            threading.Thread(
                target=self.on_text_command,
                args=(message,),
                daemon=True,
            ).start()

    # --------------------------------------------------------
    # MUTE
    # --------------------------------------------------------

    def _toggle_mute(self):
        self._muted = not self._muted

        self.hud.muted = self._muted

        self._style_mute_btn()

        if self._muted:
            self._apply_state(
                "MUTED"
            )

            self._log.append_log(
                "SYS: Microphone muted."
            )

        else:
            self._apply_state(
                "LISTENING"
            )

            self._log.append_log(
                "SYS: Microphone active."
            )

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇  MICROPHONE MUTED")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(38, 4, 12, 210);
                    color: {C.RED};
                    border: 1px solid rgba(255,73,102,185);
                    border-radius: 12px;
                    padding: 0 10px;
                }}
            """)
        else:
            self._mute_btn.setText("♟  MICROPHONE ACTIVE")
            self._mute_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(2, 28, 20, 210);
                    color: {C.GREEN};
                    border: 1px solid rgba(57,255,154,180);
                    border-radius: 12px;
                    padding: 0 10px;
                }}
                QPushButton:hover {{
                    background: rgba(57,255,154,25);
                    border: 1px solid {C.GREEN};
                }}
            """)

    # --------------------------------------------------------
    # SEND
    # --------------------------------------------------------

    def _send(self):
        text = self._input.text().strip()

        if not text:
            return

        self._input.clear()

        self._log.append_log(
            f"You: {text}"
        )

        if self.on_text_command:
            threading.Thread(
                target=self.on_text_command,
                args=(text,),
                daemon=True,
            ).start()

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    def _apply_state(
        self,
        state: str,
    ):
        self.hud.state = state

        self.hud.speaking = (
            state == "SPEAKING"
        )

    # --------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------

    def _check_config(
        self,
    ) -> bool:
        if not API_FILE.exists():
            return False

        try:
            data = json.loads(
                API_FILE.read_text(
                    encoding="utf-8"
                )
            )

            return (
                bool(
                    data.get(
                        "gemini_api_key"
                    )
                )
                and bool(
                    data.get(
                        "openrouter_api_key"
                    )
                )
                and bool(
                    data.get(
                        "os_system"
                    )
                )
            )

        except Exception:
            return False

    def _show_setup(self):
        overlay = SetupOverlay(
            self.centralWidget()
        )

        central = self.centralWidget()

        overlay_width = 460
        overlay_height = 430

        overlay.setGeometry(
            (
                central.width()
                - overlay_width
            ) // 2,
            (
                central.height()
                - overlay_height
            ) // 2,
            overlay_width,
            overlay_height,
        )

        overlay.done.connect(
            self._on_setup_done
        )

        overlay.show()

        self._overlay = overlay

    def _on_setup_done(
        self,
        key: str,
        openrouter_key: str,
        os_name: str,
    ):
        os.makedirs(
            CONFIG_DIR,
            exist_ok=True,
        )

        API_FILE.write_text(
            json.dumps(
                {
                    "gemini_api_key": key,
                    "openrouter_api_key": openrouter_key,
                    "os_system": os_name,
                },
                indent=4,
            ),
            encoding="utf-8",
        )

        self._ready = True

        if self._overlay:
            self._overlay.hide()
            self._overlay = None

        self._apply_state(
            "LISTENING"
        )

        self._log.append_log(
            f"SYS: Initialised. "
            f"OS={os_name.upper()}."
        )


# ============================================================
# ROOT SHIM
# ============================================================

class _RootShim:
    def __init__(
        self,
        app: QApplication,
    ):
        self._app = app

    def mainloop(self):
        self._app.exec()

    def protocol(
        self,
        *_,
        **__,
    ):
        pass


# ============================================================
# PUBLIC JEEV UI
# ============================================================

class JarvisUI:
    def __init__(
        self,
        face_path: str,
        size=None,
    ):
        self._app = (
            QApplication.instance()
            or QApplication(sys.argv)
        )

        self._app.setStyle(
            "Fusion"
        )

        # Load the bundled Zaslia identity font AFTER QApplication exists.
        # QFontDatabase can then register the OTF for this application.
        global _JEEV_FONT_FAMILY
        loaded_family = _load_jeev_font()
        if loaded_family:
            _JEEV_FONT_FAMILY = loaded_family

        self._win = MainWindow(
            face_path
        )

        self._win.show()

        self.root = _RootShim(
            self._app
        )

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(
        self,
        value: bool,
    ):
        if value != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(
        self,
    ) -> str | None:
        return self._win._drop_zone.current_file()

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(
        self,
        callback,
    ):
        self._win.on_text_command = callback

    def set_state(
        self,
        state: str,
    ):
        self._win._state_sig.emit(
            state
        )

    def write_log(
        self,
        text: str,
    ):
        self._win._log_sig.emit(
            text
        )

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def start_speaking(self):
        self.set_state(
            "SPEAKING"
        )

    def stop_speaking(self):
        if not self.muted:
            self.set_state(
                "LISTENING"
            )