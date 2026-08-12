
import time
import subprocess
import os
import pyautogui

try:
    import pyperclip
except ImportError:
    pyperclip = None


def computer_control(parameters=None, player=None):
    parameters = parameters or {}

    action = str(parameters.get("action", "")).strip().lower()
    text = str(parameters.get("text", ""))
    keys = str(parameters.get("keys", ""))
    key = str(parameters.get("key", ""))
    direction = str(parameters.get("direction", "down")).lower()
    amount = parameters.get("amount", 3)
    seconds = parameters.get("seconds", 1)
    x = parameters.get("x")
    y = parameters.get("y")
    title = str(parameters.get("title", ""))
    description = str(parameters.get("description", ""))
    path = str(parameters.get("path", ""))
    contact = str(parameters.get("contact", "")).strip()
    message = str(parameters.get("message", ""))
    value = str(parameters.get("value", ""))

    try:
        if action in ("type", "smart_type"):
            _type_text(text)
            return "Text typed."

        elif action == "click":
            if x is None or y is None:
                return "X and Y coordinates are required."
            pyautogui.click(int(x), int(y))
            return f"Clicked at {x}, {y}."

        elif action == "double_click":
            if x is None or y is None:
                return "X and Y coordinates are required."
            pyautogui.doubleClick(int(x), int(y))
            return f"Double-clicked at {x}, {y}."

        elif action == "right_click":
            if x is None or y is None:
                return "X and Y coordinates are required."
            pyautogui.rightClick(int(x), int(y))
            return f"Right-clicked at {x}, {y}."

        elif action == "move":
            if x is None or y is None:
                return "X and Y coordinates are required."
            pyautogui.moveTo(int(x), int(y), duration=0.2)
            return f"Mouse moved to {x}, {y}."

        elif action == "hotkey":
            if not keys:
                return "No key combination was provided."
            key_list = [k.strip().lower() for k in keys.split("+") if k.strip()]
            pyautogui.hotkey(*key_list)
            return f"Hotkey {keys} executed."

        elif action == "press":
            if not key:
                return "No key was provided."
            pyautogui.press(key)
            return f"Pressed {key}."

        elif action == "copy":
            pyautogui.hotkey("ctrl", "c")
            return "Copied."

        elif action == "paste":
            pyautogui.hotkey("ctrl", "v")
            return "Pasted."

        elif action == "clear_field":
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")
            return "Field cleared."

        elif action == "scroll":
            scroll_amount = int(amount)
            if direction == "up":
                scroll_amount = abs(scroll_amount)
            elif direction == "down":
                scroll_amount = -abs(scroll_amount)
            pyautogui.scroll(scroll_amount)
            return f"Scrolled {direction}."

        elif action == "wait":
            time.sleep(float(seconds))
            return f"Waited {seconds} seconds."

        elif action == "focus_window":
            return _focus_window(title)

        elif action == "screenshot":
            screenshot = pyautogui.screenshot()
            if path:
                screenshot.save(path)
                return f"Screenshot saved to {path}."
            return "Screenshot captured."

        elif action == "open_app":
            if not text:
                return "Application name/path is required."
            return _open_application(text)

        # ================= WHATSAPP =================

        elif action == "whatsapp_open":
            return _open_whatsapp()

        elif action == "whatsapp_search":
            if not contact:
                return "WhatsApp contact name or phone number is required."
            opened = _open_whatsapp()
            if "could not" in opened.lower() or "failed" in opened.lower():
                return opened
            time.sleep(1)
            return _whatsapp_search_contact(contact)

        elif action == "whatsapp_type":
            if not message:
                return "Message text is required."
            result = _whatsapp_type_message(message)
            return result or "WhatsApp message typed."

        elif action == "whatsapp_send":
            return _whatsapp_send_message(contact, message)

        elif action == "whatsapp_reply":
            return _whatsapp_send_message("", message)

        # ================= FORMS =================

        elif action == "form_fill":
            if not value:
                return "A value is required."
            _fill_current_field(value)
            return f"Form field filled with: {value}"

        elif action == "form_clear":
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")
            return "Current form field cleared."

        elif action == "form_next":
            pyautogui.press("tab")
            return "Moved to the next form field."

        elif action == "form_previous":
            pyautogui.hotkey("shift", "tab")
            return "Moved to the previous form field."

        elif action == "form_fill_sequence":
            values = parameters.get("values", [])
            if not isinstance(values, list):
                return "Form values must be a list."
            return _fill_form_sequence(values)

        elif action == "form_checkbox":
            pyautogui.press("space")
            return "Form checkbox toggled."

        elif action == "form_dropdown":
            option = str(parameters.get("option", ""))
            if not option:
                return "Dropdown option is required."
            return _select_dropdown(option)

        elif action == "form_upload":
            if not path:
                return "File path is required."
            return _upload_file(path)

        elif action == "form_submit":
            pyautogui.press("enter")
            return "Form submission was requested. Verify the result on screen."

        elif action in ("screen_find", "screen_click"):
            return (
                f"{action} requested for: {description or 'unknown element'}. "
                "Visual element detection is not configured yet."
            )

        elif action == "random_data":
            return "Random data generation requested."

        elif action == "user_data":
            return "User data retrieval requested."

        return f"Unknown computer control action: {action}"

    except Exception as e:
        return f"Computer control failed: {e}"


def _type_text(text):
    if not text:
        return

    if pyperclip is not None:
        try:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            return
        except Exception:
            pass

    pyautogui.write(text, interval=0.02)


def _focus_window(title):
    if not title:
        return "No window title was provided."

    safe_title = title.replace("'", "''")

    ps = f"""
    $shell = New-Object -ComObject WScript.Shell
    $processes = Get-Process |
        Where-Object {{
            $_.MainWindowTitle -and
            $_.MainWindowTitle -like "*{safe_title}*"
        }}

    if ($processes) {{
        $window = $processes | Select-Object -First 1
        $shell.AppActivate($window.Id)
        Write-Output "SUCCESS"
    }}
    else {{
        Write-Output "NOT_FOUND"
    }}
    """

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps],
            capture_output=True,
            text=True,
            timeout=10
        )

        if "SUCCESS" in (result.stdout or ""):
            return f"Focused window: {title}"

        return f"Could not find window: {title}"

    except Exception as e:
        return f"Window focus failed: {e}"


def _open_application(application):
    application = application.strip()

    if not application:
        return "Application name is empty."

    try:
        subprocess.Popen(application, shell=True)
        time.sleep(2)
        return f"Attempted to open {application}."
    except Exception as e:
        return f"Could not open {application}: {e}"


def _open_whatsapp():
    # 1. Use existing WhatsApp window if available.
    try:
        existing = _focus_window("WhatsApp")
        if "Focused window" in existing:
            return "WhatsApp is already open."
    except Exception:
        pass

    # 2. Find the registered Windows Start App.
    try:
        ps_script = r"""
        $apps = Get-StartApps |
            Where-Object {
                $_.Name -like "*WhatsApp*"
            }

        if ($apps) {
            $apps |
                Select-Object -First 1 |
                ForEach-Object {
                    Write-Output ($_.AppID + "|" + $_.Name)
                }
        }
        """

        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10
        )

        app_line = (result.stdout or "").strip()

        if app_line:
            app_id = app_line.split("|", 1)[0].strip()

            print(f"[JEEV] WhatsApp Start AppID: {app_id}")

            launch_script = f"""
            Start-Process "shell:AppsFolder\\{app_id}"
            """

            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-Command", launch_script]
            )

            for _ in range(16):
                time.sleep(0.5)
                if "Focused window" in _focus_window("WhatsApp"):
                    return "WhatsApp opened successfully."

    except Exception as e:
        print(f"[JEEV] Start App WhatsApp launch failed: {e}")

    # 3. Try common desktop installation paths.
    possible_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\WhatsApp\WhatsApp.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\WhatsApp\Update.exe"),
        os.path.expandvars(r"%PROGRAMFILES%\WhatsApp\WhatsApp.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\WhatsApp\WhatsApp.exe"),
    ]

    for whatsapp_path in possible_paths:
        try:
            if os.path.isfile(whatsapp_path):
                print(f"[JEEV] Launching WhatsApp: {whatsapp_path}")
                subprocess.Popen([whatsapp_path])

                for _ in range(16):
                    time.sleep(0.5)
                    if "Focused window" in _focus_window("WhatsApp"):
                        return "WhatsApp opened successfully."

        except Exception as e:
            print(f"[JEEV] Executable launch failed: {e}")

    # 4. Start Menu fallback.
    try:
        print("[JEEV] Using Windows Start Menu fallback...")

        pyautogui.press("win")
        time.sleep(1)

        _type_text("WhatsApp")
        time.sleep(2)

        pyautogui.press("enter")

        for _ in range(16):
            time.sleep(0.5)
            if "Focused window" in _focus_window("WhatsApp"):
                return "WhatsApp opened successfully."

        return (
            "Windows attempted to open WhatsApp, "
            "but Jeev could not verify the WhatsApp window."
        )

    except Exception as e:
        return f"Could not open WhatsApp: {e}"


def _whatsapp_search_contact(contact):
    if not contact:
        return "Contact name is required."

    focused = _focus_window("WhatsApp")

    if "Could not find" in focused:
        return "WhatsApp is not currently focused."

    time.sleep(0.5)

    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.5)

    pyautogui.hotkey("ctrl", "a")
    _type_text(contact)

    time.sleep(1.5)
    pyautogui.press("enter")
    time.sleep(1)

    return f"Searched WhatsApp for {contact}."


def _whatsapp_type_message(message):
    focused = _focus_window("WhatsApp")

    if "Could not find" in focused:
        return "WhatsApp is not open."

    time.sleep(0.3)
    _type_text(message)
    return None


def _whatsapp_send_message(contact, message):
    if not message:
        return "Message text is required."

    opened = _open_whatsapp()

    if "could not" in opened.lower() or "failed" in opened.lower():
        return opened

    time.sleep(1)

    if contact:
        search_result = _whatsapp_search_contact(contact)

        if "Could not" in search_result:
            return search_result

        time.sleep(1)

    type_result = _whatsapp_type_message(message)

    if type_result:
        return type_result

    time.sleep(0.3)
    pyautogui.press("enter")

    return "WhatsApp message sent" + (
        f" to {contact}." if contact else "."
    )


def _fill_current_field(value):
    pyautogui.hotkey("ctrl", "a")
    pyautogui.press("backspace")
    _type_text(value)


def _fill_form_sequence(values):
    if not values:
        return "No form values were supplied."

    filled = 0

    for value in values:
        if value is None:
            value = ""

        _fill_current_field(str(value))
        filled += 1

        pyautogui.press("tab")
        time.sleep(0.25)

    return f"Filled {filled} form fields."


def _select_dropdown(option):
    pyautogui.press("space")
    time.sleep(0.3)
    _type_text(option)
    time.sleep(0.3)
    pyautogui.press("enter")
    return f"Selected dropdown option: {option}"


def _upload_file(path):
    if not os.path.exists(path):
        return f"File does not exist: {path}"

    _type_text(path)
    time.sleep(0.5)
    pyautogui.press("enter")

    return f"Uploaded file: {path}"
