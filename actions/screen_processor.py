import os
import subprocess
from pathlib import Path


def screen_process(
    parameters=None,
    response=None,
    player=None,
    session_memory=None
):
    parameters = parameters or {}

    angle = str(parameters.get("angle", "screen")).lower()
    text = str(parameters.get("text", "")).strip()

    try:
        if angle == "camera":
            return "Camera vision processing is not configured yet."

        # Use Windows Snipping Tool to capture the screen.
        screenshot_dir = Path.home() / "Pictures" / "JARVIS"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        screenshot_path = (
            screenshot_dir / "jarvis_screen.png"
        )

        # Windows Snipping Tool capture
        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "Add-Type -AssemblyName System.Drawing; "
                    "$screen = "
                    "[System.Windows.Forms.Screen]::PrimaryScreen; "
                    "$bitmap = New-Object "
                    "System.Drawing.Bitmap($screen.Bounds.Width,"
                    "$screen.Bounds.Height); "
                    "$graphics = "
                    "[System.Drawing.Graphics]::FromImage($bitmap); "
                    "$graphics.CopyFromScreen("
                    "$screen.Bounds.Location, "
                    "[System.Drawing.Point]::Empty, "
                    "$screen.Bounds.Size); "
                    f"$bitmap.Save('{screenshot_path}', "
                    "[System.Drawing.Imaging.ImageFormat]::Png); "
                    "$graphics.Dispose(); "
                    "$bitmap.Dispose();"
                ),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return (
            f"Screen captured successfully at: {screenshot_path}. "
            f"User requested: {text or 'screen analysis'}."
        )

    except Exception as e:
        return f"Screen processing failed: {e}"