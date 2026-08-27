"""
Point Break 3.0 — Master Brain & Tri-Core Sub-Agent Swarm Engine (Default Edition)
===================================================================================
1. Master Brain Router: 15ms intent triage with robust regex pattern matching.
2. 🔴 ALPHA: Career, Writing & Knowledge (Job hunting, IMAP Email Triage, Ghostwriting, Dossiers, Vision).
3. 🔴 BETA:  Commerce, Media & Communications (Amazon/Flipkart/Myntra Sniper, YouTube, WhatsApp, News, Food).
4. 🔴 GAMMA: Tactical OS, Hardware, Sentry & Wireless ADB Phone Bridge.
5. Master Speech Priority Queue (Zero audio collisions, hardware-safe).
6. Shared In-Memory Blackboard with 0ms real-time HUD telemetry push.
"""

import os
import sys
import time
import re
import json
import queue
import threading
import subprocess
import urllib.parse
from typing import Dict, Any, Optional, List, Callable

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pyautogui
import webbrowser

JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))


# ── 1. MASTER SPEECH ARBITER (PRIORITY QUEUE) ────────────────────────
class SpeechArbiter:
    """Thread-safe speech arbiter preventing audio collisions."""
    def __init__(self):
        self.speech_queue = queue.PriorityQueue()
        self.speak_fn: Optional[Callable] = None
        self.is_running = True
        self._worker = threading.Thread(target=self._speech_loop, daemon=True)
        self._worker.start()

    def set_speaker(self, speak_fn: Callable):
        self.speak_fn = speak_fn

    def speak(self, text: str, priority: int = 2, block: bool = False):
        if not text or not text.strip():
            return
        if self.speak_fn and block:
            try:
                self.speak_fn(text.strip())
                return
            except Exception:
                pass
        self.speech_queue.put((priority, time.time(), text.strip()))

    def _speech_loop(self):
        while self.is_running:
            try:
                priority, ts, text = self.speech_queue.get(timeout=0.2)
                if self.speak_fn:
                    try:
                        self.speak_fn(text)
                    except Exception as e:
                        print(f"[SpeechArbiter] Output error: {e}")
                self.speech_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass


speech_arbiter = SpeechArbiter()


# ── 2. SHARED IN-MEMORY BLACKBOARD ───────────────────────────────────
class SwarmBlackboard:
    """Synchronized shared state across Alpha, Beta, Gamma, and Master Core."""
    def __init__(self):
        self._lock = threading.Lock()
        self.state: Dict[str, Any] = {
            "alpha_status": "IDLE",
            "beta_status": "IDLE",
            "gamma_status": "IDLE",
            "active_agent": "STANDBY",
            "last_agent_event": "Swarm Core Online"
        }
        self.update_status_fn: Optional[Callable] = None

    def set_status_callback(self, fn: Callable):
        self.update_status_fn = fn

    def update_agent(self, agent_name: str, status: str, event_text: str = ""):
        with self._lock:
            key = f"{agent_name.lower()}_status"
            self.state[key] = status
            if status != "IDLE":
                self.state["active_agent"] = agent_name.upper()
                self.state["last_agent_event"] = event_text or f"{agent_name.upper()} processing"
            else:
                self.state["active_agent"] = "STANDBY"

        if self.update_status_fn:
            try:
                self.update_status_fn({
                    "swarm_state": self.state,
                    "agent_task": {
                        "agent": agent_name.upper(),
                        "status": status,
                        "description": event_text
                    }
                })
            except Exception:
                pass


blackboard = SwarmBlackboard()


# ── 3. SUB-AGENT ALPHA: CAREER, WRITING & KNOWLEDGE ─────────────────
class SubAgentAlpha:
    """Handles Career, Writing, Native Email Triage, PDF Dossiers, and Vision."""
    def __init__(self):
        self.task_queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def dispatch(self, task_type: str, query: str, context: Dict[str, Any] = None):
        self.task_queue.put({"type": task_type, "query": query, "context": context or {}})

    def _worker_loop(self):
        while True:
            task = self.task_queue.get()
            t_type = task["type"]
            q = task["query"]
            blackboard.update_agent("ALPHA", "ACTIVE", f"Executing: {t_type}")
            try:
                if t_type == "triage_email":
                    self.triage_gmail_and_autodraft(q)
                elif t_type == "hunt_jobs":
                    self.hunt_jobs_and_internships(q)
                elif t_type == "ghostwriter":
                    self.notepad_gpt_ghostwriter(q)
                elif t_type == "dossier":
                    self.generate_research_dossier(q)
                elif t_type == "explain_screen":
                    self.explain_screen_cmd(q)
            except Exception as e:
                print(f"[ALPHA Error] {t_type}: {e}")
            finally:
                blackboard.update_agent("ALPHA", "IDLE")
                self.task_queue.task_done()

    def triage_gmail_and_autodraft(self, query: str):
        speech_arbiter.speak("Scanning inbox via direct IMAP protocol...", priority=2)
        try:
            from tars_email_copilot import email_copilot
            res = email_copilot.triage_inbox()
            if res.get("spoken_debrief"):
                speech_arbiter.speak(res["spoken_debrief"], priority=2)
        except Exception as e:
            print("[ALPHA Email] Error:", e)
            webbrowser.open("https://mail.google.com/mail/u/0/#search/is%3Aunread+category%3Aprimary")
            speech_arbiter.speak("Opening your unread priority emails in Gmail.", priority=2)

    def hunt_jobs_and_internships(self, query: str):
        speech_arbiter.speak("Scouting verified job and internship openings on LinkedIn...", priority=2)
        clean = re.sub(r'(?i)\b(find\s+jobs|find\s+internships|hunt\s+jobs|job\s+search|internship\s+search|look\s+for\s+jobs|look\s+for\s+internships|scout\s+openings|jobs|internships|for|in|openings|open)\b', ' ', query)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if not clean: clean = "software engineer intern"
        url = f"https://www.linkedin.com/jobs/search/?keywords={urllib.parse.quote(clean)}&f_TPR=r86400&position=1&pageNum=0"
        webbrowser.open(url)
        speech_arbiter.speak(f"Surfacing verified openings for {clean} on LinkedIn.", priority=2)

    def notepad_gpt_ghostwriter(self, query: str):
        speech_arbiter.speak("Ghostwriting text directly to active editor...", priority=2)
        topic = re.sub(r'(?i)\b(write|draft|compose|ghostwrite|an\s+essay\s+on|an\s+article\s+on|a\s+letter\s+to|about|for)\b', ' ', query)
        topic = re.sub(r'\s+', ' ', topic).strip()
        try:
            import google.generativeai as genai
            model = genai.GenerativeModel("gemini-2.5-flash")
            res = model.generate_content(f"Write a crisp, professional, ready-to-use piece for: {topic}")
            text = res.text.strip()
            subprocess.Popen(["notepad.exe"], creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            time.sleep(0.6)
            import pyperclip
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'v')
            speech_arbiter.speak("Draft completed in Notepad, Daksh.", priority=2)
        except Exception as e:
            print("[ALPHA Ghostwriter] Error:", e)
            speech_arbiter.speak("Draft generation error.", priority=2)

    def generate_research_dossier(self, query: str):
        speech_arbiter.speak("Synthesizing comprehensive intelligence dossier on target topic...", priority=2)
        try:
            import tars_research_dossier
            dossier_engine = getattr(tars_research_dossier, "dossier_engine", None)
            if dossier_engine:
                res = dossier_engine.generate_dossier_pdf(query, owner_name="Daksh")
                if res.get("success"):
                    fp = res.get("file_path")
                    topic = res.get("topic", "Target")
                    speech_arbiter.speak(f"Intelligence dossier for {topic} compiled and rendered to Desktop.", priority=2)
                    try:
                        webbrowser.open(f"file:///{fp.replace(os.sep, '/')}")
                    except Exception:
                        os.startfile(fp)
                else:
                    speech_arbiter.speak("Encountered an issue compiling the dossier report.", priority=2)
        except Exception as e:
            print("[ALPHA Dossier] Error:", e)
            speech_arbiter.speak("Intelligence dossier generation encountered an error.", priority=2)

    def explain_screen_cmd(self, query: str):
        speech_arbiter.speak("Analyzing screen visual context...", priority=2)
        try:
            from pointbreak_ambient import ambient_engine
            ambient_engine.explain_and_solve_screen(
                speak_fn=lambda txt: speech_arbiter.speak(txt, priority=2)
            )
        except Exception as e:
            print("[ALPHA Screen] Error:", e)


# ── 4. SUB-AGENT BETA: COMMERCE, MEDIA & COMMUNICATIONS ─────────────
class SubAgentBeta:
    """Handles E-Commerce Price Tracking, Media/YouTube, WhatsApp, and News."""
    def __init__(self):
        self.task_queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def dispatch(self, task_type: str, query: str, context: Dict[str, Any] = None):
        self.task_queue.put({"type": task_type, "query": query, "context": context or {}})

    def _worker_loop(self):
        while True:
            task = self.task_queue.get()
            t_type = task["type"]
            q = task["query"]
            blackboard.update_agent("BETA", "ACTIVE", f"Executing: {t_type}")
            try:
                if t_type == "ecom_sniper":
                    self.ecom_price_sniper(q)
                elif t_type == "media_playback":
                    self.play_media_or_youtube(q)
                elif t_type == "whatsapp":
                    self.send_whatsapp(q)
                elif t_type == "news_briefing":
                    self.read_world_news_protocol(q)
                elif t_type == "order_food":
                    self.order_coffee_cmd(q)
            except Exception as e:
                print(f"[BETA Error] {t_type}: {e}")
            finally:
                blackboard.update_agent("BETA", "IDLE")
                self.task_queue.task_done()

    def ecom_price_sniper(self, query: str):
        low = query.lower().strip()
        store = "amazon"
        if "flipkart" in low: store = "flipkart"
        elif "myntra" in low: store = "myntra"

        clean = re.sub(r'(?i)\b(search\s+up\s+on|search\s+up|search\s+on|search\s+for|search|look\s+up\s+to\s+on|look\s+up\s+to|look\s+up\s+on|look\s+up|look\s+for|look|check\s+price\s+of|check\s+price\s+on|check\s+price|check|price\s+of|snipe\s+price\s+of|snipe\s+price|how\s+much\s+is|find\s+on|find|buy\s+on|buy|order\s+on|order|on\s+amazon|on\s+flipkart|on\s+myntra|amazon|flipkart|myntra|about|for|to|the|product|item)\b', ' ', query)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if not clean: clean = "deals"

        if store == "amazon":
            url = f"https://www.amazon.in/s?k={urllib.parse.quote(clean)}"
            speech_arbiter.speak(f"Opening Amazon listings for {clean}.", priority=2)
        elif store == "flipkart":
            url = f"https://www.flipkart.com/search?q={urllib.parse.quote(clean)}"
            speech_arbiter.speak(f"Opening Flipkart listings for {clean}.", priority=2)
        elif store == "myntra":
            url = f"https://www.myntra.com/{urllib.parse.quote(clean)}"
            speech_arbiter.speak(f"Opening Myntra listings for {clean}.", priority=2)
        else:
            url = f"https://www.amazon.in/s?k={urllib.parse.quote(clean)}"
            speech_arbiter.speak(f"Opening listings for {clean}.", priority=2)

        webbrowser.open(url)

    def play_media_or_youtube(self, query: str):
        q_clean = re.sub(r'(?i)\b(play|stream|listen\s+to|watch|on\s+youtube|youtube)\b', ' ', query)
        q_clean = re.sub(r'\s+', ' ', q_clean).strip()
        if not q_clean: q_clean = "AC/DC Back in Black"
        speech_arbiter.speak(f"Streaming {q_clean} on YouTube.", priority=2)
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q_clean)}"
        webbrowser.open(url)

    def send_whatsapp(self, query: str):
        speech_arbiter.speak("Opening WhatsApp portal...", priority=2)
        webbrowser.open("https://web.whatsapp.com")

    def read_world_news_protocol(self, query: str):
        # Check if user specified a keyword/topic
        clean_topic = re.sub(r'(?i)\b(read\s+me\s+the\s+news|read\s+the\s+news|world\s+news|global\s+news|news\s+briefing|daily\s+news|give\s+me\s+the\s+news|show\s+me\s+the\s+news|tell\s+me\s+the\s+news|news\s+about|news\s+on|news\s+for|latest\s+news\s+on|latest\s+news\s+about|headlines\s+about|headlines\s+on|news|headlines|today|latest)\b', ' ', query)
        clean_topic = re.sub(r'\s+', ' ', clean_topic).strip()

        if clean_topic:
            speech_arbiter.speak(f"Gathering latest intelligence on {clean_topic}...", priority=2)
            rss_url = f"https://news.google.com/rss/search?q={urllib.parse.quote(clean_topic)}"
            web_url = f"https://news.google.com/search?q={urllib.parse.quote(clean_topic)}"
            fallback_speech = f"Opening news coverage for {clean_topic}."
            spoken_prefix = f"Top headlines for {clean_topic}: "
        else:
            speech_arbiter.speak("Accessing World Monitor. Intelligence feeds coming online.", priority=2)
            rss_url = "https://news.google.com/rss"
            web_url = "https://world-monitor.app/"
            fallback_speech = "Opening World Monitor global intelligence console."
            spoken_prefix = "Top global headlines: "

        try:
            import urllib.request
            req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                xml_data = resp.read().decode('utf-8')
                titles = re.findall(r'<title>(.*?)</title>', xml_data)[2:6]
                clean_titles = [t.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"').split(" - ")[0] for t in titles]
                if clean_titles:
                    spoken = spoken_prefix + "; ".join(clean_titles) + "."
                    speech_arbiter.speak(spoken, priority=2)
                    webbrowser.open(web_url)
                else:
                    webbrowser.open(web_url)
                    speech_arbiter.speak(fallback_speech, priority=2)
        except Exception:
            webbrowser.open(web_url)
            speech_arbiter.speak(fallback_speech, priority=2)

    def order_coffee_cmd(self, query: str):
        speech_arbiter.speak("Opening ordering portal for you, Daksh.", priority=2)
        if "zomato" in query.lower():
            webbrowser.open("https://www.zomato.com")
        else:
            webbrowser.open("https://www.swiggy.com")


# ── 5. SUB-AGENT GAMMA: TACTICAL OS, HARDWARE & SENTRY ──────────────
class SubAgentGamma:
    """Handles File Hunter, Alarms/Clock, Workspace Cleaning, Hardware, Gestures, ADB."""
    def __init__(self, enable_adb: bool = True):
        self.enable_adb = enable_adb
        self.task_queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def dispatch(self, task_type: str, query: str, context: Dict[str, Any] = None):
        self.task_queue.put({"type": task_type, "query": query, "context": context or {}})

    def _worker_loop(self):
        while True:
            task = self.task_queue.get()
            t_type = task["type"]
            q = task["query"]
            blackboard.update_agent("GAMMA", "ACTIVE", f"Executing: {t_type}")
            try:
                if t_type == "hunt_files":
                    self.precision_file_hunter(q)
                elif t_type == "organize_workspace":
                    self.organize_workspace(q)
                elif t_type == "phone_lockdown" and self.enable_adb:
                    self.lock_phone_remotely()
                elif t_type == "phone_battery" and self.enable_adb:
                    self.get_phone_battery()
                elif t_type == "companion_display" and self.enable_adb:
                    self.launch_companion_display()
                elif t_type == "gods_eye":
                    self.launch_gods_eye(q)
            except Exception as e:
                print(f"[GAMMA Error] {t_type}: {e}")
            finally:
                blackboard.update_agent("GAMMA", "IDLE")
                self.task_queue.task_done()
    def launch_gods_eye(self, query: str):
        speech_arbiter.speak("God's Eye satellite and tactical recon features are restricted for Sir only.", priority=2)

    def show_cctv_matrix(self, query: str):
        speech_arbiter.speak("Optical CCTV surveillance feeds are restricted for Sir only.", priority=2)

    def precision_file_hunter(self, query: str):
        speech_arbiter.speak("Scanning local volumes for target file...", priority=2)
        target = re.sub(r'(?i)\b(find\s+file|locate\s+file|search\s+file|where\s+is\s+my|find\s+my|find|search|document|pdf|file)\b', ' ', query)
        target = re.sub(r'\s+', ' ', target).strip()
        if not target: target = "resume"
        search_dirs = [
            os.path.join(os.path.expanduser("~"), "Downloads"),
            os.path.join(os.path.expanduser("~"), "Documents"),
            os.path.join(os.path.expanduser("~"), "Desktop"),
        ]
        found = []
        for d in search_dirs:
            if not os.path.exists(d): continue
            for root, _, files in os.walk(d):
                for f in files:
                    if target.lower() in f.lower():
                        found.append(os.path.join(root, f))
                        if len(found) >= 3: break
                if len(found) >= 3: break

        if found:
            speech_arbiter.speak(f"Located matching file. Opening {os.path.basename(found[0])}.", priority=2)
            os.startfile(found[0])
        else:
            speech_arbiter.speak(f"Could not find any file named '{target}' in Downloads or Documents.", priority=2)

    def organize_workspace(self, query: str):
        speech_arbiter.speak("Organizing workspace files into categorized directories...", priority=2)
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        categories = {
            "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"],
            "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx"],
            "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
            "Installers": [".exe", ".msi", ".dmg"],
            "Audio_Video": [".mp4", ".mp3", ".mkv", ".wav", ".avi"]
        }
        count = 0
        try:
            for f in os.listdir(downloads_dir):
                fp = os.path.join(downloads_dir, f)
                if os.path.isfile(fp):
                    ext = os.path.splitext(f)[1].lower()
                    for cat, exts in categories.items():
                        if ext in exts:
                            cat_dir = os.path.join(downloads_dir, cat)
                            os.makedirs(cat_dir, exist_ok=True)
                            dest = os.path.join(cat_dir, f)
                            if not os.path.exists(dest):
                                os.rename(fp, dest)
                                count += 1
                            break
            speech_arbiter.speak(f"Workspace organized. Sorted {count} files cleanly.", priority=2)
        except Exception as e:
            print("[GAMMA Clean] Error:", e)
            speech_arbiter.speak("Error organizing workspace files.", priority=2)

    def lock_phone_remotely(self):
        if not self.enable_adb: return
        speech_arbiter.speak("Engaging wireless phone lockdown protocol...", priority=1)
        try:
            subprocess.run(['adb', 'shell', 'input', 'keyevent', '26'], capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            subprocess.run(['adb', 'shell', 'cmd', 'audio', 'set-volume', '0', '0'], capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            speech_arbiter.speak("Phone display locked and silenced remotely.", priority=1)
        except Exception as e:
            print("[GAMMA ADB] Error:", e)

    def get_phone_battery(self):
        if not self.enable_adb: return
        try:
            r = subprocess.run(['adb', 'shell', 'dumpsys', 'battery'], capture_output=True, text=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            lvl = "Unknown"
            for line in r.stdout.splitlines():
                if 'level:' in line:
                    lvl = line.split(':')[1].strip() + "%"
            speech_arbiter.speak(f"Phone battery level is at {lvl}.", priority=2)
        except Exception:
            speech_arbiter.speak("Could not read phone battery level.", priority=2)

    def launch_companion_display(self):
        if not self.enable_adb: return
        speech_arbiter.speak("Launching Cyber Sentinel companion display on your phone, Daksh.", priority=2)
        try:
            subprocess.run(['adb', 'reverse', 'tcp:8000', 'tcp:8000'], capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            subprocess.run(['adb', 'shell', 'input', 'keyevent', '224'], capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            subprocess.run(['adb', 'shell', 'am', 'start', '-a', 'android.intent.action.VIEW', '-d', 'http://localhost:8000/companion_display.html'], capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        except Exception as e:
            print("[GAMMA Companion] Launch error:", e)


# Global instances
agent_alpha = SubAgentAlpha()
agent_beta = SubAgentBeta()
agent_gamma = SubAgentGamma(enable_adb=True)


# ── 6. MASTER BRAIN FAST ROUTER (< 15ms) ─────────────────────────────
def point_break_master_brain(query: str, speak_fn=None, update_status_fn=None, is_commercial: bool = False) -> bool:
    """
    Sub-15ms fast triage router:
    Dispatches task to ALPHA, BETA, or GAMMA queues with robust natural language pattern matching.
    """
    if not query or not query.strip():
        return False

    if speak_fn:
        speech_arbiter.set_speaker(speak_fn)
    if update_status_fn:
        blackboard.set_status_callback(update_status_fn)

    low = query.lower().strip()

    # ── ALPHA DOMAIN (Career, Writing, Email Triage, Dossiers, Vision) ──
    if re.search(r'\b(triage|unread|check|scan|read|show|get|open|draft|reply|respond)\b.*\b(emails?|mails?|inbox|draft)\b', low) or 'triage' in low or 'unread email' in low or 'check my mail' in low or 'check my email' in low or 'check mail' in low or 'read my email' in low or 'scan my inbox' in low or 'scan inbox' in low:
        agent_alpha.dispatch("triage_email", query)
        return True

    if re.search(r'\b(find|hunt|search|scout|look\s+for)\b.*\b(jobs?|internships?|openings?)\b', low) or 'find jobs' in low or 'find internships' in low:
        agent_alpha.dispatch("hunt_jobs", query)
        return True

    if re.search(r'\b(ghostwrite|draft\s+essay|compose\s+draft|write\s+an\s+essay|write\s+an\s+article|write\s+a\s+letter)\b', low):
        agent_alpha.dispatch("ghostwriter", query)
        return True

    if any(k in low for k in ["research dossier", "generate dossier", "pdf report on", "compile research on"]):
        agent_alpha.dispatch("dossier", query)
        return True

    if any(k in low for k in ["explain screen", "what is on my screen", "solve screen", "debug screen"]):
        agent_alpha.dispatch("explain_screen", query)
        return True

    # ── BETA MEDIA: Play music/video ──────────────────────────────
    if re.search(r'\b(play|stream|listen\s+to|watch|put\s+on)\b', low) and not any(k in low for k in ['amazon', 'flipkart', 'myntra', 'email', 'mail', 'file', 'todo', 'job', 'intern']):
        agent_beta.dispatch("media_playback", query)
        return True

        # ── BETA DOMAIN (Commerce, Media, Comms, News, Food) ─────────────
    if any(k in low for k in ['amazon', 'flipkart', 'myntra', 'price of', 'check price', 'how much is', 'snipe price']) or re.search(r'\b(search|look|check|find|buy|order)\b.*\b(on\s+amazon|on\s+flipkart|on\s+myntra|amazon|flipkart|myntra)\b', low):
        agent_beta.dispatch("ecom_sniper", query)
        return True

    if any(k in low for k in ["world news", "news briefing", "global news", "read the news", "read me the news", "daily news", "news about", "news on", "latest news"]) or re.search(r'\b(news|headlines)\b.*\b(about|on|regarding|for|today|latest)\b', low) or low.strip() == "news":
        agent_beta.dispatch("news_briefing", query)
        return True

    if any(k in low for k in ["order coffee", "order food", "zomato", "swiggy", "open swiggy", "open zomato"]):
        agent_beta.dispatch("order_food", query)
        return True

    if any(k in low for k in ["open whatsapp", "send whatsapp", "whatsapp web"]):
        agent_beta.dispatch("whatsapp", query)
        return True

    # ── GAMMA DOMAIN (Tactical OS, Files, Alarms, Workspace, ADB) ─────
    if re.search(r'\b(find|locate|search|where\s+is\s+my|hunt)\b.*\b(file|document|pdf|resume|aadhaar|pan|photo)\b', low) or 'find file' in low or 'locate file' in low:
        agent_gamma.dispatch("hunt_files", query)
        return True

    if any(k in low for k in ["organize workspace", "clean downloads", "organize downloads", "sort downloads"]):
        agent_gamma.dispatch("organize_workspace", query)
        return True

    # ── INQUIRY: Which Sir / Who is Sir ──────────────────────────────
    if any(k in low for k in ["which sir", "who is sir", "who is this sir", "who is your sir", "which sir?", "who is the sir", "what sir"]):
        speech_arbiter.speak("Sir Daksh.", priority=2)
        return True

    # ── GAMMA: God's Eye View / Orbital Satellite Reconnaissance ──────
    if any(k in low for k in [
        "god's eye", "gods eye", "orbital reconnaissance", "satellite view",
        "satellite recon", "track flights on globe", "open 3d globe", "tactical globe",
        "orbital watch", "open satellite map", "global tracking"
    ]) or re.search(r'\b(track|show|open)\b.*\b(satellite|globe|gods eye|god\'s eye|orbit)\b', low):
        agent_gamma.dispatch("gods_eye", query)
        return True

    # ADB Phone commands (ONLY active if NOT commercial)
    if not is_commercial:
        if any(k in low for k in ["lock down my phone", "lockdown phone", "lock my phone", "silence phone"]):
            agent_gamma.dispatch("phone_lockdown", query)
            return True

        if any(k in low for k in ["phone battery", "mobile battery", "check phone battery"]):
            agent_gamma.dispatch("phone_battery", query)
            return True

        if any(k in low for k in ["launch companion display", "open companion display", "companion display", "eagle display"]):
            agent_gamma.dispatch("companion_display", query)
            return True

    return False
