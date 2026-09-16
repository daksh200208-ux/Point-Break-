# ◈ POINT BREAK // OFFICIAL USER GUIDE ◈

> **"Not just artificial intelligence. Your personal assistant."**  
> *Autonomous Desktop AI Agent, Multi-Agent Swarm & Workstation Telemetry.*

---

## 🎙️ HOW TO TALK TO POINT BREAK

### ⚡ The Wake-Up Phrase
To start talking to Point Break at any time, simply say:
# 👉 **`"Hey Point Break"`**
*(You can also say **`"Point Break"`** or speak/type your request naturally if you have active focus.)*

---

## ⚡ QUICK START & INSTALLATION (1-CLICK)

### Prerequisites
* **Windows 10 / 11**
* **Python 3.10+** (ensure *"Add Python to PATH"* is checked during Python installation)
* A free Gemini API Key from [Google AI Studio](https://aistudio.google.com/)

### 3-Step Setup:
1. **Clone this repository**:
   ```bash
   git clone https://github.com/daksh200208-ux/Point-Break-.git
   cd Point-Break-
   ```
2. **Run the 1-Click Setup**:
   * Double-click **`setup.bat`** (or run `pip install -r requirements.txt`).
3. **Add Your Key & Run**:
   * Open `.env` and paste your key: `GEMINI_API_KEY=your_key_here`
   * Double-click **`run.bat`** (or run `python jarvis.py`).

---

## 🚀 MODES OF USE

You can interact with Point Break in **three simple ways**:
1. **Voice Mode**: Say `"Hey Point Break, [your command]"` — it listens, speaks back, and executes directly on your screen.
2. **Text / Terminal Prompt**: Type any command directly and hit `Enter`.
3. **Proactive Confirmation**: Whenever Point Break suggests a next step (*"Sir, would you like me to check flights or filter 4-star stays?"*), simply say:
   * **`"Yes"`** / **`"Do it"`** / **`"Sure"`** / **`"Proceed"`** / **`"Go ahead"`**  
   *It will immediately execute the anticipated action without repeating instructions.*

---

## 📚 MASTER DIRECTORY OF FEATURES & COMMANDS

---

### 1. ✈️ Travel Planning & Live Hotel Booking
*Point Break calculates realistic trip budgets and automatically launches live rates without getting stuck.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"Hey Point Break, how much would a trip to Goa cost?"` | Calculates full budget breakdown (stays, flights, food, activities) and opens live hotel searches on MakeMyTrip & Google Travel. |
| `"Plan a weekend trip to Manali under 15,000"` | Breaks down budget travel, routes, and opens available accommodations. |
| `"Find 4-star hotels in Dubai"` | Opens live filtered hotel listings for Dubai. |
| `"How much is a vacation to Paris for two?"` | Computes international travel estimates and currency breakdown. |

---

### 2. 🍕 Food Ordering & Delivery (Swiggy & Zomato)
*Isolates exact dish names and opens delivery apps directly with your search—no messy sentence typing.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"Hey Point Break, order lassi"` | Opens Swiggy/Zomato directly searching strictly for `"lassi"`. |
| `"Can you order me a sweet lassi from Swiggy?"` | Cleans conversational noise and opens Swiggy search for `"sweet lassi"`. |
| `"Order a paneer pizza on Zomato"` | Opens Zomato directly with `"paneer pizza"`. |
| `"Order 2 burgers and compare prices on Swiggy and Zomato"` | Opens both platforms to compare menu prices side-by-side. |

---

### 3. 🎙️ Live Meeting & Lecture Co-Pilot
*Runs quietly in the background during Zoom, Google Meet, Teams, or in-person lectures.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"Hey Point Break, start meeting [Title]"` | Begins silent background audio recording and live transcription. |
| `"Hey Point Break, record this lecture"` | Activates lecture monitoring mode. |
| `"Hey Point Break, what did they just say?"` | Provides an instant 60-second recap/translation of the last dialogue. |
| `"Hey Point Break, end meeting and summarize"` | Concludes the meeting, synthesizes key decisions and action items, and saves an executive dossier on your Desktop. |

---

### 4. 📬 Email Triage & Ghost-Drafting
*Scans actionable correspondence and drafts contextual replies.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"Hey Point Break, triage my emails"` | Scans unread emails, isolates urgent threads requiring manual replies, and opens your inbox. |
| `"Check my unread emails"` | Reports number of pending messages and highlights high-priority threads. |
| `"Ghostwrite reply to John"` | Synthesizes a polished professional draft based on conversation context. |

---

### 5. 🖥️ Hands-Free Desktop Control & Native GUI Actions
*Complete control over Windows, mouse, keyboard, and applications.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"action type Hello World"` | Types `"Hello World"` cleanly into the active text box (no extra command text). |
| `"action click Submit"` | Clicks the specified button or UI element in sub-50ms native speed. |
| `"action double click"` | Triggers a double-click on the current target. |
| `"action right click"` | Triggers a context click. |
| `"action scroll down"` / `"action scroll up"` | Scrolls the active window or page smoothly. |
| `"action press enter"` / `"action press tab"` | Presses native hardware keys (`enter`, `tab`, `esc`, `win`). |
| `"Take a screenshot"` | Captures your screen and saves it directly to your Desktop. |
| `"Lock my PC"` | Immediately locks the Windows workstation for security. |
| `"Mute audio"` / `"Unmute"` / `"Set volume to 40%"` | Controls Windows master system audio. |

---

### 6. 🌐 Direct Web Browsing & Navigation
*Fast-lane browser shortcuts for the most popular web services.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"browse youtube"` | Launches YouTube instantly. |
| `"browse reddit"` | Opens Reddit homepage. |
| `"browse amazon"` / `"browse flipkart"` | Opens shopping portals. |
| `"browse github"` / `"browse netflix"` / `"browse spotify"` | Direct service launches. |
| `"browse https://example.com"` | Opens specific web address directly. |
| `"browse best mechanical keyboards in 2026"` | Performs direct Google search in default browser. |

---

### 7. 🎵 Music & Media Playback (Spotify)
*Hands-free soundtrack for your workstation.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"Hey Point Break, play Interstellar soundtrack on Spotify"` | Searches and plays the track/album on Spotify. |
| `"Play lo-fi chill beats"` | Launches a continuous ambient background radio. |
| `"Play songs by The Weeknd"` | Starts playing top tracks by the artist. |
| `"Pause music"` / `"Resume music"` / `"Next song"` | Media playback controls. |

---

### 8. 📺 YouTube Video Summarizer & Key Takeaway Extractor
*Turn lengthy videos and podcasts into structured text in seconds.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"Hey Point Break, summarize this video"` | Pulls the YouTube URL currently in your clipboard, transcribes it, and outputs key points with timestamps. |
| `"Summarize this lecture [YouTube URL]"` | Fetches full transcript and gives a structured breakdown. |

---

### 9. 👁️ Screen Vision & Autonomous Takeover
*Visual intelligence that sees your display and helps solve complex problems.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"Hey Point Break, look at my screen and explain what's wrong"` | Inspects open code, error messages, or layouts and explains the issue. |
| `"Take over"` / `"Point Break take over"` | Engages autonomous visual agent to navigate active desktop tasks. |
| `"Analyze this chart on my screen"` | Extracts trends, metrics, and data points from visible images or dashboards. |

---

### 10. 📑 Deep Research & Executive PDF Dossier Generation
*Generates publication-grade briefing papers on your Desktop.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"Hey Point Break, research Quantum Computing trends"` | Conducts web research, synthesizes findings, and compiles a PDF report on Desktop. |
| `"Create a market analysis report on Electric Vehicles"` | Gathers financial, competitive, and regulatory intel into a structured document. |

---

### 11. 💻 Developer & Code Automation (Gamma Swarm Agent)
*Full development environment support.*

| What You Say / Type | What Point Break Does |
|---|---|
| `"Hey Point Break, explain this function"` | Reads highlighted or visible code and explains logic. |
| `"Create a Python script to convert images to webp"` | Generates and saves script to current workspace. |
| `"Check system health"` / `"Show CPU and memory usage"` | Displays real-time hardware telemetry. |

---

## 🔒 PRIVACY & LOCAL SECURITY

* **Private by Design**: Your credentials, API keys, and email passwords stay strictly on your local PC.
* **No Unsolicited Actions**: Destructive actions (like sending payments or deleting files) require explicit confirmation.
* **Authenticode Code Signed**: Verified with official digital signature (`CN=Point Break Technologies Inc.`) for Windows integrity.

---

## 💡 PRO TIPS FOR THE BEST EXPERIENCE

1. **Be Conversational**: You don't have to memorize rigid syntax. Talk to Point Break as if you are talking to a colleague sitting next to your desk.
2. **Use Confirmations**: When Point Break finishes a task and asks *"Would you like me to do X next?"*, just say `"Yes"` or `"Go ahead"` to keep your flow going hands-free.
3. **Headset / Microphone**: A clear microphone setup allows Point Break to pick up the `"Hey Point Break"` wake-up phrase reliably from across the room.

---
*Point Break Technologies Inc. — All Rights Reserved.*
