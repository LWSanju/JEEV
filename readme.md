JEEV
### The Ultimate Cross-Platform Personal AI Assistant — By Sanju

A real-time voice AI that can hear, see, understand, and control your computer — on any OS. Supporting Windows, macOS, and Linux. Local execution. Zero subscriptions. Engineered for total autonomy.

---

## ✨ Overview

MARK I-OR represents the pinnacle of the JEEV series, evolving into a more flexible and robust system. It bridges the gap between the operating system and human intent. Through natural dialogue, Mark I analyzes your screen, processes uploaded documents, and executes complex workflows with a brand-new, adaptive interface.

It's not just an assistant — it's an extension of your digital life.

---

## 🚀 Capabilities

### Core Features
| Feature | Description |
|---|---|
| 🎙️ Real-time Voice | Ultra-low latency conversation in any language |
| 🖥️ System Control | Launch apps, manage files, execute terminal commands |
| 🧩 Autonomous Tasks | High-level planning for complex, multi-step goals |
| 👁️ Visual Awareness | Real-time screen processing and webcam vision |
| 🧠 Persistent Memory | Deeply remembers your projects, preferences, and personal context |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |

---

## 🆕 What's New in MARK I-OR

- 📂 **Advanced File Handling** — New support for direct file uploads. Drop PDFs, source code, or images into the assistant to have them analyzed, summarized, or edited instantly.
- 🎨 **Adaptive & Flexible UI** — A complete overhaul of the interface. The new UI is fully resizable and responsive, featuring transparency controls and customizable layouts to fit your workspace perfectly.
- 🐧🍎 **Refined Cross-Platform Stability** — Major fixes for macOS and Linux compatibility. Core system actions are now more consistent across all three major operating systems.
- ⚡ **Optimized Core Engine** — Significant performance boost in tool-calling logic and response generation, resulting in a 40% faster interaction speed.
- 🔀 **OpenRouter Integration** — Selected action modules (web search, memory, flight finder, desktop control, and more) now route their LLM calls through OpenRouter's free-tier models. This significantly increases the effective request limit without any additional cost, while Gemini Live continues to handle real-time voice and tool-calling.

---

JEEV — COMPLETE INSTALLATION & SETUP GUIDE
============================================

GitHub Repository:
https://github.com/LWSanju/JEEV


1. REQUIREMENTS
---------------

Before installing JEEV, install:

- Windows 10 or Windows 11
- Python 3.11 or newer
- Git
- Working microphone
- Internet connection
- Required API keys

Check Python:

python --version

Check Git:

git --version


2. DOWNLOAD JEEV
-----------------

Open PowerShell and run:

cd $env:USERPROFILE\Downloads

git clone https://github.com/LWSanju/JEEV.git

cd JEEV

Check the project files:

dir


3. CREATE PYTHON VIRTUAL ENVIRONMENT
-------------------------------------

Inside the JEEV folder:

python -m venv .venv

Activate it:

.\.venv\Scripts\Activate.ps1

Your PowerShell prompt should now look similar to:

(.venv) PS C:\Users\YourName\Downloads\JEEV>


4. IF POWERSHELL BLOCKS VIRTUAL ENVIRONMENT ACTIVATION
-------------------------------------------------------

Run:

Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

Then activate again:

.\.venv\Scripts\Activate.ps1


5. UPDATE PIP
-------------

Run:

python -m pip install --upgrade pip setuptools wheel


6. INSTALL JEEV DEPENDENCIES
----------------------------

Install all required Python packages:

pip install -r requirements.txt

Also install PyAutoGUI:

pip install pyautogui


7. CREATE API KEY CONFIGURATION
--------------------------------

JEEV does NOT store API keys on GitHub.

Create the config folder if necessary:

mkdir config -Force

Create the API key file:

notepad config\api_keys.json

Add your own API keys.

Example:

{
    "google_api_key": "YOUR_GOOGLE_API_KEY",
    "openrouter_api_key": "YOUR_OPENROUTER_API_KEY"
}

Save the file.

IMPORTANT:
Never upload this file to GitHub.


8. OPENROUTER API KEY
---------------------

Get your own OpenRouter API key from:

https://openrouter.ai/

Put the key inside:

config\api_keys.json

Example:

{
    "openrouter_api_key": "YOUR_OPENROUTER_API_KEY"
}


9. GOOGLE / GEMINI API KEY
--------------------------

If your JEEV installation uses Google Gemini, create your own Google API key from:

https://aistudio.google.com/

Add it to:

config\api_keys.json

Example:

{
    "google_api_key": "YOUR_GOOGLE_API_KEY",
    "openrouter_api_key": "YOUR_OPENROUTER_API_KEY"
}

IMPORTANT:
Do not use somebody else's API key.


10. VERIFY API KEY FILE
-----------------------

You can check that the file exists with:

dir config

You should see:

api_keys.json

Do NOT print or share the contents of this file because it contains private API keys.


11. VERIFY GIT IS IGNORING API KEYS
------------------------------------

Run:

git check-ignore -v config/api_keys.json

You should get something similar to:

.gitignore:9:config/api_keys.json    config/api_keys.json

This confirms that the API key file will not be uploaded to GitHub.


12. TEST OPENROUTER
-------------------

Run:

python or_client.py

The test will check things such as:

- API key
- Free model discovery
- Basic chat
- JSON mode
- Multi-turn conversation
- OpenRouter health

If OpenRouter returns HTTP 429, it means the OpenRouter account/model is temporarily rate-limited.


13. TEST JEEV
------------

Start JEEV with:

python main.py

The JEEV interface should open.


14. MICROPHONE PERMISSIONS
--------------------------

Windows must allow JEEV/Python to use the microphone.

Go to:

Settings
→ Privacy & security
→ Microphone

Make sure these are enabled:

Microphone access: ON

Let desktop apps access your microphone: ON


15. CHECK AUDIO DEVICES
-----------------------

You can check available audio devices with:

python -c "import sounddevice as sd; print(sd.query_devices())"


16. WHATSAPP DESKTOP
--------------------

For JEEV's WhatsApp automation, install the actual WhatsApp Desktop application.

Do NOT use WhatsApp Web in Edge or Chrome for the desktop automation.

Log into WhatsApp Desktop normally.

JEEV can then control supported WhatsApp actions such as:

- Open WhatsApp
- Focus WhatsApp
- Open a contact/chat
- Send a message
- Reply in the current chat

The automation contains browser protection so it does not intentionally control Edge, Chrome, Firefox, Brave, or other browsers.


17. FIRST JEEV TEST
-------------------

After starting:

python main.py

Try:

Hello Jeev

Then:

What time is it?

Then:

Open WhatsApp

Then:

Open the WhatsApp chat with [CONTACT NAME]

Then:

Send [MESSAGE] to [CONTACT NAME] on WhatsApp


18. RUNNING JEEV AGAIN
----------------------

You do NOT need to reinstall everything every time.

Open PowerShell:

cd C:\PATH\TO\JEEV

Activate the virtual environment:

.\.venv\Scripts\Activate.ps1

Then start JEEV:

python main.py


19. UPDATE JEEV FROM GITHUB
---------------------------

If a newer version has been uploaded to GitHub:

cd C:\PATH\TO\JEEV

git pull

Your local API key file:

config\api_keys.json

will remain local because it is ignored by Git.


20. PROJECT STRUCTURE
---------------------

JEEV/
│
├── .git/
├── .gitignore
├── .venv/
│
├── actions/
├── agent/
├── config/
│   ├── __init__.py
│   └── api_keys.json
│
├── core/
├── memory/
│
├── location_service.py
├── news_service.py
├── or_client.py
├── main.py
├── ui.py
│
├── requirements.txt
├── setup.py
└── README.md


IMPORTANT:

The following file exists only on the user's local computer:

config/api_keys.json

It is intentionally NOT included in the GitHub repository.


21. FILES THAT MUST NEVER BE UPLOADED
-------------------------------------

Never upload private credentials such as:

.env
.env.*
config/api_keys.json
credentials.json
secrets.json
tokens.json
*.pem
*.key
*.p12


22. COMPLETE FRESH INSTALLATION
--------------------------------

For a completely new Windows computer:

1. Install Python.
2. Install Git.
3. Open PowerShell.
4. Run:

cd $env:USERPROFILE\Downloads

git clone https://github.com/LWSanju/JEEV.git

cd JEEV

python -m venv .venv

.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel

pip install -r requirements.txt

pip install pyautogui

mkdir config -Force

notepad config\api_keys.json

5. Enter your own API keys.
6. Save api_keys.json.
7. Install/configure WhatsApp Desktop if WhatsApp control is required.
8. Allow microphone access in Windows.
9. Start JEEV:

python main.py


23. QUICK INSTALLATION
----------------------

Copy and run:

git clone https://github.com/LWSanju/JEEV.git
cd JEEV
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install pyautogui
mkdir config -Force
notepad config\api_keys.json

After entering your API keys:

python main.py


24. IMPORTANT SECURITY NOTICE
-----------------------------

JEEV requires API keys for external AI services.

Never share your API keys publicly.

Never commit config/api_keys.json to Git.

Never paste API keys into GitHub issues, Discord, WhatsApp, YouTube comments, or public code.

If an API key is accidentally exposed, immediately revoke/rotate that key and create a new one.


JEEV GitHub Repository:
https://github.com/LWSanju/JEEV

---

## 📋 Requirements

| Requirement | Details |
|---|---|
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.14 or 3.12 |
| **Microphone** | Required for voice interaction |
| **API Keys** | Free Gemini API key + Free OpenRouter API key |

---



---
Connect with creator
LW_SANJAY (instagram)
