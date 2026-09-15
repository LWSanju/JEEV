# JEEV MARK I

**JEEV MARK I** is a Windows desktop AI assistant designed to combine
natural voice conversation, desktop automation, application control,
document analysis, messaging, web research, memory, and a Dynamic
Island-style interface into one assistant.

> **Project:** JEEV\
> **Repository:** LWSanju/JEEV\
> **Platform:** Windows\
> **Primary interface:** Voice + Dynamic Island desktop UI

------------------------------------------------------------------------

## ✨ What is JEEV?

JEEV MARK I is a personal desktop AI assistant built around a real-time
voice interaction loop.

It is designed to:

-   🎙️ Listen through the system microphone
-   🗣️ Hold real-time AI conversations
-   🔊 Respond with generated audio
-   🧠 Maintain conversational memory
-   🖥️ Control supported Windows applications
-   📧 Work with Gmail
-   💬 Control WhatsApp Desktop
-   🎵 Control Spotify
-   🌐 Search the web when web research is actually needed
-   📄 Analyze documents and PDFs
-   🖼️ Analyze images
-   ✈️ Find flights
-   🌦️ Get weather information
-   ▶️ Work with YouTube
-   ⚙️ Control supported computer settings
-   🔔 Create reminders
-   💻 Assist with project/code tasks
-   🧩 Support a plugin-oriented architecture
-   🎨 Provide a Dynamic Island-style desktop interface

------------------------------------------------------------------------

## 🧠 Core Architecture

JEEV is organized into separate components so individual capabilities
can be developed without replacing the entire assistant.

``` text
JEEV
│
├── main.py
│   └── Main application, voice loop, Gemini Live integration,
│       routing and tool execution
│
├── ui.py
│   └── Dynamic Island-style desktop interface
│
├── or_client.py
│   └── OpenRouter integration
│
├── microphone_controller.py
│   └── Microphone capture and audio preparation
│
├── actions/
│   ├── whatsapp_control.py
│   ├── spotify_control.py
│   ├── gmail_control.py
│   ├── send_message.py
│   ├── browser_control.py
│   ├── computer_control.py
│   ├── computer_settings.py
│   ├── desktop.py
│   ├── file_controller.py
│   ├── file_processor.py
│   ├── open_app.py
│   ├── screen_processor.py
│   ├── web_search.py
│   ├── youtube_video.py
│   ├── weather_report.py
│   ├── flight_finder.py
│   └── reminder.py
│
├── analyser/
│   ├── core.py
│   ├── document_analyser.py
│   └── image_analyser.py
│
├── personality/
│   ├── conversation_style.py
│   ├── humor_bank.py
│   └── sarcasm_engine.py
│
├── core/
│   └── coding / assistant infrastructure
│
├── memory/
│   └── local memory management
│
├── config/
│   └── local configuration
│
└── plugin_manager/
    └── plugin-related functionality
```

------------------------------------------------------------------------

## 🎙️ Real-Time Voice

JEEV uses a real-time Gemini Live connection for voice interaction.

The current audio pipeline is designed around:

``` text
Microphone
    ↓
Windows audio device
    ↓
JeevMicrophone
    ↓
Mono PCM16
    ↓
16 kHz
    ↓
Gemini Live
    ↓
24 kHz generated audio
    ↓
Windows output
```

The microphone controller automatically selects the appropriate input
device instead of relying on a permanently hard-coded Windows device
index.

------------------------------------------------------------------------

## 🖥️ Dynamic Island UI

JEEV uses a compact Dynamic Island-style desktop interface.

### Collapsed state

The compact pill is intended to show JEEV's status and visualizer
without displaying conversation messages.

### Expanded state

Clicking the Dynamic Island expands it into the assistant chat panel.

The expanded interface provides:

-   Conversation history
-   User input
-   Assistant responses
-   Message bubbles
-   Attachment support
-   Animated transitions
-   Visual voice activity feedback

Clicking the Dynamic Island again collapses the expanded panel.

------------------------------------------------------------------------

## 🤖 AI Systems

JEEV currently uses separate AI paths for different jobs.

### Gemini Live

Used for:

-   Real-time voice interaction
-   Voice responses
-   Natural conversation
-   Tool routing during the live assistant session

### OpenRouter

Used for tasks that require the OpenRouter client, including supported
analysis and coding-oriented functionality.

The project is configured to use **free OpenRouter model routes only**.

No paid OpenRouter model fallback is intended.

------------------------------------------------------------------------

## 🛠️ Automation

JEEV can route commands to dedicated automation modules.

Examples include:

### WhatsApp

JEEV can work with the installed WhatsApp Desktop application for
supported operations such as:

-   Opening WhatsApp
-   Searching for contacts
-   Selecting search results
-   Sending messages
-   Replying in the current conversation

### Gmail

JEEV provides a dedicated Gmail controller rather than routing Gmail
requests through the generic browser controller.

### Spotify

JEEV includes a dedicated Spotify controller for supported desktop
automation.

### Windows

JEEV can interact with supported:

-   Applications
-   Files
-   Folders
-   Desktop controls
-   Computer settings
-   Screen operations

------------------------------------------------------------------------

## 📄 Document & Image Analysis

The `analyser` package provides document and image analysis
capabilities.

Supported document workflows include:

-   PDF text extraction
-   PDF analysis
-   Scanned-document processing
-   OCR-oriented workflows
-   Key-point extraction
-   Summarization
-   Question answering
-   Page-aware analysis

Image analysis can be used for:

-   OCR
-   Image descriptions
-   Visual analysis

------------------------------------------------------------------------

## 🧠 Memory

JEEV includes a local memory system intended to allow useful information
from conversations to persist between sessions.

Local runtime memory should remain outside the public repository.

Sensitive/local files such as:

``` text
.env
config/api_keys.json
config/api_config.json
memory/*.db
memory/*.json
```

are excluded through `.gitignore`.

------------------------------------------------------------------------

## 🧩 Plugin Architecture

JEEV includes a plugin-oriented structure intended to make adding new
capabilities easier.

The project has a `plugin_manager` component for plugin-related
functionality.

The intended workflow is to allow supported plugins to be added without
manually rebuilding the entire assistant architecture.

------------------------------------------------------------------------

## 🗣️ Personality

JEEV has a separate personality layer.

Current personality-related components include:

``` text
personality/
├── conversation_style.py
├── humor_bank.py
└── sarcasm_engine.py
```

This keeps conversational style separate from the underlying automation
modules.

------------------------------------------------------------------------

## 🔐 Security & Local Configuration

**Never commit API keys or private credentials.**

Create a local `.env` file for private environment variables.

Example:

``` env
GEMINI_API_KEY=your_gemini_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
```

Use your own credentials and never publish them to GitHub.

The repository intentionally excludes local credentials and runtime
data.

------------------------------------------------------------------------

## 💻 Requirements

JEEV is currently intended for Windows.

Recommended environment:

-   Windows 10/11
-   Python 3.12+
-   Working microphone
-   Working audio output
-   Internet connection
-   Gemini API access
-   OpenRouter API access for features that use OpenRouter

------------------------------------------------------------------------

## 🚀 Installation

Clone the repository:

``` powershell
git clone https://github.com/LWSanju/JEEV.git
cd JEEV
```

Create a virtual environment:

``` powershell
python -m venv .venv
```

Activate it:

``` powershell
.\.venv\Scripts\Activate.ps1
```

Install the required dependencies:

``` powershell
python -m pip install --upgrade pip
```

Install project dependencies according to the project's dependency
configuration.

For document-analysis support, the analyzer currently uses packages
including:

``` powershell
python -m pip install pymupdf pypdf python-docx openpyxl
```

Configure your private API credentials in `.env`.

Then start JEEV:

``` powershell
.\.venv\Scripts\python.exe .\main.py
```

------------------------------------------------------------------------

## 🧪 Basic Verification

Before running the full assistant, Python files can be syntax checked
with:

``` powershell
.\.venv\Scripts\python.exe -m py_compile .\main.py
.\.venv\Scripts\python.exe -m py_compile .\ui.py
```

To verify the analyzer:

``` powershell
.\.venv\Scripts\python.exe -c "from analyser import analyze_file, JEEVAnalyzer; print('JEEV ANALYZER OK')"
```

------------------------------------------------------------------------

## ⌨️ Controls

### Emergency Kill Switch

``` text
Ctrl + Shift + Q
```

This is the emergency JEEV shutdown/kill shortcut.

### Terminal shutdown

When running JEEV from PowerShell:

``` text
Ctrl + C
```

stops the running process.

------------------------------------------------------------------------

## 📁 Important Files

  File                         Purpose
  ---------------------------- --------------------------------------
  `main.py`                    Main JEEV application
  `ui.py`                      Dynamic Island desktop UI
  `or_client.py`               OpenRouter client
  `microphone_controller.py`   Microphone/audio capture
  `actions/`                   Automation and assistant actions
  `analyser/`                  Document and image analysis
  `personality/`               Personality and conversational style
  `memory/`                    Local memory infrastructure
  `plugin_manager/`            Plugin-related infrastructure
  `config/`                    Local configuration

------------------------------------------------------------------------

## 🔒 What Should NOT Be Committed

Do not commit:

``` text
.env
.env.*
config/api_keys.json
config/api_config.json
memory/*.db
memory/*.json
.venv/
__pycache__/
.jeev/
.jeev_gmail/
```

Local credentials, tokens, databases and personal runtime information
should stay on the local machine.

------------------------------------------------------------------------

## 🧭 Project Philosophy

JEEV is designed around a simple idea:

> **One assistant, multiple capabilities, separate systems.**

Voice interaction, AI reasoning, automation, memory, analysis,
personality and UI are kept as separate layers wherever practical.

This makes it easier to:

-   Add features
-   Replace individual modules
-   Debug failures
-   Improve automation
-   Upgrade the interface
-   Add new tools
-   Keep credentials and runtime data local

------------------------------------------------------------------------

## 📌 Current Project Status

**JEEV MARK I is an active development project.**

The current project contains working infrastructure for:

-   Real-time voice interaction
-   Dynamic Island UI
-   OpenRouter integration
-   Desktop automation
-   WhatsApp automation
-   Gmail integration
-   Spotify integration
-   Document analysis
-   Image analysis
-   Memory
-   Personality
-   Reminders
-   Weather
-   Web search
-   YouTube
-   Flight search
-   Coding/project assistance
-   Plugin-oriented functionality

Individual automation capabilities depend on the target application's
current state, Windows permissions, available APIs, and installed
software.

------------------------------------------------------------------------

## 👤 Creator

**JEEV MARK I**

Created and developed by **Sanjay Adhityan**.

------------------------------------------------------------------------

## 📜 License

No open-source license has been specified for this project yet.

Until a license is added, the repository should be treated as **all
rights reserved**.

------------------------------------------------------------------------

## ⭐ JEEV

**JEEV MARK I --- a personal AI assistant built for the Windows
desktop.**
