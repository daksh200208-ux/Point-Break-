POINT_BREAK_FAVORITE_PLAYLIST = [
    ("AC/DC Back In Black", "Back in Black by AC/DC"),
    ("Hans Zimmer Interstellar No Time For Caution", "the Interstellar theme by Hans Zimmer"),
    ("Daft Punk Tron Legacy The Son of Flynn", "The Son of Flynn by Daft Punk"),
    ("The Rolling Stones Paint It Black", "Paint It Black by The Rolling Stones"),
    ("Eminem Lose Yourself", "Lose Yourself by Eminem"),
    ("Linkin Park In The End", "In The End by Linkin Park")
]

GENRE_MOOD_MAP = [
    (r'\b(hindi\s+songs?|hindi\s+music|a\s+hindi\s+song|bollywood\s+songs?|bollywood\s+music)\b', "trending hindi songs playlist", "trending Hindi hits"),
    (r'\b(punjabi\s+songs?|punjabi\s+music|a\s+punjabi\s+song)\b', "latest punjabi hits playlist", "latest Punjabi tracks"),
    (r'\b(romantic\s+songs?|love\s+songs?|romantic\s+music)\b', "best romantic love songs playlist", "romantic melodies"),
    (r'\b(sad\s+songs?|emotional\s+songs?|heartbreak\s+songs?)\b', "heart touching sad songs playlist", "soulful melancholic tracks"),
    (r'\b(party\s+songs?|dance\s+songs?|club\s+music|club\s+songs?)\b', "top party dance songs playlist", "high energy party anthems"),
    (r'\b(lofi|lo-fi|lofi\s+beats?|chill\s+beats?|study\s+beats?)\b', "lofi hip hop chill study beats", "lofi chill beats"),
    (r'\b(rock\s+songs?|rock\s+music|classic\s+rock)\b', "best classic rock hits playlist", "legendary rock hits"),
    (r'\b(english\s+songs?|pop\s+songs?|pop\s+music|top\s+hits)\b', "top billboard pop hits playlist", "global pop chart-toppers"),
    (r'\b(bhojpuri\s+songs?|bhojpuri\s+music)\b', "top bhojpuri hits", "top Bhojpuri hits"),
    (r'\b(tamil\s+songs?|telugu\s+songs?|south\s+songs?)\b', "top south indian hits playlist", "top South Indian hits")
]

def resolve_intelligent_media_selection(raw_query: str, owner_name: str = "sir"):
    """
    Resolves human-nuanced music requests:
    Strips emotional fluff ('cause i am bored', 'because i am tired', 'to relax', 'for me'),
    maps genre/mood intents ('a hindi song' -> 'trending hindi songs playlist'),
    and handles AI favorite playlist choices with high-fidelity streaming.
    """
    import random, re
    low = raw_query.lower().strip()
    
    # 1. AI Autonomous Choice / Personality Playlist Check
    ai_choice_patterns = [
        r'\b(song\s+you\s+wanna\s+play|song\s+you\s+want\s+to\s+play|song\s+you\s+want\s+to|any\s*song\s+you\s+wanna\s+play|any\s*song\s+you\s+like|song\s+you\s+like|your\s+favorite\s+song|your\s+choice|whatever\s+you\s+want|whatever\s+you\s+like|something\s+good|something\s+nice|some\s+music|any\s*song|random\s+song|surprise\s+me|pick\s+a\s+song|pick\s+something|play\s+something)\b',
        r'^(?:play|stream|listen\s+to|put\s+on)\s+(?:a\s+)?(?:song|music|track|tracks|something)?$'
    ]
    if any(re.search(p, low) for p in ai_choice_patterns):
        track, display = random.choice(POINT_BREAK_FAVORITE_PLAYLIST)
        spoken = f"Excellent choice, {owner_name}. Pulling from my personal playlist: streaming {display}."
        return track, spoken

    # 2. Strip assistant prefixes & politeness
    clean = re.sub(r'^(?:hey\s+|ok\s+|yo\s+|bro\s+)?(?:point\s*break|pointbreak|tars|jarvis)?[\s,\-:]*', '', raw_query, flags=re.I).strip()
    clean = re.sub(r'^(?:please\s+|can\s+you\s+|could\s+you\s+|just\s+|play\s+on\s+youtube\s+|play\s+me\s+|play\s+song\s+|play\s+track\s+|play\s+music\s+|play\s+|stream\s+|listen\s+to\s+|watch\s+on\s+youtube\s+|watch\s+)', '', clean, flags=re.I).strip()

    # 3. Strip conversational fluff / emotions / sentiment reasons
    fluff_patterns = [
        r'\b(?:cause|because|coz|as|since)\s+(?:i\s+am|i\'m|im)\s+(?:bored|tired|sad|happy|stressed|exhausted|depressed|excited|alone|working|studying|coding|chilling|relaxing)\b',
        r'\b(?:to\s+make\s+me\s+feel\s+good|to\s+relax|to\s+chill|to\s+sleep|to\s+focus|to\s+dance|to\s+workout|to\s+study)\b',
        r'\b(?:for\s+me|right\s+now|pls|please|bro|sir)\b'
    ]
    for fp in fluff_patterns:
        clean = re.sub(fp, ' ', clean, flags=re.I).strip()

    # 4. Strip trailing platform indicators
    clean = re.sub(r'[\s,\-:]+(?:on\s+youtube|in\s+youtube|from\s+youtube|on\s+yt|on\s+spotify)$', '', clean, flags=re.I).strip()
    clean = clean.strip(" ,.:;!?\"'\`-_")
    clean = re.sub(r'\s+', ' ', clean).strip()

    # 5. Check if query matches a curated Genre / Mood / Language
    for pat, yt_search, spoken_genre in GENRE_MOOD_MAP:
        if re.search(pat, clean, flags=re.I):
            spoken = f"Streaming {spoken_genre} for you on YouTube, {owner_name}."
            return yt_search, spoken

    # 6. Fallback if clean query is empty or too short
    if not clean or len(clean) < 2:
        track, display = random.choice(POINT_BREAK_FAVORITE_PLAYLIST)
        spoken = f"Playing {display} for you, {owner_name}."
        return track, spoken

    spoken = f"Streaming {clean.title()} on YouTube."
    return clean, spoken

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
                elif t_type == "draft_email":
                    self.draft_and_stage_email(q)
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

    def draft_and_stage_email(self, query: str):
        speech_arbiter.speak("Drafting and polishing your email with formal grievance formatting, sir...", priority=2)
        try:
            from tars_email_copilot import email_copilot
            email_copilot.generate_and_stage_email(
                user_prompt=query,
                speak_fn=lambda msg: speech_arbiter.speak(msg, priority=2),
                update_status_fn=None
            )
        except Exception as e:
            print("[ALPHA Email Draft Error]:", e)
            speech_arbiter.speak("Encountered an issue staging email draft, sir.", priority=2)

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
        speech_arbiter.speak("Synthesizing draft, sir...", priority=2)
        topic = re.sub(r'(?i)\b(write|draft|compose|ghostwrite|an\s+essay\s+on|an\s+article\s+on|a\s+letter\s+to|a\s+formal\s+mail\s+to|a\s+mail\s+to|about|for)\b', ' ', query)
        topic = re.sub(r'\s+', ' ', topic).strip()
        try:
            import google.generativeai as genai
            model = genai.GenerativeModel("gemini-3.5-flash-lite")
            res = model.generate_content(f"Write a crisp, highly articulate, professional, ready-to-use piece for: {topic}\nInclude proper greeting, body, formatting, and sign-off.")
            text = res.text.strip()
            
            # 1. Push to Response Monolith on HUD
            if blackboard.update_status_fn:
                try:
                    blackboard.update_status_fn({"last_monolith_response": text})
                except Exception:
                    pass
            
            # 2. Copy to clipboard
            import pyperclip
            pyperclip.copy(text)
            
            # 3. If Notepad or editor is in foreground, paste it
            speech_arbiter.speak("Sir, I have compiled your draft and rendered it directly in the Response Monolith.", priority=2)
        except Exception as e:
            print("[ALPHA Ghostwriter] Error:", e)
            speech_arbiter.speak("Encountered an error compiling your draft, sir.", priority=2)

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
                    err = res.get("error", "processing failed")
                    speech_arbiter.speak(f"Encountered an issue compiling the dossier report: {err}", priority=2)
            else:
                speech_arbiter.speak("Dossier engine module is offline. Unable to compile the report, sir.", priority=2)
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
                    self.order_food_cmd(q)
                elif t_type == "booking_transaction":
                    self.booking_transaction_cmd(q)
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
        owner_name = "Operator" if getattr(self, 'is_commercial', False) else "Daksh"
        if "spotify" in query.lower():
            from pointbreak_spotify import spotify_engine
            spotify_engine.play_track(query, speak_fn=lambda m: speech_arbiter.speak(m, priority=2), owner_name=owner_name)
            return
        clean_song, spoken_msg = resolve_intelligent_media_selection(query, owner_name=owner_name)
        speech_arbiter.speak(spoken_msg, priority=2)
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(clean_song)}"
        try:
            import pywhatkit
            pywhatkit.playonyt(clean_song)
        except Exception as e:
            webbrowser.open(url)
            return

        q_clean = re.sub(r'(?i)\b(play|stream|listen\s+to|watch|on\s+youtube|youtube)\b', ' ', query)
        q_clean = re.sub(r'\s+', ' ', q_clean).strip()
        speech_arbiter.speak(f"Streaming {q_clean} on YouTube.", priority=2)
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q_clean)}"
        webbrowser.open(url)

    def send_whatsapp(self, query: str):
        low = query.lower().strip()
        voice_triggers = [
            "voice message", "voice note", "voicemail", "voice mail", "audio message",
            "audio note", "send a voice", "voice msg", "send voice"
        ]
        is_voice = any(k in low for k in voice_triggers)
        if low in ["open whatsapp", "launch whatsapp", "start whatsapp", "whatsapp web", "open wa"]:
            speech_arbiter.speak("Opening WhatsApp portal on web...", priority=2)
            webbrowser.open("https://web.whatsapp.com")
            return

        import jarvis
        if is_voice:
            jarvis.send_whatsapp_voice_note_cmd(query)
        else:
            jarvis.send_whatsapp_message_cmd(query)

    def read_world_news_protocol(self, query: str):
        import urllib.request, urllib.parse
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

    def order_food_cmd(self, query: str):
        try:
            from pointbreak_transactions import transaction_engine
            transaction_engine.dispatch_transaction(
                command=query,
                speak_fn=lambda txt: speech_arbiter.speak(txt, priority=2)
            )
        except Exception as e:
            print(f"[BETA Food Order Error]: {e}")
            speech_arbiter.speak("Opening ordering portal for you.", priority=2)
            if "zomato" in query.lower():
                webbrowser.open("https://www.zomato.com")
            else:
                webbrowser.open("https://www.swiggy.com")

    def booking_transaction_cmd(self, query: str):
        try:
            from pointbreak_transactions import transaction_engine
            transaction_engine.dispatch_transaction(
                command=query,
                speak_fn=lambda txt: speech_arbiter.speak(txt, priority=2)
            )
        except Exception as e:
            print(f"[BETA Booking Transaction Error]: {e}")
            speech_arbiter.speak("Transaction booking engine encountered an issue.", priority=2)


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
                elif t_type == "cctv_matrix":
                    self.show_cctv_matrix(q)
            except Exception as e:
                print(f"[GAMMA Error] {t_type}: {e}")
            finally:
                blackboard.update_agent("GAMMA", "IDLE")
                self.task_queue.task_done()

    def launch_gods_eye(self, query: str):
        try:
            from pointbreak_godseye import gods_eye_bridge
            gods_eye_bridge.launch(query, speak_fn=lambda txt: speech_arbiter.speak(txt, priority=2))
        except Exception as e:
            print("[GAMMA God's Eye Error]:", e)
            speech_arbiter.speak("Unable to launch God's Eye View satellite matrix.", priority=2)

    def show_cctv_matrix(self, query: str):
        try:
            import pointbreak_cctv
            pointbreak_cctv.cctv_engine.launch_cctv_recon(query, speak_fn=lambda txt: speech_arbiter.speak(txt, priority=2))
        except Exception as e:
            print("[GAMMA CCTV Error]:", e)
            speech_arbiter.speak("Unable to access optical CCTV surveillance feeds.", priority=2)

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

    # ── GMAIL VISION & IN-THREAD TAKEOVER ───────────────────────────
    if any(k in low for k in ["open that mail", "open it up", "open this mail", "open the mail", "open unread mail", "open the email"]):
        try:
            from pointbreak_takeover import takeover_engine
            import jarvis
            takeover_engine.open_and_focus_email(speak_fn=lambda txt: speech_arbiter.speak(txt, priority=2), listen_fn=getattr(jarvis, "take_command", None))
            return True
        except Exception as e:
            print(f"[Swarm Email Open Error]: {e}")

    if any(k in low for k in ["read it out", "read the mail", "read this mail", "read the email", "what does the mail say", "what is the mail about", "read mail"]) and "news" not in low:
        try:
            from pointbreak_takeover import takeover_engine
            import jarvis
            takeover_engine.read_and_summarize_open_email(speak_fn=lambda txt: speech_arbiter.speak(txt, priority=2), listen_fn=getattr(jarvis, "take_command", None))
            return True
        except Exception as e:
            print(f"[Swarm Email Read Error]: {e}")

    if any(k in low for k in ["respond to the mail", "reply to the mail", "reply to email", "draft a reply", "respond to email", "answer the mail"]):
        try:
            from pointbreak_takeover import takeover_engine
            import jarvis
            takeover_engine.respond_to_open_email(user_intent=query, speak_fn=lambda txt: speech_arbiter.speak(txt, priority=2), listen_fn=getattr(jarvis, "take_command", None))
            return True
        except Exception as e:
            print(f"[Swarm Email Reply Error]: {e}")

    # ── GMAIL WEB INBOX OPEN (DIRECT WEB NAVIGATION) ──
    if low in [
        "open mails", "open mail", "open gmail", "open my mail", "open my mails",
        "open my emails", "open my email", "open inbox", "open my inbox",
        "check mails", "check mail", "check gmail", "check email", "check emails",
        "check my mail", "check my mails", "check my email", "check my emails",
        "check inbox", "check my inbox", "mails", "mail", "gmail", "inbox"
    ] or re.search(r'^(?:open|launch|show|go\s+to)\s+(?:my\s+)?(?:gmail|mails?|emails?|inbox)$', low):
        import webbrowser
        webbrowser.open("https://mail.google.com/mail/u/0/#inbox")
        speech_arbiter.speak("Opening your Gmail inbox on web, sir.", priority=2)
        return True

    # ── TIER 2: SUPERPOWERS SOFTWARE FACTORY ──────────────────────────
    # Voice-commanded autonomous software engineering factory engine
    _swe_build_match = any(k in low for k in [
        "build app", "build an app", "build a app", "create app", "create an app",
        "code project", "code a project", "engineer a", "develop tool", "develop a tool",
        "build software", "build a software", "superpowers build", "build me",
        "build a script", "build script", "create a script", "code a script",
        "build a program", "build program", "create a program", "make an app",
        "make a tool", "make a script", "build a website", "build website",
        "create a website", "build a bot", "create a bot", "build bot",
        "build a cli", "build cli", "build a server", "build server",
        "build a game", "code a game", "build a library", "build library",
        "build a package", "build package", "build an api", "build api",
    ]) or re.search(r'\b(?:build|create|develop|code|engineer|make)\b.*\b(?:app|tool|script|program|website|bot|server|api|library|package|project|software)\b', low)

    _swe_status_match = any(k in low for k in [
        "project status", "status of app", "status of project", "how is the app",
        "how is the project", "how is the build", "engineering status",
        "check on the project", "check on the app", "app status",
        "how is the app going", "how is my project", "is the app done",
        "is the project done", "is the build done", "cancel project",
        "cancel the project", "cancel engineering", "stop the build",
        "cancel build", "cancel the build"
    ])

    if _swe_build_match or _swe_status_match:
        try:
            from pointbreak_superpowers_bridge import superpowers_factory

            if _swe_status_match:
                # Status query or cancel
                if any(k in low for k in ["cancel project", "cancel the project", "cancel engineering", "stop the build", "cancel build", "cancel the build"]):
                    superpowers_factory.cancel_project(speak_fn=speak_fn)
                else:
                    status = superpowers_factory.get_project_status()
                    msg = status.get('message', 'No project status available.')
                    speech_arbiter.speak(msg, priority=2)
            else:
                # Extract goal from command
                goal = re.sub(
                    r'^(?:point\s*break|tars|jarvis)?[\s,\-:]*(?:can\s+you\s+|please\s+)?',
                    '', query, flags=re.I
                ).strip()
                superpowers_factory.dispatch_engineering_task(
                    goal=goal,
                    speak_fn=speak_fn,
                    update_status_fn=update_status_fn
                )
            return True
        except Exception as e:
            print(f"[Superpowers Bridge Error]: {e}")
            speech_arbiter.speak(f"Software engineering dispatch error: {e}", priority=2)
            return True

    # ── ALPHA DOMAIN (Career, Writing, Email Drafting & Triage, Dossiers, Vision) ──
    if (
        any(k in low for k in [
            "draft email", "draft an email", "write an email", "write email",
            "compose email", "compose an email", "polish email", "polish draft",
            "polish this draft", "polish policybazaar", "policybazaar.com", "policybazaar",
            "draft a mail", "write a mail", "compose a mail", "grievance email",
            "health insurance email", "health insurance grievance", "email to",
            "send email to", "draft to"
        ]) or
        re.search(r'\bmail\s+to\b', low) or
        re.search(r'\b(draft|write|compose|polish)\b.*\b(emails?|mails?|grievance|draft)\b', low)
    ) and not any(v in low for v in ["voice", "voicemail", "voice mail", "voice note", "voice message", "audio", "whatsapp"]):
        agent_alpha.dispatch("draft_email", query)
        return True

    if re.search(r'\b(triage|unread|check|scan|read\s+my|show\s+my|open\s+my)\b.*\b(emails?|mails?|inbox)\b', low) or 'triage' in low or 'unread email' in low or 'scan inbox' in low:
        agent_alpha.dispatch("triage_email", query)
        return True

    if re.search(r'\b(find|hunt|search|scout|look\s+for)\b.*\b(jobs?|internships?|openings?)\b', low) or 'find jobs' in low or 'find internships' in low:
        agent_alpha.dispatch("hunt_jobs", query)
        return True

    if re.search(r'\b(ghostwrite|draft\s+essay|compose\s+draft|write\s+an\s+essay|write\s+an\s+article|write\s+a\s+letter)\b', low):
        agent_alpha.dispatch("ghostwriter", query)
        return True

    if any(k in low for k in [
        "research dossier", "generate dossier", "pdf report on", "compile research on",
        "dossier on", "dossier about", "dossier for", "make a dossier", "create a dossier",
        "intel report on", "intelligence report", "compile dossier"
    ]) or re.search(r'\b(dossier|intel\s+report)\b', low):
        agent_alpha.dispatch("dossier", query)
        return True

    if any(k in low for k in ["explain screen", "what is on my screen", "solve screen", "debug screen"]):
        agent_alpha.dispatch("explain_screen", query)
        return True

    # ── BETA MEDIA: Play music/video ──────────────────────────────
    if re.search(r'\b(play|stream|listen\s+to|watch|put\s+on)\b', low) and not any(k in low for k in ['amazon', 'flipkart', 'myntra', 'email', 'mail', 'file', 'todo', 'job', 'intern', 'chess', 'game', 'take over', 'takeover', 'next move', 'best move']):
        agent_beta.dispatch("media_playback", query)
        return True

        # ── BETA DOMAIN (Commerce, Media, Comms, News, Food) ─────────────
    if any(k in low for k in ['amazon', 'flipkart', 'myntra', 'price of', 'check price', 'how much is', 'snipe price']) or re.search(r'\b(search|look|check|find|buy|order)\b.*\b(on\s+amazon|on\s+flipkart|on\s+myntra|amazon|flipkart|myntra)\b', low):
        agent_beta.dispatch("ecom_sniper", query)
        return True

    if any(k in low for k in ["world news", "news briefing", "global news", "read the news", "read me the news", "daily news", "news about", "news on", "latest news"]) or re.search(r'\b(news|headlines)\b.*\b(about|on|regarding|for|today|latest)\b', low) or low.strip() == "news":
        agent_beta.dispatch("news_briefing", query)
        return True

    # ── BETA FOOD TRANSACTIONS & CROSS-PLATFORM SNIPER ───────────
    if (
        any(k in low for k in [
            "order food", "compare food", "zomato", "swiggy", "zinger burger", "zinger", "order pizza",
            "order coffee", "order biryani", "order burger", "which is cheaper", "whichever is cheaper",
            "compare on zomato and swiggy", "compare zomato and swiggy", "compare swiggy and zomato"
        ])
        or (("order" in low or "buy" in low or "get" in low or "compare" in low) and any(f in low for f in ["food", "burger", "pizza", "biryani", "zomato", "swiggy", "zinger", "kfc", "mcdonalds", "dominos", "meal", "coffee"]))
        or (any(low.startswith(f) for f in ["order ", "buy "]) and any(f in low for f in ["burger", "pizza", "biryani", "roll", "sandwich", "noodles", "cake", "ice cream"]))
    ):
        agent_beta.dispatch("order_food", query)
        return True

    # ── BETA TRAVEL & BOOKING TRANSACTIONS (IRCTC, Google Flights, MakeMyTrip) ──
    _is_train_booking = any(k in low for k in [
        "book train", "train ticket", "train to", "train from", "book irctc", "irctc ticket", "check train", "find train", "train tickets"
    ]) or re.search(r'\b(book|reserve|find)\b.*\b(train|railway|irctc)\b', low)

    _is_flight_booking = (any(k in low for k in [
        "book flight", "flight ticket", "flights to", "fly to", "air ticket", "airline ticket", "cheapest flight", "flight tickets"
    ]) or re.search(r'\b(book|reserve|find|cheapest)\b.*\b(flight|flights|airline|plane\s+ticket)\b', low)) and not any(k in low for k in ["game", "sim", "simulator"])

    if _is_train_booking or _is_flight_booking:
        agent_beta.dispatch("booking_transaction", query)
        return True

    if (
        any(k in low for k in [
            "open whatsapp", "whatsapp", "voice note", "voice message", "voicemail", "voice mail",
            "audio message", "audio note", "send a text", "send text"
        ]) or
        ("send" in low and any(w in low for w in ["message", "msg", "text", "voice", "note"])) or
        re.search(r'\b(message|text|msg|dm|ping)\s+to\b', low)
    ) and not any(k in low for k in ["email", "gmail", "amazon", "flipkart", "youtube", "order"]):
        agent_beta.dispatch("whatsapp", query)
        return True

    # ── GAMMA DOMAIN (Tactical OS, Files, Alarms, Workspace, ADB) ─────
    if re.search(r'\b(find|locate|search|where\s+is\s+my|hunt)\b.*\b(file|document|pdf|resume|aadhaar|pan|photo)\b', low) or 'find file' in low or 'locate file' in low:
        agent_gamma.dispatch("hunt_files", query)
        return True

    if any(k in low for k in ["organize workspace", "clean downloads", "organize downloads", "sort downloads"]):
        agent_gamma.dispatch("organize_workspace", query)
        return True

    # ── GAMMA: God's Eye View / Orbital Satellite Reconnaissance ──────
    if any(k in low for k in [
        "god's eye", "gods eye", "god eye", "godseye", "orbital reconnaissance", "satellite view",
        "satellite recon", "track flights on globe", "open 3d globe", "tactical globe",
        "orbital watch", "open satellite map", "global tracking"
    ]) or re.search(r'\b(track|show|open)\b.*\b(satellite|globe|gods?\s*eye|orbit)\b', low):
        agent_gamma.dispatch("gods_eye", query)
        return True

    # ── GAMMA: Global CCTV / Traffic Cameras Reconnaissance ──────────
    if any(k in low for k in [
        "cctv", "traffic cams", "traffic cameras", "traffic camera", "surveillance cams",
        "webcams", "live cams", "street cameras", "highway cameras"
    ]) or re.search(r'\b(show|open|view|watch|stream|feed)\b.*\b(cctv|traffic\s+cams?|traffic\s+cameras?|cameras?|webcams?)\b', low):
        agent_gamma.dispatch("cctv_matrix", query)
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
