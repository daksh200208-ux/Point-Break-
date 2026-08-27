# ◈ POINT BREAK // COMMERCIAL EDITION ◈

> **Enterprise Tactical AI Desktop Assistant & Autonomous Multi-Agent Swarm**  
> *Engineered for High-Performance Workstation Automation, Intelligence Synthesis, and Voice Telemetry.*

---

## ⚡ Quick Start (1-Click Installation)

### Prerequisites
* **Windows 10 / 11**
* **Python 3.10+** (ensure *"Add Python to PATH"* is checked during installation)
* A free **Gemini API Key** from [Google AI Studio](https://aistudio.google.com/)

---

### Installation Steps

1. **Clone or Download** this repository to your computer:
   ```bash
   git clone https://github.com/YOUR_USERNAME/PointBreak-Commercial.git
   cd PointBreak-Commercial
   ```
2. **Double-click `setup.bat`**:
   * Automatically creates the isolated virtual environment (`venv`).
   * Installs all required dependencies.
   * Generates your local `.env` configuration file.
3. **Add Your API Key**:
   * Open the newly created `.env` file with Notepad.
   * Paste your Gemini API key:
     ```env
     GEMINI_API_KEY=your_actual_key_here
     ```
4. **Launch Point Break**:
   * Double-click **`run.bat`** to start the assistant!

---

## 🔄 Getting Updates

Whenever new features or improvements are released, simply double-click:
```text
update.bat
```
This automatically syncs the latest commits and updates any new dependencies in seconds.

---

## 🧠 Core Swarm Capabilities & Voice Commands

### 1. 🎙️ Live Meeting & Lecture Copilot
* *"Point Break, start meeting [Title]"* — Silently transcribes Zoom / Google Meet / Microsoft Teams calls.
* *"Point Break, what did they just say?"* — Live 60-second ear-translation / summary.
* *"Point Break, end meeting and summarize"* — Compiles an executive summary, decisions matrix, and action items dossier onto your Desktop.

### 2. 📺 YouTube Video Summarizer
* *"Point Break, summarize this video"* — Extracts the transcript and synthesizes key takeaways with timestamps from the video in your clipboard.
* *"Point Break, extract key takeaways from this lecture [URL]"*

### 3. 📬 High-Speed Native Email Triage
* *"Point Break, triage my emails"* — Scans priority unread emails in under 0.4 seconds via native IMAP SSL.
* *"Point Break, ghostwrite reply to [Name]"* — Drafts a contextual response directly into your Gmail Drafts.

### 4. 🛒 E-Commerce Price Sniper & Web Automation
* *"Point Break, price of Sony WH-1000XM5 on Amazon"*
* *"Point Break, open WhatsApp to [Contact]"*
* *"Point Break, read the latest global news"*

---

## 🛠️ Project Structure

```
PointBreak-Commercial/
├── jarvis.py                   # Core runtime & voice interaction loop
├── point_break_swarm.py        # Sub-15ms multi-agent fast router (Alpha, Beta, Gamma)
├── tars_meeting_copilot.py     # Live audio meeting transcriber & dossier generator
├── tars_video_summarizer.py    # YouTube transcript intelligence engine
├── tars_email_copilot.py       # High-speed IMAP email triage & ghost-drafter
├── tars_research_dossier.py    # Deep research PDF report synthesizer
├── jarvis_hud.html             # Interactive HTML status HUD
├── setup.bat                   # 1-Click virtual environment & package installer
├── run.bat                     # 1-Click startup launcher
├── update.bat                  # 1-Click auto-updater from GitHub
├── requirements.txt            # Locked package dependencies
├── .env.example                # Configuration template
└── .gitignore                  # Security filter for private keys & cache
```

---

## 🔒 Security & Privacy Notice
* All credentials, API keys, and email passwords remain strictly on your local machine inside `.env`.
* `.gitignore` prevents secrets from ever being uploaded or leaked.
