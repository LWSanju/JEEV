import subprocess
from datetime import datetime


def reminder(parameters=None, response=None, player=None):
    parameters = parameters or {}

    date = str(parameters.get("date", "")).strip()
    time = str(parameters.get("time", "")).strip()
    message = str(parameters.get("message", "")).strip()

    if not date or not time or not message:
        return "Date, time, and reminder message are required."

    try:
        reminder_time = datetime.strptime(
            f"{date} {time}",
            "%Y-%m-%d %H:%M"
        )

        if reminder_time <= datetime.now():
            return "That reminder time has already passed."

        task_name = "JARVIS_Reminder_" + datetime.now().strftime("%Y%m%d%H%M%S")

        # Windows Task Scheduler command
        command = [
            "schtasks",
            "/Create",
            "/TN", task_name,
            "/TR", f'msg * "{message}"',
            "/SC", "ONCE",
            "/ST", reminder_time.strftime("%H:%M"),
            "/SD", reminder_time.strftime("%m/%d/%Y"),
            "/F",
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return f"Could not create reminder: {result.stderr.strip()}"

        return (
            f"Reminder set for {reminder_time.strftime('%d %B %Y at %I:%M %p')}: "
            f"{message}"
        )

    except ValueError:
        return "Invalid date or time. Use YYYY-MM-DD and HH:MM."

    except Exception as e:
        return f"Reminder failed: {e}"