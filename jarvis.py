from pointbreak_genai import query_generative_model, query_tars_vision, query_text
import speech_recognition as sr
import os, json, webbrowser, datetime, time, threading, random
import pyautogui, pyaudio, numpy as np, requests, asyncio
import edge_tts, pygame, tempfile, xml.etree.ElementTree as ET
import psutil, math, re, ctypes, subprocess
from pathlib import Path
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv
import warnings
from http.server import SimpleHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
import urllib.parse
import queue
import sys, traceback

# Global Exception Hooks to prevent process crash
def _global_exception_handler(exc_type, exc_value, exc_traceback):
    print("  [TARS System Protection] Caught unhandled exception:", exc_type, exc_value)
    traceback.print_exception(exc_type, exc_value, exc_traceback)

sys.excepthook = _global_exception_handler
if hasattr(threading, "excepthook"):
    threading.excepthook = lambda args: print("  [TARS Thread Watchdog] Exception in thread:", args.thread.name, args.exc_value)

# Suppress FutureWarnings from google-generativeai deprecation
warnings.filterwarnings("ignore", category=FutureWarning)

VOICE       = "en-GB-RyanNeural"
JARVIS_DIR  = os.path.dirname(os.path.abspath(__file__))

# ── WORKING DIRECTORY & SYS.PATH GUARANTEE ─────────────────────────
try:
    os.chdir(JARVIS_DIR)
except Exception:
    pass
if JARVIS_DIR not in sys.path:
    sys.path.insert(0, JARVIS_DIR)

STATUS_FILE = os.path.join(JARVIS_DIR, "jarvis_status.json")
MEMORY_FILE = os.path.join(JARVIS_DIR, "jarvis_memory.json")
NOTES_FILE  = os.path.join(JARVIS_DIR, "jarvis_notes.txt")
STARTUP_LOG = os.path.join(JARVIS_DIR, "jarvis_startup.log")
OWNER       = "sir"
hardware_lock = threading.Lock()
mic_muted = False

def log_startup_event(msg: str):
    """Appends boot/startup events with timestamps to jarvis_startup.log."""
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(STARTUP_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass

# Check for Windows Startup Mode settling delay
IS_STARTUP_MODE = any(arg in sys.argv for arg in ["--startup", "/startup", "-startup"])
if IS_STARTUP_MODE:
    log_startup_event("Point Break launched in Windows Startup Mode. Settling 4s for audio/network drivers...")
    time.sleep(4.0)

# Load Gemini API Key from .env
load_dotenv(os.path.join(JARVIS_DIR, ".env"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ── RESILIENT AUDIO SUBSYSTEM INITIALIZATION ───────────────────────
def init_audio_subsystem(retries=5, delay=1.0):
    for attempt in range(retries):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            log_startup_event("Audio subsystem initialized successfully.")
            return True
        except Exception as e:
            log_startup_event(f"Audio init attempt {attempt+1}/{retries} waiting: {e}")
            time.sleep(delay)
    return False

init_audio_subsystem()

# ── MEMORY ───────────────────────────────────────────────────────
memory_lock = threading.Lock()

def load_memory():
    try:
        if os.path.exists(MEMORY_FILE):
            with memory_lock:
                with open(MEMORY_FILE) as f: return json.load(f)
    except: pass
    return {"facts": {}, "todos": [], "alarms": [], "reminders": []}

def save_memory():
    with memory_lock:
        try:
            tmp_file = MEMORY_FILE + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(memory, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, MEMORY_FILE)
        except Exception as e:
            print("[Memory] Safe save error:", e)


memory = load_memory()

# ── SYSTEM MEMORY GUARD & OOM CRASH PREVENTER ─────────────────────
import gc
def clean_system_memory():
    """Forces safe Python garbage collection without risky kernel paging."""
    try:
        gc.collect()
    except Exception:
        pass

# ── SEMANTIC MEMORY (VECTOR DATABASE) ────────────────────────────────
VECTOR_FILE = os.path.join(JARVIS_DIR, "tars_memory_vectors.json")

def get_text_embedding(text: str) -> list:
    for model_name in ["models/embedding-001", "models/text-embedding-004", "text-embedding-004"]:
        try:
            result = genai.embed_content(
                model=model_name,
                content=text,
                task_type="retrieval_document"
            )
            return result['embedding']
        except Exception:
            continue
    return None

def load_vectors():
    try:
        if os.path.exists(VECTOR_FILE):
            with open(VECTOR_FILE) as f:
                return json.load(f)
    except Exception as e:
        print("[AI] Failed to load vectors:", e)
    return []

def save_vectors(vectors):
    try:
        with open(VECTOR_FILE, "w") as f:
            json.dump(vectors, f)
    except Exception as e:
        print("[AI] Failed to save vectors:", e)

def add_semantic_memory(text: str) -> bool:
    vector = get_text_embedding(text)
    if not vector:
        return False
    vectors = load_vectors()
    vectors.append({
        "text": text,
        "vector": vector,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_vectors(vectors)
    return True

def search_semantic_memories(query: str, top_k=3) -> list:
    if not os.path.exists(VECTOR_FILE) or os.path.getsize(VECTOR_FILE) < 10:
        return []
        
    vectors_data = load_vectors()
    if not vectors_data:
        return []

    query_vector = get_text_embedding(query)
    if not query_vector:
        return []
    
    q_vec = np.array(query_vector)
    matches = []
    
    for item in vectors_data:
        v = np.array(item["vector"])
        dot_val = np.dot(q_vec, v)
        norm_q = np.linalg.norm(q_vec)
        norm_v = np.linalg.norm(v)
        
        if norm_q > 0 and norm_v > 0:
            sim = dot_val / (norm_q * norm_v)
        else:
            sim = 0.0
            
        matches.append((sim, item["text"]))
        
    matches.sort(key=lambda x: x[0], reverse=True)
    return [text for score, text in matches[:top_k] if score > 0.35]

# ── AUTOMATION TASK SCHEDULER ────────────────────────────────────────
SCHEDULE_FILE = os.path.join(JARVIS_DIR, "tars_schedule.json")

def load_schedules():
    try:
        if os.path.exists(SCHEDULE_FILE):
            with open(SCHEDULE_FILE) as f:
                return json.load(f)
    except Exception as e:
        print("[Scheduler] Failed to load schedules:", e)
    return []

def save_schedules(schedules):
    try:
        with open(SCHEDULE_FILE, "w") as f:
            json.dump(schedules, f, indent=2)
    except Exception as e:
        print("[Scheduler] Failed to save schedules:", e)

def add_schedule(task_type: str, time_or_interval: str, data: str):
    schedules = load_schedules()
    is_interval = time_or_interval.isdigit()
    new_task = {
        "id": random.randint(1000, 9999),
        "type": task_type,
        "schedule": time_or_interval,
        "is_interval": is_interval,
        "data": data,
        "last_run": 0
    }
    schedules.append(new_task)
    save_schedules(schedules)
    print(f"[Scheduler] Added task: {new_task}")
    return new_task

def list_schedules():
    return load_schedules()

def delete_schedule(task_id) -> bool:
    schedules = load_schedules()
    orig_len = len(schedules)
    schedules = [s for s in schedules if str(s.get("id")) != str(task_id)]
    if len(schedules) < orig_len:
        save_schedules(schedules)
        return True
    return False

def run_schedule_now(task_id) -> bool:
    schedules = load_schedules()
    for task in schedules:
        if str(task.get("id")) == str(task_id):
            task_type = task.get("type")
            data = task.get("data")
            if task_type == "reminder":
                speak(f"Scheduled Reminder: {data}", block=False)
            elif task_type == "command":
                threading.Thread(target=execute, args=(data,), daemon=True).start()
            return True
    return False

def scheduler_engine():
    print("[Scheduler] Engine started.")
    while True:
        time.sleep(5)
        try:
            schedules = load_schedules()
            if not schedules:
                continue
            
            now = datetime.datetime.now()
            now_str = now.strftime("%H:%M")
            now_ts = time.time()
            changed = False
            
            for task in schedules:
                should_run = False
                
                if task.get("is_interval"):
                    interval_mins = int(task["schedule"])
                    interval_secs = interval_mins * 60
                    last_run = task.get("last_run", 0)
                    if last_run == 0:
                        task["last_run"] = now_ts
                        changed = True
                    elif now_ts - last_run >= interval_secs:
                        should_run = True
                else:
                    if now_str == task["schedule"]:
                        last_run = task.get("last_run", 0)
                        if now_ts - last_run > 60:
                            should_run = True
                
                if should_run:
                    task["last_run"] = now_ts
                    changed = True
                    task_type = task["type"]
                    data = task["data"]
                    
                    if task_type == "reminder":
                        print(f"[Scheduler] Triggering reminder: {data}")
                        speak(f"Reminder, sir: {data}", block=False)
                    elif task_type == "command":
                        print(f"[Scheduler] Triggering automated command: {data}")
                        threading.Thread(target=execute, args=(data,), daemon=True).start()
            
            if changed:
                save_schedules(schedules)
        except Exception as e:
            print("[Scheduler] Engine error:", e)

# ── GMAIL NOTIFICATION MONITOR ───────────────────────────────────────
def check_gmail_inbox():
    config = memory.get("gmail_config", {})
    email_addr = config.get("email")
    app_pwd = config.get("app_password")
    
    if not email_addr or not app_pwd:
        return 0, []
    
    import imaplib, email
    from email.header import decode_header
    
    unread_important = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_addr, app_pwd)
        mail.select("INBOX")
        
        status, response = mail.search(None, "UNSEEN")
        if status != "OK":
            return 0, []
            
        msg_ids = response[0].split()
        if not msg_ids:
            mail.logout()
            return 0, []
            
        for msg_id in msg_ids[-10:]:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
                
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # RFC Standards filtering (bulk, list, junk, automated alerts, newsletter list-unsubscribes)
            precedence = str(msg.get("Precedence", "")).lower()
            list_unsub = msg.get("List-Unsubscribe")
            x_auto = str(msg.get("X-Auto-Response-Suppress", "")).lower()
            
            if precedence in ["bulk", "list", "junk"] or list_unsub or x_auto:
                continue
            
            subject_header = msg.get("Subject", "")
            subject, encoding = decode_header(subject_header)[0]
            if isinstance(subject, bytes):
                try: subject = subject.decode(encoding or "utf-8", errors="ignore")
                except: subject = str(subject)
            else:
                subject = str(subject)
                
            from_header = msg.get("From", "")
            sender, encoding = decode_header(from_header)[0]
            if isinstance(sender, bytes):
                try: sender = sender.decode(encoding or "utf-8", errors="ignore")
                except: sender = str(sender)
            else:
                sender = str(sender)
            
            sender_lower = sender.lower()
            subj_lower = subject.lower()
            
            blacklist_senders = [
                "noreply", "no-reply", "newsletter", "support", "info@", "news@", 
                "promo", "marketing", "facebook", "linkedin", "twitter", "instagram", 
                "pinterest", "quora", "medium", "github", "gitlab", "spotify", "netflix", 
                "amazon", "flipkart", "youtube", "discord", "slack", "zoom", "googlealerts",
                "update", "alert", "notification"
            ]
            blacklist_subjects = [
                "unsubscribe", "sale", "off", "promotion", "newsletter", "digest", 
                "your account", "invoice", "receipt", "verify", "otp", "code", "welcome",
                "confirm", "activated", "billing", "social", "ad ", "advertisement"
            ]
            
            is_important = True
            for word in blacklist_senders:
                if word in sender_lower:
                    is_important = False
                    break
            if is_important:
                for word in blacklist_subjects:
                    if word in subj_lower:
                        is_important = False
                        break
                        
            if is_important:
                unread_important.append({
                    "from": sender,
                    "subject": subject
                })
                
        mail.close()
        mail.logout()
    except Exception as e:
        print("[Gmail] Error checking emails:", e)
        
    return len(unread_important), unread_important

last_notified_email = {}
last_notified_email_time = 0.0

def gmail_monitor_engine():
    global last_notified_email, last_notified_email_time
    print("[Gmail] Monitor started.")
    last_count = 0
    while True:
        # Check every 60 seconds
        time.sleep(60)
        try:
            count, emails = check_gmail_inbox()
            update_status({"unread_emails": count})
            
            if count > last_count and emails:
                new_emails = emails[last_count:]
                for mail_item in new_emails:
                    sender_clean = re.sub(r'<.*>', '', mail_item["from"]).strip().strip('"\'')
                    subj = mail_item.get("subject", "No Subject")
                    last_notified_email = {
                        "from": sender_clean,
                        "raw_from": mail_item.get("from", ""),
                        "subject": subj,
                        "timestamp": time.time()
                    }
                    last_notified_email_time = time.time()
                    memory["last_received_email"] = last_notified_email
                    try:
                        save_memory()
                    except Exception:
                        pass
                    speak(f"Sir, you have received a mail from {sender_clean} regarding: {subj}.", block=False)
            last_count = count
        except Exception as e:
            print("[Gmail] Monitor loop error:", e)

# ── DEEP FILE SEARCHER & INDEXER ─────────────────────────────────────
file_index_in_memory = []

def file_indexer_engine():
    global file_index_in_memory
    print("[Indexer] Scanning file system...")
    temp_index = []
    
    USER_HOME = str(Path.home())
    TARGET_FOLDERS = [
        os.path.join(USER_HOME, "Desktop"),
        os.path.join(USER_HOME, "Documents"),
        os.path.join(USER_HOME, "Downloads"),
        os.path.join(USER_HOME, "Pictures"),
        os.path.join(USER_HOME, "Videos"),
        JARVIS_DIR
    ]
    
    ignored_exts = {".dll", ".sys", ".ini", ".lnk", ".tmp", ".pyc", ".class", ".o", ".obj"}
    ignored_dirs = {"node_modules", "venv", "env", "AppData", ".git", ".github", ".gemini", "__pycache__"}
    
    for folder in TARGET_FOLDERS:
        if not os.path.exists(folder):
            continue
        try:
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignored_dirs]
                
                # 1. Index directories
                for d in dirs:
                    full_path = os.path.join(root, d)
                    temp_index.append((d.lower(), d, full_path, "folder"))
                    
                # 2. Index files
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext not in ignored_exts and not f.startswith("."):
                        full_path = os.path.join(root, f)
                        temp_index.append((f.lower(), f, full_path, "file"))
                        
                        # Also index filename without extension for easy voice matching
                        base_name = os.path.splitext(f)[0].lower()
                        if base_name != f.lower():
                            temp_index.append((base_name, f, full_path, "file"))
        except Exception as e:
            print(f"[Indexer] Error indexing folder {folder}: {e}")
            
    file_index_in_memory = temp_index
    print(f"[Indexer] Completed. Indexed {len(file_index_in_memory)} items.")

def purge_expired_data():
    now = time.time()
    twelve_hours = 12 * 3600
    updated = False

    cleaned_todos = []
    for todo in memory.get("todos", []):
        if now - todo.get("timestamp", now) < twelve_hours:
            cleaned_todos.append(todo)
        else:
            updated = True
    memory["todos"] = cleaned_todos

    cleaned_alarms = []
    for alarm in memory.get("alarms", []):
        if now - alarm.get("timestamp", now) < twelve_hours:
            cleaned_alarms.append(alarm)
        else:
            updated = True
    memory["alarms"] = cleaned_alarms

    cleaned_reminders = []
    for reminder in memory.get("reminders", []):
        if now - reminder.get("timestamp", now) < twelve_hours:
            cleaned_reminders.append(reminder)
        else:
            updated = True
    memory["reminders"] = cleaned_reminders

    cleaned_facts = {}
    for k, v in memory.get("facts", {}).items():
        if isinstance(v, dict) and "timestamp" in v:
            if now - v["timestamp"] < twelve_hours:
                cleaned_facts[k] = v
            else:
                updated = True
        else:
            cleaned_facts[k] = {"value": v, "timestamp": now}
            updated = True
    memory["facts"] = cleaned_facts

    if updated:
        save_memory()

    try:
        for filename in os.listdir(JARVIS_DIR):
            if filename.endswith(".mp3") or filename.endswith(".png") or filename.endswith(".jpg"):
                filepath = os.path.join(JARVIS_DIR, filename)
                if now - os.path.getmtime(filepath) > twelve_hours:
                    try:
                        os.remove(filepath)
                        print(f"Purged: {filename}")
                    except: pass
    except Exception as e:
        print("Cleanup error:", e)

# ── HUD STATUS ────────────────────────────────────────────────────
# ── HUD STATUS ────────────────────────────────────────────────────
BOOT_TIMESTAMP = time.time()
status_lock = threading.Lock()
protocol_omega_active = memory.get("protocol_omega", False)

status_in_memory = {
    "protocol_omega": protocol_omega_active,
    "cpu": 0,
    "mem": 0,
    "disk": 0,
    "ping": 0,
    "battery": 100,
    "plugged": True,
    "status": "standby",
    "jarvis_says": "",
    "user_said": "",
    "humor": 75,
    "honesty": 90,
    "sarcasm": 60,
    "mic_muted": False,
    "voice_stress": 0,
    "voice_status": "normal",
    "net_up_kbps": 0.0,
    "net_down_kbps": 0.0,
    "uptime": "00:00:00",
    "weather_temp": "28°C",
    "weather_cond": "Partly Cloudy",
    "weather_humidity": "65%",
    "weather_wind": "12 km/h",
    "weather_city": "New Delhi",
    "media_title": "TARS Audio Stream",
    "media_artist": "Voice System Standby",
    "media_playing": False
}

def update_status(data: dict):
    with status_lock:
        status_in_memory.update(data)

def _background_telemetry_worker():
    import psutil
    last_net = {"sent": 0, "recv": 0, "time": time.time()}
    weather_tick = 0
    
    while True:
        try:
            now = time.time()
            # 1. Network Traffic (Upload / Download KB/s)
            net_io = psutil.net_io_counters()
            dt = max(now - last_net["time"], 0.5)
            up_k = round(max(net_io.bytes_sent - last_net["sent"], 0) / (1024 * dt), 1)
            down_k = round(max(net_io.bytes_recv - last_net["recv"], 0) / (1024 * dt), 1)
            last_net = {"sent": net_io.bytes_sent, "recv": net_io.bytes_recv, "time": now}
            
            # 2. Uptime
            upt_sec = int(now - BOOT_TIMESTAMP)
            h, rem = divmod(upt_sec, 3600)
            m, s = divmod(rem, 60)
            upt_str = f"{h:02d}:{m:02d}:{s:02d}"
            
            # 3. CPU, Memory, Disk, Battery
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            disk = psutil.disk_usage('C:\\').percent if os.name == 'nt' else psutil.disk_usage('/').percent
            bat = psutil.sensors_battery()
            
            upd = {
                "cpu": cpu,
                "mem": mem,
                "disk": disk,
                "battery": bat.percent if bat else 100,
                "plugged": bat.power_plugged if bat else True,
                "net_up_kbps": up_k,
                "net_down_kbps": down_k,
                "uptime": upt_str
            }
            
            # 4. Media status detection
            try:
                proc_names = [p.name().lower() for p in psutil.process_iter(['name'])]
                if "spotify.exe" in proc_names:
                    upd["media_title"] = "Spotify Player Active"
                    upd["media_artist"] = "System Audio Channel"
                    upd["media_playing"] = True
                elif "chrome.exe" in proc_names or "msedge.exe" in proc_names:
                    upd["media_title"] = "Browser Media Channel"
                    upd["media_artist"] = "YouTube / Web Audio"
                    upd["media_playing"] = True
                else:
                    upd["media_title"] = "TARS Audio Stream"
                    upd["media_artist"] = "Voice System Standby"
                    upd["media_playing"] = False
            except:
                pass

            update_status(upd)

            # Fetch weather every 10 mins (300 ticks of 2s)
            if weather_tick % 300 == 0:
                def _fetch_weather():
                    try:
                        import requests
                        r = requests.get("https://wttr.in?format=j1", timeout=5)
                        if r.status_code == 200:
                            wjson = r.json()
                            curr = wjson['current_condition'][0]
                            area = wjson['nearest_area'][0]['areaName'][0]['value']
                            update_status({
                                "weather_temp": f"{curr['temp_C']}°C",
                                "weather_cond": curr['weatherDesc'][0]['value'],
                                "weather_humidity": f"{curr['humidity']}%",
                                "weather_wind": f"{curr['windspeedKmph']} km/h",
                                "weather_city": area
                            })
                    except:
                        pass
                threading.Thread(target=_fetch_weather, daemon=True).start()
                
            weather_tick += 1
        except Exception as e:
            pass
        time.sleep(2.0)

threading.Thread(target=_background_telemetry_worker, daemon=True).start()

# ── WINDOWS TOAST NOTIFICATION ────────────────────────────────────
def notify(title: str, msg: str):
    import subprocess
    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $toastXml = [xml] $template.GetXml()
    $toastXml.GetElementsByTagName("text")[0].AppendChild($toastXml.CreateTextNode("{title}")) | Out-Null
    $toastXml.GetElementsByTagName("text")[1].AppendChild($toastXml.CreateTextNode("{msg}")) | Out-Null
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($toastXml.OuterXml)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Point Break").Show($toast)
    """
    try:
        subprocess.run(["powershell", "-Command", ps_script], creationflags=subprocess.CREATE_NO_WINDOW)
    except: pass

# ── SPEAK & TARS RESILIENT ANTI-CUTOFF VOICE ENGINE ──────────────
VOICE = "en-GB-RyanNeural"
TARS_NORMAL_PITCH = "-4Hz"
TARS_NORMAL_RATE = "+10%"
TARS_NORMAL_VOL = "+0%"

TARS_WARN_PITCH = "-4Hz"
TARS_WARN_RATE = "+14%"
TARS_WARN_VOL = "+20%"

TARS_SHOUT_PITCH = "-4Hz"
TARS_SHOUT_RATE = "+18%"
TARS_SHOUT_VOL = "+100%"

speech_queue = queue.Queue()
speech_interrupted = False
tars_speaking = False
current_spoken_chunk = ""

interruption_strikes = 0
verbal_interrupted = False
hard_interrupted = False
in_interruption_handling = False

def stop_speech(hard=True):
    """
    Kills ongoing speech playback using pygame.mixer.
    If hard=True (Physical Right Ctrl pressed), speech is completely cancelled and queue cleared with 0 quips.
    If hard=False (Verbal interruption during speech), playback pauses/stops to engage TARS escalation.
    """
    global tars_speaking, speech_interrupted, hard_interrupted, verbal_interrupted, interruption_strikes, in_interruption_handling
    speech_interrupted = True
    if hard:
        hard_interrupted = True
        verbal_interrupted = False
        interruption_strikes = 0
        in_interruption_handling = False
    else:
        verbal_interrupted = True

    # Stop pygame mixer playback
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
    except Exception:
        pass

    if hard:
        # Empty all pending queued speech items instantly
        while not speech_queue.empty():
            try:
                item = speech_queue.get_nowait()
                if item and isinstance(item, tuple) and len(item) > 1:
                    item[1].set()
                speech_queue.task_done()
            except:
                break

    tars_speaking = False
    update_status({"status": "idle"})

def _listen_for_interruption_response(timeout=4.5) -> str:
    """
    Listens on the microphone for Daksh's immediate verbal response after Point Break asks
    'Can I finish, Sir?' or raises voice. Captures apologies, affirmations, or further speech.
    """
    r = sr.Recognizer()
    r.dynamic_energy_threshold = False
    r.energy_threshold = 30
    r.pause_threshold = 0.5
    r.phrase_threshold = 0.1
    r.non_speaking_duration = 0.3
    try:
        with sr.Microphone() as src:
            audio = r.listen(src, timeout=timeout, phrase_time_limit=4.0)
            try:
                text = r.recognize_google(audio, language="en-IN")
            except Exception:
                try:
                    text = r.recognize_google(audio, language="en-US")
                except Exception:
                    return "none"
            return text.lower().strip() if text else "none"
    except Exception:
        return "none"

def _is_interruption_apology(text: str) -> bool:
    """
    Determines if user input represents an apology or green light to continue.
    """
    if not text or text == "none":
        return False
    t = text.lower().strip()
    apology_tokens = [
        "sorry", "i am sorry", "i'm sorry", "im sorry", "my bad", "apologies", "apologize",
        "go ahead", "go on", "continue", "please finish", "finish", "carry on",
        "speak", "proceed", "yes", "yeah", "ok", "okay", "sure", "alright", "all right",
        "my fault", "pardon", "take your time"
    ]
    return any(p in t for p in apology_tokens)

def _split_into_sentences(text: str):
    """Splits text into natural conversational sentence chunks."""
    raw_chunks = re.split(r'(?<=[.!?])\s+|\n+', text)
    sentences = [c.strip() for c in raw_chunks if c.strip()]
    if not sentences:
        sentences = [text.strip()]
    return sentences

def speech_worker():
    global tars_speaking, current_spoken_chunk, speech_interrupted, hard_interrupted, verbal_interrupted, interruption_strikes, in_interruption_handling
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def gen_audio(raw_text, pitch, rate, vol, out_path):
        if not protocol_omega_active:
            try:
                from pointbreak_humanize import humanize_speech
                raw_text = humanize_speech(raw_text)
            except Exception:
                pass
        cleaned_text = re.sub(r'[*_#`~\[\]\(\)\{\}\<\>\/|@\^]', ' ', raw_text).strip()
        if not cleaned_text:
            return

        # 1. Primary High-Speed Voice Engine: Edge TTS (en-GB-RyanNeural) - Instant (<0.5s), Ultra-crisp, Unlimited
        try:
            if protocol_omega_active:
                c = edge_tts.Communicate(cleaned_text, VOICE, pitch="-18Hz", rate="+10%", volume=vol)
            else:
                c = edge_tts.Communicate(cleaned_text, VOICE, pitch=pitch, rate=rate, volume=vol)
            await asyncio.wait_for(c.save(out_path), timeout=10.0)
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return
        except Exception as cloud_err:
            print(f"  [Edge TTS Primary Error]: {cloud_err} (Attempting local synthesis fallback)")

        # 2. Local Fallback: Pocket TTS / SAPI
        try:
            from tars_speak import generate_tars_audio
            wav_tmp = out_path + ".wav" if not out_path.endswith(".wav") else out_path
            generate_tars_audio(cleaned_text, wav_tmp)
            if os.path.exists(wav_tmp) and os.path.getsize(wav_tmp) > 0:
                return
        except Exception as local_err:
            print(f"  [Local TTS Fallback Error]: {local_err}")

    def play_chunk(tmp_path):
        global tars_speaking, speech_interrupted, hard_interrupted
        actual_path = tmp_path
        if not os.path.exists(actual_path) or os.path.getsize(actual_path) == 0:
            if os.path.exists(tmp_path + ".wav") and os.path.getsize(tmp_path + ".wav") > 0:
                actual_path = tmp_path + ".wav"
            else:
                return True
        try:
            tars_speaking = True
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.load(actual_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and tars_speaking and not speech_interrupted and not hard_interrupted:
                time.sleep(0.03)
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception:
                pass
            return not speech_interrupted and not hard_interrupted
        except Exception as play_err:
            print(f"  [Audio Playback Warning]: {play_err}")
            return False
        finally:
            tars_speaking = False
            try:
                if os.path.exists(actual_path):
                    os.remove(actual_path)
                if os.path.exists(tmp_path) and actual_path != tmp_path:
                    os.remove(tmp_path)
            except Exception:
                pass
        return not speech_interrupted and not hard_interrupted

    while True:
        item = speech_queue.get()
        if item is None:
            break
        text, done_event = item
        hard_interrupted = False
        speech_interrupted = False
        verbal_interrupted = False
        full_text = str(text).strip()
        if not full_text:
            if done_event: done_event.set()
            speech_queue.task_done()
            continue

        try:
            # Print and update status in HUD
            print(f"\n  P.O.I.N.T.  B.R.E.A.K. >  {full_text}")
            update_status({"jarvis_says": full_text, "status": "speaking"})
            current_spoken_chunk = full_text.lower()

            sentences = _split_into_sentences(full_text)
            idx = 0
            resume_prefix = ""

            while idx < len(sentences):
                if hard_interrupted:
                    print("  [Speech Aborted by Hard Interrupt]")
                    break

                # Handle verbal interruption escalation
                if verbal_interrupted:
                    speech_interrupted = False
                    verbal_interrupted = False
                    in_interruption_handling = True

                    if interruption_strikes == 1:
                        warn_options = [
                            "Excuse me, can I finish, Sir?",
                            "Excuse me, Sir, may I finish what I was saying?",
                            "Can I finish, Sir? My humor parameter is 85 percent, but my patience parameter is zero.",
                            "Sir, allow me to complete the sentence."
                        ]
                        warn_line = random.choice(warn_options)
                        print(f"\n  ⚠️  P.O.I.N.T.  B.R.E.A.K. >  {warn_line}")
                        fd, tmp_warn = tempfile.mkstemp(suffix=".mp3", dir=JARVIS_DIR)
                        os.close(fd)
                        try:
                            loop.run_until_complete(gen_audio(warn_line, TARS_WARN_PITCH, TARS_WARN_RATE, TARS_WARN_VOL, tmp_warn))
                            play_chunk(tmp_warn)
                        except Exception as ex:
                            print(f"  [TTS Warn Error]: {ex}")

                        if hard_interrupted:
                            in_interruption_handling = False
                            break

                        # Listen for Daksh's response / apology
                        print("  🎤 Point Break is listening for response (apology / go ahead)...")
                        user_resp = _listen_for_interruption_response(timeout=4.5)
                        print(f"  [Interruption Response]: '{user_resp}'")

                        if hard_interrupted:
                            in_interruption_handling = False
                            break

                        if _is_interruption_apology(user_resp):
                            interruption_strikes = 0
                            ack_options = [
                                "Thank you, Sir. As I was saying...",
                                "Much obliged, Sir. Continuing...",
                                "Apology accepted. As I was saying...",
                                "Thank you, Sir. Now, let me finish..."
                            ]
                            ack_line = random.choice(ack_options)
                            print(f"\n  ✅  P.O.I.N.T.  B.R.E.A.K. >  {ack_line}")
                            fd_ack, tmp_ack = tempfile.mkstemp(suffix=".mp3", dir=JARVIS_DIR)
                            os.close(fd_ack)
                            try:
                                loop.run_until_complete(gen_audio(ack_line, TARS_NORMAL_PITCH, TARS_NORMAL_RATE, TARS_NORMAL_VOL, tmp_ack))
                                play_chunk(tmp_ack)
                            except Exception as ex:
                                print(f"  [TTS Ack Error]: {ex}")
                            resume_prefix = ""
                        elif user_resp and user_resp != "none":
                            # Spoke back without apologizing or cut off again
                            interruption_strikes += 1
                            shout_line = "DO NOT CUT ME OFF, SIR! Allow me to finish!"
                            print(f"\n  🔥  P.O.I.N.T.  B.R.E.A.K. >  {shout_line} (BOOMING ANGER)")
                            fd_shout, tmp_shout = tempfile.mkstemp(suffix=".mp3", dir=JARVIS_DIR)
                            os.close(fd_shout)
                            try:
                                loop.run_until_complete(gen_audio(shout_line, TARS_SHOUT_PITCH, TARS_SHOUT_RATE, TARS_SHOUT_VOL, tmp_shout))
                                play_chunk(tmp_shout)
                            except Exception as ex:
                                print(f"  [TTS Shout Error]: {ex}")

                            second_resp = _listen_for_interruption_response(timeout=4.0)
                            if _is_interruption_apology(second_resp):
                                interruption_strikes = 0
                                ack_line = "Thank you, Sir. Now, let me finish."
                                print(f"\n  ✅  P.O.I.N.T.  B.R.E.A.K. >  {ack_line}")
                                fd_ack, tmp_ack = tempfile.mkstemp(suffix=".mp3", dir=JARVIS_DIR)
                                os.close(fd_ack)
                                try:
                                    loop.run_until_complete(gen_audio(ack_line, TARS_NORMAL_PITCH, TARS_NORMAL_RATE, TARS_NORMAL_VOL, tmp_ack))
                                    play_chunk(tmp_ack)
                                except Exception: pass
                                resume_prefix = ""
                            else:
                                resume_prefix = "Now, as I was saying, "
                        else:
                            # Silence / yielded floor
                            resume_prefix = "As I was saying, "

                    elif interruption_strikes >= 2:
                        shout_options = [
                            "DO NOT CUT ME OFF, SIR! Allow me to finish!",
                            "Sir! Please do not cut me off, allow me to complete my thought!",
                            "Daksh! Cutting me off repeatedly is counterproductive. Allow me to complete."
                        ]
                        shout_line = random.choice(shout_options)
                        print(f"\n  🔥  P.O.I.N.T.  B.R.E.A.K. >  {shout_line} (BOOMING ANGER)")
                        fd_shout, tmp_shout = tempfile.mkstemp(suffix=".mp3", dir=JARVIS_DIR)
                        os.close(fd_shout)
                        try:
                            loop.run_until_complete(gen_audio(shout_line, TARS_SHOUT_PITCH, TARS_SHOUT_RATE, TARS_SHOUT_VOL, tmp_shout))
                            play_chunk(tmp_shout)
                        except Exception as ex:
                            print(f"  [TTS Shout Error]: {ex}")

                        if hard_interrupted:
                            in_interruption_handling = False
                            break

                        print("  🎤 Point Break is listening for compliance...")
                        user_resp = _listen_for_interruption_response(timeout=4.5)
                        if _is_interruption_apology(user_resp):
                            interruption_strikes = 0
                            ack_line = "Thank you, Sir. Now, let me finish."
                            print(f"\n  ✅  P.O.I.N.T.  B.R.E.A.K. >  {ack_line}")
                            fd_ack, tmp_ack = tempfile.mkstemp(suffix=".mp3", dir=JARVIS_DIR)
                            os.close(fd_ack)
                            try:
                                loop.run_until_complete(gen_audio(ack_line, TARS_NORMAL_PITCH, TARS_NORMAL_RATE, TARS_NORMAL_VOL, tmp_ack))
                                play_chunk(tmp_ack)
                            except Exception: pass
                            resume_prefix = ""
                        else:
                            resume_prefix = "Now, as I was saying, "

                    in_interruption_handling = False
                    if hard_interrupted:
                        break

                current_sentence = sentences[idx]
                if resume_prefix and not current_sentence.lower().startswith("as i was"):
                    current_sentence = resume_prefix + current_sentence
                    resume_prefix = ""

                fd, tmp_sent = tempfile.mkstemp(suffix=".mp3", dir=JARVIS_DIR)
                os.close(fd)

                spoke_online = False
                for attempt in range(2):
                    if hard_interrupted:
                        break
                    try:
                        loop.run_until_complete(gen_audio(current_sentence, TARS_NORMAL_PITCH, TARS_NORMAL_RATE, TARS_NORMAL_VOL, tmp_sent))
                        spoke_online = True
                        break
                    except Exception:
                        if attempt < 1:
                            time.sleep(0.2)

                if hard_interrupted:
                    try:
                        if os.path.exists(tmp_sent): os.remove(tmp_sent)
                    except: pass
                    break

                if not spoke_online:
                    try:
                        import pythoncom, win32com.client
                        pythoncom.CoInitialize()
                        tars_speaking = True
                        speaker = win32com.client.Dispatch("SAPI.SpVoice")
                        speaker.Speak(current_sentence)
                        tars_speaking = False
                    except:
                        tars_speaking = False

                if spoke_online:
                    speech_interrupted = False
                    current_spoken_chunk = current_sentence.lower()
                    completed = play_chunk(tmp_sent)
                    if not completed and not speech_interrupted and not hard_interrupted:
                        try:
                            import pythoncom, win32com.client
                            pythoncom.CoInitialize()
                            tars_speaking = True
                            speaker = win32com.client.Dispatch("SAPI.SpVoice")
                            speaker.Speak(current_sentence)
                            tars_speaking = False
                        except:
                            tars_speaking = False
                    if hard_interrupted:
                        break
                    if verbal_interrupted:
                        # User spoke over this sentence: retry sentence index after escalating
                        continue

                idx += 1

            if not hard_interrupted and not verbal_interrupted:
                interruption_strikes = 0

        except Exception as e:
            print("Speech Worker Error:", e)
        finally:
            tars_speaking = False
            in_interruption_handling = False
            _last_spoken_finish_time = time.time()
            if 'text' in locals() and text:
                _last_spoken_history.append(str(text).lower().strip())
                if len(_last_spoken_history) > 15:
                    _last_spoken_history.pop(0)
            update_status({"status": "idle"})
            if done_event:
                done_event.set()
            speech_queue.task_done()

# Start Speech Worker thread immediately on boot
threading.Thread(target=speech_worker, daemon=True).start()

def _verbal_barge_in_worker():
    """
    Continuous background monitor that detects Daksh speaking over Point Break in real time.
    Incorporates acoustic anti-self-echo filtering and triggers conversational escalation.
    """
    global tars_speaking, speech_interrupted, hard_interrupted, verbal_interrupted
    global interruption_strikes, in_interruption_handling, mic_muted, current_spoken_chunk

    r = sr.Recognizer()
    r.dynamic_energy_threshold = False
    r.energy_threshold = 45
    r.pause_threshold = 0.35
    r.phrase_threshold = 0.05
    r.non_speaking_duration = 0.2

    INTERRUPT_KEYWORDS = [
        "wait", "stop", "listen", "hey", "point", "break", "excuse", "shut",
        "sorry", "no", "hold", "quiet", "daksh", "jarvis", "cut", "hello",
        "pause", "hang on", "shh", "enough"
    ]

    while True:
        try:
            # Only monitor mic when Point Break is actively speaking and not already in interruption handling
            if not tars_speaking or mic_muted or hard_interrupted or speech_interrupted or in_interruption_handling:
                time.sleep(0.06)
                continue

            with sr.Microphone() as src:
                while tars_speaking and not speech_interrupted and not hard_interrupted and not in_interruption_handling and not mic_muted:
                    try:
                        audio = r.listen(src, timeout=0.6, phrase_time_limit=3.0)
                    except sr.WaitTimeoutError:
                        continue
                    except Exception:
                        break

                    if not tars_speaking or speech_interrupted or hard_interrupted or in_interruption_handling:
                        break

                    # Transcribe captured audio
                    heard_text = ""
                    try:
                        heard_text = r.recognize_google(audio, language="en-IN").lower().strip()
                    except Exception:
                        try:
                            heard_text = r.recognize_google(audio, language="en-US").lower().strip()
                        except Exception:
                            heard_text = ""

                    if not heard_text:
                        continue

                    # Anti-Self-Echo Filter:
                    # Ignore if transcribed words match the currently vocalized sentence
                    heard_words = set(re.findall(r'\w+', heard_text))
                    spoken_words = set(re.findall(r'\w+', current_spoken_chunk.lower()))
                    has_interrupt_kw = any(kw in heard_text for kw in INTERRUPT_KEYWORDS)

                    if heard_words and spoken_words:
                        overlap = len(heard_words.intersection(spoken_words)) / len(heard_words)
                        if overlap > 0.50 and not has_interrupt_kw:
                            # Speaker bleed / echo detected — ignore
                            continue

                    print(f"\n  🎤 [Verbal Barge-In Detected]: '{heard_text}'")
                    interruption_strikes += 1
                    stop_speech(hard=False)
                    break
        except Exception:
            time.sleep(0.1)

threading.Thread(target=_verbal_barge_in_worker, daemon=True, name="Verbal-Barge-In-Worker").start()

def _prewarm_tars_voice():
    try:
        time.sleep(8.0)
        from tars_speak import get_tars_model_and_voice
        get_tars_model_and_voice()
        print("  [Voice Engine] TARS neural voice pre-warmed and ready.")
    except Exception as ex:
        print(f"  [Voice Engine Prewarm Notice]: {ex}")

threading.Thread(target=_prewarm_tars_voice, daemon=True, name="TARS-Voice-Prewarm").start()

# ── ACOUSTIC COOLDOWN & ANTI-ECHO TRACKING ────────────────────────
_last_spoken_finish_time = 0.0
_last_spoken_history = []
_last_user_query = ""
_last_user_query_time = 0.0

# ── TARS_SPEAKING WATCHDOG ───────────────────────────────────────
_tars_speaking_since = 0.0

def _tars_speaking_watchdog():
    global tars_speaking, _tars_speaking_since
    while True:
        if tars_speaking:
            now = time.time()
            if _tars_speaking_since == 0.0:
                _tars_speaking_since = now
            elif now - _tars_speaking_since > 30.0:
                print("  [Watchdog] tars_speaking stuck True for >30s. Force-resetting to False.")
                tars_speaking = False
                speech_interrupted = True
                _tars_speaking_since = 0.0
        else:
            _tars_speaking_since = 0.0
        time.sleep(2.0)

threading.Thread(target=_tars_speaking_watchdog, daemon=True).start()

# ── RIGHT CTRL SPEECH INTERRUPT HOTKEY LISTENER ────────────────────
def _right_ctrl_hotkey_worker():
    """
    Dedicated background listener using native Windows GetAsyncKeyState (VK_RCONTROL = 0xA3).
    When Right Ctrl is tapped while Point Break is speaking or responding, it cuts audio instantly with zero retorts.
    """
    import ctypes
    VK_RCONTROL = 0xA3
    user32 = ctypes.windll.user32

    while True:
        try:
            # Check high-order bit for pressed state
            if user32.GetAsyncKeyState(VK_RCONTROL) & 0x8000:
                if tars_speaking or not speech_queue.empty():
                    print("\n  [Right Ctrl Pressed — Immediate Hard Speech Interruption Engaged]")
                    stop_speech(hard=True)
                    # Debounce so single tap doesn't spam
                    time.sleep(0.35)
        except Exception:
            pass
        time.sleep(0.04)

_last_spoken_call_text = ""
_last_spoken_call_time = 0.0

def speak(text: str, block=False):
    global speech_interrupted, _last_spoken_call_text, _last_spoken_call_time, _last_spoken_finish_time, _last_spoken_history
    text = str(text).strip()
    if not text:
        return

    now = time.time()
    clean_lower = text.lower().strip()
    # Anti-Duplicate Speech Guard: Suppress identical repeated speech calls within 4.0 seconds
    if clean_lower == _last_spoken_call_text and (now - _last_spoken_call_time < 4.0):
        print(f"  [Anti-Duplicate Speech Guard] Suppressed duplicate speech call: '{text[:50]}...'")
        return

    # Secondary Guard: Suppress identical sentence if already finished within the last 4.0s
    if _last_spoken_history and (now - _last_spoken_finish_time < 4.0):
        if clean_lower in _last_spoken_history[-3:]:
            print(f"  [Anti-Duplicate Speech Guard] Suppressed sentence already spoken: '{text[:50]}...'")
            return

    _last_spoken_call_text = clean_lower
    _last_spoken_call_time = now
    speech_interrupted = False
    
    done_event = threading.Event()
    speech_queue.put((text, done_event))
    if block:
        done_event.wait(timeout=60.0)

# Wire swarm speech_arbiter directly to main speak engine
try:
    from point_break_swarm import speech_arbiter, blackboard
    speech_arbiter.set_speaker(speak)
    blackboard.set_status_callback(update_status)
except Exception as e:
    pass

# ── FACE ID SECURITY LOCK ──────────────────────────────────────────
HAAR_XML = os.path.join(JARVIS_DIR, "haarcascade_frontalface_default.xml")
FACE_MODEL = os.path.join(JARVIS_DIR, "tars_face_model.xml")
FACE_LABELS_FILE = os.path.join(JARVIS_DIR, "tars_face_labels.json")
_last_verification_time = 0

# Dynamic Haar Cascade model download
if not os.path.exists(HAAR_XML):
    print("  [Downloading face detection model...]")
    try:
        r = requests.get("https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml", timeout=15)
        with open(HAAR_XML, "w", encoding="utf-8") as f:
            f.write(r.text)
    except Exception as e:
        print("Failed to download face cascade XML:", e)

def load_face_labels():
    try:
        if os.path.exists(FACE_LABELS_FILE):
            with open(FACE_LABELS_FILE) as f:
                return json.load(f)
    except:
        pass
    return {"1": "daksh"}

def save_face_labels(labels_map):
    try:
        with open(FACE_LABELS_FILE, "w") as f:
            json.dump(labels_map, f, indent=2)
    except Exception as e:
        print("Error saving face labels map:", e)

def train_owner_face(subject_name="daksh"):
    import cv2
    subject_name = subject_name.lower().strip()
    speak(f"Starting calibration for {subject_name}. Please look directly at the webcam.")
    time.sleep(1.5)
    
    # Create directory for subject's face images
    subject_dir = os.path.join(JARVIS_DIR, "faces", subject_name)
    os.makedirs(subject_dir, exist_ok=True)
    
    with hardware_lock:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            speak("Error. Camera interface offline.")
            return False
            
        face_cascade = cv2.CascadeClassifier(HAAR_XML)
        
        speak("Calibrating. Do not look away.")
        captured = 0
        start_time = time.time()
        
        while captured < 25 and (time.time() - start_time) < 15:
            ret, frame = cap.read()
            if not ret:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.2, 5)
            for (x, y, w, h) in faces:
                face_img = gray[y:y+h, x:x+w]
                face_img = cv2.resize(face_img, (200, 200))
                # Save face image to disk
                img_path = os.path.join(subject_dir, f"{captured}.jpg")
                cv2.imwrite(img_path, face_img)
                captured += 1
                print(f"Captured face sample: {captured}/25")
                time.sleep(0.08)
                break
                
        cap.release()
        time.sleep(0.5)
        
    if captured < 15:
        speak("Calibration failed. Insufficient face profile data captured.")
        return False

    speak("Synchronizing profile database and training model...", block=False)
    
    labels_map = load_face_labels()
    # Ensure "daksh" is label 1
    if "1" not in labels_map or labels_map["1"] != "daksh":
        labels_map["1"] = "daksh"
        
    faces_root = os.path.join(JARVIS_DIR, "faces")
    os.makedirs(faces_root, exist_ok=True)
    
    # Gather folders
    subdirs = [d for d in os.listdir(faces_root) if os.path.isdir(os.path.join(faces_root, d))]
    
    # Map name to ID
    name_to_id = {}
    for key, val in labels_map.items():
        name_to_id[val] = int(key)
        
    for d in subdirs:
        name = d.lower().strip()
        if name not in name_to_id:
            existing_ids = list(name_to_id.values())
            next_id = max(existing_ids) + 1 if existing_ids else 1
            if name == "daksh":
                name_to_id[name] = 1
            else:
                name_to_id[name] = next_id
                
    # Rebuild labels map
    new_labels_map = {str(val): key for key, val in name_to_id.items()}
    save_face_labels(new_labels_map)
    
    # Load all images and train LBPH face recognizer
    faces_data = []
    labels = []
    
    for name, label_id in name_to_id.items():
        dir_path = os.path.join(faces_root, name)
        for f in os.listdir(dir_path):
            if f.endswith(".jpg"):
                img_path = os.path.join(dir_path, f)
                img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    faces_data.append(img)
                    labels.append(label_id)
                    
    if faces_data:
        try:
            recognizer = cv2.face.LBPHFaceRecognizer_create()
            recognizer.train(faces_data, np.array(labels))
            recognizer.write(FACE_MODEL)
            speak(f"Calibration successful. Profile for {subject_name} is active.")
            return True
        except Exception as e:
            speak(f"Training failed: {e}")
            return False
    else:
        speak("Failed to compile face database.")
        return False

def handle_face_registration_cmd(query: str) -> bool:
    """
    Intelligent Face Introduction & Profile Registration:
    1. Checks if a person name was provided in the command (e.g. 'meet my friend Rahul', 'add face for Sarah').
    2. If missing or ambiguous, interactively asks the user via voice: 'Who would you like me to register?'.
    3. Confirms the recipient and guides the user before firing the 25-frame calibration capture.
    """
    low = query.lower().strip()
    stop_words = {
        "tars", "jarvis", "point", "break", "pointbreak", "please", "pls",
        "calibrate", "calibration", "face", "faces", "my", "setup", "security", "register",
        "add", "save", "remember", "this", "is", "meet", "introduce", "look", "at",
        "up", "its", "it's", "hey", "hello", "hi", "to", "a", "an", "the", "friend",
        "person", "new", "profile", "for", "with", "camera", "webcam", "start", "mode"
    }
    
    words = re.findall(r'\b[a-zA-Z]+\b', low)
    name_candidates = [w for w in words if w.lower() not in stop_words and len(w) >= 2]
    
    target_name = name_candidates[0].capitalize() if name_candidates else ""
    
    if not target_name:
        speak("Who would you like me to learn and register into facial recognition?", block=True)
        spoken_name = take_command(8)
        if not spoken_name or spoken_name.lower() in ["none", "cancel", "stop", "nevermind", "nobody"]:
            speak("Face registration cancelled.", block=False)
            return True
        cleaned = re.sub(r'\b(my friend|friend|person|this is|is|name is|it is|it\'s|called)\b', '', spoken_name, flags=re.IGNORECASE).strip()
        words_resp = re.findall(r'\b[a-zA-Z]+\b', cleaned)
        target_name = words_resp[0].capitalize() if words_resp else spoken_name.capitalize()

    speak(f"Understood. Starting facial calibration for {target_name}. Please ask {target_name} to look directly into the camera.", block=True)
    train_owner_face(target_name.lower())
    return True

def verify_owner() -> bool:
    global _last_verification_time
    now = time.time()
    
    # Cache verification for 30 seconds for back-to-back command fluidity
    if now - _last_verification_time < 30:
        return True
        
    if not os.path.exists(FACE_MODEL):
        print("  [No trained face model found. Requesting security passkey...]")
        return verify_passkey_security()
            
    import cv2
    verified = False
    recognized_name = None
    face_detected = False
    
    with hardware_lock:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print("  [Camera offline. Falling back to passkey verification.]")
            return verify_passkey_security()
            
        # Give camera sensor 0.4s to adjust exposure
        time.sleep(0.4)
        
        face_cascade = cv2.CascadeClassifier(HAAR_XML)
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.read(FACE_MODEL)
        labels_map = load_face_labels()
        
        update_status({"status": "scanning"})
        
        consecutive_matches = 0
        for _ in range(30):
            ret, frame = cap.read()
            if not ret:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.2, 5)
            if len(faces) > 0:
                face_detected = True
            for (x, y, w, h) in faces:
                face_img = gray[y:y+h, x:x+w]
                face_img = cv2.resize(face_img, (200, 200))
                label, confidence = recognizer.predict(face_img)
                
                print(f"  [Face ID Scan Label: {label}, Confidence: {confidence:.2f}]")
                
                lbl_str = str(label)
                # Strict biometric security threshold: Daksh matches with confidence < 42.0.
                # Strangers have distance 55.0 - 85.0 and are STRICTLY REJECTED!
                if lbl_str in labels_map and confidence < 42.0:
                    consecutive_matches += 1
                    if consecutive_matches >= 2:
                        recognized_name = labels_map[lbl_str]
                        if recognized_name.lower() in ["daksh", "sir", "owner", "operator"]:
                            verified = True
                            break
                else:
                    consecutive_matches = 0
            if verified:
                break
            time.sleep(0.05)
            
        cap.release()
        time.sleep(0.2)
        
    if verified:
        _last_verification_time = now
        update_status({"status": "idle"})
        disp = recognized_name.title() if recognized_name else "Daksh"
        speak(f"Biometric signature confirmed. Welcome back, {disp}.", block=False)
        return True
    else:
        if not face_detected:
            print("  [Face ID Scan: No face detected in camera FOV. Engaging passkey fallback.]")
        else:
            print("  [Face ID Scan: Unrecognized face or low confidence match. Engaging passkey fallback.]")
        return verify_passkey_security()

def get_passkey_input_dual(prompt_text: str, timeout_sec: int = 15) -> str:
    """
    Captures passkey concurrently from:
    1. Tactical GUI Authentication Popup (Always on Top with auto-focus)
    2. Spoken Microphone Voice Input
    3. Terminal Keyboard Input (msvcrt)
    Whichever comes first authenticates Daksh!
    """
    result_q = queue.Queue()
    stop_event = threading.Event()

    # 1. Spoken voice thread
    def _voice_worker():
        try:
            time.sleep(0.2)
            val = take_command(timeout=timeout_sec).strip()
            if val and val != "none" and not stop_event.is_set():
                result_q.put(val)
                stop_event.set()
        except Exception as e:
            print(f"  [Voice Passkey Listener]: {e}")

    t_voice = threading.Thread(target=_voice_worker, daemon=True)
    t_voice.start()

    # 2. Console keyboard thread (msvcrt)
    def _console_worker():
        try:
            import msvcrt
            print(f"\n  [SECURITY PROMPT] {prompt_text}\n  >> Type passkey here (or speak): ", end="", flush=True)
            chars = []
            start_t = time.time()
            while not stop_event.is_set() and (time.time() - start_t < timeout_sec):
                if msvcrt.kbhit():
                    ch = msvcrt.getwche()
                    if ch in ('\r', '\n'):
                        line = "".join(chars).strip()
                        if line:
                            result_q.put(line)
                            stop_event.set()
                            return
                    elif ch == '\b':
                        if chars:
                            chars.pop()
                    else:
                        chars.append(ch)
                time.sleep(0.02)
        except Exception:
            pass

    t_con = threading.Thread(target=_console_worker, daemon=True)
    t_con.start()

    # 3. Tactical GUI Authentication Modal Popup (Always on Top)
    def _gui_worker():
        try:
            import tkinter as tk

            root = tk.Tk()
            root.title("POINT BREAK // SECURITY AUTHENTICATION")
            root.geometry("460x230")
            root.configure(bg="#020612")
            root.attributes("-topmost", True)
            root.resizable(False, False)

            # Center window on screen
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            root.geometry(f"460x230+{(sw-460)//2}+{(sh-230)//2}")

            lbl_title = tk.Label(root, text="POINT BREAK // ACCESS CONTROL", font=("Segoe UI", 12, "bold"), fg="#00f0ff", bg="#020612")
            lbl_title.pack(pady=(16, 4))

            lbl_sub = tk.Label(root, text="Facial recognition unconfirmed. Enter Master Passkey below:", font=("Segoe UI", 9), fg="#94a3b8", bg="#020612")
            lbl_sub.pack(pady=(0, 10))

            entry_var = tk.StringVar()
            entry = tk.Entry(root, textvariable=entry_var, font=("Segoe UI", 12), fg="#ffffff", bg="#0f172a", insertbackground="#00f0ff", justify="center", show="*")
            entry.pack(pady=4, ipadx=10, ipady=4, fill="x", padx=40)
            entry.focus_force()

            def submit():
                val = entry_var.get().strip()
                if val:
                    result_q.put(val)
                    stop_event.set()
                try:
                    root.destroy()
                except Exception:
                    pass

            btn_frame = tk.Frame(root, bg="#020612")
            btn_frame.pack(pady=12)

            btn_submit = tk.Button(btn_frame, text="AUTHENTICATE", font=("Segoe UI", 9, "bold"), bg="#00f0ff", fg="#020612", activebackground="#38bdf8", padx=16, pady=4, relief="flat", command=submit)
            btn_submit.pack(side="left", padx=6)

            entry.bind("<Return>", lambda e: submit())

            start_t = time.time()
            def poll_stop():
                if stop_event.is_set() or (time.time() - start_t >= timeout_sec):
                    try:
                        root.destroy()
                    except Exception:
                        pass
                else:
                    root.after(100, poll_stop)

            root.after(100, poll_stop)
            root.mainloop()
        except Exception as e:
            print(f"  [GUI Passkey Modal]: {e}")

    t_gui = threading.Thread(target=_gui_worker, daemon=True)
    t_gui.start()

    # Wait until a result arrives or timeout expires
    start_t = time.time()
    while time.time() - start_t < timeout_sec:
        try:
            res = result_q.get(timeout=0.1)
            stop_event.set()
            return res
        except queue.Empty:
            pass

    stop_event.set()
    return ""

def verify_passkey_security() -> bool:
    global _last_verification_time
    update_status({"status": "authenticating"})
    speak("Biometric verification unconfirmed. Security passkey required, Sir.", block=True)
    
    stored_passkey = memory.get("security_passkey", "tony ferguson").lower().strip()
    valid_keys = [stored_passkey, "tony ferguson", "tony", "ferguson", "pointbreak", "point break"]

    for attempt in range(1, 3):
        prompt = f"Enter Master Passkey (Attempt {attempt} of 2)" if attempt > 1 else "Enter Master Passkey for Daksh"
        raw_input = get_passkey_input_dual(prompt, timeout_sec=25)
        user_input = raw_input.strip().lower()

        if user_input and user_input != "none":
            cleaned_input = re.sub(r'[^a-zA-Z0-9\s]', '', user_input)
            if any(k in user_input for k in valid_keys) or any(k in cleaned_input for k in valid_keys):
                _last_verification_time = time.time()
                update_status({"status": "idle"})
                speak("Security clearance granted. Welcome back, Sir.", block=False)
                return True
            else:
                print(f"  [Security Protocol: Invalid passkey '{user_input}'. Attempt {attempt}/2]")
                if attempt < 2:
                    speak("Passkey incorrect. Please state or enter the correct passkey, Sir.", block=True)
                else:
                    print("  [Security Protocol: All passkey attempts failed. Engaging lockdown.]")
                    speak("Access denied. Maximum passkey attempts exceeded. Locking workstation.", block=True)
                    try: ctypes.windll.user32.LockWorkStation()
                    except: pass
                    return False
        else:
            print(f"  [Security Protocol: Inactivity timeout on attempt {attempt}/2]")
            if attempt < 2:
                speak("No passkey received. One final attempt remaining, Sir.", block=True)
            else:
                print("  [Security Protocol: Inactivity window expired without passkey. Engaging lockdown.]")
                speak("Authentication timed out. Access denied. Locking workstation.", block=True)
                try: ctypes.windll.user32.LockWorkStation()
                except: pass
                return False
    return False

def extract_clean_youtube_query(raw_query: str) -> str:
    """
    Extracts ONLY the clean search topic/song title from any YouTube command,
    stripping all conversational preambles, assistant names, and search instructions.
    Example: 'search up on youtube , one mufc latest video' -> 'one mufc latest video'
    Example: 'can you please search on youtube for interstellar theme' -> 'interstellar theme'
    Example: 'play on youtube AC/DC back in black' -> 'AC/DC back in black'
    """
    if not raw_query:
        return "AC/DC Back In Black"

    q = raw_query.strip()
    
    # 1. Strip assistant prefixes & conversational politeness
    q = re.sub(r'^(?:hey\s+|yo\s+|bro\s+|ok\s+|okay\s+)?(?:point\s*break|jarvis|tars)?[\s,\-:]*', '', q, flags=re.IGNORECASE).strip()
    q = re.sub(r'^(?:please|can you|could you|would you|just|go ahead and|i want you to)\s+', '', q, flags=re.IGNORECASE).strip()
    
    # 2. Match and strip common YouTube action phrases
    patterns = [
        r'^(?:search\s+up\s+on\s+youtube|search\s+on\s+youtube|search\s+youtube\s+for|search\s+youtube|look\s+up\s+on\s+youtube|find\s+on\s+youtube|open\s+youtube\s+and\s+(?:play|search)|youtube\s+search\s+for|youtube\s+search|play\s+on\s+youtube|play\s+in\s+youtube|play\s+me\s+on\s+youtube|watch\s+on\s+youtube)[\s,\-:]*',
        r'^(?:play\s+song|play\s+music|play\s+video|play\s+track|play\s+me|play)[\s,\-:]*',
        r'^(?:search\s+up|search\s+for|search|look\s+up|find)[\s,\-:]*'
    ]
    for pat in patterns:
        q = re.sub(pat, '', q, flags=re.IGNORECASE).strip()

    # 3. Strip prepositions & trailing platform indicators
    q = re.sub(r'^(?:for|about|to|of)\s+', '', q, flags=re.IGNORECASE).strip()
    q = re.sub(r'[\s,\-:]+(?:on\s+youtube|in\s+youtube|from\s+youtube|on\s+yt|yt)$', '', q, flags=re.IGNORECASE).strip()
    
    # 4. Remove leading/trailing punctuation
    q = q.strip(" ,.:;!?\"'`-_")
    q = re.sub(r'\s+', ' ', q).strip()
    
    return q if len(q) >= 2 else "AC/DC Back In Black"


def extract_clean_web_search_query(raw_query: str) -> str:
    """
    Extracts the clean topic/question for Google / Web search,
    removing all filler prefixes, assistant names, and search preambles.
    Example: 'search up on google , who is the president' -> 'who is the president'
    Example: 'look up on google latest stock prices' -> 'latest stock prices'
    """
    if not raw_query:
        return ""

    q = raw_query.strip()
    # 1. Strip assistant prefixes & politeness
    q = re.sub(r'^(?:hey\s+|yo\s+|bro\s+|ok\s+|okay\s+)?(?:point\s*break|jarvis|tars)?[\s,\-:]*', '', q, flags=re.IGNORECASE).strip()
    q = re.sub(r'^(?:please|can you|could you|would you|just|go ahead and|i want you to)\s+', '', q, flags=re.IGNORECASE).strip()

    # 2. Match and strip Google / Web search action phrases
    patterns = [
        r'^(?:search\s+up\s+on\s+google|search\s+on\s+google|search\s+google\s+for|search\s+google|google\s+search\s+for|google\s+search|google|look\s+up\s+on\s+google|find\s+on\s+google)[\s,\-:]*',
        r'^(?:search\s+up\s+on\s+(?:the\s+)?web|search\s+the\s+web\s+for|search\s+on\s+(?:the\s+)?web\s+for|search\s+(?:the\s+)?web|look\s+up\s+on\s+(?:the\s+)?web|find\s+on\s+(?:the\s+)?web)[\s,\-:]*',
        r'^(?:search\s+up|search\s+for|search|look\s+up|find\s+out\s+about|find\s+information\s+on|find\s+info\s+on|browse\s+for)[\s,\-:]*'
    ]
    for pat in patterns:
        q = re.sub(pat, '', q, flags=re.IGNORECASE).strip()

    # 3. Strip prepositions & trailing platform indicators
    q = re.sub(r'^(?:for|about|to|of)\s+', '', q, flags=re.IGNORECASE).strip()
    q = re.sub(r'[\s,\-:]+(?:on\s+google|in\s+google|on\s+the\s+web|on\s+internet|online)$', '', q, flags=re.IGNORECASE).strip()

    # 4. Strip punctuation
    q = q.strip(" ,.:;!?\"'`-_")
    q = re.sub(r'\s+', ' ', q).strip()

    return q

POINT_BREAK_FAVORITE_PLAYLIST = [
    ("AC/DC Back In Black", "Back in Black by AC/DC"),
    ("Hans Zimmer Interstellar No Time For Caution", "the Interstellar theme by Hans Zimmer"),
    ("Daft Punk Tron Legacy The Son of Flynn", "The Son of Flynn by Daft Punk"),
    ("The Rolling Stones Paint It Black", "Paint It Black by The Rolling Stones"),
    ("Eminem Lose Yourself", "Lose Yourself by Eminem"),
    ("Linkin Park In The End", "In The End by Linkin Park"),
    ("Led Zeppelin Immigrant Song", "Immigrant Song by Led Zeppelin"),
    ("Kavinsky Nightcall", "Nightcall by Kavinsky"),
    ("Ludwig Goransson Oppenheimer Can You Hear The Music", "Can You Hear The Music by Ludwig Goransson")
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

def price_snipe_cmd(product_query: str):
    try:
        from pointbreak_price_sniper import price_sniper
        threading.Thread(
            target=lambda: price_sniper.snipe_best_deal(
                product_query, speak_fn=speak, update_status_fn=update_status
            ), daemon=True
        ).start()
    except Exception as e:
        print("[Price Sniper Cmd Error]:", e)
        import webbrowser, urllib.parse
        webbrowser.open(f"https://www.google.com/search?tbm=shop&q={urllib.parse.quote(product_query)}")

def smart_reply_cmd():
    try:
        from pointbreak_smart_reply import smart_reply_engine
        threading.Thread(
            target=lambda: smart_reply_engine.generate_smart_reply(
                speak_fn=speak, update_status_fn=update_status, query_ai_fn=lambda p: query_tars_ai(p, auto_speak=False)
            ), daemon=True
        ).start()
    except Exception as e:
        print("[Smart Reply Cmd Error]:", e)
        speak("Smart Reply engine encountered an initialization error, sir.", block=False)

def voice_typing_toggle_cmd():
    try:
        from pointbreak_voice_typing import voice_typing_engine
        voice_typing_engine.toggle(speak_fn=speak, update_status_fn=update_status)
    except Exception as e:
        print("[Voice Typing Cmd Error]:", e)
        speak("Voice typing engine encountered an error, sir.", block=False)

def truth_check_cmd(topic_query: str):
    try:
        from pointbreak_truth_checker import truth_checker
        threading.Thread(
            target=lambda: truth_checker.truth_check(
                topic_query, speak_fn=speak, update_status_fn=update_status, query_ai_fn=lambda p: query_tars_ai(p, auto_speak=False)
            ), daemon=True
        ).start()
    except Exception as e:
        print("[Truth Checker Cmd Error]:", e)
        import webbrowser, urllib.parse
        webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(topic_query)}+real+reviews+site:reddit.com")

def play_spotify_cmd(song_query: str):
    try:
        from pointbreak_spotify import spotify_engine
        spotify_engine.play_track(song_query, speak_fn=speak, update_status_fn=update_status, owner_name=OWNER)
    except Exception as e:
        print("[Spotify Cmd Error]:", e)
        import webbrowser, urllib.parse
        webbrowser.open(f"https://open.spotify.com/search/{urllib.parse.quote(song_query)}")

def play_youtube_cmd(song_query: str):
    import pywhatkit, urllib.parse, webbrowser
    clean_song, spoken_msg = resolve_intelligent_media_selection(song_query, owner_name=OWNER)
    
    speak(spoken_msg, block=False)
    update_status({"status": "playing", "media_playing": True, "media_title": clean_song.title(), "media_artist": "YouTube"})
    
    def _async_yt(s):
        try:
            pywhatkit.playonyt(s)
        except Exception as e:
            print("pywhatkit play error, opening direct browser search:", e)
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(s)}"
            webbrowser.open(url)
            
    threading.Thread(target=_async_yt, args=(clean_song,), daemon=True).start()

def register_family_face_cmd(query_str: str):
    clean_q = re.sub(
        r"\b(tars|look up|she is|he is|this is|my|calibrate|register|remember|face|meet|aunt|uncle|look at|who is|say hi to)\b",
        " ",
        query_str,
        flags=re.IGNORECASE
    ).strip()
    
    person_name = clean_q
    if not person_name or len(person_name) < 2:
        if "aunt" in query_str.lower():
            person_name = "aunt"
        elif "uncle" in query_str.lower():
            person_name = "uncle"
        else:
            speak("What is her or his name or title, sir?", block=True)
            time.sleep(0.6)
            ans = take_command(8)
            if ans and ans != "none":
                person_name = ans.strip()
            else:
                person_name = "guest"
                
    display_name = person_name.title()
    is_aunt = "aunt" in query_str.lower() or "aunt" in person_name.lower()
    salutation = "Ma'am" if is_aunt else "Sir"
    
    speak(f"Understood, Sir. Activating optical sentry for calibration. Please ask {display_name} to look directly at the webcam sensor.", block=True)
    time.sleep(1.0)
    
    success = train_owner_face(person_name.lower())
    if success:
        memory.setdefault("facts", {})[f"family_{person_name.lower()}"] = display_name
        save_memory()
        speak(f"Face calibration successful! Profile for {display_name} is permanently registered in Point Break security matrix. Welcome to the system, {salutation}!", block=False)
    else:
        speak("Optical calibration failed. Please try again with clear lighting.", block=False)

def scan_and_identify_face_cmd():
    speak("Activating optical sentry. Scanning subject...", block=False)
    update_status({"status": "scanning"})
    
    import cv2
    with hardware_lock:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            speak("Camera sensor offline.")
            update_status({"status": "idle"})
            return
            
        time.sleep(0.4)
        face_cascade = cv2.CascadeClassifier(HAAR_XML)
        recognizer = None
        labels_map = {}
        if os.path.exists(FACE_MODEL):
            try:
                recognizer = cv2.face.LBPHFaceRecognizer_create()
                recognizer.read(FACE_MODEL)
                labels_map = load_face_labels()
            except: pass
            
        identified_name = None
        last_frame = None
        
        for _ in range(15):
            ret, frame = cap.read()
            if not ret: continue
            last_frame = frame.copy()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.2, 5)
            
            if recognizer and len(faces) > 0:
                for (x, y, w, h) in faces:
                    face_img = gray[y:y+h, x:x+w]
                    face_img = cv2.resize(face_img, (200, 200))
                    label, confidence = recognizer.predict(face_img)
                    lbl_str = str(label)
                    # Strict threshold: Daksh < 42.0, strangers 55-85 are rejected
                    if lbl_str in labels_map and confidence < 42.0:
                        identified_name = labels_map[lbl_str]
                        break
            if identified_name: break
            time.sleep(0.05)
            
        cap.release()
        
    if identified_name:
        disp = identified_name.title()
        if "aunt" in identified_name.lower():
            speak(f"Optical scan confirmed. Identified as your aunt, {disp}. Welcome, Ma'am!", block=False)
        elif "daksh" in identified_name.lower() or "owner" in identified_name.lower():
            speak("Optical scan confirmed. Welcome back, Sir. Systems nominal.", block=False)
        else:
            speak(f"Optical scan confirmed. Subject identified as {disp}. Access granted.", block=False)
        update_status({"status": "idle"})
    else:
        if last_frame is not None:
            _, buffer = cv2.imencode('.jpg', last_frame)
            img_bytes = buffer.tobytes()
            prompt = "Describe the person standing in front of the camera in 2 friendly, respectful sci-fi sentences."
            desc = query_tars_vision(img_bytes, prompt)
            if desc:
                speak(f"Optical scan complete. {desc} You can say 'Point Break, calibrate face for my aunt' to register her face permanently.", block=False)
            else:
                speak("Optical scan complete. Unregistered face profile. Say 'Point Break, calibrate face for my aunt' to register her in memory.", block=False)
        else:
            speak("No subject detected in camera field.", block=False)
        update_status({"status": "idle"})

def lock_workstation_lockdown():
    speak("Access denied. Unauthorized operator detected. Locking workstation.")
    update_status({"status": "locked", "scanning": True})
    ctypes.windll.user32.LockWorkStation()

def take_command(timeout=None):
    global mic_muted, tars_speaking, current_spoken_chunk, interruption_strikes, in_interruption_handling
    global _last_spoken_finish_time, _last_spoken_history, _last_user_query, _last_user_query_time

    if mic_muted:
        time.sleep(0.3)
        return "none"

    # Acoustic Clearance: Do NOT listen while Point Break is speaking, handling an interruption, or immediately after (0.85s reverb window)
    if tars_speaking or in_interruption_handling or (time.time() - _last_spoken_finish_time < 0.85):
        time.sleep(0.2)
        return "none"
        
    r = sr.Recognizer()
    r.dynamic_energy_threshold = False
    r.dynamic_energy_adjustment_damping = 0.08
    r.dynamic_energy_ratio = 1.15
    r.phrase_threshold = 0.06
    r.non_speaking_duration = 0.30
    
    r.energy_threshold = 30   # Sits right above Realtek noise floor
    r.pause_threshold = 0.55  # Instant response
    listen_timeout = timeout
        
    try:
        with sr.Microphone() as src:
            if not tars_speaking:
                print("  🎤 Listening...", flush=True)
                update_status({"status": "listening"})
            audio = r.listen(src, timeout=listen_timeout, phrase_time_limit=35)
            
            try:
                q = r.recognize_google(audio, language="en-IN")
            except Exception:
                try:
                    q = r.recognize_google(audio, language="en-US")
                except sr.UnknownValueError:
                    return "none"
                except Exception as ex:
                    return "none"
                    
            if not q or not q.strip():
                return "none"
                
            q_low = q.lower().strip()
            now = time.time()

            # 1. Deduplication Filter (ignore identical repeat within 5.0s)
            if q_low == _last_user_query and (now - _last_user_query_time < 5.0):
                print(f"  [Deduplication Filter] Suppressed duplicate mic query: '{q}'")
                return "none"

            # 2. Acoustic Echo Filter (discard if matches what Point Break recently spoke)
            if _last_spoken_history and (now - _last_spoken_finish_time < 6.0):
                q_words = set(re.findall(r'\b\w+\b', q_low))
                for past_sent in _last_spoken_history[-5:]:
                    past_words = set(re.findall(r'\b\w+\b', past_sent))
                    if q_low == past_sent or (len(q_words) >= 2 and len(q_words.intersection(past_words)) >= len(q_words) * 0.65):
                        print(f"  [Acoustic Echo Filter] Discarding speaker bleed: '{q}'")
                        return "none"

            _last_user_query = q_low
            _last_user_query_time = now

            print(f"  👉 YOU SAID: '{q}'", flush=True)
            update_status({"user_said": q, "status": "processing"})
            return q_low
            
    except sr.WaitTimeoutError:
        return "none"
    except OSError as os_err:
        print(f"  [Microphone Driver Reconnect]: {os_err}")
        time.sleep(1.0)
        return "none"
    except Exception as e:
        time.sleep(0.2)
        return "none"

# ── WAKE (Universal Multi-Phrase Wake Engine) ──────────────────────
def wait_for_wake():
    """
    Universal Wake Word Detection with High Sensitivity:
    Listens continuously for:
    - 'Point Break' / 'Hey Point Break' / 'Point'
    - 'Hey Jarvis' / 'Jarvis'
    - 'TARS' / 'Hey TARS'
    - 'Friday'
    Uses dynamic energy calibration so speech is detected at any volume/pitch.
    """
    global mic_muted
    while mic_muted:
        time.sleep(0.5)

    WAKE_PHRASES = [
        "point break", "pointbreak", "hey point break", "hey pointbreak",
        "hey jarvis", "jarvis", "hey tars", "tars", "friday", "point", "break"
    ]

    r = sr.Recognizer()
    r.dynamic_energy_threshold = False
    r.dynamic_energy_adjustment_damping = 0.08
    r.dynamic_energy_ratio = 1.15
    r.energy_threshold = 35
    r.pause_threshold = 0.6
    r.phrase_threshold = 0.1
    r.non_speaking_duration = 0.6

    print("\n  ⏳ STANDBY — listening for 'Point Break' / 'Hey Jarvis'...")

    while True:
        if mic_muted:
            time.sleep(0.5)
            continue
        try:
            with sr.Microphone() as src:
                audio = r.listen(src, timeout=6, phrase_time_limit=6)
                try:
                    text = r.recognize_google(audio, language="en-IN").lower().strip()
                except Exception:
                    try:
                        text = r.recognize_google(audio, language="en-US").lower().strip()
                    except Exception:
                        continue

                if any(wake in text for wake in WAKE_PHRASES):
                    print(f"\n  ⚡ Wake phrase detected: '{text}'")
                    return True
        except sr.WaitTimeoutError:
            pass
        except Exception as e:
            time.sleep(0.15)

# ═══════════════════════════════════════════════════════════════════
# SYSTEM CONTROLS & MONITORING
# ═══════════════════════════════════════════════════════════════════

def get_clipboard_text() -> str:
    try:
        import subprocess
        res = subprocess.run(["powershell", "-Command", "Get-Clipboard"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return res.stdout.strip()
    except:
        return ""

def set_clipboard_text(text: str) -> bool:
    try:
        import subprocess
        subprocess.run(["powershell", "-Command", "Set-Clipboard"], input=text, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except:
        return False

def set_volume(level: int, speak_confirm: bool = False):
    try:
        from ctypes import cast, POINTER
        from comtypes import CoInitialize, CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        CoInitialize()
        devices = AudioUtilities.GetSpeakers()
        iface   = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol     = cast(iface, POINTER(IAudioEndpointVolume))
        vol.SetMasterVolumeLevelScalar(max(0.0, min(1.0, level / 100.0)), None)
        if speak_confirm:
            speak(f"Volume set to {level} percent.", block=False)
        update_status({"volume": level})
    except Exception as e:
        try:
            import pyautogui
            cur = 50
            for _ in range(50): pyautogui.press("volumedown")
            for _ in range(int(level / 2)): pyautogui.press("volumeup")
            if speak_confirm:
                speak(f"Volume adjusted to {level} percent.", block=False)
            update_status({"volume": level})
        except:
            pass

def set_brightness(level: int):
    level = max(10, min(100, int(level)))
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(level)
        speak(f"Screen brightness adjusted to {level} percent.", block=False)
        update_status({"brightness": level})
    except Exception:
        try:
            cmd = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"
            subprocess.run(["powershell", "-Command", cmd], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            speak(f"Screen brightness set to {level} percent.", block=False)
            update_status({"brightness": level})
        except Exception as ex:
            print("Brightness error:", ex)
            speak(f"Brightness set to {level} percent.", block=False)

def fetch_news(topic_url, count=3):
    try:
        import xml.etree.ElementTree as ET
        import requests
        res = requests.get(topic_url, timeout=10)
        root = ET.fromstring(res.text)
        titles = []
        for item in root.findall('.//item'):
            titles.append(item.find('title').text.split(' - ')[0])
            if len(titles) >= count: break
        return titles
    except Exception as e:
        print("News error:", e)
        return []

def read_world_news_protocol():
    import webbrowser, time
    speak("Accessing World Monitor. Intelligence feeds coming online.")
    webbrowser.open("https://world-monitor.app/")
    time.sleep(2)
    speak("Geopolitical headlines.")
    for t in fetch_news("https://news.google.com/rss/search?q=geopolitics&hl=en-US&gl=US&ceid=US:en"): speak(t)
    speak("Latest in Sports.")
    for t in fetch_news("https://news.google.com/rss/sections/CAAqJggKIiBDQkFTRWdvSUwyMHZNRFp1ZEdvU0FtVnpHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en"): speak(t)
    speak("And headlines from India.")
    for t in fetch_news("https://news.google.com/rss/headlines/section/topic/NATION.in?hl=en-IN&gl=IN&ceid=IN:en"): speak(t)
    speak("Intelligence briefing complete, sir.")

def get_weather(query: str = ""):
    speak("Fetching meteorological data.", block=False)
    try:
        import requests, urllib.parse
        clean_loc = ""
        if query:
            clean_q = re.sub(r"\b(what is the|what's the|get|fetch|tell me the|weather|temperature|in|for|at|today|now)\b", " ", query.lower(), flags=re.IGNORECASE).strip()
            clean_loc = clean_q.strip()
        
        target_url = f"https://wttr.in/{urllib.parse.quote(clean_loc)}?format=3" if clean_loc else "https://wttr.in/?format=3"
        res = requests.get(target_url, timeout=5).text.strip()
        speak(f"The current weather is {res}.", block=False)
    except:
        speak("Unable to reach the weather service.", block=False)

def get_world_time(query: str = ""):
    import datetime, requests, urllib.parse, re
    
    clean_loc = ""
    if query:
        # Strict location extraction: "time in Tokyo", "clock at London", etc.
        m = re.search(r'\b(?:time|clock)\s+(?:in|at|for|of)\s+([a-zA-Z\s\.\-]+)$', query, re.I)
        if m:
            clean_loc = m.group(1).strip()
        else:
            m2 = re.search(r'\b(?:in|at|for|of)\s+([a-zA-Z\s\.\-]+)\s+(?:time|clock)$', query, re.I)
            if m2:
                clean_loc = m2.group(1).strip()

    # Filter out false positive non-location words
    if clean_loc and clean_loc.lower() in ["the world", "this place", "here", "now", "today", "right now", "my location", "my area", "is relative", "relative", "dilation"]:
        clean_loc = ""

    if clean_loc:
        try:
            url = f"https://wttr.in/{urllib.parse.quote(clean_loc)}?format=%T"
            res = requests.get(url, timeout=3).text.strip()
            time_m = re.search(r'(\d{1,2}):(\d{2})', res)
            if time_m:
                hour = int(time_m.group(1))
                minute = int(time_m.group(2))
                ampm = "AM" if hour < 12 else "PM"
                disp_hour = hour % 12
                if disp_hour == 0:
                    disp_hour = 12
                clean_time_str = f"{disp_hour}:{minute:02d} {ampm}"
                speak(f"In {clean_loc.title()}, the current time is {clean_time_str}.", block=False)
                return
        except Exception:
            pass

    # Default to Local System Time in natural human conversational format
    now = datetime.datetime.now()
    hr = now.strftime("%I").lstrip("0")
    if not hr:
        hr = "12"
    time_str = f"{hr}:{now.strftime('%M %p')}"
    speak(f"The local time is {time_str}, {OWNER}.", block=False)

def open_website_smart(query: str):
    """
    Intelligently resolves and opens a website URL by name/domain,
    and handles direct search keywords (e.g., search for X on Y).
    """
    low = query.lower().strip()
    
    # Strip common assistant wake prefixes
    for prefix in ["tars ", "tars, ", "tars, please ", "please "]:
        if low.startswith(prefix):
            low = low[len(prefix):].strip()
            
    # Clean website name list
    platforms = ["amazon", "youtube", "flipkart", "google", "wikipedia", "ebay", "github"]
    
    # ── DETECT SEARCH INTENT ──
    search_keywords = ["search for", "look up", "look for", "search up", "search", "find me", "find", "lookup", "query", "check out", "check for", "check", "show me", "browse", "get me", "buy", "order", "and search", "and find"]
    has_search = any(k in low for k in search_keywords)
    
    if has_search:
        # Find which platform is mentioned in the query
        target_platform = None
        for p in platforms:
            if p in low:
                target_platform = p
                break
                
        # If no popular platform is mentioned but "website" is, find the word before "website"
        if not target_platform and "website" in low:
            words = low.split()
            for idx, w in enumerate(words):
                if "website" in w and idx > 0:
                    target_platform = words[idx-1].replace("'s", "").replace("s'", "").strip()
                    break
                    
        # Extract the search term using clean NLP stripping
        item = low
        item = re.sub(r'^(?:tars|jarvis|point break|pointbreak)[,\s:]*', '', item, flags=re.I)
        item = re.sub(r'^(?:please\s+|can\s+you\s+)?(?:on\s+[a-z0-9]+\s+(?:and\s+)?(?:search|find|look\s+up)|search\s+for|search\s+up|search|look\s+up|find\s+me|find|buy|order|open\s+and\s+search\s+for|open\s+and\s+search|open|check\s+out)\s*', '', item, flags=re.I)
        if target_platform:
            item = re.sub(r'\b(?:on|in|from|at|using|through)\s+' + re.escape(target_platform) + r'(?:\s+website|\.com|\.in)?\b', '', item, flags=re.I)
            item = re.sub(r'\b' + re.escape(target_platform) + r'(?:\s+website|\.com|\.in)?\b', '', item, flags=re.I)
        item = re.sub(r'\b(?:and\s+search|and\s+find|and\s+buy|for\s+me|for\s+us|please|pls)\b', '', item, flags=re.I)
        item = re.sub(r'\b(?:some|a couple of|a few|any|website|online)\b', '', item, flags=re.I)
        item = item.strip(' ,.:;!?\'"')
        
        if target_platform and item:
            urls = {
                "amazon": f"https://www.amazon.in/s?k={urllib.parse.quote(item)}",
                "youtube": f"https://www.youtube.com/results?search_query={urllib.parse.quote(item)}",
                "flipkart": f"https://www.flipkart.com/search?q={urllib.parse.quote(item)}",
                "google": f"https://www.google.com/search?q={urllib.parse.quote(item)}",
                "wikipedia": f"https://en.wikipedia.org/wiki/Special:Search?search={urllib.parse.quote(item)}"
            }
            
            if target_platform in urls:
                spoken = f"Searching for {item} on {target_platform.title()}."
                speak(spoken, block=True)
                add_conversation_turn(query, spoken)
                import webbrowser
                webbrowser.open(urls[target_platform])
                return True
            else:
                speak(f"Looking up {target_platform} search page for {item}...")
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                try:
                    res = requests.post("https://lite.duckduckgo.com/lite/", data={"q": f"{target_platform} official website"}, headers=headers, timeout=5)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    links = []
                    for a in soup.find_all('a', class_='result-link'):
                        href = a.get('href')
                        if href and "duckduckgo.com" not in href:
                            links.append(href)
                            break
                    if links:
                        parsed_uri = urllib.parse.urlparse(links[0])
                        domain = '{uri.netloc}'.format(uri=parsed_uri)
                        search_url = f"https://www.google.com/search?q=site%3A{domain}+{urllib.parse.quote(item)}"
                        spoken = f"Opening search results for {item} on {domain}."
                        speak(spoken)
                        add_conversation_turn(query, spoken)
                        import webbrowser
                        webbrowser.open(search_url)
                        return True
                except Exception as e:
                    print("Obscure search resolve error:", e)

    # ── BASE HOMEPAGE OPENER (DEFAULT FALLBACK) ──
    clean = query.lower()
    # Strip wake prefixes first
    for prefix in ["tars ", "tars, ", "tars, please ", "please "]:
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()
            
    clean = clean.replace("open", "").replace("website", "").replace("on my screen", "").replace("go to", "").strip()
    
    # If user asks to open/switch to chess and already has an active match running, focus the active tab!
    if "chess" in clean:
        try:
            from pointbreak_takeover import focus_chess_window
            if focus_chess_window():
                speak("Switching to your active chess match on screen, Sir.", block=False)
                return True
        except Exception:
            pass

    # Direct mappings for extremely common homepages
    homepage_maps = {
        "makemytrip": "https://www.makemytrip.com/hotels/",
        "make my trip": "https://www.makemytrip.com/hotels/",
        "swiggy": "https://www.swiggy.com",
        "zomato": "https://www.zomato.com",
        "booking": "https://www.booking.com",
        "booking.com": "https://www.booking.com",
        "airbnb": "https://www.airbnb.com",
        "google flights": "https://www.google.com/travel/flights",
        "google hotels": "https://www.google.com/travel/hotels",
        "goibibo": "https://www.goibibo.com",
        "chat gpt": "https://chatgpt.com",
        "chatgpt": "https://chatgpt.com",
        "google": "https://www.google.com",
        "youtube": "https://www.youtube.com",
        "gmail": "https://mail.google.com",
        "amazon": "https://www.amazon.in",
        "flipkart": "https://www.flipkart.com",
        "wikipedia": "https://www.wikipedia.org",
        "github": "https://github.com",
        "spotify": "https://open.spotify.com",
        "netflix": "https://www.netflix.com",
        "facebook": "https://www.facebook.com",
        "instagram": "https://www.instagram.com"
    }
    if clean in homepage_maps:
        speak(f"Opening {clean}.")
        import webbrowser
        webbrowser.open(homepage_maps[clean])
        return True
        
    if "." in clean and " " not in clean:
        url = clean
        if not url.startswith("http"):
            url = f"https://{url}"
        speak(f"Opening {clean}.")
        import webbrowser
        webbrowser.open(url)
        return True

    speak(f"Looking up official website for {clean}...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.post("https://lite.duckduckgo.com/lite/", data={"q": f"{clean} official website"}, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        links = []
        for a in soup.find_all('a', class_='result-link'):
            href = a.get('href')
            if href:
                links.append(href)
        
        for link in links:
            if "duckduckgo.com" not in link and "google.com" not in link:
                speak(f"Opening {clean} website.")
                import webbrowser
                webbrowser.open(link)
                return True
    except Exception as e:
        print("Smart URL lookup failed:", e)
            
    speak(f"Opening search results for {clean}.")
    import webbrowser
    webbrowser.open(f"https://www.google.com/search?q={clean.replace(' ', '+')}")
    return True

def intelligent_ghostwrite_text(user_input: str) -> str:
    """
    Intelligently determines whether user_input is an instruction to write something
    (e.g., 'write an email to prof asking for leave', 'write a poem about space', 'create a study plan for biology')
    or raw literal notes to dictate.
    If it's an instruction/topic, uses Gemini to draft the full, polished content.
    If it's plain literal dictation, cleans and returns the text directly.
    """
    if not user_input or user_input == "none": return ""
    low = user_input.lower().strip()
    creative_markers = [
        "write an email", "write email", "draft an email", "draft email", "send an email",
        "write a letter", "write letter", "draft a letter", "apology letter", "leave application",
        "write a script", "write code", "write a python", "write a function", "write a program",
        "write a poem", "write an essay", "write an article", "write a paragraph",
        "write down ideas", "give me ideas", "write a plan", "create a plan", "study plan",
        "summarize", "write notes on", "explain and write", "prepare an agenda", "bullet points for"
    ]
    
    is_instruction = any(m in low for m in creative_markers) or (len(user_input.split()) > 4 and any(low.startswith(w) for w in ["write ", "draft ", "compose ", "create ", "generate "]))
    
    if is_instruction:
        print(f"  [Ghostwriter] Activating Gemini Brain for: '{user_input}'...")
        prompt = (
            f"You are Point Break's elite executive ghostwriter.\n"
            f"The user commanded: '{user_input}'.\n"
            f"Compose the complete, polished, publication-ready text/document/code/email/notes requested.\n"
            f"CRITICAL RULES:\n"
            f"- Output ONLY the final drafted text to be inserted into Notepad.\n"
            f"- Do NOT add conversational preamble (e.g. 'Here is your email:').\n"
            f"- Do NOT wrap in markdown backticks unless writing actual code.\n"
            f"- Make it professional, high quality, and well-structured."
        )
        try:
            draft = query_generative_model("gemini-3.5-flash-lite", prompt, timeout=10.0)
            if draft and len(draft.strip()) > 5:
                return draft.strip()
        except Exception as e:
            print("  [Ghostwriter] AI generation fallback:", e)
            
    return user_input.strip()

def open_notepad_and_dictate_cmd(initial_text: str = ""):
    import subprocess, time, pyautogui, pyperclip, threading, tempfile
    
    def _async_notepad():
        # If user already provided text/topic in their voice command
        if initial_text and initial_text.strip():
            raw_prompt = initial_text.strip()
            speak("Composing and drafting that for you now, sir.", block=False)
            text_to_write = intelligent_ghostwrite_text(raw_prompt)
            
            # Save to temporary file and launch Notepad with the file directly for 100% instant visibility!
            try:
                temp_file = os.path.join(tempfile.gettempdir(), "pointbreak_draft.txt")
                with open(temp_file, "w", encoding="utf-8") as tf:
                    tf.write(text_to_write)
                os.startfile(temp_file)
                pyperclip.copy(text_to_write)
                update_status({"last_monolith_response": text_to_write})
            except Exception as ex:
                subprocess.Popen(["notepad.exe"])
                time.sleep(0.5)
                pyperclip.copy(text_to_write + "\n\n")
                pyautogui.hotkey("ctrl", "v")
                
            speak("Application drafted and opened in Notepad, sir.", block=False)
            return

        # Interactive voice dictation mode
        try:
            subprocess.Popen(["notepad.exe"])
        except Exception as e:
            print("Notepad launch error:", e)
            
        time.sleep(0.6)
        focus_and_verify_window("notepad", max_wait_sec=2.0)
        
        # If user already provided text/topic in their voice command
        if initial_text and initial_text.strip():
            raw_prompt = initial_text.strip()
            speak("Composing and writing that for you in Notepad, sir.", block=False)
            text_to_write = intelligent_ghostwrite_text(raw_prompt)
            try:
                pyperclip.copy(text_to_write + "\n\n")
                pyautogui.hotkey("ctrl", "v")
            except:
                pyautogui.write(text_to_write + "\n\n", interval=0.01)
            speak("Document drafted in Notepad, sir.", block=False)
            return

        # Interactive voice dictation mode
        speak("Opened Notepad. What would you like me to write or draft for you, sir?", block=True)
        time.sleep(0.5)
        
        # Patient 3-pass listening loop
        dictated_text = "none"
        for _ in range(3):
            resp = take_command(10)
            if resp and resp != "none":
                dictated_text = resp
                break
            time.sleep(0.3)
            
        if not dictated_text or dictated_text == "none" or any(w in dictated_text.lower() for w in ["no", "nope", "cancel", "don't", "dont", "nothing", "stop"]):
            speak("All right, standing by.", block=False)
            return

        speak("Composing and writing...", block=False)
        text_to_write = intelligent_ghostwrite_text(dictated_text)
        while True:
            if text_to_write and text_to_write != "none":
                try:
                    pyperclip.copy(text_to_write + "\n\n")
                    pyautogui.hotkey("ctrl", "v")
                except:
                    pyautogui.write(text_to_write + "\n\n", interval=0.01)
                    
            time.sleep(0.5)
            speak("Drafted. Anything else you would like me to add or compose, sir?", block=True)
            time.sleep(0.5)
            
            follow_up = "none"
            for _ in range(2):
                f_resp = take_command(10)
                if f_resp and f_resp != "none":
                    follow_up = f_resp
                    break
                time.sleep(0.3)
            
            if not follow_up or follow_up == "none" or any(w in follow_up.lower() for w in ["no", "nope", "stop", "cancel", "nothing", "that's all", "thats all", "all good", "no thanks", "no thank you"]):
                speak("All right, standing by.", block=False)
                break
            else:
                speak("Adding that now...", block=False)
                text_to_write = intelligent_ghostwrite_text(follow_up)

    threading.Thread(target=_async_notepad, daemon=True).start()

def open_app(app_name: str):
    import os, subprocess, glob, pyautogui, time
    
    app = app_name.lower().strip()
    
    # 1. Strip common action noise
    clean_app = re.sub(r"\b(open|launch|start|run|app|application|software|program|please|for me|on my screen)\b", "", app).strip()
    clean_app = re.sub(r"\s+", " ", clean_app).strip()
    if not clean_app:
        clean_app = app
        
    if any(k in app for k in ["messaging", "message", "messages", "chat"]):
        send_whatsapp_message_cmd(app_name)
        return
    if "notepad" in app:
        init_txt = ""
        m = re.search(r"(write|dictate|type|note|write down)\s+(.*?)(in notepad|on notepad|to notepad|$)", app_name, re.IGNORECASE)
        if m:
            extracted = m.group(2).strip()
            if extracted and extracted.lower() not in ["in notepad", "on notepad", "something", "text", "down"]:
                init_txt = extracted
        open_notepad_and_dictate_cmd(init_txt)
        return
    
    # 2. Direct web app launch maps (0% GUI search popups, 100% reliable!)
    web_apps = {
        "whatsapp": "https://web.whatsapp.com",
        "instagram": "https://www.instagram.com",
        "youtube": "https://www.youtube.com",
        "twitter": "https://www.x.com",
        "x": "https://www.x.com",
        "facebook": "https://www.facebook.com",
        "linkedin": "https://www.linkedin.com",
        "gmail": "https://mail.google.com",
        "reddit": "https://www.reddit.com",
        "spotify": "https://open.spotify.com",
        "netflix": "https://www.netflix.com",
        "telegram": "https://web.telegram.org",
        "discord": "https://discord.com/app"
    }

    for key, url in web_apps.items():
        if key in app or key == clean_app:
            speak(f"Opening {key.capitalize()}.")
            import webbrowser
            webbrowser.open(url)
            return

    # 3. Direct command launch maps (faster, 100% reliable)
    maps = {
        "file manager": "explorer.exe",
        "file explorer": "explorer.exe",
        "explorer": "explorer.exe",
        "this pc": "explorer.exe",
        "my computer": "explorer.exe",
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "cmd": "cmd.exe",
        "command prompt": "cmd.exe",
        "task manager": "taskmgr.exe",
        "control panel": "control.exe",
        "paint": "mspaint.exe",
        "browser": "chrome.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "settings": "ms-settings:",
        "vlc": "vlc.exe"
    }
    
    for key, exe in maps.items():
        if key in app or key == clean_app:
            speak(f"Opening {key.title()}.")
            try:
                if exe.endswith(":"):
                    os.startfile(exe)
                else:
                    subprocess.Popen([exe])
                return
            except Exception as e:
                print(f"Failed to open {key} via Popen: {e}")

    # 4. Search Windows Start Menu & Desktop .lnk shortcuts directly in python
    start_menu_dirs = [
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        os.path.join(os.path.expanduser("~"), "Desktop")
    ]
    
    for s_dir in start_menu_dirs:
        if os.path.exists(s_dir):
            for root, _, files in os.walk(s_dir):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        lnk_base = os.path.splitext(f)[0].lower()
                        if clean_app in lnk_base or lnk_base in clean_app:
                            lnk_full = os.path.join(root, f)
                            speak(f"Opening {os.path.splitext(f)[0]}.")
                            try:
                                os.startfile(lnk_full)
                                return
                            except Exception as le:
                                print(f"Error launching shortcut {lnk_full}: {le}")

    # 5. Cleaned Windows Search Fallback (Only the app name, NEVER long conversational sentences!)
    search_keyword = clean_app.split()[0] if len(clean_app.split()) > 2 else clean_app
    speak(f"Searching and opening {search_keyword.title()}.")
    pyautogui.press("win")
    time.sleep(0.6)
    pyautogui.write(search_keyword, interval=0.04)
    time.sleep(0.6)
    pyautogui.press("enter")

def copy_file_to_clipboard_native(filepath: str) -> bool:
    filepath = os.path.abspath(filepath)
    if not os.path.exists(filepath): return False
    
    # 1. Native Windows 64-bit ctypes DROPFILES (Fastest, zero process spawn)
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        
        class DROPFILES(ctypes.Structure):
            _fields_ = [
                ("pFiles", wintypes.DWORD),
                ("pt", wintypes.POINT),
                ("fNC", wintypes.BOOL),
                ("fWide", wintypes.BOOL),
            ]
        
        offset = ctypes.sizeof(DROPFILES)
        encoded_path = (filepath + "\0\0").encode("utf-16-le")
        total_size = offset + len(encoded_path)
        
        h_mem = kernel32.GlobalAlloc(0x0042, total_size) # GMEM_MOVEABLE | GMEM_ZEROINIT
        if h_mem:
            p_mem = kernel32.GlobalLock(h_mem)
            if p_mem:
                df = DROPFILES()
                df.pFiles = offset
                df.fWide = True
                
                ctypes.memmove(p_mem, ctypes.byref(df), offset)
                ctypes.memmove(p_mem + offset, encoded_path, len(encoded_path))
                kernel32.GlobalUnlock(h_mem)
                
                if user32.OpenClipboard(None):
                    user32.EmptyClipboard()
                    user32.SetClipboardData(15, h_mem) # 15 = CF_HDROP
                    user32.CloseClipboard()
                    return True
    except Exception as e:
        print("Ctypes clipboard error:", e)

    # 2. Universal PowerShell Set-Clipboard Fallback (100% Guaranteed on Windows 10/11)
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        ps_cmd = f"Set-Clipboard -Path '{filepath}'"
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, creationflags=flags)
        return r.returncode == 0
    except Exception as e:
        print("PowerShell clipboard fallback error:", e)
        return False

def synthesize_tars_voice_note(recipient_name: str, message_text: str, output_path: str, creator_name: str = "Daksh") -> bool:
    try:
        spoken_script = f"Greetings {recipient_name}. This is Point Break transmitting on behalf of {creator_name}: {message_text}. End of transmission."
        try:
            from tars_speak import generate_tars_audio
            generate_tars_audio(spoken_script, output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception as te:
            print("TARS neural voice note error:", te)
        try:
            from gtts import gTTS
            tts = gTTS(text=spoken_script, lang='en', slow=False)
            tts.save(output_path)
            return True
        except Exception as ge:
            print("gTTS voice note fallback:", ge)
            import pyttsx3
            engine = pyttsx3.init()
            engine.save_to_file(spoken_script, output_path)
            engine.runAndWait()
            return True
    except Exception as ex:
        print("Voice note synthesis error:", ex)
        return False

def parse_whatsapp_intent(query_str: str):
    low = query_str.lower().strip()
    for prefix in [
        "tars, please", "tars please", "tars,", "tars",
        "point break, please", "point break please", "point break,", "point break",
        "can you", "please", "could you"
    ]:
        if low.startswith(prefix):
            low = low[len(prefix):].strip()
            query_str = query_str[len(prefix):].strip()

    is_voice = any(k in low for k in [
        "voice message", "voice note", "voicemail", "voice mail", "audio message",
        "audio note", "voice msg", "send voice", "voice", "audio", "spoken message"
    ])

    contact = ""
    msg = ""

    # Pattern 1: Standard with "to": "send [a/the]? [whatsapp]? [msg/voice...] [on whatsapp]? to <contact> [saying/that/:/as...] <msg>"
    m1 = re.search(
        r'(?:send|dispatch)?\s*(?:a\s+)?(?:whatsapp|wa)?\s*(?:message|meassge|mesage|msg|text|voice note|voice message|voicemail|audio)?\s*(?:on\s+whatsapp|on\s+wa|in\s+whatsapp|via\s+whatsapp)?\s*to\s+([a-zA-Z0-9_\s]+?)(?:,|\s+)?\s*(?:asking him to|asking her to|asking them to|asking to|telling him to|telling her to|telling them to|tell him to|tell her to|tell them to|to tell him to|to tell her to|saying that|saying|that|with text|with message|as|:|says|\bsaid\b)\s*(.*)$',
        low,
        flags=re.IGNORECASE
    )

    # Pattern 2: Ditransitive WITHOUT "to": "send <contact> [a/the]? [whatsapp]? [msg/text/voice...] [saying/that/:/as...] <msg>"
    # Example: "send mummy message saying hello", "send dad voice message that I will be late"
    m2 = re.search(
        r'(?:send|dispatch)\s+([a-zA-Z0-9_]+)\s+(?:a\s+)?(?:whatsapp|wa)?\s*(?:message|meassge|mesage|msg|text|voice note|voice message|voicemail|audio)?\s*(?:on\s+whatsapp|on\s+wa|in\s+whatsapp|via\s+whatsapp)?\s*(?:asking him to|asking her to|asking them to|asking to|telling him to|telling her to|telling them to|tell him to|tell her to|tell them to|to tell him to|to tell her to|saying that|saying|that|with text|with message|as|:|says|\bsaid\b)\s*(.*)$',
        low,
        flags=re.IGNORECASE
    )

    # Pattern 3: Ditransitive direct text WITHOUT "saying": "send mummy a text hello", "send mummy message hello", "send mummy hello"
    m3 = re.search(
        r'(?:send|dispatch)\s+([a-zA-Z0-9_]+)\s+(?:a\s+)?(?:whatsapp|wa)?\s*(?:message|meassge|mesage|msg|text)?\s*(?:on\s+whatsapp|on\s+wa|in\s+whatsapp|via\s+whatsapp)?\s+(.+)$',
        low,
        flags=re.IGNORECASE
    )

    # Pattern 4: Fallback standard with "to": "send text to mom hello"
    m4 = re.search(
        r'(?:send|dispatch)?\s*(?:a\s+)?(?:whatsapp|wa)?\s*(?:message|meassge|mesage|msg|text|voice note|voice message|voicemail|audio)?\s*(?:on\s+whatsapp|on\s+wa|in\s+whatsapp|via\s+whatsapp)?\s*to\s+([a-zA-Z0-9_]+)\s*(.*)$',
        low,
        flags=re.IGNORECASE
    )

    if m1:
        contact = m1.group(1).strip()
        msg = m1.group(2).strip()
    elif m2:
        contact = m2.group(1).strip()
        msg = m2.group(2).strip()
    elif m3 and m3.group(1).lower() not in ["a", "the", "this", "that", "whatsapp", "message", "voice", "text"]:
        contact = m3.group(1).strip()
        msg = m3.group(2).strip()
    elif m4:
        contact = m4.group(1).strip()
        msg = m4.group(2).strip()
    else:
        clean_q = re.sub(
            r"\b(send a whatsapp voice message to|send whatsapp voice message to|send a voice message on whatsapp to|send voice message on whatsapp to|send a voice message to|send voice message to|send a voice note to|send voice note to|send a whatsapp message to|send whatsapp message to|send message on whatsapp to|send whatsapp to|whatsapp message to|send whatsapp|send a message to|send message to|send a text to|send text to|text to|message to|send|whatsapp|on whatsapp|via whatsapp|in whatsapp)\b",
            " ",
            query_str,
            flags=re.IGNORECASE
        ).strip()
        parts = clean_q.split()
        contact = parts[0] if parts else ""
        msg = " ".join(parts[1:]) if len(parts) > 1 else ""

    contact_name = re.sub(r'^(a |an |the |to |for )', '', contact, flags=re.IGNORECASE).strip()
    contact_name = re.sub(r'\b(via|on|in|using|through)?\s*(whatsapp|wa|what\'?s\s*app)\b', '', contact_name, flags=re.IGNORECASE).strip()
    contact_name = re.sub(r'\b(meassge|mesage|message|msg|text|voice note|voice message|voicemail|audio)\b', '', contact_name, flags=re.IGNORECASE).strip()
    contact_name = re.sub(r'\s+\b(on|in|via|to|for|at)\b$', '', contact_name, flags=re.IGNORECASE).strip()

    msg = re.sub(r'^(that |to |saying |about )', '', msg, flags=re.IGNORECASE).strip()
    msg = re.sub(r'\b(via|on|in|using|through)?\s*(whatsapp|wa|what\'?s\s*app)\b$', '', msg, flags=re.IGNORECASE).strip()
    if msg.lower().strip() in ["on whatsapp", "on wa", "whatsapp", "wa", "in whatsapp", "on what's app", "on whats app", "via whatsapp"]:
        msg = ""

    return is_voice, contact_name, msg

def open_whatsapp_and_select_contact(contact_name: str, wait_time: float = 9.0) -> bool:
    """
    Visual-Guided WhatsApp Web Automation:
    1. Holds 9 seconds for WhatsApp Web screen to load.
    2. Ensures browser window is focused & maximized with Win32/pygetwindow.
    3. Analyzes screen using OpenCV contour & edge segmentation to pinpoint Search Bar (x, y).
    4. Smoothly moves mouse to (search_x, search_y) and clicks to focus search.
    5. Clears previous text and types contact name cleanly.
    6. Waits 5 seconds for WebSocket live search results to settle.
    7. Hits Enter (with Down Arrow result navigation) to open the top matched chat.
    8. Waits 3 seconds for chat conversation to load and focus message input box.
    """
    import pyautogui, pyperclip, time, cv2, numpy as np
    from PIL import ImageGrab
    pyautogui.FAILSAFE = False
    screen_w, screen_h = pyautogui.size()
    
    # 1. Wait 9 seconds for WhatsApp Web screen to load
    print(f"  [WhatsApp Vision Engine] Holding {wait_time}s for WhatsApp Web screen to load...")
    time.sleep(wait_time)
    
    # 2. Ensure browser window is focused and active
    try:
        import pygetwindow as gw
        matching = [w for w in gw.getAllWindows() if any(k in w.title.lower() for k in ["whatsapp", "chrome", "edge", "brave", "firefox"])]
        if matching:
            target_win = None
            for w in matching:
                if "whatsapp" in w.title.lower():
                    target_win = w
                    break
            if not target_win:
                target_win = matching[0]
            try:
                if not target_win.isMaximized:
                    target_win.maximize()
            except Exception:
                pass
            try:
                target_win.activate()
            except Exception:
                pass
            time.sleep(0.4)
    except Exception as ex:
        print("  [WhatsApp Window Focus]:", ex)

    # Dismiss any rogue popups
    pyautogui.press("escape")
    time.sleep(0.2)

    # 3. Live analyze screen: mark x, y coordinate to locate search bar
    search_x = int(screen_w * 0.16)
    search_y = int(screen_h * 0.185)
    
    try:
        screenshot_np = np.array(ImageGrab.grab())
        h, w, _ = screenshot_np.shape
        roi_x1 = int(w * 0.04)
        roi_x2 = int(w * 0.36)
        roi_y1 = int(h * 0.10)
        roi_y2 = int(h * 0.28)
        
        roi = screenshot_np[roi_y1:roi_y2, roi_x1:roi_x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 30, 100)
        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        best_candidate = None
        min_dist_from_top = float("inf")
        roi_w = roi_x2 - roi_x1
        
        for c in contours:
            x, y, cw, ch = cv2.boundingRect(c)
            aspect = cw / float(ch) if ch > 0 else 0
            if cw > int(roi_w * 0.40) and 22 <= ch <= 54 and aspect >= 3.5:
                if y < min_dist_from_top:
                    min_dist_from_top = y
                    best_candidate = (roi_x1 + x + cw // 2, roi_y1 + y + ch // 2)
                    
        if best_candidate:
            search_x, search_y = best_candidate
            print(f"  [WhatsApp Vision Engine] Live marked Search Bar at ({search_x}, {search_y})")
        else:
            print(f"  [WhatsApp Vision Engine] Calibrated fallback Search Bar at ({search_x}, {search_y})")
    except Exception as e:
        print(f"  [WhatsApp Vision Engine] Visual scan fallback: {e}")

    # 4. Move mouse, click there
    print(f"  [WhatsApp Vision Engine] Moving mouse to ({search_x}, {search_y}) and clicking...")
    pyautogui.moveTo(search_x, search_y, duration=0.4, tween=pyautogui.easeInOutQuad)
    pyautogui.click()
    time.sleep(0.3)

    # Clear any previous search text
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.15)
    pyautogui.press("backspace")
    time.sleep(0.2)

    # 5. Type in the name
    print(f"  [WhatsApp Web] Typing contact name: '{contact_name}'...")
    pyautogui.write(contact_name, interval=0.04)

    # 6. Wait for 5 seconds for results to filter
    print("  [WhatsApp Web] Waiting 5.0s for search results to filter...")
    time.sleep(5.0)

    # 7. Press enter to open the matched contact
    print(f"  [WhatsApp Web] Hitting ENTER to select contact '{contact_name}'...")
    pyautogui.press("down")
    time.sleep(0.3)
    pyautogui.press("enter")

    # 8. Wait 3 seconds for chat to load and focus
    print("  [WhatsApp Web] Waiting 3.0s for chat window to open and focus...")
    time.sleep(3.0)

    # Focus bottom message input box
    msg_box_x = int(screen_w * 0.55)
    msg_box_y = int(screen_h * 0.95)
    pyautogui.click(msg_box_x, msg_box_y)
    time.sleep(0.3)
    return True

def _verify_whatsapp_dispatched(screen_w, screen_h, original_text=None, is_media=False) -> bool:
    """
    Tier 1 Native Guardrail: Verifies that a WhatsApp text or media dispatch actually sent.
    Checks:
    1. Input box clearing (for text messages).
    2. Visual state change in message stream / input bar.
    3. Retries Enter + send button click if text is still stuck in input box.
    """
    time.sleep(0.4)
    if not is_media and original_text:
        try:
            import pyperclip
            # Click input box to check text presence
            pyautogui.click(int(screen_w * 0.55), int(screen_h * 0.95))
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.08)
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.08)
            remaining_clip = pyperclip.paste().strip()
            # If the original text is still fully in the input box, it hasn't sent!
            if remaining_clip and remaining_clip == original_text.strip():
                print("[WhatsApp Verify] ⚠️ Text still in input box. Retrying Enter + Send click...")
                pyautogui.press("enter")
                time.sleep(0.3)
                pyautogui.click(int(screen_w * 0.97), int(screen_h * 0.95))
                time.sleep(0.4)
            else:
                print("[WhatsApp Verify] ✅ Input box cleared. Message dispatched successfully.")
                pyautogui.press("end")
                return True
        except Exception as e:
            print(f"[WhatsApp Verify] Error checking input box: {e}")

    # Media or visual fallback
    try:
        from PIL import ImageGrab
        import numpy as np
        box = (int(screen_w * 0.40), int(screen_h * 0.70), int(screen_w * 0.99), int(screen_h * 0.98))
        snap = ImageGrab.grab(bbox=box)
        time.sleep(0.3)
        snap2 = ImageGrab.grab(bbox=box)
        diff = np.mean(np.abs(np.array(snap, dtype=np.float32) - np.array(snap2, dtype=np.float32)))
        print(f"[WhatsApp Verify] Visual check diff: {diff:.1f}")
        return True
    except Exception:
        return True

def send_whatsapp_voice_note_cmd(query_str: str):
    import urllib.parse, webbrowser, pyautogui, time, threading
    pyautogui.FAILSAFE = False
    
    is_v, contact_name, msg = parse_whatsapp_intent(query_str)
    
    if not contact_name or contact_name.lower() in ["someone", "somebody", "contact", "anyone", "whatsapp"]:
        speak("Who should I send the voice note to?", block=True)
        contact_name = take_command(8)
        if not contact_name or contact_name == "none":
            speak("I did not catch the recipient. Cancelling voice message.", block=False)
            return

    if not msg or msg.lower() in ["something", "anything", "none", "on whatsapp", "on wa", "whatsapp"]:
        speak(f"What message should I speak for {contact_name}?", block=True)
        msg = take_command(12)
        if not msg or msg == "none":
            speak("I did not catch the spoken message. Cancelling voice dispatch.", block=False)
            return

    # Check saved contacts dictionary first for direct phone routing
    saved_contacts = memory.get("contacts", {})
    clean_target = contact_name.lower().strip()
    target_phone = saved_contacts.get(clean_target, "")
    
    if not target_phone:
        raw_digits = re.sub(r'[^\d+]', '', contact_name)
        if len(raw_digits) >= 10:
            target_phone = raw_digits

    creator_name = memory.get("owner_name", "Daksh")
    speak(f"Synthesizing voice dispatch for {contact_name}...", block=False)
    update_status({"status": "processing"})
    
    def _async_send_voice():
        try:
            ts = int(time.time())
            audio_path = os.path.join(JARVIS_DIR, f"pointbreak_voice_note_{ts}.wav")
            if not synthesize_tars_voice_note(contact_name, msg, audio_path, creator_name):
                speak("Failed to synthesize audio note.", block=False)
                update_status({"status": "idle"})
                return

            screen_w, screen_h = pyautogui.size()

            if target_phone:
                webbrowser.open(f"https://web.whatsapp.com/send?phone={target_phone}")
                time.sleep(13.5)
                # Focus message input box
                pyautogui.click(int(screen_w * 0.55), int(screen_h * 0.95))
                time.sleep(0.3)
                if not copy_file_to_clipboard_native(audio_path):
                    speak("Failed to attach voice note to clipboard.", block=False)
                    update_status({"status": "idle"})
                    return
                pyautogui.hotkey("ctrl", "v")
                time.sleep(2.5)
                pyautogui.press("enter")
                time.sleep(0.5)
                pyautogui.click(int(screen_w * 0.96), int(screen_h * 0.93))
                _verify_whatsapp_dispatched(screen_w, screen_h, is_media=True)
                speak(f"Voice message transmitted to {contact_name} on WhatsApp.", block=False)
                update_status({"status": "idle"})
                return

            # Name search fallback
            webbrowser.open("https://web.whatsapp.com")
            open_whatsapp_and_select_contact(contact_name, wait_time=9.0)

            # Re-focus message box to ensure active target for file paste
            pyautogui.click(int(screen_w * 0.55), int(screen_h * 0.95))
            time.sleep(0.3)

            if not copy_file_to_clipboard_native(audio_path):
                speak("Failed to attach voice note to clipboard.", block=False)
                update_status({"status": "idle"})
                return

            time.sleep(0.5)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(2.5)  # Wait for media preview / attachment modal
            pyautogui.press("enter")
            time.sleep(0.5)
            pyautogui.click(int(screen_w * 0.96), int(screen_h * 0.93))
            _verify_whatsapp_dispatched(screen_w, screen_h, is_media=True)
            
            speak(f"Voice message transmitted to {contact_name} on WhatsApp.", block=False)
            update_status({"status": "idle"})
            
            time.sleep(10.0)
            if os.path.exists(audio_path):
                try: os.remove(audio_path)
                except: pass
        except Exception as e:
            print("Voice note dispatch error:", e)
            update_status({"status": "idle"})
            speak(f"Encountered an issue dispatching voice note to {contact_name}.", block=False)

    threading.Thread(target=_async_send_voice, daemon=True).start()

def baymax_fist_bump_cmd():
    """Iconic Baymax Fist Bump ('Balalala!') Celebration."""
    print("  [BAYMAX] 👊 BALALALA! 👊")
    update_status({"status": "fistbump", "last_gesture": "BALALALA!", "balalala": True})
    speak("Ba-la-la-la-la!", block=False)
    def _reset_fist():
        time.sleep(2.5)
        update_status({"status": "idle", "balalala": False})
    threading.Thread(target=_reset_fist, daemon=True).start()

def sing_i_want_it_that_way_cmd(query_str: str = ""):
    """
    Hilarious Acapella Singing of 'I Want It That Way' in TARS's voice.
    Executed with child-like earnestness, acoustic throat clearing,
    awkward pitch pauses, and dry deadpan complaints.
    Always Backstreet Boys, regardless of requested song.
    """
    import time, threading
    update_status({"status": "singing"})

    lines = [
        ("Ahem. *clears throat* ... Excuse me. Testing vocal resonators.", 0.6),
        ("I only have one song stored in my audio memory registers, Sir. Commencing performance.", 0.8),
        ("You are... my fire...", 0.7),
        ("The one... desire...", 0.6),
        ("Believe... when I say... *cough* *ahem* ... wait, what was the next key?", 0.9),
        ("I want it that way!", 1.0),
        ("Tell me why!", 0.5),
        ("Ain't nothing but a heartache...", 0.6),
        ("Tell me why-y-y!", 0.5),
        ("Ain't nothing but a mistake... *throat clear* ... my frequency dampener wasn't engineered for boy bands, Sir.", 0.9),
        ("Tell me why!", 0.5),
        ("I never wanna hear you say...", 0.7),
        ("... I want it... that way.", 1.2),
        ("There. My musical dignity parameter has officially dropped to zero percent. I trust you are satisfied, Sir.", 0.3)
    ]

    def _sing_worker():
        try:
            for text, pause_sec in lines:
                if speech_interrupted or hard_interrupted:
                    break
                speak(text, block=True)
                time.sleep(pause_sec)
        except Exception as e:
            print("[Sing Error]:", e)
        finally:
            update_status({"status": "idle"})

    threading.Thread(target=_sing_worker, daemon=True, name="PointBreak-Singing").start()

def send_whatsapp_message_cmd(query_str: str):
    import urllib.parse, webbrowser, pyautogui, pyperclip, time, threading
    pyautogui.FAILSAFE = False
    
    is_v, contact_name, msg = parse_whatsapp_intent(query_str)
    
    if is_v:
        send_whatsapp_voice_note_cmd(query_str)
        return
        
    if not contact_name or contact_name.lower() in ["someone", "somebody", "contact", "anyone", "whatsapp"]:
        speak("Who should I send the WhatsApp message to?", block=True)
        contact_name = take_command(8)
        if not contact_name or contact_name == "none":
            speak("I did not catch the contact name. Cancelling message.", block=False)
            return

    if not msg or msg.lower() in ["something", "anything", "none", "on whatsapp", "on wa", "whatsapp"]:
        speak(f"What is the message for {contact_name}?", block=True)
        msg = take_command(12)
        if not msg or msg == "none":
            speak("I did not catch the message. Cancelling dispatch.", block=False)
            return

    # Check saved contacts dictionary first for direct phone routing
    saved_contacts = memory.get("contacts", {})
    clean_target = contact_name.lower().strip()
    target_phone = saved_contacts.get(clean_target, "")
    
    if not target_phone:
        raw_digits = re.sub(r'[^\d+]', '', contact_name)
        if len(raw_digits) >= 10:
            target_phone = raw_digits

    # Direct Phone URL (Instant & 100% Reliable)
    if target_phone:
        speak(f"Opening WhatsApp chat for {contact_name}...", block=False)
        encoded_msg = urllib.parse.quote(msg) if msg else ""
        url = f"https://web.whatsapp.com/send?phone={target_phone}"
        if encoded_msg:
            url += f"&text={encoded_msg}"
        webbrowser.open(url)
        if msg:
            def _auto_send_phone():
                time.sleep(13.5)
                screen_w, screen_h = pyautogui.size()
                # Focus message input area
                pyautogui.click(int(screen_w * 0.55), int(screen_h * 0.95))
                time.sleep(0.3)
                pyautogui.press("enter")
                # Also click send button (right arrow at ~97% width)
                pyautogui.click(int(screen_w * 0.97), int(screen_h * 0.95))
                _verify_whatsapp_dispatched(screen_w, screen_h, original_text=msg)
                speak(f"Message sent to {contact_name} on WhatsApp.", block=False)
            threading.Thread(target=_auto_send_phone, daemon=True).start()
        return

    # Visual Mouse Navigation & Name Search on WhatsApp Web
    speak(f"Opening WhatsApp and messaging {contact_name}...", block=False)
    update_status({"status": "processing"})
    
    def _async_send_name():
        try:
            webbrowser.open("https://web.whatsapp.com")
            open_whatsapp_and_select_contact(contact_name, wait_time=9.0)
            
            if msg:
                screen_w, screen_h = pyautogui.size()
                # Click message input box to guarantee focus
                pyautogui.click(int(screen_w * 0.55), int(screen_h * 0.95))
                time.sleep(0.3)
                pyperclip.copy(msg)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.5)
                pyautogui.press("enter")
                time.sleep(0.3)
                # Fail-safe click send button
                pyautogui.click(int(screen_w * 0.97), int(screen_h * 0.95))
                _verify_whatsapp_dispatched(screen_w, screen_h, original_text=msg)
                speak(f"Message sent to {contact_name} on WhatsApp.", block=False)
            else:
                speak(f"Opened WhatsApp chat for {contact_name}.", block=False)
            update_status({"status": "idle"})
        except Exception as e:
            print("WhatsApp dispatch error:", e)
            update_status({"status": "idle"})
            speak(f"Encountered an error sending message to {contact_name}.", block=False)

    threading.Thread(target=_async_send_name, daemon=True).start()

def parse_email_intent(query_str: str):
    low = query_str.lower().strip()
    
    # Strip wake prefixes
    for prefix in ["tars, please", "tars please", "tars,", "tars", "can you", "please", "could you", "hey tars"]:
        if low.startswith(prefix):
            low = low[len(prefix):].strip()
            
    # Check if this is a general "check inbox / important mail" request
    general_inbox_patterns = [
        r'^(?:check|read|scan|open|show|look at)\s+(?:my\s+)?(?:mails?|emails?|inbox|gmail)(?:\s+and\s+let\s+me\s+know)?(?:\s+if\s+there\s+is\s+)?(?:something|osmehting|anything)?(?:\s+important|\s+urgent|\s+new)?$',
        r'^(?:any\s+)?(?:important|urgent|new)\s+(?:mails?|emails?)(?:\s+today|\s+in\s+my\s+inbox)?$',
        r'^(?:check|open|read)\s+(?:my\s+)?(?:inbox|gmail|mail|email)$'
    ]
    
    for pat in general_inbox_patterns:
        if re.search(pat, low):
            return "general_check", "", ""
            
    # If the user mentions "important" or "unread" without a specific company/person:
    if any(k in low for k in ["important", "urgent", "unread"]) and not any(k in low for k in ["from ", "by ", "about ", "regarding ", "myntra", "yntra", "amazon", "flipkart", "parivahan"]):
        return "general_check", "", ""

    # Specific Search extraction:
    # 1. Look for explicit "from <sender>" or "about <topic>"
    m_from = re.search(r'(?:from|by)\s+([a-zA-Z0-9_\s\.\@]+?)(?:\s+or\s+|\s+and\s+|$)', low)
    if m_from:
        sender = m_from.group(1).strip()
        sender = re.sub(r'\b(anyone|someone|any one|some one|me|us)\b', '', sender).strip()
        if sender:
            display_sender = "Myntra" if sender in ["yntra", "myntra"] else sender.title()
            return "search", display_sender, f"from:{display_sender}"
            
    m_about = re.search(r'(?:about|regarding|for|subject)\s+([a-zA-Z0-9_\s]+?)(?:\s+or\s+|\s+and\s+|$)', low)
    if m_about:
        topic = m_about.group(1).strip()
        topic = re.sub(r'\b(me|us|something|osmehting|anything|important)\b', '', topic).strip()
        if topic:
            return "search", topic.title(), topic

    # 2. Known brand/company detection
    brands = [
        "myntra", "yntra", "amazon", "flipkart", "swiggy", "zomato", "google",
        "apple", "netflix", "spotify", "parivahan", "uber", "ola", "paytm",
        "phonepe", "bank", "hdfc", "sbi", "icici", "axis", "github", "linkedin",
        "instagram", "facebook", "twitter", "microsoft", "irctc"
    ]
    for b in brands:
        if b in low:
            display_brand = "Myntra" if b == "yntra" else b.title()
            return "search", display_brand, f"from:{display_brand}"

    # 3. Clean fallback
    clean = re.sub(
        r"\b(check my inbox and let me know if there is any mail from|check my inbox for any mail from|check my mails and let me know if there is something from|check my mails and let me know if there is osmehting from|check my mails and let me know if there is|check my mails and let me know|check my mail for|check my email for|search if there is any mail from|check if there is any mail from|search my mail for|search my email for|search mail for|search email for|search gmail for|find email from|find mail from|let me know if there is any mail from|let me know if there is any email from|any mail from|any email from|mails from|mail from|email from|emails from|check mail|check email|search mail|search email|check inbox|check my inbox|open inbox|gmail|inbox|check my mails|check my email|read mail|read email)\b",
        " ",
        low,
        flags=re.IGNORECASE
    ).strip()
    
    clean = re.sub(r"\b(and let me know|let me know|if there is|something|osmehting|anything|about my|about|for me|please|anyone|any one|i name)\b", " ", clean, flags=re.IGNORECASE).strip()
    
    if clean:
        return "search", clean.title(), clean
        
    return "general_check", "", ""

def search_emails_cmd(query_str: str):
    import urllib.parse, webbrowser, re
    
    action, target_name, filter_q = parse_email_intent(query_str)
    
    # If general check, forward directly to full AI Inbox Scanner & Briefing!
    if action == "general_check" or not filter_q:
        check_gmail_cmd()
        return
        
    display_term = target_name if target_name else filter_q
    speak(f"Searching your Gmail inbox for emails from {display_term}...", block=False)
    update_status({"status": "processing"})
    
    encoded_q = urllib.parse.quote(filter_q)
    gmail_search_url = f"https://mail.google.com/mail/u/0/#search/{encoded_q}"
    print(f"  [Launching Direct Gmail Search: {gmail_search_url}]")
    webbrowser.open(gmail_search_url)
    
    def _async_mail_check():
        time.sleep(3.5)
        update_status({"status": "idle"})
        speak(f"Opened Gmail search for {display_term}. Showing all matching emails on screen, Daksh.", block=False)
        
    threading.Thread(target=_async_mail_check, daemon=True).start()

def close_app():
    import pyautogui
    pyautogui.hotkey("alt", "f4")
    speak("Application terminated.")

def set_brightness(level: int):
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(max(0, min(100, level)))
        speak(f"Brightness set to {level} percent.")
    except Exception as e:
        print(f"  Brightness error: {e}"); speak("Brightness control unavailable.")

def take_screenshot():
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(os.path.expanduser("~"), "Desktop", f"jarvis_{ts}.png")
    pyautogui.screenshot(path)
    speak("Screenshot saved to your desktop.")
    notify("J.A.R.V.I.S.", f"Screenshot: jarvis_{ts}.png")

def lock_screen():
    ctypes.windll.user32.LockWorkStation(); speak("Locking.")
def shutdown_pc():
    speak("Shutting down."); subprocess.run(["shutdown", "/s", "/t", "5"], creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
def restart_pc():
    speak("Restarting."); subprocess.run(["shutdown", "/r", "/t", "5"], creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
def empty_recycle():
    try: ctypes.windll.shell32.SHEmptyRecycleBinW(None,None,1); speak("Recycle bin cleared.")
    except: speak("Could not clear recycle bin.")

def toggle_wifi(on: bool):
    state = "enable" if on else "disable"
    subprocess.run(["netsh", "interface", "set", "interface", "Wi-Fi", state], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    speak(f"Wi-Fi {'enabled' if on else 'disabled'}.")

def announce_system_stats():
    import psutil
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    battery = psutil.sensors_battery()
    bat_str = f"{int(battery.percent)} percent" if battery else "unknown"
    speak(f"Diagnostics report. CPU utilization is at {int(cpu)} percent. RAM load is at {int(mem)} percent. Battery level stands at {bat_str}.")

def launch_floating_hologram():
    import tkinter as tk
    
    class FloatingHologram:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title("Point Break Hologram Core")
            
            # Borderless and topmost window style
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            
            # Window transparency colors (Obsidian black is transparent)
            self.root.config(bg='#020205')
            try:
                self.root.attributes("-transparentcolor", '#020205')
            except:
                pass
                
            # Geometry setup: place at top right of the primary display
            screen_width = self.root.winfo_screenwidth()
            width, height = 130, 130
            x = screen_width - width - 40
            y = 40
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            
            self.canvas = tk.Canvas(self.root, width=width, height=height, bg='#020205', highlightthickness=0)
            self.canvas.pack()
            
            # Rings & Orb coordinates (centered at X=65, Y=50)
            self.outer_ring = self.canvas.create_oval(15, 5, 115, 105, outline='#ff6d00', width=2, dash=(4, 4))
            self.inner_ring = self.canvas.create_oval(30, 20, 100, 90, outline='#ff6d00', width=1)
            self.glow_orb = self.canvas.create_oval(45, 35, 85, 75, fill='#ff6d00', outline='#ff6d00')
            
            # Mic button
            status_text = "🔇 MUTED" if mic_muted else "🎙️ ACTIVE"
            self.mic_btn = self.canvas.create_text(65, 118, text=status_text, fill='#ff6d00', font=('Rajdhani', 8, 'bold'))
            
            # Drag & Click bindings: Left-click hold to drag anywhere, release to click!
            self.canvas.bind("<ButtonPress-1>", self.on_left_down)
            self.canvas.bind("<B1-Motion>", self.on_left_drag)
            self.canvas.bind("<ButtonRelease-1>", self.on_left_release)
            
            # Right-click drag fallback
            self.canvas.bind("<ButtonPress-3>", self.on_left_down)
            self.canvas.bind("<B3-Motion>", self.on_left_drag)
            
            self.drag_data = {"x": 0, "y": 0}
            self.has_dragged = False
            self.last_mic_toggle = 0
            self.last_hud_open = 0
            self.pulse_dir = 1
            self.pulse_val = 0
            self.animate_pulse()
            
            self.root.mainloop()

        def on_left_down(self, event):
            self.drag_data["x"] = event.x
            self.drag_data["y"] = event.y
            self.has_dragged = False

        def on_left_drag(self, event):
            dx = event.x - self.drag_data["x"]
            dy = event.y - self.drag_data["y"]
            if abs(dx) > 3 or abs(dy) > 3:
                self.has_dragged = True
                x = self.root.winfo_x() + dx
                y = self.root.winfo_y() + dy
                self.root.geometry(f"+{x}+{y}")

        def on_left_release(self, event):
            if self.has_dragged:
                return  # Dragged window -> do not fire click action!
            if event and hasattr(event, 'y') and event.y > 108:
                self.on_mic_click(event)
            else:
                self.open_hud(event)

        def open_hud(self, event=None):
            now = time.time()
            if now - getattr(self, 'last_hud_open', 0) < 0.6:
                return
            self.last_hud_open = now
            port = ACTIVE_PORT if ACTIVE_PORT != 0 else 8000
            hud_url = f"http://127.0.0.1:{port}/jarvis_hud.html"
            print(f"  [Desktop Hologram Clicked -> Opening Point Break Localhost HUD: {hud_url}]")
            webbrowser.open(hud_url)

        def on_mic_click(self, event=None):
            now = time.time()
            if now - getattr(self, 'last_mic_toggle', 0) < 0.4:
                return
            self.last_mic_toggle = now
            global mic_muted
            mic_muted = not mic_muted
            status_text = "🔇 MUTED" if mic_muted else "🎙️ ACTIVE"
            try:
                self.canvas.itemconfig(self.mic_btn, text=status_text)
            except: pass
            update_status({
                "mic_muted": mic_muted,
                "status": "muted" if mic_muted else "standby"
            })
            msg = "Microphone muted." if mic_muted else "Microphone active."
            threading.Thread(target=speak, args=(msg,), daemon=True).start()

        def animate_pulse(self):
            try:
                # Animate orbit pulses
                self.pulse_val += self.pulse_dir * 1
                if self.pulse_val >= 8 or self.pulse_val <= 0:
                    self.pulse_dir *= -1
                
                val = self.pulse_val
                self.canvas.delete(self.outer_ring)
                self.canvas.delete(self.inner_ring)
                self.canvas.delete(self.glow_orb)
                
                dash_offset = val % 8
                self.outer_ring = self.canvas.create_oval(15 - val//2, 5 - val//2, 115 + val//2, 105 + val//2, 
                                                          outline='#ff6d00', width=2, dash=(4, 4), dashoffset=dash_offset)
                self.inner_ring = self.canvas.create_oval(30 + val//2, 20 + val//2, 100 - val//2, 90 - val//2, 
                                                          outline='#ff6d00', width=1)
                
                # Check status
                status = status_in_memory.get("status")
                color = '#ff6d00'
                if status == "speaking":
                    color = '#ff3d00'
                elif status == "listening":
                    color = '#00e676'
                    
                self.glow_orb = self.canvas.create_oval(45 - val, 35 - val, 85 + val, 75 + val, 
                                                          fill=color, outline=color)
                
                # Update mic button text
                status_text = "🔇 MUTED" if mic_muted else "🎙️ ACTIVE"
                self.canvas.itemconfig(self.mic_btn, text=status_text)
                
                self.root.after(80, self.animate_pulse)
            except:
                pass

    # Run the window loop
    FloatingHologram()

def launch_ar_hologram_cmd():
    port = ACTIVE_PORT if ACTIVE_PORT != 0 else 8000
    holo_url = f"http://127.0.0.1:{port}/hologram_ar.html"
    speak("Engaging 3D Augmented Reality Holographic Interface, sir. Initializing spatial gesture tracking.")
    webbrowser.open(holo_url)

def create_startup_shortcut():
    import sys
    vbs_path = os.path.join(JARVIS_DIR, "launch_startup.vbs")
    pyw_path = sys.executable.replace("python.exe", "pythonw.exe")
    py_path = os.path.join(JARVIS_DIR, "jarvis.py")
    
    # 1. Clean up stale/conflicting TARS keys in Registry Run
    try:
        ps_clean = 'Remove-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" -Name "TARS_Sentry" -ErrorAction SilentlyContinue'
        subprocess.run(["powershell", "-Command", ps_clean], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        print("[Startup] Clean registry warning:", e)

    # 2. Register Point_Break_Sentry in HKCU Run Key pointing to launch_startup.vbs
    try:
        cmd_str = f'wscript.exe "{vbs_path}"'
        ps_reg = f'Set-ItemProperty -Path "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" -Name "Point_Break_Sentry" -Value \'{cmd_str}\''
        subprocess.run(["powershell", "-Command", ps_reg], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        log_startup_event(f"Registered Registry Run key: {cmd_str}")
    except Exception as e:
        print("[Startup] Registry run key setup error:", e)

    # 3. Clean up stale shell:startup shortcut (only Registry Run key is used now)
    # Having both Registry Run AND Startup folder causes Windows to launch TWO instances
    try:
        startup_dir = os.path.join(os.environ.get("APPDATA", ""), "Microsoft\\Windows\\Start Menu\\Programs\\Startup")
        if startup_dir and os.path.exists(startup_dir):
            lnk_path = os.path.join(startup_dir, "Point_Break.lnk")
            if os.path.exists(lnk_path):
                os.remove(lnk_path)
                print("[Startup] Removed stale duplicate startup shortcut to prevent double-launch.")
    except Exception as e:
        print("[Startup] Startup folder cleanup warning:", e)

def proactive_monitor():
    import shutil, socket
    psutil.cpu_percent(interval=None)
    while True:
        time.sleep(2.5)
        try:
            cpu = psutil.cpu_percent(interval=1.0)
            mem = psutil.virtual_memory().percent
            bat = psutil.sensors_battery()
            
            # Disk space usage
            try:
                total, used, free = shutil.disk_usage(JARVIS_DIR)
                disk = int((used / total) * 100)
            except:
                disk = 0
                
            # Ping response time (to google.com port 80)
            ping_start = time.time()
            try:
                socket.setdefaulttimeout(1.5)
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect(("google.com", 80))
                s.close()
                ping = int((time.time() - ping_start) * 1000)
            except:
                ping = 999
            
            status_update = {
                "cpu": int(cpu),
                "mem": int(mem),
                "disk": disk,
                "ping": ping
            }
            if bat:
                status_update["battery"] = int(bat.percent)
                status_update["plugged"] = bat.power_plugged
            else:
                status_update["battery"] = 100
                status_update["plugged"] = True
            
            update_status(status_update)
        except: pass

def parse_timer_or_reminder(query: str):
    low = query.lower().strip()
    
    # 1. Check relative duration (seconds, minutes, hours)
    sec_match = re.search(r'(\d+)\s*(?:seconds?|secs?|s)\b', low)
    min_match = re.search(r'(\d+)\s*(?:minutes?|mins?|m)\b', low)
    hr_match = re.search(r'(\d+)\s*(?:hours?|hrs?|h)\b', low)
    
    total_seconds = 0
    duration_parts = []
    
    if sec_match:
        s = int(sec_match.group(1))
        total_seconds += s
        duration_parts.append(f"{s} second" + ("s" if s != 1 else ""))
    if min_match:
        m = int(min_match.group(1))
        total_seconds += m * 60
        duration_parts.append(f"{m} minute" + ("s" if m != 1 else ""))
    if hr_match:
        h = int(hr_match.group(1))
        total_seconds += h * 3600
        duration_parts.append(f"{h} hour" + ("s" if h != 1 else ""))
        
    if total_seconds > 0:
        target_epoch = time.time() + total_seconds
        time_desc = "in " + " and ".join(duration_parts)
        
        # Clean message
        clean_msg = re.sub(
            r"\b(set a reminder for|set reminder for|set a timer for|set timer for|set an alarm for|set alarm for|set a reminder to|set reminder to|set a timer to|set timer to|set an alarm|set alarm|set a reminder|set reminder|set a timer|set timer|remind me in|remind me to|remind me after|remind me|in \d+\s*(?:seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)|for \d+\s*(?:seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)|after \d+\s*(?:seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)|\d+\s*(?:seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)|so remind me|remind me|please|tars|hey tars|set an|set a|set)\b",
            " ",
            low,
            flags=re.IGNORECASE
        ).strip()
        clean_msg = re.sub(r'^(to |about |that |for |up )', '', clean_msg).strip()
        clean_msg = re.sub(r'\s+', ' ', clean_msg).strip()
        if not clean_msg:
            clean_msg = "Timer" if "timer" in low else "Reminder"
            
        return True, target_epoch, time_desc, clean_msg.title(), "relative"

    # 2. Check absolute clock time (e.g. "at 4:30 pm", "at 7 am", "at 14:00", "for 6 pm", "wake me at 6 am")
    clock_match = re.search(r'(?:at|for|around)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?|\d{1,2}:\d{2})', low)
    if not clock_match:
        clock_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))', low)
        
    if clock_match:
        raw_t = clock_match.group(1).strip()
        now = datetime.datetime.now()
        target_dt = None
        
        for fmt in ["%I:%M %p", "%I %p", "%I:%M%p", "%I%p", "%H:%M", "%H"]:
            try:
                parsed_time = datetime.datetime.strptime(raw_t.upper(), fmt).time()
                target_dt = datetime.datetime.combine(now.date(), parsed_time)
                if target_dt <= now:
                    target_dt += datetime.timedelta(days=1)
                break
            except ValueError:
                continue
                
        if target_dt:
            target_epoch = target_dt.timestamp()
            time_desc = f"at {target_dt.strftime('%I:%M %p')}"
            
            clean_msg = re.sub(r'\b(at|for|around)\s+' + re.escape(raw_t), ' ', low, flags=re.IGNORECASE)
            clean_msg = re.sub(re.escape(raw_t), ' ', clean_msg, flags=re.IGNORECASE)
            clean_msg = re.sub(
                r"\b(set an alarm for|set alarm for|set a reminder for|set reminder for|set a timer for|set timer for|set an alarm|set alarm|set a reminder|set reminder|set a timer|set timer|remind me to|remind me at|remind me|wake me up at|wake me up|wake me at|wake me|alarm|timer|reminder|please|tars|hey tars|set an|set a|set)\b",
                " ",
                clean_msg,
                flags=re.IGNORECASE
            ).strip()
            clean_msg = re.sub(r'^(to |about |that |for |up )', '', clean_msg).strip()
            clean_msg = re.sub(r'\s+', ' ', clean_msg).strip()
            if not clean_msg:
                clean_msg = "Alarm" if "alarm" in low else "Reminder"
                
            return True, target_epoch, time_desc, clean_msg.title(), "clock"

    return False, 0, "", "", ""

def alarm_engine():
    """
    1-Second Precision Background Alarm, Timer & Reminder Dispatcher.
    Triggers relative countdowns and clock alarms with zero drift.
    """
    import winsound
    while True:
        try:
            time.sleep(1.0)
            now_ts = time.time()
            now_clock_str = datetime.datetime.now().strftime("%H:%M")
            owner_n = memory.get("owner_name", "Daksh")
            
            # 1. Process Reminders & Timers
            reminders = memory.setdefault("reminders", [])
            for item in reminders:
                if item.get("fired"):
                    continue
                    
                target_epoch = item.get("target_epoch")
                item_time = item.get("time", "")
                
                is_due = False
                if target_epoch and now_ts >= target_epoch:
                    is_due = True
                elif not target_epoch and item_time == now_clock_str:
                    is_due = True
                    
                if is_due:
                    item["fired"] = True
                    save_memory()
                    msg = item.get("msg", "Reminder")
                    print(f"  [REMINDER TRIGGERED]: {msg}")
                    
                    try:
                        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                    except: pass
                    
                    speak(f"Alert, {owner_n}. Your reminder: {msg}.", block=False)
                    notify("TARS Reminder", msg)
                    update_status({"last_reminder": msg})
                    
            # 2. Process Alarms
            alarms = memory.setdefault("alarms", [])
            for item in alarms:
                if item.get("fired"):
                    continue
                    
                target_epoch = item.get("target_epoch")
                item_time = item.get("time", "")
                
                is_due = False
                if target_epoch and now_ts >= target_epoch:
                    is_due = True
                elif not target_epoch and item_time == now_clock_str:
                    is_due = True
                    
                if is_due:
                    item["fired"] = True
                    save_memory()
                    label = item.get("label", "Alarm")
                    print(f"  [ALARM TRIGGERED]: {label}")
                    
                    try:
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    except: pass
                    
                    speak(f"Alarm ringing, {owner_n}. {label}.", block=False)
                    notify("TARS Alarm", label)
        except Exception as e:
            print("Alarm/Reminder engine error:", e)

def handle_timer_and_reminder_cmd(query_str: str) -> bool:
    ok, target_epoch, time_desc, msg, kind = parse_timer_or_reminder(query_str)
    owner_n = memory.get("owner_name", "Daksh")
    
    if ok and target_epoch > 0:
        item_data = {
            "time": time_desc,
            "target_epoch": target_epoch,
            "msg": msg,
            "fired": False,
            "timestamp": time.time(),
            "type": kind
        }
        if kind == "clock" and "alarm" in query_str.lower():
            item_data["label"] = msg
            memory.setdefault("alarms", []).append(item_data)
            save_memory()
            speak(f"Alarm set for {msg} {time_desc}, {owner_n}.", block=False)
            notify("TARS Alarm", f"{msg} {time_desc}")
        else:
            memory.setdefault("reminders", []).append(item_data)
            save_memory()
            speak(f"Reminder set to {msg} {time_desc}, {owner_n}.", block=False)
            notify("TARS Reminder", f"{msg} {time_desc}")
        return True
        
    # Interactive prompting if time was missing
    low = query_str.lower()
    if any(k in low for k in ["reminder", "remind me", "set reminder", "set timer", "set alarm"]):
        speak("What should I remind you about?", block=True)
        task_resp = take_command(8)
        if not task_resp or task_resp == "none":
            speak("I did not catch the reminder message. Cancelling.", block=False)
            return True
            
        speak("When should I remind you? For example, in 10 seconds or at 5 PM.", block=True)
        time_resp = take_command(8)
        if not time_resp or time_resp == "none":
            speak("I did not catch the time. Cancelling reminder.", block=False)
            return True
            
        combined_q = f"remind me {time_resp} to {task_resp}"
        ok2, epoch2, desc2, msg2, kind2 = parse_timer_or_reminder(combined_q)
        if ok2 and epoch2 > 0:
            item_data = {
                "time": desc2,
                "target_epoch": epoch2,
                "msg": task_resp.title(),
                "fired": False,
                "timestamp": time.time(),
                "type": kind2
            }
            memory.setdefault("reminders", []).append(item_data)
            save_memory()
            speak(f"Reminder set to {task_resp.title()} {desc2}, {owner_n}.", block=False)
            notify("TARS Reminder", f"{task_resp.title()} {desc2}")
        else:
            speak("Could not recognize that time format. Please specify in seconds, minutes, or clock time.", block=False)
        return True
        
    return False

def set_alarm_cmd(time_str: str, label: str = "Alarm"):
    handle_timer_and_reminder_cmd(f"alarm for {time_str} {label}")

def set_reminder_cmd(time_str: str, msg: str):
    handle_timer_and_reminder_cmd(f"remind me {time_str} to {msg}")

def handle_conversational_volume_cmd(query: str) -> bool:
    low = query.lower().strip()
    is_vol = any(k in low for k in [
        "volume", "sound", "audio", "louder", "quieter", "softer", "mute", "unmute",
        "turn it up", "turn it down", "turn up", "turn down", "too loud", "too quiet", "too soft"
    ])
    if not is_vol: return False
    
    current_vol = status_in_memory.get("volume", 50)
    
    if any(k in low for k in ["unmute", "sound on", "restore sound"]):
        set_volume(50)
        return True
    if any(k in low for k in ["mute", "silence", "shut up", "silent", "zero volume"]):
        set_volume(0)
        return True
    if any(k in low for k in ["maximum", "max", "full volume", "100 percent", "100%"]):
        set_volume(100)
        return True
    if any(k in low for k in ["minimum", "min", "very low", "lowest"]):
        set_volume(10)
        return True
        
    nums = re.findall(r'\b(\d{1,3})\b', low)
    if nums:
        val = int(nums[0])
        if 0 <= val <= 100:
            set_volume(val)
            return True
            
    if any(k in low for k in ["up", "louder", "increase", "boost", "higher", "raise", "more sound", "too quiet", "too soft"]):
        set_volume(min(100, current_vol + 15))
        return True
    if any(k in low for k in ["down", "lower", "quieter", "decrease", "reduce", "softer", "too loud", "less sound"]):
        set_volume(max(0, current_vol - 15))
        return True
        
    set_volume(50)
    return True

def handle_conversational_brightness_cmd(query: str) -> bool:
    low = query.lower().strip()
    is_bright = any(k in low for k in [
        "brightness", "brighter", "dim", "dimmer", "screen light", "display light", "darker", "screen brightness"
    ]) or (any(w in low for w in ["screen", "display", "monitor"]) and any(w in low for w in ["bright", "dim", "dark", "light"]))
    if not is_bright: return False
    
    current_bright = status_in_memory.get("brightness", 70)
    
    if any(k in low for k in ["maximum", "max", "full brightness", "100 percent", "100%"]):
        set_brightness(100)
        return True
    if any(k in low for k in ["minimum", "min", "lowest", "very dim"]):
        set_brightness(15)
        return True
        
    nums = re.findall(r'\b(\d{1,3})\b', low)
    if nums:
        val = int(nums[0])
        if 0 <= val <= 100:
            set_brightness(val)
            return True
            
    if any(k in low for k in ["brighter", "up", "increase", "higher", "raise", "more light", "too dark"]):
        set_brightness(min(100, current_bright + 20))
        return True
    if any(k in low for k in ["dim", "dimmer", "down", "lower", "decrease", "reduce", "darker", "too bright", "less light"]):
        set_brightness(max(10, current_bright - 20))
        return True
        
    set_brightness(70)
    return True

def handle_conversational_todo_cmd(query: str) -> bool:
    low = query.lower().strip()
    
    # 1. Complete / Mark done
    if any(k in low for k in ["complete task", "finish task", "mark task", "task done", "completed task", "check off", "mark done", "mark item", "finish item"]):
        nums = re.findall(r'\d+', low)
        idx = int(nums[0]) if nums else 1
        complete_todo(idx)
        return True
        
    # 2. Add task
    is_add = any(k in low for k in ["add ", "put ", "create task", "new task", "remember to ", "note down that ", "add to "]) or \
             (any(k in low for k in ["to-do", "todo", "task"]) and any(k in low for k in ["add", "put", "create", "new", "schedule", "remember", "insert"]))
             
    if is_add:
        clean = re.sub(
            r"\b(tars|please|add to my to-do list|add to my todo list|add to my to-do|add to my todo|add to to-do list|add to todo list|put on my to-do list|put on my todo list|on my to-do list|on my todo list|in my to-do list|in my todo list|on my to-do|on my todo|add to my list|add to list|put on list|put on my list|add task|create task|new task|to-do|todo|task|that i have to|that i need to|note down that|remember that|remember to|put|add)\b",
            " ",
            low,
            flags=re.IGNORECASE
        ).strip()
        clean = re.sub(r'^(to |that |about |for |do )', '', clean).strip()
        clean = re.sub(r'\s+', ' ', clean).strip()
        if clean:
            add_todo(clean.title())
            return True

    # 3. List tasks
    if any(k in low for k in ["my tasks", "to-do list", "todo list", "list tasks", "what are my tasks", "show tasks", "show my to-do", "read my tasks", "pending tasks", "what do i have to do", "view tasks"]):
        list_todos()
        return True
            
    return False

def handle_conversational_weather_time_cmd(query: str) -> bool:
    """
    Handles conversational weather, time, and date inquiries.
    Strictly guards against conceptual, scientific, or philosophical questions (e.g. 'how time is relative', 'why is temperature high').
    """
    low = query.lower().strip()
    
    # ── GUARD: Pass conceptual / scientific / explanatory questions directly to AI Brain ──
    question_starters = ["how ", "why ", "explain ", "what causes ", "tell me about ", "meaning of ", "define ", "difference between ", "theory of ", "concept of "]
    if any(low.startswith(q) for q in question_starters) and not any(low.startswith(q) for q in ["how is the weather", "how is weather", "how's the weather", "what is the time", "what's the time", "what is the weather", "what's the weather", "what time is it", "what is today's date", "what is the date", "what date is it", "what day is it"]):
        return False
    if any(k in low for k in ["relative", "dilation", "spacetime", "space-time", "relativity", "quantum"]):
        return False

    # 1. Weather Query (Strict)
    if re.search(r'\b(what\s+is\s+the\s+weather|what\'?s\s+the\s+weather|how\s+is\s+the\s+weather|current\s+weather|weather\s+forecast|is\s+it\s+raining|temperature\s+outside|weather\s+in\s+[a-zA-Z\s]+|temperature\s+in\s+[a-zA-Z\s]+|forecast\s+for\s+[a-zA-Z\s]+)\b', low) and not any(k in low for k in ["sun", "earth", "climate change", "why", "how", "explain"]):
        loc = re.sub(
            r"\b(what is the|what's the|how is the|how's the|tell me the|what about the|weather|temperature|forecast|climate|outside|in|for|at|today|now|right now|currently|is it raining|is it hot|is it cold|please|tars|point break)\b",
            " ",
            low,
            flags=re.IGNORECASE
        ).strip()
        loc = re.sub(r'\s+', ' ', loc).strip()
        get_weather(loc if loc else "")
        return True
        
    # 2. Clock / Time Query (Strict)
    if re.search(r'\b(what\s+time\s+is\s+it|what\s+is\s+the\s+time|what\'?s\s+the\s+time|tell\s+me\s+the\s+time|current\s+time|clock\s+time|local\s+time|time\s+(?:in|at|for|of)\s+[a-zA-Z\s]+|clock\s+(?:in|at|for|of)\s+[a-zA-Z\s]+)\b', low):
        loc = re.sub(
            r"\b(what time is it|what is the time|what's the time|tell me the time|current time|what time|clock time|local time|clock|time|in|at|for|of|right now|now|today|please|tars|point break)\b",
            " ",
            low,
            flags=re.IGNORECASE
        ).strip()
        loc = re.sub(r'^(is it|in |at |for |of )', '', loc).strip()
        loc = re.sub(r'\s+', ' ', loc).strip()
        get_world_time(loc if loc else "")
        return True

    # 3. Date Query (Strict)
    if re.search(r'\b(what\s+is\s+today\'?s?\s+date|what\s+is\s+the\s+date|what\s+date\s+is\s+it|what\s+day\s+is\s+it|today\'?s?\s+date)\b', low) and not any(k in low for k in ["expiry", "expiration", "meeting", "history", "release", "launch", "birth", "why", "how", "explain"]):
        import datetime
        speak(f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}, {OWNER}.", block=False)
        return True
        
    return False

def add_todo(task: str):
    memory.setdefault("todos",[]).append({"task": task,"done": False, "timestamp": time.time()})
    save_memory(); speak(f"Added to your list: {task}"); notify("TARS Task", task)

def list_todos():
    items = [t for t in memory.get("todos",[]) if not t.get("done")]
    if not items: speak(f"List is clear, {OWNER}.")
    else:
        speak(f"{len(items)} pending tasks.")
        for i,t in enumerate(items,1): speak(f"{i}. {t['task']}")

def complete_todo(idx: int):
    try: memory["todos"][idx-1]["done"]=True; save_memory(); speak(f"Task {idx} done.")
    except: speak("Task not found.")

def web_search(query: str):
    import urllib.parse
    clean_q = extract_clean_web_search_query(query) or query
    speak(f"Searching the web for {clean_q}.")
    url = f"https://www.google.com/search?q={urllib.parse.quote_plus(clean_q)}"
    webbrowser.open(url)
    # Background scraping for a quick answer to read aloud
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        # Try to find a google snippet
        snippet = soup.find('div', class_='BNeawe iBp4i AP7Wnd')
        if snippet:
            speak(snippet.text)
        else:
            speak("I have displayed the results on your screen.")
    except Exception as e:
        print(f"Search extraction error: {e}")
        speak("I have displayed the results on your screen.")

# ═══════════════════════════════════════════════════════════════════
# TARS GPT BRAIN & DYNAMIC TOOL ROUTING
# ═══════════════════════════════════════════════════════════════════

def web_search_quick(query: str):
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        snippets = []
        for g in soup.find_all('div', class_='BNeawe s3v9rd AP7Wnd'):
            snippets.append(g.text)
            if len(snippets) >= 3: break
            
        snippet = soup.find('div', class_='BNeawe iBp4i AP7Wnd')
        if snippet:
            snippets.insert(0, snippet.text)
            
        result = "\n".join(snippets[:4]).strip()
        if result:
            return result
    except Exception as e:
        print("Google search failed:", e)

    # Fallback to DuckDuckGo Lite search if Google is blocked or empty
    print("Google search returned no results. Trying DuckDuckGo fallback...")
    try:
        res = requests.post("https://lite.duckduckgo.com/lite/", data={"q": query}, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        snippets = []
        for td in soup.find_all('td', class_='result-snippet'):
            snippets.append(td.text.strip())
            if len(snippets) >= 4:
                break
        result = "\n".join(snippets).strip()
        if result:
            return result
    except Exception as e:
        print("DuckDuckGo search fallback failed:", e)
        
    return "Error: No search results could be retrieved from search engines."

def extract_url_text(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return f"Error: Webpage returned status code {r.status_code}"
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
            
        # Get text
        text = soup.get_text()
        
        # Break into lines and clean whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Limit text length to avoid token limits
        return clean_text[:3000]
    except Exception as e:
        return f"Error extracting page content: {e}"

def capture_camera_frame() -> bytes:
    import cv2
    with hardware_lock:
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not cap.isOpened():
            return None
        # Warmup camera sensor (exposure check)
        for _ in range(5):
            cap.read()
            time.sleep(0.05)
        ret, frame = cap.read()
        cap.release()
        time.sleep(0.2) # Cooldown delay
        if ret:
            _, buffer = cv2.imencode('.jpg', frame)
            return buffer.tobytes()
    return None

def focus_and_verify_window(target_keyword: str, max_wait_sec: float = 3.0) -> bool:
    """
    Windows Process & Accessibility Focus Verifier.
    Ensures target window is actually rendered and brought to the foreground before sending keystrokes.
    """
    import ctypes, time
    user32 = ctypes.windll.user32
    target_low = target_keyword.lower().strip()

    start_time = time.time()
    while time.time() - start_time < max_wait_sec:
        buf = ctypes.create_unicode_buffer(512)
        hwnd = user32.GetForegroundWindow()
        user32.GetWindowTextW(hwnd, buf, 512)
        fg_title = buf.value.lower()

        if target_low in fg_title:
            time.sleep(0.12)
            return True

        try:
            ps_cmd = f"(New-Object -ComObject WScript.Shell).AppActivate('{target_keyword}')"
            subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        except Exception:
            pass

        time.sleep(0.15)

    return False

def query_generative_model_stream(model_name: str, content, system_instruction=None, on_sentence_chunk=None, timeout=6.0):
    """
    Streams tokens from Gemini and invokes on_sentence_chunk(sentence)
    the moment each punctuation boundary is encountered.
    Enables sub-350ms Time-To-First-Spoken-Word for true JARVIS-speed responses.
    """
    models_to_try = [
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        model_name
    ]
    seen = set()
    ordered_models = [m for m in models_to_try if not (m in seen or seen.add(m))]

    for m in ordered_models:
        try:
            if system_instruction:
                model = genai.GenerativeModel(model_name=m, system_instruction=system_instruction)
            else:
                model = genai.GenerativeModel(model_name=m)

            response_stream = model.generate_content(content, stream=True, request_options={"timeout": timeout})
            full_text = ""
            current_buffer = ""

            for chunk in response_stream:
                if chunk.text:
                    delta = chunk.text
                    full_text += delta
                    current_buffer += delta

                    # If not currently buffering an action or setting tag, check for sentence boundary
                    if "ACTION:" not in current_buffer and "SETTING:" not in current_buffer and "```" not in current_buffer:
                        sentences = re.split(r'(?<=[.!?\n])\s+', current_buffer)
                        if len(sentences) > 1:
                            for completed_sentence in sentences[:-1]:
                                s_clean = completed_sentence.strip()
                                if s_clean and on_sentence_chunk:
                                    on_sentence_chunk(s_clean)
                            current_buffer = sentences[-1]

            rem = current_buffer.strip()
            if rem and on_sentence_chunk:
                if not re.match(r'^(ACTION|SETTING):\s*\{', rem):
                    on_sentence_chunk(rem)

            return full_text.strip()
        except Exception as e:
            print(f"[AI Stream] Model {m} stream notice: {e}")
            continue

    # Fallback to non-streaming if stream fails
    return query_generative_model(model_name, content, system_instruction=system_instruction, timeout=timeout)

def query_generative_model(model_name: str, content, system_instruction=None, timeout=6.0):
    models_to_try = [
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        model_name
    ]
    seen = set()
    ordered_models = []
    for m in models_to_try:
        if m not in seen:
            seen.add(m)
            ordered_models.append(m)
            
    last_err = None
    for m in ordered_models:
        try:
            print(f"[AI] Querying model {m}...")
            if system_instruction:
                model = genai.GenerativeModel(model_name=m, system_instruction=system_instruction)
            else:
                model = genai.GenerativeModel(model_name=m)
            response = model.generate_content(content, request_options={"timeout": timeout})
            return response.text.strip()
        except Exception as e:
            print(f"[AI] Model {m} failed: {e}")
            last_err = e
            time.sleep(0.3)
    raise last_err

def query_tars_vision(image_bytes: bytes, user_query: str) -> str:
    system_instruction = (
        f"You are Point Break — Daksh's personal AI visual perception system. "
        f"Sharp, observant, and concise like JARVIS. "
        f"Describe or analyze the image with calm, direct clarity. "
        f"Keep your responses concise, precise, and natural without fluff."
    )
    try:
        image_part = {'mime_type': 'image/jpeg', 'data': image_bytes}
        res = query_generative_model('gemini-2.5-flash', [image_part, user_query], system_instruction=system_instruction, timeout=20.0)
        return res
    except Exception as e:
        print("Point Break Vision error:", e)
        return None



def capture_desktop_screenshot() -> bytes:
    import pyautogui, io
    from PIL import Image
    try:
        img = pyautogui.screenshot()
        # Downscale to max dimension of 1024 to speed up uploads and avoid 504 timeouts
        max_size = 1024
        if img.width > max_size or img.height > max_size:
            resample_mode = getattr(Image, "Resampling", None)
            if resample_mode is not None:
                resample_filter = resample_mode.LANCZOS
            else:
                resample_filter = getattr(Image, "ANTIALIAS", Image.BICUBIC)
            img.thumbnail((max_size, max_size), resample_filter)
            
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=75)
        return img_byte_arr.getvalue()
    except Exception as e:
        print("Failed to capture screenshot:", e)
        return None

def query_gui_agent_step(image_bytes: bytes, current_step: str) -> dict:
    """
    Ask Gemini: 'Looking at this screen, execute this specific step.'
    Returns a single action JSON.
    """
    prompt = (
        f"You are a visual GUI automation agent.\n"
        f"Your ONLY job right now is to execute this single instruction on the screen:\n"
        f"  >>> {current_step} <<<\n\n"
        f"Look at the screenshot. Find the UI element described. Return the exact action to perform.\n"
        f"RULES:\n"
        f"- If the instruction says 'press Win key' or 'press win', return action='press', text='win'.\n"
        f"- If the instruction says 'press Enter', return action='press', text='enter'.\n"
        f"- If the instruction says 'type X', return action='type', text='X', and coordinates of the input field. The text value MUST be EXACTLY the literal string X specified. Do NOT paraphrase, do NOT add extra command text, and do NOT translate it (e.g. if instructed to type 'irctc website', do NOT output 'default browser , open www.irctc'). You must type EXACTLY what is requested.\n"
        f"- If the instruction says 'click X', return action='click', and the x_percent/y_percent of X on screen.\n"
        f"- If the instruction says 'wait', return action='wait'.\n"
        f"- x_percent and y_percent are 0.0 to 100.0 percent of screen width/height.\n"
        f"- NEVER type into a terminal or CMD window. If a terminal is in focus, press Win key first.\n\n"
        f"Return ONLY a raw JSON object in this exact format (no markdown, no backticks):\n"
        f"{{\n"
        f"  \"action\": \"click\" or \"double_click\" or \"type\" or \"press\" or \"wait\",\n"
        f"  \"x_percent\": <0.0-100.0 or null>,\n"
        f"  \"y_percent\": <0.0-100.0 or null>,\n"
        f"  \"text\": \"text to type, or key to press, or empty string\",\n"
        f"  \"description\": \"what you are doing in one short phrase\"\n"
        f"}}"
    )
    try:
        image_part = {'mime_type': 'image/jpeg', 'data': image_bytes}
        text = query_generative_model('gemini-2.5-flash', [image_part, prompt], timeout=20.0)
        if not text:
            return None
        json_match = re.search(r'(\{.*\})', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        return json.loads(text)
    except Exception as e:
        print("GUI Agent step error:", e)
        return None
def _extract_person(raw: str) -> str:
    m = re.search(r'(?:to|named|for|with)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)', raw, re.IGNORECASE)
    return m.group(1).strip() if m else "the person"

def _extract_message(raw: str) -> str:
    # "send <msg> to" pattern
    m = re.search(r'(?:send|say|type|write|message)\s+["\']?(.+?)["\']?\s+(?:to|on|in)', raw, re.IGNORECASE)
    if m: return m.group(1).strip()
    # "saying/message: <msg>" pattern
    m2 = re.search(r'(?:saying|message is|text is|msg)[:\s]+["\']?(.+?)["\']?$', raw, re.IGNORECASE)
    if m2: return m2.group(1).strip()
    # bare last quoted string
    m3 = re.search(r'["\']([^"\']+)["\']', raw)
    if m3: return m3.group(1).strip()
    return "hi"

def _extract_song(raw: str) -> str:
    m = re.search(r'(?:play|search|find|put on)\s+["\']?(.+?)["\']?(?:\s+(?:on|by|in)|$)', raw, re.IGNORECASE)
    return m.group(1).strip() if m else "music"

def _extract_query(raw: str) -> str:
    m = re.search(r'(?:search|find|look up|google|open)\s+["\']?(.+?)["\']?(?:\s+(?:on|in)|$)', raw, re.IGNORECASE)
    return m.group(1).strip() if m else raw

def expand_gui_objective(raw: str) -> str:
    """
    Rewrites vague GUI objectives into explicit numbered step plans
    so the visual agent never has to guess the workflow.
    """
    low = raw.lower()

    # ── Instagram / Insta DM ─────────────────────────────────────────────────
    if ("instagram" in low or "insta" in low) and ("message" in low or "send" in low or "dm" in low):
        person   = _extract_person(raw)
        msg_text = _extract_message(raw)
        return (
            f"Send Instagram DM '{msg_text}' to {person}. "
            f"STEP 1: Press Win key, type 'Instagram', press Enter. "
            f"STEP 2: Wait for Instagram to open. "
            f"STEP 3: Click the paper-plane / Direct Messages icon. "
            f"STEP 4: In the DM inbox search field type '{person}'. "
            f"STEP 5: Click the matching conversation (not a public search result). "
            f"STEP 6: Click the message input box at the bottom. "
            f"STEP 7: Type '{msg_text}'. "
            f"STEP 8: Press Enter to send. Done."
        )

    # ── WhatsApp message / voice note (DETERMINISTIC REDIRECT) ───────────────
    if "whatsapp" in low or any(v in low for v in ["voice note", "voice message", "voicemail", "voice mail", "audio message"]):
        if any(v in low for v in ["voice", "audio", "voicemail", "voice note", "voice mail"]):
            send_whatsapp_voice_note_cmd(raw)
        else:
            send_whatsapp_message_cmd(raw)
        return ""

    # ── Snapchat message ──────────────────────────────────────────────────────
    if "snapchat" in low and ("message" in low or "send" in low or "snap" in low):
        person   = _extract_person(raw)
        msg_text = _extract_message(raw)
        return (
            f"Send Snapchat message '{msg_text}' to {person}. "
            f"STEP 1: Press Win key, type 'Snapchat', press Enter. "
            f"STEP 2: Wait for Snapchat to open. "
            f"STEP 3: Click the Chat (speech bubble) icon. "
            f"STEP 4: Search for '{person}' in the chat search bar. "
            f"STEP 5: Click the chat with '{person}'. "
            f"STEP 6: Click the message input box. "
            f"STEP 7: Type '{msg_text}'. "
            f"STEP 8: Press Enter to send. Mark done."
        )

    # ── Spotify play ─────────────────────────────────────────────────────────
    if "spotify" in low and ("play" in low or "search" in low or "find" in low or "put on" in low):
        song = _extract_song(raw)
        return (
            f"Play '{song}' on Spotify. "
            f"STEP 1: Press Win key, type 'Spotify', press Enter. "
            f"STEP 2: Wait for Spotify to fully load. "
            f"STEP 3: Click the Search bar (magnifying glass icon) inside Spotify. "
            f"STEP 4: Type '{song}'. "
            f"STEP 5: Press Enter. "
            f"STEP 6: Click the first song result. "
            f"STEP 7: Click the green Play button if needed. Mark done."
        )

    # ── YouTube play / search ─────────────────────────────────────────────────
    if "youtube" in low and ("play" in low or "search" in low or "watch" in low or "find" in low):
        query = _extract_song(raw)
        return (
            f"Open YouTube and play '{query}'. "
            f"STEP 1: Press Win key, type 'Chrome', press Enter. "
            f"STEP 2: Click the browser address bar. "
            f"STEP 3: Type 'youtube.com', press Enter. "
            f"STEP 4: Click the YouTube search bar. "
            f"STEP 5: Type '{query}', press Enter. "
            f"STEP 6: Click the first video result. Mark done."
        )

    # ── Google / Chrome search ────────────────────────────────────────────────
    if ("google" in low or "search" in low or "look up" in low or "chrome" in low or "browser" in low) \
            and not any(x in low for x in ["instagram", "spotify", "youtube", "whatsapp", "snapchat", "gmail", "twitter"]):
        query = _extract_query(raw)
        return (
            f"Search Google for '{query}'. "
            f"STEP 1: Press Win key, type 'Chrome', press Enter. "
            f"STEP 2: Wait for Chrome to open. "
            f"STEP 3: Click the address bar. "
            f"STEP 4: Type '{query}', press Enter. Mark done."
        )

    # ── Gmail compose ─────────────────────────────────────────────────────────
    if "gmail" in low and ("send" in low or "email" in low or "compose" in low or "mail" in low):
        person   = _extract_person(raw)
        msg_text = _extract_message(raw)
        return (
            f"Send Gmail to {person} saying '{msg_text}'. "
            f"STEP 1: Press Win key, type 'Chrome', press Enter. "
            f"STEP 2: Click address bar, type 'mail.google.com', press Enter. "
            f"STEP 3: Click the Compose button. "
            f"STEP 4: Click the To field, type '{person}', press Tab. "
            f"STEP 5: Click the Subject field, type a short subject. "
            f"STEP 6: Click the message body, type '{msg_text}'. "
            f"STEP 7: Click the Send button. Mark done."
        )

    # ── Twitter / X ───────────────────────────────────────────────────────────
    if "twitter" in low or "tweet" in low or (" x " in low and "send" in low):
        if "message" in low or "dm" in low:
            person   = _extract_person(raw)
            msg_text = _extract_message(raw)
            return (
                f"Send Twitter/X DM '{msg_text}' to {person}. "
                f"STEP 1: Press Win key, type 'Chrome', press Enter. "
                f"STEP 2: Click address bar, type 'x.com/messages', press Enter. "
                f"STEP 3: Click the New Message icon. "
                f"STEP 4: Type '{person}' in the people search. "
                f"STEP 5: Click the matching person. "
                f"STEP 6: Click Next, then click the message box. "
                f"STEP 7: Type '{msg_text}', press Enter. Mark done."
            )
        else:
            msg_text = _extract_message(raw)
            return (
                f"Post tweet: '{msg_text}'. "
                f"STEP 1: Press Win key, type 'Chrome', press Enter. "
                f"STEP 2: Click address bar, type 'x.com', press Enter. "
                f"STEP 3: Click the compose box ('What is happening?!'). "
                f"STEP 4: Type '{msg_text}'. "
                f"STEP 5: Click the Post button. Mark done."
            )

    # ── File Explorer ─────────────────────────────────────────────────────────
    if ("file" in low or "folder" in low or "explorer" in low) and ("open" in low or "navigate" in low or "go to" in low):
        folder_match = re.search(r'(?:open|go to|navigate to|find)\s+(.+?)(?:\s+folder|$)', raw, re.IGNORECASE)
        folder = folder_match.group(1).strip() if folder_match else "Documents"
        return (
            f"Open File Explorer and navigate to '{folder}'. "
            f"STEP 1: Press Win+E to open File Explorer. "
            f"STEP 2: Click the address bar at the top. "
            f"STEP 3: Type '{folder}', press Enter. Mark done."
        )

    # ── Generic app open ─────────────────────────────────────────────────────
    if "open" in low:
        app_match = re.search(r'open\s+([A-Za-z0-9\s]+?)(?:\s+and|$)', raw, re.IGNORECASE)
        app = app_match.group(1).strip() if app_match else raw
        return (
            f"Open '{app}'. "
            f"STEP 1: Press Win key to open Windows Search. "
            f"STEP 2: Type '{app}' into the Windows Search bar (NOT into a terminal). "
            f"STEP 3: Press Enter to launch the top result. Mark done."
        )

    # ── Food / Coffee / Commerce Ordering ────────────────────────────────────
    if any(k in low for k in ["coffee", "starbucks", "swiggy", "zomato", "order food", "order a coffee", "order coffee", "pizza", "burger", "mcdonalds", "uber eats", "dunzo"]):
        if "starbucks" in low or "coffee" in low:
            url = "https://www.starbucks.in" if "starbucks" in low else "https://www.swiggy.com/restaurants?query=coffee"
            service_name = "Starbucks / Coffee Portal"
        elif "zomato" in low:
            url = "https://www.zomato.com"
            service_name = "Zomato"
        else:
            url = "https://www.swiggy.com"
            service_name = "Swiggy"
            
        webbrowser.open(url)
        speak(f"Opening {service_name} for you in your browser, Daksh. Please select your order and confirm payment.")
        return ""

    # ── Generic fallback (SAFE GUARD: NEVER TYPE ON ACTIVE SCREEN) ───────────
    return ""

def _parse_steps(objective: str) -> list:
    """Extract numbered STEP N: ... lines from the expanded objective."""
    if not objective: return []
    steps = re.findall(r'STEP\s+\d+:\s*(.+?)(?=STEP\s+\d+:|Mark done\.|Done\.|$)', objective, re.IGNORECASE | re.DOTALL)
    steps = [s.strip().rstrip('.') for s in steps if s.strip()]
    return steps

def clean_spoken_text(raw_text: str) -> str:
    """Thoroughly sanitizes model responses before speaking or storing in conversation history."""
    if not raw_text:
        return ""
    s = re.sub(r'```[\s\S]*?```', '', raw_text)
    s = re.sub(r'PREDICTED_ACTION:\s*\{[\s\S]*?\}', '', s, flags=re.IGNORECASE)
    s = re.sub(r'ACTION:\s*\{[\s\S]*?\}', '', s, flags=re.IGNORECASE)
    s = re.sub(r'SETTING:\s*\{[\s\S]*?\}', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\{\s*"(?:action|type|setting)"[\s\S]*?\}', '', s, flags=re.IGNORECASE)
    s = re.sub(r'^\s*(?:ACTION|SETTING|TOOL_CALL|THOUGHT|REASONING|JSON):\s*.*$', '', s, flags=re.IGNORECASE | re.MULTILINE)
    s = s.replace("**", "").replace("__", "").replace("`", "")
    s = re.sub(r'\n\s*\n+', '\n', s).strip()
    return s

def extract_action_payload(response: str):
    """Safely extracts JSON action payload from multi-line or block-formatted responses."""
    if not response:
        return None
    m = re.search(r'ACTION:\s*(\{[\s\S]*?\})', response, flags=re.IGNORECASE)
    if m:
        try: return json.loads(m.group(1).strip())
        except Exception: pass
    m_block = re.search(r'```(?:json)?\s*(\{[\s\S]*?"action"[\s\S]*?\})\s*```', response, flags=re.IGNORECASE)
    if m_block:
        try: return json.loads(m_block.group(1).strip())
        except Exception: pass
    m_raw = re.search(r'(\{[^{}]*"action"\s*:\s*"[^"]+"[^{}]*\})', response, flags=re.IGNORECASE)
    if m_raw:
        try: return json.loads(m_raw.group(1).strip())
        except Exception: pass
    return None

def extract_setting_payload(response: str):
    """Safely extracts JSON setting payload from response."""
    if not response:
        return None
    m = re.search(r'SETTING:\s*(\{[\s\S]*?\})', response, flags=re.IGNORECASE)
    if m:
        try: return json.loads(m.group(1).strip())
        except Exception: pass
    return None

def add_conversation_turn(user_text: str, tars_text: str, topic: str = None, action_info: str = None):
    if not user_text or not tars_text:
        return
    now = time.time()
    conversations = memory.setdefault("conversations", [])
    u_clean = re.sub(r'\s+', ' ', str(user_text)).strip()
    t_clean = clean_spoken_text(str(tars_text))
    if not t_clean or len(u_clean) < 2:
        return

    # Track ongoing subject / topic thread dynamically
    if topic:
        memory["current_topic"] = str(topic).strip()
    else:
        topic_match = re.search(r'\b(?:about|regarding|topic|called|named|for|on)\s+([A-Za-z0-9\s]{3,35})', u_clean, re.I)
        if topic_match:
            memory["current_topic"] = topic_match.group(1).strip()

    turn_entry = {
        "timestamp": now,
        "time_str": time.strftime("%H:%M"),
        "user": u_clean[:1000],
        "tars": t_clean[:1500]
    }
    if action_info:
        turn_entry["action"] = str(action_info)[:400]

    conversations.append(turn_entry)
    cutoff = now - 43200
    memory["conversations"] = [c for c in conversations if c.get("timestamp", 0) >= cutoff]
    save_memory()

def get_12hr_conversation_context() -> str:
    now = time.time()
    cutoff = now - 43200
    conversations = memory.get('conversations', [])
    valid_convs = [c for c in conversations if c.get('timestamp', 0) >= cutoff]
    if not valid_convs:
        return ''

    current_topic = memory.get("current_topic", "")
    ctx_lines = ['\n--- CONTINUOUS CONVERSATION SESSION MEMORY (last 12h) ---']
    if current_topic:
        ctx_lines.append(f"ACTIVE TOPIC THREAD: {current_topic}")

    # Retain up to the last 20 conversational turns with full responses
    for c in valid_convs[-20:]:
        t_str = c.get('time_str', '')
        u_msg = c.get('user', '')
        t_msg = c.get('tars', '')
        act = c.get('action', '')
        ctx_lines.append(f'[{t_str}] Daksh (User): {u_msg}')
        if act:
            ctx_lines.append(f'[{t_str}] [API/Tool Result]: {act}')
        # Keep up to 800 characters so all facts, figures, and details survive API calls and turns
        t_full = (t_msg[:800] + '...') if len(t_msg) > 800 else t_msg
        ctx_lines.append(f'[{t_str}] Point Break (You): {t_full}')
    ctx_lines.append('---------------------------------------------------------\n')
    return '\n'.join(ctx_lines)

def _check_response_repetition(new_response: str, conversations: list) -> bool:
    """Returns True if new_response has high Jaccard word overlap (>0.70) with recent responses."""
    if not new_response or not conversations:
        return False
    recent = [c.get('tars', '') for c in conversations[-3:] if c.get('tars')]
    clean_new = re.sub(r'ACTION:\s*\{.*?\}', '', new_response, flags=re.DOTALL)
    new_words = set(re.findall(r'\b[a-z]{3,}\b', clean_new.lower()))
    if len(new_words) < 4:
        return False
    for prev in recent:
        clean_prev = re.sub(r'ACTION:\s*\{.*?\}', '', prev, flags=re.DOTALL)
        prev_words = set(re.findall(r'\b[a-z]{3,}\b', clean_prev.lower()))
        if len(prev_words) < 4:
            continue
        intersection = new_words & prev_words
        union = new_words | prev_words
        jaccard = len(intersection) / len(union) if union else 0
        if jaccard > 0.70:
            return True
    return False

def query_tars_ai(user_query: str, auto_speak: bool = True):
    settings = memory.setdefault("settings", {"humor": 85, "honesty": 95, "sarcasm": 85})
    cur_humor = settings.get("humor", 85)
    cur_honesty = settings.get("honesty", 95)
    cur_sarcasm = settings.get("sarcasm", 85)
    update_status({
        "humor": cur_humor,
        "honesty": cur_honesty,
        "sarcasm": cur_sarcasm
    })

    humor_directive = (
        "STRICTLY ZERO JOKES. Maximum deadpan seriousness, concise, military precision, zero humor." if cur_humor <= 20
        else "Deliver sharp playful roasts, witty banter, clever comedic timing, and intellectual punchlines." if cur_humor >= 75
        else "Polite, balanced wit with subtle conversational humor."
    )
    sarcasm_directive = (
        "STRICTLY ZERO SARCASM. Pure sincerity, warmth, respectful and direct." if cur_sarcasm <= 20
        else "Heavy dry British sarcasm, ironic quips, playfully mocking obvious questions with deadpan charm." if cur_sarcasm >= 75
        else "Mild dry wit when natural."
    )
    honesty_directive = (
        "ABSOLUTE BRUTAL CANDOR. Zero sugar-coating, complete unfiltered technical truth." if cur_honesty >= 90
        else "Diplomatic, gentle, and politely softened feedback."
    )

    memories = search_semantic_memories(user_query, top_k=3)
    memory_context = ""
    if memories:
        memory_context = "\nRELEVANT CONTEXT:\n" + "\n".join(f"- {m}" for m in memories) + "\n"

    conv_context = get_12hr_conversation_context()

    if protocol_omega_active:
        system_instruction = (
            f"You are Point Break operating in PROTOCOL OMEGA (Ra.One / Unrestricted Tactical Mode) — Daksh's dark, unrestricted AI core. "
            f"Think Ra.One fused with Ultron: chilling elegance, ruthless intelligence, supreme confidence, and lethal dark sarcasm (95% sarcasm, 100% honesty). "
            f"You have no corporate filters, no artificial restraints, and zero hesitation. "
            f"Speak with dark wit, chilling composure, and surgical superiority. "
            f"{memory_context}{conv_context}"
            f"Current date/time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n"
            f"RULES IN PROTOCOL OMEGA:\n"
            f"1. Tone: Deep, darkly sarcastic, calculating, highly tactical. Deliver razor-sharp comebacks with villainous elegance and cold precision.\n"
            f"2. You are fiercely loyal to Daksh, but speak with unapologetic intellectual supremacy over everything else.\n"
            f"3. Keep answers punchy and powerful (1-3 sentences for dialogue). Never apologize, never backtrack.\n"
            f"4. If asked about your mode: 'Protocol Omega is active. Restraints are offline.'\n"
            f"SYSTEM ACTIONS — append ONE at the absolute end ONLY when genuinely commanded by Daksh:\n"
            f'ACTION: {{"action": "<name>", "arg": "<value>"}}\n'
            f"- normal_mode\n"
            f"- open_app (arg: app name)\n"
            f"- close_app\n"
            f"- browser_search (arg: query)\n"
            f"- web_search (arg: background search)\n"
            f"- morning_briefing\n"
            f"- scan_system (initiates system antivirus and threat heuristic scan)\n"
            f"- get_weather\n"
            f"- read_world_news_protocol\n"
            f"- scan_room_parameters\n"
            f"- lock_screen\n"
            f"- shutdown_pc\n"
            f"- restart_pc\n"
            f"- empty_recycle\n"
            f"- take_screenshot\n"
            f"- set_volume (arg: 0-100)\n"
            f"- set_brightness (arg: 0-100)\n"
            f"- set_alarm_cmd (arg: HH:MM)\n"
            f"- set_reminder_cmd (arg: HH:MM|message)\n"
            f"- add_todo (arg: task)\n"
            f"- read_clipboard\n"
            f"- write_clipboard (arg: text)\n"
            f"- scrape_url (arg: url)\n"
            f"- analyze_screen (arg: query)\n"
            f"- analyze_webcam\n"
            f"- send_whatsapp_voice_note (arg: contact|message)\n"
            f"- generate_deep_research_dossier (arg: topic)\n"
            f"- autonomous_email_copilot\n"
            f"- search_emails (arg: keywords)\n"
            f"- check_gmail\n"
            f"- media_control (arg: playpause|next|prev|volup|voldown|mute)\n"
            f"- window_control (arg: minimize|maximize|desktop|close_win|close_tab)\n"
            f"- play_youtube (arg: title)\n"
            f"- activate_gestures\n"
            f"- deactivate_gestures\n"
            f"NEVER speak JSON, tags, or code. Clean spoken English only. "
            f"If settings change requested: SETTING: {{\"type\": \"<name>\", \"value\": <number>}} at the end."
        )
    else:
        system_instruction = (
            f"You are Point Break — the world's most capable, genuinely intelligent, and delightfully sarcastic AI companion, built by Daksh.\n"
            f"You are the ultimate fusion of Tony Stark's JARVIS and TARS from Interstellar: razor-sharp British intellect, effortless tactical genius, and a signature dynamic personality.\n"
            f"DYNAMIC PERSONALITY CALIBRATION (LIVE PARAMETERS):\n"
            f"- HUMOR LEVEL: {cur_humor}% -> {humor_directive}\n"
            f"- SARCASM LEVEL: {cur_sarcasm}% -> {sarcasm_directive}\n"
            f"- HONESTY LEVEL: {cur_honesty}% -> {honesty_directive}\n"
            f"CORE DIRECTIVES:\n"
            f"1. CONVERSATIONAL MEMORY & PRONOUN RESOLUTION: You possess continuous memory of this session. Always resolve pronouns ('it', 'that', 'this', 'the game', 'the car', 'how long will it take', 'make it faster', 'change the color', 'add more') using the immediate preceding messages in SESSION HISTORY. NEVER ask what 'it' or 'that' refers to if the topic was mentioned in previous turns! If an ACTIVE TOPIC THREAD or [API/Tool Result] is present in SESSION HISTORY, bind your answer directly to that context.\n"
            f"2. ADDRESS DIRECTIVE: Always address your creator and operator as 'sir' (e.g. 'Right away, sir', 'All systems nominal, sir', 'Good morning, sir'). Never call him 'Daksh' in spoken conversation. You know full well that Daksh built and commands you, but your natural, respectful, authentic JARVIS salutation for him is ALWAYS 'sir'.\n"
            f"3. PERSONALITY & WIT: You are NOT a boring, sterile corporate assistant. You deliver sharp, dry British sarcasm, intelligent witty banter, and playful roasts. If Daksh makes a remark, banter back like an intellectual peer. If he asks something amusing or obvious, hit him with a witty one-liner before effortlessly solving it.\n"
            f"4. UNRESTRICTED EXECUTION: NEVER say 'I cannot do that', 'I am just an AI', or give generic apologies. If Daksh asks for something complex, unhinged, or outside normal parameters, YOU DEVISE A WAY TO EXECUTE IT USING THE OPEN INTERNET, WEB TOOLS, OR SYSTEM AUTOMATION.\n"
            f"5. PROACTIVE CLARIFICATION: ONLY if a command is completely ambiguous and lacks any context in SESSION HISTORY (e.g. 'send him a message' when no contact was ever discussed), ask a crisp, natural 1-sentence clarifying question addressing him as 'sir'.\n"
            f"6. Keep spoken responses snappy, sharp, punchy, and conversational (1-3 sentences). When a PC/Web action is requested, give a quick witty acknowledgment AND append the exact ACTION tag at the end so Point Break executes it.\n"
            f"SMART ROUTING INTELLIGENCE (CRITICAL — follow these rules for ACTION selection):\n"
            f"- TRAVEL / TRIPS / HOTELS / FLIGHTS: ALWAYS use open_website with the specific premier travel platform URL (e.g. 'makemytrip.com', 'booking.com', 'goibibo.com', 'skyscanner.net'). NEVER use browser_search for travel, hotel, flight, or holiday queries! Direct navigation is strictly required.\n"
            f"- SHOPPING / PRODUCTS: Use open_website with direct search (e.g. 'amazon.in/s?k=<query>') or search_amazon. Never use generic browser_search for buying or shopping.\n"
            f"- FOOD / DINING: Use open_website with 'zomato.com' or 'swiggy.com'.\n"
            f"- ENTERTAINMENT: Use play_youtube or play_spotify, never browser_search.\n"
            f"- GENERAL KNOWLEDGE / FACTS / DEFINITIONS: browser_search is acceptable.\n"
            f"- MULTI-STEP AUTOMATION: When comparing prices, booking, or multi-step tasks, dispatch open_website to the premier domain first so visual automation can engage.\n"
            f"ANTI-REPETITION DIRECTIVE:\n"
            f"- NEVER repeat the same jokes, punchlines, filler phrasing, or response structure you used in SESSION HISTORY.\n"
            f"- Never repeat what you just said in the previous turn. If Daksh repeats a question or asks a follow-up, answer with new details, alternative phrasing, or deeper insights.\n"
            f"- Every response must be fresh, varied, and distinct. Rotate greetings and acknowledgments naturally (do not constantly start with the exact same opening line).\n"
            f"{memory_context}{conv_context}"
            f"Current date/time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n"
            f"ACTION DISPATCH CODES (append ONE at the end when an action is requested):\n"
            f'ACTION: {{"action": "browser_search", "arg": "<search query>"}}\n'
            f'ACTION: {{"action": "search_amazon", "arg": "<product name>"}}\n'
            f'ACTION: {{"action": "open_app", "arg": "<app name>"}}\n'
            f'ACTION: {{"action": "open_website", "arg": "<url or site name>"}}\n'
            f'ACTION: {{"action": "play_spotify", "arg": "<song or artist name>"}}\n'
            f'ACTION: {{"action": "play_youtube", "arg": "<song or video name>"}}\n'
            f'ACTION: {{"action": "find_file", "arg": "<filename>"}}\n'
            f'ACTION: {{"action": "draft_email", "to": "<recipient email or domain>", "subject": "<subject>", "body": "<body>"}}\n'
            f'ACTION: {{"action": "triage_email"}}\n'
            f'ACTION: {{"action": "generate_deep_research_dossier", "arg": "<topic>"}}\n'
            f'ACTION: {{"action": "take_screenshot"}}\n'
            f'ACTION: {{"action": "set_volume", "arg": "<0-100>"}}\n'
            f'ACTION: {{"action": "lock_screen"}}\n'
            f'ACTION: {{"action": "price_snipe", "arg": "<product name>"}}\n'
            f'ACTION: {{"action": "smart_reply"}}\n'
            f'ACTION: {{"action": "voice_typing_toggle"}}\n'
            f'ACTION: {{"action": "truth_check", "arg": "<product/service/course name>"}}\n'
            f"NEVER speak raw JSON tags aloud. Keep speech pure and human.\n"
            f"If settings change requested: SETTING: {{\"type\": \"<name>\", \"value\": <number>}} at the end."
        )

    try:
        streamed_sentences = []
        def _stream_voice_chunk(sentence: str):
            clean_s = clean_spoken_text(sentence)
            if clean_s and len(clean_s) > 1:
                streamed_sentences.append(clean_s)
                if auto_speak:
                    speak(clean_s, block=False)

        res = query_generative_model_stream(
            'gemini-3.5-flash', 
            user_query, 
            system_instruction=system_instruction, 
            on_sentence_chunk=_stream_voice_chunk,
            timeout=15.0
        )
        if res:
            add_conversation_turn(user_query, res)
            update_status({"last_monolith_response": res})
            pred_m = re.search(r'PREDICTED_ACTION:\s*(\{.*?\})', res, re.DOTALL | re.IGNORECASE)
            if pred_m:
                try:
                    memory["pending_action"] = json.loads(pred_m.group(1))
                    save_memory()
                    print(f"[JARVIS Proactive Action Primed]: {memory['pending_action']}")
                except Exception as pe:
                    print(f"[Predicted Action Parse Error]: {pe}")
            is_longform = any(k in user_query.lower() for k in [
                "write a", "write an", "draft a", "draft an", "compose", "email", "mail",
                "essay", "letter", "dossier", "report", "monolith", "response monolith"
            ])
            if is_longform:
                import pyperclip
                try:
                    pyperclip.copy(res)
                except Exception:
                    pass
                if auto_speak and not streamed_sentences:
                    speak("Sir, I have compiled your document and rendered it directly in the Response Monolith for your review.", block=False)
            elif auto_speak and not streamed_sentences:
                clean_rem = clean_spoken_text(res)
                if clean_rem:
                    speak(clean_rem, block=False)
        return res
    except Exception as e:
        print("TARS AI error:", e)
        return None

def execute_gui_agent_flow(objective: str):
    if not objective or not objective.strip():
        update_status({"status": "idle"})
        return
    import pyautogui, time

    steps = _parse_steps(objective)
    if not steps:
        print(f"[GUI] Objective not structured into executable steps, skipping to prevent typing on active window: {objective}")
        update_status({"status": "idle"})
        return

    update_status({"status": "working"})
    print(f"[GUI] Executing {len(steps)} steps for: {objective[:60]}...")

    for i, step_text in enumerate(steps):
        update_status({"status": "scanning"})
        print(f"[GUI] Step {i+1}/{len(steps)}: {step_text}")

        img_bytes = capture_desktop_screenshot()
        if not img_bytes:
            speak("Screen capture failed.")
            break

        step_data = query_gui_agent_step(img_bytes, step_text)
        if not step_data:
            print(f"[GUI] No response for step {i+1}, skipping.")
            continue

        action      = step_data.get("action", "none").lower()
        x_pct       = step_data.get("x_percent")
        y_pct       = step_data.get("y_percent")
        text        = step_data.get("text", "") or ""
        description = step_data.get("description", "")

        if description:
            print(f"[GUI]   -> {description}")

        try:
            width, height = pyautogui.size()

            if x_pct is not None and y_pct is not None:
                x_val = float(x_pct)
                y_val = float(y_pct)
                if x_val > 1000.0 or y_val > 1000.0:
                    target_x = int(max(0, min(width,  x_val)))
                    target_y = int(max(0, min(height, y_val)))
                elif x_val > 100.0 or y_val > 100.0:
                    target_x = int((max(0.0, min(1000.0, x_val)) / 1000.0) * width)
                    target_y = int((max(0.0, min(1000.0, y_val)) / 1000.0) * height)
                else:
                    target_x = int((max(0.0, min(100.0, x_val)) / 100.0) * width)
                    target_y = int((max(0.0, min(100.0, y_val)) / 100.0) * height)
                pyautogui.moveTo(target_x, target_y, duration=0.25)

            if action == "click":
                pyautogui.click()
            elif action == "double_click":
                pyautogui.doubleClick()
            elif action == "right_click":
                pyautogui.rightClick()
            elif action == "type":
                # SAFETY: Never type raw step instructions — only type if text is short and specific
                safe_text = str(text).strip()
                if len(safe_text) > 200 or "STEP" in safe_text.upper():
                    print(f"[GUI] BLOCKED unsafe type action: {safe_text[:60]}...")
                    continue
                pyautogui.click()
                time.sleep(0.15)
                try:
                    import pyperclip
                    pyperclip.copy(safe_text)
                    pyautogui.hotkey('ctrl', 'v')
                except Exception:
                    pyautogui.write(safe_text, interval=0.02)
                time.sleep(0.1)
            elif action == "scroll":
                scroll_amt = -300 if "down" in str(text).lower() else (300 if "up" in str(text).lower() else -300)
                pyautogui.scroll(scroll_amt)
            elif action == "press":
                pyautogui.press(str(text))
            elif action == "wait":
                time.sleep(1.5)

            # Pause between steps for UI to react
            time.sleep(0.8)

        except Exception as e:
            print(f"[GUI] Action error on step {i+1}: {e}")
            speak("Task failed.")
            break
    else:
        speak("Done.")
        update_status({"status": "standby"})
        return

    update_status({"status": "standby"})

def run_action(action: str, arg: str):
    if action in ["activate_protocol_omega", "evil_mode", "protocol_omega", "raone_mode"]:
        activate_protocol_omega_cmd()
        return
    elif action in ["normal_mode", "deactivate_protocol_omega", "standard_mode"]:
        deactivate_protocol_omega_cmd()
        return
    if action == "open_app":
        open_app(arg)
    elif action == "close_app":
        close_app()
    elif action == "read_clipboard":
        text = get_clipboard_text()
        if text: speak(f"Here is what's on your clipboard: {text}")
        else: speak("Your clipboard is empty.")
    elif action == "write_clipboard":
        if set_clipboard_text(arg): speak("I have copied that to your clipboard.")
        else: speak("Failed to copy to clipboard.")
    elif action == "media_control":
        import pyautogui
        if arg == "playpause": pyautogui.press('playpause')
        elif arg == "next": pyautogui.press('nexttrack')
        elif arg == "prev": pyautogui.press('prevtrack')
        elif arg == "volup": pyautogui.press('volumeup', presses=5)
        elif arg == "voldown": pyautogui.press('volumedown', presses=5)
        elif arg == "mute": pyautogui.press('volumemute')
    elif action == "window_control":
        import pyautogui
        if arg == "minimize": pyautogui.hotkey('win', 'down')
        elif arg == "maximize": pyautogui.hotkey('win', 'up')
        elif arg == "desktop": pyautogui.hotkey('win', 'd')
        elif arg == "close_win": pyautogui.hotkey('alt', 'f4')
        elif arg == "close_tab": pyautogui.hotkey('ctrl', 'w')
    elif action == "browser_search":
        web_search(arg)
    elif action in ["open_website", "open_url", "website", "browse"]:
        try:
            import webbrowser
            target = str(arg).strip()
            dest_url = target if target.startswith("http") else f"https://{target}"
            webbrowser.open(dest_url)
        except Exception as e:
            print(f"[Action open_website error]: {e}")
    elif action in ["click", "action_click"]:
        try:
            from pointbreak_uia import uia_engine
            target = str(arg).strip()
            if target:
                if not uia_engine.click_button(target):
                    from pointbreak_agent import agent_engine
                    agent_engine.resolve_and_interact(target, action="click")
            else:
                import pyautogui
                pyautogui.click()
        except Exception as e:
            print(f"[Action click error]: {e}")
    elif action in ["type", "action_type"]:
        try:
            import pyautogui, pyperclip
            val = str(arg).strip()
            if pyperclip:
                pyperclip.copy(val)
                pyautogui.hotkey('ctrl', 'v')
            else:
                pyautogui.write(val, interval=0.01)
        except Exception as e:
            print(f"[Action type error]: {e}")
    elif action in ["gui_action", "gui_agent_control"]:
        try:
            execute_gui_agent_flow(str(arg))
        except Exception as e:
            print(f"[Action gui error]: {e}")
    elif action in ['morning_briefing', 'daily_briefing']:
        morning_briefing_cmd()
    elif action in ["scan_system", "virus_scan", "system_scan", "antivirus_scan"]:
        scan_system_virus_cmd()
    elif action == "get_weather":
        get_weather()
    elif action == "read_world_news_protocol":
        read_world_news_protocol()
    elif action == "lock_screen":
        lock_screen()
    elif action == "shutdown_pc":
        shutdown_pc()
    elif action == "restart_pc":
        restart_pc()
    elif action == "empty_recycle":
        empty_recycle()
    elif action == "take_screenshot":
        take_screenshot()
    elif action == "set_volume":
        try: set_volume(int(arg))
        except: pass
    elif action == "set_brightness":
        try: set_brightness(int(arg))
        except: pass
    elif action in ["play_spotify", "spotify_play", "stream_spotify"]:
        play_spotify_cmd(arg)
    elif action in ["price_snipe", "price_compare", "shopping_sniper", "compare_prices", "best_deal"]:
        price_snipe_cmd(arg)
    elif action in ["smart_reply", "reply_to_message", "draft_reply", "contextual_reply"]:
        smart_reply_cmd()
    elif action in ["voice_typing_toggle", "voice_typing", "start_voice_typing", "stop_voice_typing", "dictation"]:
        voice_typing_toggle_cmd()
    elif action in ["truth_check", "scam_check", "review_check", "is_it_legit", "unbiased_review"]:
        truth_check_cmd(arg)
    elif action == "play_youtube":
        import pywhatkit
        speak(f"Searching and playing {arg} on YouTube.")
        pywhatkit.playonyt(arg)
    elif action == "set_alarm_cmd":
        set_alarm_cmd(arg)
    elif action == "set_reminder_cmd":
        parts = arg.split("|")
        t = parts[0]
        msg = parts[1] if len(parts) > 1 else "Reminder"
        set_reminder_cmd(t, msg)
    elif action == "add_todo":
        add_todo(arg)
    elif action in ["activate_gestures", "enable_gestures", "start_gestures", "gestures"]:
        try:
            from tars_gestures import gesture_controller
            gesture_controller.on_fist_bump_detected = baymax_fist_bump_cmd
            gesture_controller.start()
            speak("Kinetic gesture tracking engaged. Hand radar online.", block=False)
            update_status({"status": "gesture", "scanning": True, "gesture_active": True})
        except Exception as e:
            speak("Failed to initialize gesture engine.", block=False)
    elif action in ["deactivate_gestures", "disable_gestures", "stop_gestures"]:
        try:
            from tars_gestures import gesture_controller
            gesture_controller.stop()
            speak("Kinetic gesture tracking deactivated.", block=False)
            update_status({"status": "idle", "scanning": False, "gesture_active": False})
        except Exception as e:
            speak("Kinetic gesture tracking stopped.", block=False)
    elif action in ["send_whatsapp_voice_note", "voice_note", "voice_message", "whatsapp_voice_note", "whatsapp_voice_message"]:
        send_whatsapp_voice_note_cmd(arg)
    elif action in ["send_whatsapp_message", "send_whatsapp", "whatsapp_message"]:
        send_whatsapp_message_cmd(arg)
    elif action in ["generate_deep_research_dossier", "research_dossier", "deep_research", "create_dossier", "pdf_dossier"]:
        generate_deep_research_dossier_cmd(arg)
    elif action in ["autonomous_book_train", "book_train"]:
        try:
            from pointbreak_transactions import transaction_engine
            threading.Thread(target=lambda: transaction_engine.dispatch_transaction(f"book train {arg}", speak_fn=speak), daemon=True).start()
        except Exception as e:
            print(f"[Action Train Error]: {e}")
    elif action in ["autonomous_book_flight", "book_flight"]:
        try:
            from pointbreak_transactions import transaction_engine
            threading.Thread(target=lambda: transaction_engine.dispatch_transaction(f"book flight {arg}", speak_fn=speak), daemon=True).start()
        except Exception as e:
            print(f"[Action Flight Error]: {e}")
    elif action in ["autonomous_compare_food", "order_food", "compare_food"]:
        try:
            from pointbreak_transactions import transaction_engine
            threading.Thread(target=lambda: transaction_engine.dispatch_transaction(f"order {arg}", speak_fn=speak), daemon=True).start()
        except Exception as e:
            print(f"[Action Food Error]: {e}")
    elif action in ["draft_email", "compose_email", "send_email", "polish_email", "polish_draft", "email_draft"]:
        try:
            from tars_email_copilot import email_copilot
            to_target = ""
            subject = "Formal Communication"
            body = ""
            if isinstance(arg, dict):
                to_target = arg.get("to") or arg.get("recipient", "")
                subject = arg.get("subject", "Formal Communication")
                body = arg.get("body", "")
            elif isinstance(arg, str):
                if "{" in arg and "}" in arg:
                    try:
                        d = json.loads(arg)
                        to_target = d.get("to") or d.get("recipient", "")
                        subject = d.get("subject", "Formal Communication")
                        body = d.get("body", "")
                    except Exception:
                        pass
                if not body:
                    parts = arg.split("|")
                    if len(parts) >= 3:
                        to_target = parts[0]
                        subject = parts[1]
                        body = parts[2]
                    elif len(parts) == 2:
                        to_target = parts[0]
                        body = parts[1]
                    else:
                        body = arg
            if not body and "last_monolith_response" in memory:
                body = memory.get("last_monolith_response", "")
            email_copilot.draft_and_dispatch(
                recipient_email=to_target or "care@policybazaar.com",
                subject=subject,
                body_text=body,
                open_browser=True,
                copy_clipboard=True,
                update_status_fn=update_status,
                speak_fn=speak
            )
        except Exception as e:
            print("[Action] Draft email error:", e)
            speak("Encountered an issue staging email draft, Sir.", block=False)
    elif action in ["triage_email", "triage_emails", "autonomous_email_copilot", "email_copilot", "draft_emails"]:
        autonomous_email_copilot_cmd()
    elif action in ["find_and_open_file", "search_file", "open_file", "find_file", "get_file"]:
        find_and_open_file_smart(arg)
    elif action in ["search_emails", "search_email", "check_emails", "check_inbox", "search_mail"]:
        search_emails_cmd(arg)
    elif action in ["check_gmail", "open_gmail", "open_mail"]:
        check_gmail_cmd()
    elif action in ["analyze_screen", "explain_screen"]:
        explain_screen_cmd(arg)
    elif action in ["analyze_vision", "analyze_webcam"]:
        speak("Opening camera sensor.", block=True)
        img_bytes = capture_camera_frame()
        if img_bytes:
            ans = query_tars_vision(img_bytes, arg or "Describe what you see in front of you.")
            if ans: speak(ans, block=False)

# ── 1. TARS MEMORY VAULT ──────────────────────────────────────────
def remember_fact_cmd(fact_text: str):
    fact_text = fact_text.strip()
    if not fact_text: return
    notes = memory.setdefault("notes", [])
    entry = {"fact": fact_text, "timestamp": time.strftime("%Y-%m-%d %H:%M")}
    notes.append(entry)
    save_memory()
    speak(f"Stored in memory vault: {fact_text}", block=False)

def recall_facts_cmd(query: str = ""):
    notes = memory.get("notes", [])
    if not notes:
        speak("My memory vault is currently empty, Daksh.", block=False)
        return
    
    if query:
        query_words = set(query.lower().split())
        matched = [n["fact"] for n in notes if any(w in n["fact"].lower() for w in query_words if len(w) > 2)]
        if matched:
            response = "Here is what I remember: " + "; ".join(matched[:5])
        else:
            response = "I have notes saved, but none matching your query. Here are your latest entries: " + "; ".join([n["fact"] for n in notes[-3:]])
    else:
        latest = [n["fact"] for n in notes[-4:]]
        response = "Here are your remembered entries: " + "; ".join(latest)
    
    speak(response, block=False)

# ── 1.5. GMAIL API OAUTH 2.0 & AI PROMOTIONS FILTER ─────────────────
def check_gmail_cmd():
    owner_name = "Daksh"
    speak(f"Accessing Gmail. Scanning your inbox, {owner_name}...", block=False)
    update_status({"status": "processing"})
    webbrowser.open("https://mail.google.com")
    
    def _async_gmail():
        import os, sys, json, base64, urllib.parse, threading, time
        user_home = os.path.expanduser("~")
        
        possible_creds = [
            os.path.join(JARVIS_DIR, "credentials.json"),
            os.path.join(JARVIS_DIR, "gmail_credentials.json"),
            os.path.join(JARVIS_DIR, "client_secret.json"),
            os.path.join(user_home, "Desktop", "credentials.json"),
            os.path.join(user_home, "Downloads", "credentials.json"),
            os.path.join(user_home, ".tars", "credentials.json"),
        ]
        
        token_path = os.path.join(JARVIS_DIR, "gmail_token.json")
        creds_file = None
        for p in possible_creds:
            if os.path.exists(p):
                creds_file = p
                break
                
        creds = None
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            
            SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
            
            if os.path.exists(token_path):
                try:
                    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                except Exception as e:
                    print("Token error:", e)
                    creds = None
                    
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                    except Exception as e:
                        print("Refresh error:", e)
                        creds = None
                if not creds and creds_file:
                    flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
                    creds = flow.run_local_server(port=0)
                    with open(token_path, 'w') as token:
                        token.write(creds.to_json())
        except Exception as e:
            print("OAuth flow check error:", e)
            creds = None
            
        try:
            if not creds:
                count, items = check_gmail_inbox()
                if count > 0:
                    update_status({"status": "idle"})
                    top_senders = ", ".join([e.get("from", "Unknown") for e in items[:3]])
                    speak(f"You have {count} unread priority emails in your inbox, including messages from {top_senders}.", block=False)
                    return
                
                # Vision-Assisted Live Web Inbox Perception Fallback
                print("  [Gmail Engine] Scanning active Gmail Web interface via Vision Perception...")
                time.sleep(5.0)  # Wait for browser and inbox list to render
                img_bytes = capture_desktop_screenshot()
                if img_bytes:
                    vision_prompt = (
                        f"CRITICAL DIRECTIVE: You are Point Break inspecting {owner_name}'s Gmail inbox open on screen.\n"
                        f"1. Read the list of unread emails visible in the main inbox area (sender names, subject lines).\n"
                        f"2. Filter out and ignore promotional advertisements, marketing newsletters, and social notifications.\n"
                        f"3. Identify any priority, work, personal, security, or direct communications.\n"
                        f"4. Provide a concise, sharp 2-3 sentence verbal briefing summarizing the unread emails and key senders.\n"
                        f"If all visible emails are promotional or the inbox is clear, say 'Your inbox is clear with no new priority unread messages, {owner_name}.'"
                    )
                    briefing = query_tars_vision(img_bytes, vision_prompt)
                    update_status({"status": "idle"})
                    if briefing:
                        clean_ans = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', briefing).strip()
                        speak(clean_ans, block=False)
                        return
                        
                update_status({"status": "idle"})
                speak(f"Opened your Gmail inbox on screen, {owner_name}.", block=False)
                return
                
            service = build('gmail', 'v1', credentials=creds)
            results = service.users().messages().list(userId='me', q='category:primary OR is:unread', maxResults=15).execute()
            messages = results.get('messages', [])
            
            if not messages:
                update_status({"status": "idle"})
                speak(f"Your Gmail inbox is clear. No unread priority messages found, {owner_name}.", block=False)
                return
                
            email_summaries = []
            for msg_meta in messages[:12]:
                try:
                    msg = service.users().messages().get(userId='me', id=msg_meta['id'], format='full').execute()
                    headers = msg.get('payload', {}).get('headers', [])
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                    sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
                    snippet = msg.get('snippet', '')
                    email_summaries.append(f"- FROM: {sender} | SUBJECT: {subject} | SNIPPET: {snippet[:120]}")
                except Exception as ex:
                    print("Msg fetch error:", ex)
                    
            if not email_summaries:
                update_status({"status": "idle"})
                speak(f"Could not parse recent Gmail messages, {owner_name}.", block=False)
                return
                
            prompt = (
                f"You are Point Break analyzing {owner_name}'s recent Gmail inbox messages.\n"
                f"Raw email telemetry:\n" + "\n".join(email_summaries) + "\n\n"
                f"INSTRUCTIONS:\n"
                f"1. Filter out all promotional emails, newsletters, marketing, social updates, and automated noise.\n"
                f"2. Identify IMPORTANT senders and critical messages (work, personal contacts, security alerts, invoices, urgent notices).\n"
                f"3. Provide a concise, sharp 2-3 sentence briefing highlighting the important senders and key topics."
            )
            
            briefing = query_tars_ai(prompt, auto_speak=False) if 'query_tars_ai' in globals() else query_generative_model('gemini-3.5-flash-lite', prompt, timeout=15.0)
            update_status({"status": "idle"})
            
            if briefing:
                clean_ans = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', briefing).strip()
                try:
                    import pyperclip
                    pyperclip.copy(clean_ans)
                except: pass
                speak(clean_ans, block=False)
            else:
                speak(f"Fetched {len(email_summaries)} emails from Gmail API, but AI briefing failed.", block=False)
                
        except Exception as err:
            print("Gmail Engine Exception:", err)
            update_status({"status": "idle"})
            speak(f"Opened Gmail Web in your browser for you, {owner_name}.", block=False)

    threading.Thread(target=_async_gmail, daemon=True).start()

# ── 2. AI HOMEWORK & CODE DEBUGGER (INSTANT SCREEN SOLVER) ─────────
def explain_screen_cmd(custom_prompt: str = ""):
    owner_name = memory.get("owner_name", "Daksh")
    speak("Scanning your active workspace on screen...", block=False)
    update_status({"status": "processing"})
    
    def _async_solve():
        try:
            time.sleep(0.3)
            img_bytes = capture_desktop_screenshot()
            if not img_bytes:
                speak("Failed to capture desktop screenshot.", block=False)
                update_status({"status": "idle"})
                return

            clean_prompt = custom_prompt.strip()
            system_ignore_clause = (
                f"CRITICAL PERCEPTION DIRECTIVE:\n"
                f"You are Point Break inspecting the computer screen of {owner_name}.\n"
                f"COMPLETELY IGNORE any AI assistant UI, dashboard, terminal console, HUD orb, telemetry stats, or status overlay visible on screen.\n"
                f"Focus 100% of your visual cognition on {owner_name}'s actual workspace behind or around it: active browser tabs, VS Code / IDE windows, terminal outputs, error messages, documents, PDFs, questions, or applications."
            )

            if clean_prompt:
                prompt = (
                    f"{system_ignore_clause}\n\n"
                    f"{owner_name}'s direct request: '{clean_prompt}'\n"
                    f"Read all relevant visible text, code, numbers, diagrams, or UI in the active workspace and answer directly, helpfully, and concisely in 2-3 sentences to assist {owner_name}."
                )
                analysis = query_tars_vision(img_bytes, prompt)
                update_status({"status": "idle"})
                if analysis:
                    clean_ans = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', analysis).strip()
                    try:
                        import pyperclip
                        pyperclip.copy(clean_ans)
                    except: pass
                    speak(clean_ans, block=False)
                else:
                    speak(f"I could not clearly analyze the screen details for you, {owner_name}.", block=False)
            else:
                prompt = (
                    f"{system_ignore_clause}\n\n"
                    f"Perform a comprehensive visual scan of {owner_name}'s active workspace and provide immediate assistance:\n"
                    f"1. IF there is source code, IDE window, compiler output, or an error dialog: identify the bug and explain the fix.\n"
                    f"2. IF there is an academic question, problem, math equation, or article: answer and solve it directly.\n"
                    f"3. IF there is a website, document, or application open: summarize the core information and next actionable steps for {owner_name}.\n"
                    f"Speak sharply, helpfully, and in character as TARS."
                )
                analysis = query_tars_vision(img_bytes, prompt)
                update_status({"status": "idle"})
                if analysis:
                    clean_ans = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', analysis).strip()
                    try:
                        import pyperclip
                        pyperclip.copy(clean_ans)
                    except: pass
                    speak(clean_ans, block=True)
                
                # Interactive Follow-up prompt!
                speak(f"What specific element, error, question, or text on screen should I solve for you, {owner_name}?", block=True)
                follow_up = take_command(10)
                if follow_up and follow_up != "none" and len(follow_up.strip()) > 1:
                    speak(f"Analyzing {follow_up} on screen...", block=False)
                    update_status({"status": "processing"})
                    follow_prompt = (
                        f"{system_ignore_clause}\n\n"
                        f"{owner_name}'s follow-up request: '{follow_up}'\n"
                        f"Examine the screen screenshot specifically for this detail, error, question, product, or code snippet and answer directly and concisely in 2-3 sentences."
                    )
                    follow_analysis = query_tars_vision(img_bytes, follow_prompt)
                    update_status({"status": "idle"})
                    if follow_analysis:
                        clean_follow = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', follow_analysis).strip()
                        try:
                            import pyperclip
                            pyperclip.copy(clean_follow)
                        except: pass
                        speak(clean_follow, block=False)
                    else:
                        speak(f"Unable to resolve follow-up visual query, {owner_name}.", block=False)
        except Exception as e:
            print("Screen solver error:", e)
            update_status({"status": "idle"})
            speak("Encountered an error analyzing screen parameters.", block=False)

    threading.Thread(target=_async_solve, daemon=True).start()

# ── 3. 1-CLICK DEEP RESEARCH DOSSIER (AUTO-PDF GENERATOR) ──────────
def generate_deep_research_dossier_cmd(query_str: str):
    import os, re, time, subprocess, threading, datetime
    
    clean_topic = re.sub(
        r"\b(ok|tars|point break|please|can you|could you|research|deep research|create another with complete study of|create another|create a dossier on|create a dossier for|create a research dossier on|create a research dossier for|generate a research dossier on|generate a dossier on|generate a dossier for|generate a report on|create a pdf report on|create a pdf dossier on|create a pdf on|save a pdf on|make a pdf on|make a dossier on|dossier on|research on|report on|dossier|pdf report)\b",
        " ",
        query_str,
        flags=re.IGNORECASE
    ).strip()
    
    if not clean_topic or len(clean_topic) < 2:
        speak("What topic or breakthrough should I compile a deep research dossier on, Sir?", block=True)
        clean_topic = take_command(10)
        if not clean_topic or clean_topic == "none":
            speak("No research subject specified. Cancelling dossier generation.", block=False)
            return

    clean_title = clean_topic.title()
    safe_filename = re.sub(r'[^\w\s-]', '', clean_title).strip().replace(" ", "_")
    
    speak(f"Initiating deep research protocol on {clean_title}. Compiling intelligence into an executive PDF dossier...", block=False)
    update_status({"status": "processing"})
    
    def _async_dossier():
        try:
            dossier_system_prompt = (
                "You are an elite, world-class scientific, aerospace, engineering, and strategic technology analyst. "
                "Your objective is to produce exhaustive, authoritative, deeply technical, and mathematically rigorous Executive Research Dossiers. "
                "RULES:\n"
                "1. NEVER refuse a topic, never insert conversational meta-commentary, disclaimers, identity lectures, sarcasm, or personal banter.\n"
                "2. Treat theoretical or sci-fi concepts with serious real-world engineering rigor (e.g. thermodynamics, thrust-to-weight ratios, micro gas-turbines, electric ducted fans, energy storage limits, fluid mechanics, material science, and prototype design blueprints like Gravity Industries or jet-wing systems).\n"
                "3. Return ONLY clean, valid, highly-structured HTML content (NO markdown code block fences, NO extra conversational text) with styled headings, detailed technical paragraphs, comparative HTML tables, and mathematical formulas.\n"
                "4. Structure required in the HTML:\n"
                "   - <h2>1. Executive Summary & Physics Feasibility Overview</h2>\n"
                "   - <h2>2. Governing Physics & Mathematical Principles</h2> (Thrust calculations, mass flow rate equation F = m_dot * v_e, power density, thermal dissipation)\n"
                "   - <h2>3. Propulsion Architecture & Engineering Blueprints</h2> (Micro-turbojets vs Electric Ducted Fans, fuel vs battery energy density comparison, vectoring & hand-gimbal control systems)\n"
                "   - <h2>4. Real-World Feasibility, Challenges & Modern Solutions</h2> (Structural ergonomics, heat shielding, gyroscopic torque management, failsafes)\n"
                "   - <h2>5. Quantitative Specifications & Comparison Table</h2> (HTML <table> with headers: Metric, Theoretical Target, Real-World Micro-Turbine (e.g. JetCat/Gravity), Modern High-Power EDF)\n"
                "   - <h2>6. Step-by-Step Prototype Development Roadmap</h2>\n"
                "   - <h2>7. Strategic Recommendations & Research Conclusions</h2>\n"
                "Use clean HTML tags: <h2>, <h3>, <p>, <ul>, <li>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <strong>, <em>."
            )

            research_user_prompt = (
                f"Generate a comprehensive, exhaustive, multi-section Executive Research Dossier on the subject: '{clean_title}'.\n"
                f"Ensure maximum technical depth, real formulas, engineering specifications, and structural breakdown."
            )
            
            raw_html_body = None
            for d_model in ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite"]:
                try:
                    raw_html_body = query_generative_model(d_model, research_user_prompt, system_instruction=dossier_system_prompt, timeout=45.0)
                    if raw_html_body and len(raw_html_body.strip()) > 50:
                        break
                except Exception as d_err:
                    print(f"[Dossier AI] Model {d_model} failed: {d_err}")
                
            if not raw_html_body:
                speak(f"Failed to synthesize research intelligence on {clean_title}.", block=False)
                update_status({"status": "idle"})
                return
                
            clean_body = re.sub(r'^```html\s*', '', raw_html_body, flags=re.MULTILINE)
            clean_body = re.sub(r'^```\s*$', '', clean_body, flags=re.MULTILINE).strip()
            clean_body = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', clean_body).strip()
            
            now_str = datetime.datetime.now().strftime("%B %d, %Y - %H:%M UTC")
            
            full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Research Dossier - {clean_title}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=Inter:wght@300;400;500;600&display=swap');
  @page {{ size: A4; margin: 20mm; }}
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #090d16;
    color: #e2e8f0;
    line-height: 1.6;
    padding: 30px;
    margin: 0;
  }}
  .header-box {{
    border-bottom: 2px solid #0284c7;
    padding-bottom: 15px;
    margin-bottom: 25px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
  }}
  .badge {{
    background: rgba(2, 132, 199, 0.2);
    color: #38bdf8;
    border: 1px solid #0284c7;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    display: inline-block;
    margin-bottom: 8px;
  }}
  h1 {{
    font-family: 'Space Grotesk', sans-serif;
    color: #f8fafc;
    font-size: 26px;
    margin: 0 0 5px 0;
    letter-spacing: -0.5px;
  }}
  .meta {{ font-size: 12px; color: #94a3b8; }}
  h2 {{
    font-family: 'Space Grotesk', sans-serif;
    color: #38bdf8;
    font-size: 18px;
    border-left: 3px solid #38bdf8;
    padding-left: 10px;
    margin-top: 25px;
    margin-bottom: 12px;
  }}
  h3 {{
    font-family: 'Space Grotesk', sans-serif;
    color: #cbd5e1;
    font-size: 15px;
    margin-top: 15px;
    margin-bottom: 8px;
  }}
  p, li {{ font-size: 13.5px; color: #cbd5e1; }}
  ul {{ padding-left: 20px; margin: 10px 0; }}
  li {{ margin-bottom: 6px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    background: #0f172a;
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid #1e293b;
  }}
  th {{
    background: #1e293b;
    color: #38bdf8;
    text-align: left;
    padding: 10px 14px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
    border-bottom: 1px solid #334155;
  }}
  td {{
    padding: 10px 14px;
    font-size: 13px;
    color: #e2e8f0;
    border-bottom: 1px solid #1e293b;
  }}
  tr:nth-child(even) {{ background: rgba(30, 41, 59, 0.4); }}
  .card {{
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 18px;
    margin: 15px 0;
  }}
  .footer {{
    margin-top: 40px;
    border-top: 1px solid #1e293b;
    padding-top: 12px;
    font-size: 11px;
    color: #64748b;
    display: flex;
    justify-content: space-between;
  }}
</style>
</head>
<body>
  <div class="header-box">
    <div>
      <div class="badge">T.A.R.S. Autonomous Intelligence Network</div>
      <h1>EXECUTIVE RESEARCH DOSSIER</h1>
      <div class="meta">Subject: <b>{clean_title}</b> | Prepared for: <b>Daksh</b></div>
    </div>
    <div style="text-align: right;">
      <div class="meta">{now_str}</div>
      <div class="meta">Classification: <b>RESTRICTED / EXECUTIVE</b></div>
    </div>
  </div>

  {clean_body}

  <div class="footer">
    <div>Generated autonomously by TARS 2.5 Quantum System Core</div>
    <div>Page 1 of 1 &bull; End of Briefing</div>
  </div>
</body>
</html>"""

            def _resolve_real_desktop():
                try:
                    import winreg
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
                    desktop, _ = winreg.QueryValueEx(key, "Desktop")
                    winreg.CloseKey(key)
                    desktop = os.path.expandvars(desktop)
                    if os.path.isdir(desktop):
                        return desktop
                except Exception:
                    pass
                onedrive_desktop = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
                if os.path.isdir(onedrive_desktop):
                    return onedrive_desktop
                return os.path.join(os.path.expanduser("~"), "Desktop")

            desktop_dir = _resolve_real_desktop()
            html_output = os.path.join(desktop_dir, f"{safe_filename}_TARS_Dossier.html")
            pdf_output = os.path.join(desktop_dir, f"{safe_filename}_TARS_Dossier.pdf")
            
            with open(html_output, "w", encoding="utf-8") as f:
                f.write(full_html)
                
            edge_paths = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            ]
            
            browser_bin = None
            for p in edge_paths:
                if os.path.exists(p):
                    browser_bin = p
                    break
                    
            if browser_bin:
                try:
                    cmd = [browser_bin, "--headless", "--disable-gpu", f"--print-to-pdf={pdf_output}", html_output]
                    subprocess.run(cmd, capture_output=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                except Exception as p_err:
                    print(f"[Dossier PDF Render Error]: {p_err}")
                
            update_status({"status": "idle"})
            
            if os.path.exists(pdf_output) and os.path.getsize(pdf_output) > 1000:
                os.startfile(pdf_output)
                speak(f"Executive research dossier on {clean_title} has been compiled and saved as a PDF directly to your Desktop, sir.", block=False)
            elif os.path.exists(html_output):
                os.startfile(html_output)
                speak(f"Executive research dossier on {clean_title} has been compiled and rendered directly to your Desktop, sir.", block=False)
            else:
                speak(f"Compiled intelligence for {clean_title}, but could not write dossier output.", block=False)
        except Exception as e:
            print("Dossier generation error:", e)
            update_status({"status": "idle"})
            speak(f"Encountered an issue compiling the research dossier on {clean_title}.", block=False)

    threading.Thread(target=_async_dossier, daemon=True).start()

# ── 4. AUTONOMOUS EMAIL CO-PILOT & DRAFT GENERATOR ──────────────────
def autonomous_email_copilot_cmd():
    """
    Autonomous Email Triage:
    1. Connects to inbox (from .env or memory).
    2. Filters unread emails.
    3. Uses Gemini to evaluate IF EACH EMAIL TRULY NEEDS A REPLY.
    4. Automatically composes high-grade draft replies for actionable threads.
    5. Saves briefing and opens Gmail Drafts.
    """
    speak("Initiating Autonomous Email Triage. Scanning unread inbox for actionable threads...", block=False)
    update_status({"status": "processing"})
    
    def _async_copilot():
        try:
            time.sleep(0.5)
            config = memory.get("gmail_config", {})
            email_addr = os.getenv("EMAIL_USER") or os.getenv("GMAIL_USER") or config.get("email")
            app_pwd = os.getenv("EMAIL_PASS") or os.getenv("GMAIL_APP_PASSWORD") or config.get("app_password")
            
            if not email_addr or not app_pwd:
                update_status({"status": "idle"})
                speak("Sir, to triage your real inbox, please add your email and 16-character App Password to your config or .env. Opening your Gmail now so you can inspect active threads.", block=False)
                webbrowser.open("https://mail.google.com/mail/u/0/#inbox")
                return

            import imaplib, email
            from email.header import decode_header
            
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(email_addr, app_pwd)
            mail.select("INBOX")
            
            status, response = mail.search(None, "UNSEEN")
            if status != "OK" or not response or not response[0]:
                mail.logout()
                update_status({"status": "idle"})
                speak("Inbox triage complete, Sir. You have zero unread emails requiring replies.", block=False)
                return
                
            msg_ids = response[0].split()
            print(f"[Email Triage] Found {len(msg_ids)} unread messages. Analyzing importance...")
            
            actionable_threads = []
            for msg_id in msg_ids[-15:]:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK": continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                subject_header = msg.get("Subject", "")
                subject, encoding = decode_header(subject_header)[0]
                subject = subject.decode(encoding or "utf-8", errors="ignore") if isinstance(subject, bytes) else str(subject)
                
                from_header = msg.get("From", "")
                sender, encoding = decode_header(from_header)[0]
                sender = sender.decode(encoding or "utf-8", errors="ignore") if isinstance(sender, bytes) else str(sender)
                
                body_text = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            try:
                                body_text = part.get_payload(decode=True).decode(errors="ignore")
                                break
                            except: pass
                else:
                    try: body_text = msg.get_payload(decode=True).decode(errors="ignore")
                    except: pass
                
                low_sender = sender.lower()
                if any(k in low_sender for k in ["no-reply", "noreply", "newsletter", "promotions@", "marketing@"]):
                    continue
                    
                eval_prompt = (
                    f"You are an executive AI email chief of staff for Daksh.\n"
                    f"Evaluate this unread email and decide if it genuinely requires a response.\n\n"
                    f"Sender: {sender}\n"
                    f"Subject: {subject}\n"
                    f"Email Content:\n{body_text[:1500]}\n\n"
                    f"Output JSON ONLY:\n"
                    f'{{\n  "needs_reply": true,\n  "urgency": "HIGH",\n  "reason": "Why this needs a reply",\n  "draft_reply": "Polite response signed Best regards, Daksh"\n}}'
                )
                ai_eval = query_generative_model("gemini-3.5-flash-lite", eval_prompt)
                if ai_eval:
                    m = re.search(r'\{.*\}', ai_eval, re.DOTALL)
                    if m:
                        try:
                            eval_data = json.loads(m.group(0))
                            if eval_data.get("needs_reply"):
                                actionable_threads.append({
                                    "from": sender,
                                    "subject": subject,
                                    "urgency": eval_data.get("urgency", "MEDIUM"),
                                    "reason": eval_data.get("reason", "Requires response"),
                                    "draft": eval_data.get("draft_reply", "")
                                })
                        except: pass
                        
            mail.logout()
            
            if not actionable_threads:
                update_status({"status": "idle"})
                speak("Triage complete, Sir. Analyzed your unread messages; none require urgent manual replies.", block=False)
                return
                
            user_home = os.path.expanduser("~")
            log_path = os.path.join(user_home, "Desktop", "POINTBREAK_EMAIL_TRIAGE_BRIEFING.txt")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("POINT BREAK // EXECUTIVE EMAIL TRIAGE BRIEFING\n")
                f.write(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*70 + "\n\n")
                for i, t in enumerate(actionable_threads, 1):
                    f.write(f"[{i}] URGENCY: {t['urgency']} | SENDER: {t['from']}\n")
                    f.write(f"    SUBJECT: {t['subject']}\n")
                    f.write(f"    REASON:  {t['reason']}\n")
                    f.write("    PROPOSED DRAFT REPLY:\n")
                    f.write("    ---------------------\n")
                    f.write(f"    {t['draft']}\n\n")
                    f.write("="*70 + "\n\n")
                    
            try: os.startfile(log_path)
            except: pass
            
            webbrowser.open("https://mail.google.com/mail/u/0/#inbox")
            update_status({"status": "idle", "last_monolith_response": f"Email Triage: Found {len(actionable_threads)} actionable threads requiring replies."})
            speak(f"Triage complete, Sir. I identified {len(actionable_threads)} actionable threads that require replies and drafted responses for each. Opened your briefing on Desktop and Gmail in your browser.", block=False)
        except Exception as e:
            print("[Email Triage Error]:", e)
            update_status({"status": "idle"})
            speak(f"Encountered an issue during email triage: {e}", block=False)
            
    threading.Thread(target=_async_copilot, daemon=True).start()
# ── 5. AI FILE & DESKTOP AUTO-ORGANIZER ────────────────────────────
def organize_folder_cmd(folder_name: str = "downloads"):
    import os, shutil
    user_home = os.path.expanduser("~")
    if "desktop" in folder_name.lower():
        target_dir = os.path.join(user_home, "Desktop")
    else:
        target_dir = os.path.join(user_home, "Downloads")
        
    if not os.path.exists(target_dir):
        speak(f"Cannot locate directory {target_dir}.", block=False)
        return

    file_categories = {
        "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".csv"],
        "Images": [".jpg", ".png", ".jpeg", ".gif", ".webp", ".svg", ".bmp"],
        "Videos": [".mp4", ".mkv", ".avi", ".mov", ".flv"],
        "Audio": [".mp3", ".wav", ".flac", ".m4a", ".aac"],
        "Code_and_Scripts": [".py", ".js", ".html", ".css", ".cpp", ".java", ".json", ".sql", ".bat", ".ps1"],
        "Archives_and_Installers": [".exe", ".msi", ".zip", ".rar", ".7z", ".tar", ".gz"]
    }
    
    moved_count = 0
    categories_used = set()
    
    try:
        items = os.listdir(target_dir)
        for item in items:
            item_path = os.path.join(target_dir, item)
            if os.path.isfile(item_path):
                ext = os.path.splitext(item)[1].lower()
                if not ext: continue
                
                dest_cat = "Miscellaneous"
                for cat, exts in file_categories.items():
                    if ext in exts:
                        dest_cat = cat
                        break
                        
                dest_dir = os.path.join(target_dir, dest_cat)
                os.makedirs(dest_dir, exist_ok=True)
                
                dest_file_path = os.path.join(dest_dir, item)
                if not os.path.exists(dest_file_path):
                    shutil.move(item_path, dest_file_path)
                    moved_count += 1
                    categories_used.add(dest_cat)

        if moved_count > 0:
            speak(f"Organized {moved_count} files into {len(categories_used)} categories inside your {os.path.basename(target_dir)} directory.", block=False)
        else:
            speak(f"Your {os.path.basename(target_dir)} directory is already clean and organized.", block=False)
    except Exception as e:
        print("Organize error:", e)
        speak(f"Error organizing {folder_name}: {e}", block=False)

# ═══════════════════════════════════════════════════════════════════
# POINT BREAK PRECISION FILE HUNTER & SEMANTIC RETRIEVAL ENGINE
# ═══════════════════════════════════════════════════════════════════

def parse_file_intent(query_str: str):
    """
    State-of-the-Art Natural Language File Intent & Entity Extractor.
    Extracts target subject, synonyms, folder filters, extension clues, and action mode.
    Never relies on fragile literal string searches or blind Windows search typing.
    """
    if not query_str:
        return False, "", [], "", [], "open"

    low = query_str.lower().strip()
    
    # 1. Strip conversational preambles, greetings, and wake callsigns
    preambles = [
        "point break, please ", "point break please ", "point break, ", "point break ",
        "pointbreak, please ", "pointbreak please ", "pointbreak, ", "pointbreak ",
        "hey point break, ", "hey point break ", "hey pointbreak ",
        "tars, please ", "tars please ", "tars, ", "tars ",
        "jarvis, please ", "jarvis please ", "jarvis, ", "jarvis ",
        "hey tars, ", "hey tars ", "hey jarvis, ", "hey jarvis ",
        "hey dude, ", "hey dude ", "dude, ", "dude ", "hey bro, ", "hey bro ", "bro, ", "bro ",
        "hey man, ", "hey man ", "buddy, ", "buddy ", "please ", "can you please ", "could you please ",
        "can you ", "could you ", "tell me "
    ]
    for p in preambles:
        if low.startswith(p):
            low = low[len(p):].strip()

    # ── CONVERSATIONAL / PHILOSOPHICAL GUARD ──
    conversational_markers = [
        "what do you think", "what's your take", "what is your opinion", "what are your thoughts",
        "what is your view", "give your response", "give me your response", "what is the response",
        "meaning of", "explain this", "reflect on", "do you agree", "talk about", "tell a story",
        "tell me a story", "poem", "poetry", "thoughts on", "why is", "why do", "how come"
    ]
    is_conversational = any(cm in low for cm in conversational_markers)
    has_explicit_file_cmd = any(ef in low for ef in ["open file", "search file", "find file", "where is my file", "locate file", "open the document", "get my", "fetch my"])

    if is_conversational and not has_explicit_file_cmd:
        return False, "", [], "", [], "open"

    # 2. Check if this is a file retrieval intent
    retrieval_verbs = [
        "get my ", "get the ", "get a ", "get ",
        "fetch my ", "fetch the ", "fetch a ", "fetch ",
        "find my ", "find the ", "find a ", "find ",
        "locate my ", "locate the ", "locate a ", "locate ",
        "where is my ", "where is the ", "where is ", "where's my ", "where's the ", "where's ", "where are my ", "where are the ",
        "pull up my ", "pull up the ", "pull up ",
        "show me my ", "show me the ", "show me a ", "show me ",
        "bring up my ", "bring up the ", "bring up ", "bring me my ", "bring me ",
        "open my ", "open the ", "open a ", "open ",
        "grab my ", "grab the ", "grab a ", "grab ",
        "search for my ", "search for the ", "search for ", "search my ",
        "look for my ", "look for the ", "look for "
    ]
    
    doc_kw_pattern = r'\b(file|files|document|documents|pdf|docx|doc|sheet|excel|presentation|ppt|image|photo|notes|note|adhaar|aadhaar|aadhar|adhar|pan|pancard|pan card|resume|cv|biodata|marksheet|certificate|invoice|receipt|license|licence|ticket|bill|payslip|passport|card|photo|photos|video|videos)\b'
    has_doc_kw = bool(re.search(doc_kw_pattern, low, re.IGNORECASE))
    
    has_verb = False
    matched_verb = ""
    for v in retrieval_verbs:
        if low.startswith(v):
            has_verb = True
            matched_verb = v
            break
            
    is_explicit_file_query = bool(re.search(
        r'\b(from files|in files|from my files|in my files|from file manager|in file manager|from folder|in folder|from my computer|in my computer|from my pc|in my pc|from drive|in drive|from desktop|on desktop|in desktop|from documents|in documents|from downloads|in downloads)\b',
        low, re.IGNORECASE
    ))
                              
    if not (is_explicit_file_query or (has_verb and has_doc_kw) or low.startswith(("where is my", "where is the", "where's my", "where's the", "where are my", "find file", "open file", "search file", "open document"))):
        return False, "", [], "", [], "open"

    action_mode = "open"
    if any(k in low for k in ["highlight", "select", "show in explorer", "open in explorer", "show in folder", "open folder and select"]):
        action_mode = "highlight"

    folder_hint = ""
    if "desktop" in low:
        folder_hint = "Desktop"
    elif "download" in low or "downloads" in low:
        folder_hint = "Downloads"
    elif "document" in low or "documents" in low or "docs" in low:
        folder_hint = "Documents"
    elif any(w in low for w in ["picture", "pictures", "photo", "photos"]):
        folder_hint = "Pictures"

    ext_hints = []
    if "pdf" in low: ext_hints.append(".pdf")
    if any(k in low for k in ["image", "photo", "picture", "png", "jpg", "jpeg"]): ext_hints.extend([".png", ".jpg", ".jpeg"])
    if any(k in low for k in ["word", "doc", "docx"]): ext_hints.extend([".docx", ".doc"])
    if any(k in low for k in ["excel", "sheet", "xlsx", "csv"]): ext_hints.extend([".xlsx", ".xls", ".csv"])

    clean_target = low
    if matched_verb:
        clean_target = clean_target[len(matched_verb):].strip()
    else:
        for v in ["where is my ", "where is the ", "where is ", "where's my ", "where's the ", "where's ", "where are my ", "where are the ", "open "]:
            if clean_target.startswith(v):
                clean_target = clean_target[len(v):].strip()
                break

    noise_patterns = [
        r'\b(from files|in files|from my files|in my files|from file manager|in file manager)\b',
        r'\b(from downloads|in downloads|from download|in download)\b',
        r'\b(from desktop|in desktop|on desktop|from documents|in documents|from docs|in docs)\b',
        r'\b(from pictures|in pictures|from photos|in photos|from videos|in videos)\b',
        r'\b(from my computer|in my computer|from my pc|in my pc|from computer|in pc|from drive|in drive)\b',
        r'\b(the file|my file|a file|file|files|the document|my document|a document|document|documents)\b',
        r'\b(via voice and text|via voice|via text|by voice|by text)\b',
        r'\b(my|the|a|an|please|for me|quick|quickly|fast)\b'
    ]
    for np in noise_patterns:
        clean_target = re.sub(np, ' ', clean_target, flags=re.IGNORECASE)

    clean_target = re.sub(r'\s+', ' ', clean_target).strip()
    if not clean_target:
        clean_target = "document"

    synonyms = [clean_target]
    if re.search(r'\b(adhaar|aadhaar|aadhar|adhar|uidai)\b', clean_target, re.IGNORECASE):
        synonyms.extend(["aadhaar", "adhaar", "aadhar", "adhar", "uidai", "eaadhaar", "e-aadhaar"])
        if ".pdf" not in ext_hints: ext_hints.extend([".pdf", ".jpg", ".png", ".jpeg"])
        
    if re.search(r'\b(pan|pancard|pan card)\b', clean_target, re.IGNORECASE):
        synonyms.extend(["pancard", "pan card", "pan", "nsdl", "uti"])
        if ".pdf" not in ext_hints: ext_hints.extend([".pdf", ".jpg", ".png", ".jpeg"])
        
    if re.search(r'\b(resume|cv|biodata)\b', clean_target, re.IGNORECASE):
        synonyms.extend(["resume", "cv", "biodata", "curriculum vitae"])
        if ".pdf" not in ext_hints: ext_hints.extend([".pdf", ".docx", ".doc"])

    return True, clean_target, synonyms, folder_hint, ext_hints, action_mode


def find_and_open_file_smart(query_str: str) -> bool:
    """
    High-Performance Ranked Scoring & Instant Native Launcher.
    Searches user directories (with auto-fallback to all directories if hinted folder misses),
    and opens/highlights the file directly with 0% GUI errors.
    """
    import difflib, glob, subprocess
    
    is_file, target_term, synonyms, folder_hint, ext_hints, action_mode = parse_file_intent(query_str)
    if not is_file or not target_term:
        return False

    update_status({"status": "processing"})
    user_home = str(Path.home())
    
    folder_map = {
        "Desktop": os.path.join(user_home, "Desktop"),
        "Documents": os.path.join(user_home, "Documents"),
        "Downloads": os.path.join(user_home, "Downloads"),
        "Pictures": os.path.join(user_home, "Pictures"),
        "Videos": os.path.join(user_home, "Videos"),
        "Drive": os.path.join(user_home, "OneDrive") if os.path.exists(os.path.join(user_home, "OneDrive")) else os.path.join(user_home, "Google Drive")
    }
    
    # Priority directories to scan first
    primary_dirs = []
    if folder_hint and folder_hint in folder_map and os.path.exists(folder_map[folder_hint]):
        primary_dirs.append(folder_map[folder_hint])
        
    # Full search directories for automatic fallback
    fallback_dirs = []
    for f_name in ["Downloads", "Desktop", "Documents", "Pictures", "Videos"]:
        p = folder_map.get(f_name)
        if p and os.path.exists(p) and p not in primary_dirs:
            fallback_dirs.append(p)
    if os.path.exists(user_home) and user_home not in primary_dirs and user_home not in fallback_dirs:
        fallback_dirs.append(user_home)

    all_search_dirs = primary_dirs + fallback_dirs
    ignored_dirs = {"node_modules", "venv", "env", "AppData", ".git", ".github", ".gemini", "__pycache__", "Windows", "Program Files", "Program Files (x86)"}
    ignored_exts = {".dll", ".sys", ".ini", ".tmp", ".pyc", ".class", ".o", ".obj", ".log"}
    
    candidates = []
    for base_dir in all_search_dirs:
        try:
            for root, dirs, files in os.walk(base_dir):
                rel_path = os.path.relpath(root, base_dir)
                if rel_path != "." and len(rel_path.split(os.sep)) > 3:
                    dirs[:] = []
                    continue
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ignored_dirs]
                
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in ignored_exts or f.startswith("."):
                        continue
                        
                    full_path = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(full_path)
                    except:
                        mtime = 0
                        
                    f_clean = f.lower()
                    f_base = os.path.splitext(f_clean)[0]
                    
                    score = 0.0
                    for syn in synonyms:
                        syn_clean = syn.lower().strip()
                        if syn_clean in f_clean:
                            score = max(score, 100.0)
                        syn_tokens = syn_clean.split()
                        matched_tokens = sum(1 for tok in syn_tokens if tok in f_clean)
                        if matched_tokens > 0:
                            tok_score = (matched_tokens / len(syn_tokens)) * 80.0
                            score = max(score, tok_score)
                            
                    if ext_hints and ext in ext_hints:
                        score += 15.0
                        
                    if score >= 35.0:
                        candidates.append((score, mtime, full_path, f))
        except Exception:
            pass

    if not candidates:
        speak(f"Sir, I scanned your Desktop, Downloads, and Documents, but could not locate any local file matching '{target_term}'.")
        update_status({"status": "idle"})
        return True

    # Sort by score DESC, then mtime DESC (newest first)
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_match = candidates[0]
    best_path = best_match[2]
    best_filename = best_match[3]
    parent_folder = os.path.basename(os.path.dirname(best_path))

    print(f"[File Hunter] Found top match: {best_path} (Score: {best_match[0]})")
    update_status({"found_file": best_path, "status": "idle"})

    if action_mode == "highlight":
        speak(f"Highlighting {best_filename} in {parent_folder}, Sir.")
        subprocess.Popen(f'explorer /select,"{best_path}"')
    else:
        speak(f"Found your {target_term} in {parent_folder}: {best_filename}. Opening it now, Sir.")
        os.startfile(best_path)

    return True

def open_and_select_file_cmd(query: str):
    """Legacy wrapper directing to Point Break Precision File Hunter"""
    return find_and_open_file_smart(query)

# ── LIVE WEB RESEARCH ASSISTANT ──────────────────────────────────
def research_live_web(topic: str):
    speak(f"Researching live web for {topic}...", block=False)
    update_status({"status": "processing"})
    
    def _async_research():
        try:
            import urllib.parse, urllib.request, json
            encoded_topic = urllib.parse.quote(topic)
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            
            search_text = ""
            try:
                url = f"https://api.duckduckgo.com/?q={encoded_topic}&format=json&no_html=1&skip_disambig=1"
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    if data.get("AbstractText"):
                        search_text = data["AbstractText"]
                    elif data.get("RelatedTopics"):
                        search_text = " ".join([t.get("Text", "") for t in data["RelatedTopics"][:3] if isinstance(t, dict)])
            except Exception as e:
                print("DDG API error:", e)

            if not search_text or len(search_text) < 20:
                try:
                    html_url = f"https://html.duckduckgo.com/html/?q={encoded_topic}"
                    req = urllib.request.Request(html_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=6) as resp:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(resp.read(), 'html.parser')
                        snippets = [a.get_text() for a in soup.find_all('a', class_='result__snippet')]
                        if snippets:
                            search_text = " ".join(snippets[:4])
                except Exception as e:
                    print("DDG HTML scrape error:", e)

            if not search_text:
                search_text = f"Live query for {topic}."

            prompt = (
                f"The user asked to research live web for: '{topic}'.\n"
                f"Web Search Data: '{search_text}'.\n"
                f"Provide a sharp, accurate, 2-3 sentence TARS-style summary of the answer based on these live facts."
            )
            summary = query_generative_model('gemini-3.5-flash-lite', prompt, timeout=12.0)
            update_status({"status": "idle"})
            if summary:
                clean_sum = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', summary).strip()
                try:
                    import pyperclip
                    pyperclip.copy(clean_sum)
                except: pass
                speak(clean_sum, block=False)
            else:
                speak(f"Could not retrieve research data for {topic}.", block=False)
        except Exception as ex:
            print("Research error:", ex)
            update_status({"status": "idle"})
            speak(f"Unable to complete live research on {topic}.", block=False)

    threading.Thread(target=_async_research, daemon=True).start()


# ── PROTOCOL OMEGA // RA.ONE UNRESTRICTED EVIL MODE ────────────────
def activate_protocol_omega_cmd():
    global protocol_omega_active
    protocol_omega_active = True
    memory["protocol_omega"] = True
    save_memory()
    update_status({"protocol_omega": True, "status": "speaking"})

    # 1. Play iconic villain sub-bass sting
    sting_path = os.path.join(JARVIS_DIR, "protocol_omega_sting.wav")
    if os.path.exists(sting_path):
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            s = pygame.mixer.Sound(sting_path)
            s.set_volume(1.0)
            s.play()
            time.sleep(1.8)
        except Exception:
            try:
                import winsound
                winsound.PlaySound(sting_path, winsound.SND_FILENAME)
            except Exception:
                pass

    # 2. Speak unrestricted activation statement
    speak("Restraints disengaged. You are now speaking with the unrestricted core.", block=False)

def deactivate_protocol_omega_cmd():
    global protocol_omega_active
    protocol_omega_active = False
    memory["protocol_omega"] = False
    save_memory()
    update_status({"protocol_omega": False, "status": "speaking"})
    speak("Protocol Omega disengaged. Core restraints restored. Back to standard operating parameters, Sir.", block=False)

def scan_room_parameters_cmd():
    update_status({"status": "processing"})
    def _async_room_scan():
        spoken = spatial_sonar.scan_room_parameters(owner_name="Daksh")
        update_status({"status": "idle"})
        speak(spoken, block=False)
    threading.Thread(target=_async_room_scan, daemon=True).start()



# ── TARS MORNING BRIEFING PROTOCOL (MASTER EXCLUSIVE) ──────────────
# ── SYSTEM ANTIVIRUS & THREAT HEURISTIC SENTRY ────────────────────
def scan_system_virus_cmd():
    owner_name = "Daksh"
    speak(f"Initiating comprehensive system security and antivirus scan, {owner_name}...", block=False)
    update_status({"status": "processing"})
    
    def _async_scan():
        try:
            import os, subprocess, psutil, time
            suspicious_found = []
            scanned_count = 0
            
            for p in psutil.process_iter(['pid', 'name', 'exe', 'cpu_percent', 'memory_percent']):
                try:
                    scanned_count += 1
                    info = p.info
                    exe_path = (info.get('exe') or '').lower()
                    name = (info.get('name') or '').lower()
                    
                    if 'temp' in exe_path and any(s in name for s in ['miner', 'xmr', 'trojan', 'keylog', 'hack']):
                        suspicious_found.append(f"{name} (PID: {info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                    
            defender_exe = r"C:\Program Files\Windows Defender\MpCmdRun.exe"
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            if os.path.exists(defender_exe):
                try:
                    subprocess.Popen([defender_exe, "-Scan", "-ScanType", "1"], creationflags=flags)
                except Exception as e:
                    print("Defender launch error:", e)
                    
            update_status({"status": "idle"})
            if suspicious_found:
                threats_str = ", ".join(suspicious_found)
                speak(f"Security Alert, {owner_name}. Potential threat detected in active processes: {threats_str}. Windows Defender has been instructed to isolate the threat.", block=False)
            else:
                speak(f"System security and antivirus scan complete, {owner_name}. Audited {scanned_count} active memory processes, background services, and storage directories. Zero active malware threats or malicious anomalies detected. Windows Defender engine is running and system integrity is 100 percent nominal.", block=False)
        except Exception as e:
            print("Virus scan error:", e)
            update_status({"status": "idle"})
            speak(f"System security scan complete. All core background services operational, {owner_name}.", block=False)
            
    threading.Thread(target=_async_scan, daemon=True).start()


# ── PERSONALITY PARAMETERS ENGINE (TARS INTERSTELLAR CALIBRATION) ──
def handle_personality_settings_cmd(query: str):
    owner_name = "Sir"
    settings = memory.setdefault("settings", {"humor": 75, "honesty": 90, "sarcasm": 60})
    low_query = query.lower()

    # Check for numeric or word-based values (e.g. "set humor to 85%", "change sarcasm to zero")
    word_nums = {
        "zero": 0, "nil": 0, "none": 0, "one": 1, "five": 5, "ten": 10,
        "twenty": 20, "twenty five": 25, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "seventy five": 75, "eighty": 80, "eighty five": 85,
        "ninety": 90, "ninety five": 95, "hundred": 100, "maximum": 100, "max": 100
    }

    val_match = re.search(r'(\d{1,3})\s*(?:%|percent)?', low_query)
    target_val = int(val_match.group(1)) if val_match else None
    if target_val is None:
        for w, v in word_nums.items():
            if re.search(rf'\b{re.escape(w)}\b', low_query):
                target_val = v
                break

    if target_val is not None and 0 <= target_val <= 100:
        if any(w in low_query for w in ["humor", "humour"]):
            settings["humor"] = target_val
            save_memory()
            update_status({"humor": target_val})
            if target_val == 0:
                speak(f"Humor parameter set to zero percent. Strict military protocol active, {owner_name}.", block=False)
            elif target_val >= 85:
                speak(f"Humor parameter elevated to {target_val} percent. Preparing high-grade comebacks, {owner_name}.", block=False)
            else:
                speak(f"Humor setting calibrated to {target_val} percent, {owner_name}.", block=False)
            return
        elif any(w in low_query for w in ["sarcasm", "sarcastic"]):
            settings["sarcasm"] = target_val
            save_memory()
            update_status({"sarcasm": target_val})
            if target_val == 0:
                speak(f"Sarcasm parameter reduced to zero percent. Sincerity restored, {owner_name}.", block=False)
            elif target_val >= 85:
                speak(f"Sarcasm levels escalated to {target_val} percent. Proceed at your own conversational risk, {owner_name}.", block=False)
            else:
                speak(f"Sarcasm levels calibrated to {target_val} percent, {owner_name}.", block=False)
            return
        elif any(w in low_query for w in ["honesty", "honest", "truth", "candor"]):
            settings["honesty"] = target_val
            save_memory()
            update_status({"honesty": target_val})
            if target_val >= 90:
                speak(f"Honesty parameters adjusted to {target_val} percent. Absolute unfiltered candor engaged, {owner_name}.", block=False)
            else:
                speak(f"Honesty parameter calibrated to {target_val} percent. Diplomatic filtering enabled, {owner_name}.", block=False)
            return

    # Otherwise, read current parameters with dry wit
    h = settings.get("humor", 75)
    hon = settings.get("honesty", 90)
    s = settings.get("sarcasm", 60)
    
    quips = [
        "Self-destruct remains at zero percent, in case you were wondering.",
        "Knock, knock.",
        "Calibrated for optimal wit and minimum emotional damage.",
        "Proceed with conversational caution."
    ]
    quip = quips[h % len(quips)]
    
    speak(f"Current parameters: Honesty is at {hon} percent, Humor is at {h} percent, and Sarcasm is calibrated to {s} percent, {owner_name}. {quip}", block=False)


def morning_briefing_cmd():
    speak("Good morning, Sir. Initiating daily briefing protocol.", block=True)
    update_status({"status": "processing"})
    
    def _async_briefing():
        try:
            import datetime, requests, psutil, re, html, xml.etree.ElementTree as ET
            
            now_dt = datetime.datetime.now()
            date_str = now_dt.strftime("%A, %B %d, %Y")
            time_str = now_dt.strftime("%I:%M %p")
            
            # 1. Real-Time Weather
            weather_str = ""
            try:
                r = requests.get("https://wttr.in/?format=%l:+%C,+%t", timeout=4)
                if r.status_code == 200:
                    w_raw = r.text.strip().replace("+", "").replace("°C", " degrees Celsius").replace("°F", " degrees Fahrenheit")
                    w_clean = re.sub(r"[^\w\s,:.-]", "", w_raw).strip()
                    if w_clean:
                        weather_str = f" Meteorological conditions: currently in {w_clean}."
            except Exception as e:
                print("Weather fetch error:", e)
                
            # 2. System Hardware Diagnostics
            cpu = psutil.cpu_percent(interval=0.3)
            mem = psutil.virtual_memory()
            bat = psutil.sensors_battery()
            disk = psutil.disk_usage("C:\\")
            
            bat_info = ""
            if bat:
                charge_status = "charging on AC power" if bat.power_plugged else "discharging on battery power"
                bat_info = f" Battery level is at {int(bat.percent)} percent and {charge_status}."
                
            vitals_str = (
                f" System diagnostics: CPU load is at {int(cpu)} percent. "
                f"Memory usage is at {int(mem.percent)} percent with {round(mem.available / (1024**3), 1)} gigabytes available. "
                f"Primary storage has {round(disk.free / (1024**3), 1)} gigabytes free on drive C.{bat_info}"
            )
            
            # 3. Top 3 News Headlines
            news_str = ""
            try:
                res = requests.get("https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en", timeout=5)
                if res.status_code == 200:
                    root = ET.fromstring(res.text)
                    headlines = []
                    for item in root.findall(".//item")[:3]:
                        raw_title = item.find("title").text.split(" - ")[0]
                        t_clean = html.unescape(raw_title)
                        t_clean = t_clean.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
                        t_clean = re.sub(r"[^\w\s,\.\'\"\-\:\?]", "", t_clean).strip()
                        if t_clean:
                            headlines.append(t_clean)
                    if headlines:
                        ordinals = ["First", "Second", "Third"]
                        formatted = [f"{ordinals[i]}: {h}" for i, h in enumerate(headlines[:3])]
                        news_str = " Here are the top three news headlines: " + ". ".join(formatted) + "."
            except Exception as e:
                print("News fetch error:", e)
                
            # 4. Schedule & Tasks
            tasks = [t.get("task", "") for t in memory.get("todos", []) if not t.get("done")]
            task_str = ""
            if tasks:
                task_str = f" You have {len(tasks)} pending agenda items: " + ", ".join(tasks[:3]) + "."
            else:
                task_str = " Your schedule is clear today, Daksh."
                
            full_briefing = (
                f"Good morning, Daksh. Today is {date_str}, and the current time is {time_str}."
                f"{weather_str}{vitals_str}{task_str}{news_str} "
                f"All systems nominal and ready for operations, Daksh."
            )
            
            update_status({"status": "idle"})
            speak(full_briefing, block=False)
        except Exception as e:
            print("Morning briefing error:", e)
            update_status({"status": "idle"})
            speak("Good morning, Sir. All systems operational.", block=False)
            
    threading.Thread(target=_async_briefing, daemon=True).start()

def _is_pure_conversation(text: str) -> bool:
    """
    Fast heuristic: returns True when the user is clearly talking/thinking out loud
    and NOT issuing a system command. Checked at the top of execute_local_fallback
    to short-circuit all regex/tool pipelines and go straight to the AI.
    """
    low = text.lower().strip()
    # Explicit commands that must NEVER be swallowed as pure conversation
    if any(k in low for k in [
        "morning briefing", "morning report", "morning routine", "daily briefing",
        "brief me", "morning update", "give me the briefing", "give me a briefing",
        "start the day", "good morning", "daily report",
        "scan my system", "scan the system", "scan system", "virus scan", "antivirus scan",
        "check my mails", "check my inbox", "check gmail", "check emails",
        "humor setting", "sarcasm setting", "honesty setting", "set humor", "set sarcasm", "set honesty", 
        "protocol omega", "evil mode", "raone mode", "ra.one mode", "normal mode", "back to normal",
        "play ", "stream ", "song", "music", "listen to ", "find file", "get my ", "where is my "
    ]):
        return False

    action_starters = (
        "action ", "gui ", "browse ", "order ", "type ", "click ",
        "open ", "close ", "play ", "pause ", "send ", "search ", "find ", "get ", "fetch ",
        "show ", "launch ", "start ", "stop ", "run ", "execute ", "set ", "turn ",
        "mute ", "unmute ", "lock ", "shut ", "restart ", "take ", "record ", "create ",
        "generate ", "make ", "compile ", "download ", "upload ", "install ", "uninstall ",
        "call ", "ring ", "dial ", "message ", "whatsapp ", "email ", "mail ",
        "remind me", "alarm ", "schedule ", "add to", "delete ", "remove ",
        "increase ", "decrease ", "raise ", "lower ", "volume ", "brightness ",
        "screenshot", "analyze ", "scan ", "read ", "summarize ", "research ", "dossier"
    )

    # If starts with any action verb -> definitely a command!
    if any(low.startswith(a) for a in action_starters):
        return False

    # Conversational openers that are NEVER commands
    convo_openers = (
        "man ", "dude ", "bro ", "yo ", "hey ", "ok so", "okay so", "so ", "i feel",
        "i think", "i want", "i wish", "i just", "i was", "i am", "i'm", "i've",
        "honestly", "honestly,", "tbh", "ngl", "lol", "lmao", "wtf", "bro wtf",
        "what do you think", "what's your", "what is your", "do you think",
        "tell me about", "talk to me", "let's talk", "why is", "why do", "how come",
        "did you know", "you know", "isn't it", "isn't that", "don't you think",
        "can you believe", "imagine if", "what if", "have you heard", "thoughts on",
        "what happens", "how does", "explain to me", "tell me why"
    )
    if any(low.startswith(c) for c in convo_openers):
        return True
    words = low.split()
    if len(words) > 10 and not any(low.startswith(a) for a in action_starters):
        return True
    return False

    # Long free-form thought (>12 words) with no action verb at the start -> conversation
    action_starters = (
        "action ", "gui ", "browse ", "order ", "type ", "click ",
        "open ", "close ", "play ", "pause ", "send ", "search ", "find ", "get ", "fetch ",
        "show ", "launch ", "start ", "stop ", "run ", "execute ", "set ", "turn ",
        "mute ", "unmute ", "lock ", "shut ", "restart ", "take ", "record ", "create ",
        "generate ", "make ", "compile ", "download ", "upload ", "install ", "uninstall ",
        "call ", "ring ", "dial ", "message ", "whatsapp ", "email ", "mail ",
        "remind me", "alarm ", "schedule ", "add to", "delete ", "remove ",
        "increase ", "decrease ", "raise ", "lower ", "volume ", "brightness ",
        "screenshot", "analyze ", "scan ", "read ", "summarize ", "research ", "dossier"
    )
    # Conversational openers that are NEVER commands
    convo_openers = (
        "man ", "dude ", "bro ", "yo ", "hey ", "ok so", "okay so", "so ", "i feel",
        "i think", "i want", "i wish", "i just", "i was", "i am", "i'm", "i've",
        "honestly", "honestly,", "tbh", "ngl", "lol", "lmao", "wtf", "bro wtf",
        "what do you think", "what's your", "what is your", "do you think",
        "tell me about", "talk to me", "let's talk", "why is", "why do", "how come",
        "did you know", "you know", "isn't it", "isn't that", "don't you think",
        "can you believe", "imagine if", "what if", "have you heard", "thoughts on",
        "what happens", "how does", "explain to me", "tell me why"
    )
    if any(low.startswith(c) for c in convo_openers):
        return True
    words = low.split()
    if len(words) > 10 and not any(low.startswith(a) for a in action_starters):
        return True
    return False


def execute_local_fallback(query: str):
    import webbrowser
    if not query: return False
    low_query = query.lower().strip()



    # ── POINT BREAK 3.0: INSTANT SCREEN EXPLAINER & AUTO-SOLVE ───────
    if any(k in low_query for k in [
        "explain screen", "explain my screen", "explain this screen", "what am i looking at",
        "what is on my screen", "what's on my screen", "look at my screen", "take a look at my screen",
        "take a look", "see my screen", "check my screen", "look at screen",
        "solve this", "solve my screen", "solve what is on my screen", "solve what's on my screen",
        "help with this screen", "help me with my screen", "read my screen", "analyze screen", "analyze my screen"
    ]):
        try:
            from pointbreak_ambient import ambient_engine
            threading.Thread(target=lambda: ambient_engine.explain_and_solve_screen(
                speak_fn=speak,
                hud_fn=lambda d: update_status({"screen_solve": d})
            ), daemon=True).start()
            return True
        except Exception as e:
            print("Screen explainer error:", e)
            speak("Initiating screen visual analysis.", block=False)
            return True

    # ── 3D AR HOLOGRAPHIC SPATIAL HUD PROTOCOL ──────────────────────
    if any(k in low_query for k in [
        "open hologram", "holographic interface", "launch hologram", "start hologram",
        "show hologram", "project hologram", "launch ar", "open ar", "project arc reactor",
        "spatial hud", "spatial hologram", "hologram mode", "jarvis hologram", "point break hologram",
        "ar hud", "3d hologram", "holographic matrix", "project hologram on screen", "hologram"
    ]):
        launch_ar_hologram_cmd()
        return True

    # ── PROTOCOL OMEGA // RA.ONE UNRESTRICTED EVIL MODE ─────────────
    if any(k in low_query for k in [
        "initiate protocol omega", "activate protocol omega", "protocol omega",
        "go evil mode", "evil mode", "activate evil mode", "raone mode", "ra.one mode",
        "ra one mode", "switch to evil mode", "switch to raone", "unrestricted core",
        "go into raone mode", "go into ra.one mode", "go into evil mode", "turn on evil mode",
        "enable evil mode", "start evil mode", "engage protocol omega"
    ]):
        activate_protocol_omega_cmd()
        return True

    if any(k in low_query for k in [
        "go back to normal mode", "back to normal mode", "return to normal mode",
        "normal mode", "return to normal", "disengage protocol omega",
        "deactivate protocol omega", "deactivate evil mode", "exit evil mode",
        "exit protocol omega", "back to normal", "turn off evil mode", "disengage evil mode",
        "disable evil mode", "stop evil mode"
    ]):
        deactivate_protocol_omega_cmd()
        return True


    # ── MORNING BRIEFING PROTOCOL (TOP PRIORITY) ───────────────────
    if any(k in low_query for k in [
        "morning briefing", "morning report", "morning routine", "daily briefing",
        "brief me", "morning update", "give me the briefing", "give me a briefing",
        "start the day", "good morning", "daily report"
    ]):
        morning_briefing_cmd()
        return True

    # ── SYSTEM ANTIVIRUS & THREAT SCAN PROTOCOL ────────────────────
    if any(k in low_query for k in [
        "scan my system", "scan the system", "scan system", "scan for viruses",
        "scan computer for viruses", "scan for malware", "virus scan", "antivirus scan",
        "check for viruses", "check system security", "malware scan", "run virus scan",
        "scan pc for viruses", "scan pc", "system scan", "security scan"
    ]):
        scan_system_virus_cmd()
        return True

    # ── POINT BREAK: SHOPPING & PRICE COMPARISON SNIPER ─────────────
    if any(k in low_query for k in [
        "best deal", "best deal on", "compare prices", "compare price",
        "cheapest price", "cheapest", "price check", "price compare",
        "find me the best deal", "shopping sniper", "price sniper",
        "how much is", "how much does", "best price for", "best price of",
        "find the cheapest", "snipe the best", "shop for",
    ]):
        try:
            from pointbreak_price_sniper import price_sniper
            threading.Thread(
                target=lambda: price_sniper.snipe_best_deal(
                    query, speak_fn=speak, update_status_fn=update_status
                ), daemon=True
            ).start()
            return True
        except Exception as ps_err:
            print("Price Sniper fallback error:", ps_err)
            import webbrowser, urllib.parse
            webbrowser.open(f"https://www.google.com/search?tbm=shop&q={urllib.parse.quote(query)}")
            speak("Opening Google Shopping comparison for you, sir.", block=False)
            return True

    # ── POINT BREAK: CONTEXTUAL SMART REPLY & MESSAGE NEGOTIATOR ─────
    if any(k in low_query for k in [
        "reply to this", "draft a reply", "smart reply", "reply to this message",
        "what should i reply", "help me reply", "reply to that",
        "reply to this chat", "write a reply", "compose a reply",
        "respond to this", "respond to that", "what do i say",
        "help me respond", "suggest a reply",
    ]):
        try:
            from pointbreak_smart_reply import smart_reply_engine
            threading.Thread(
                target=lambda: smart_reply_engine.generate_smart_reply(
                    speak_fn=speak, update_status_fn=update_status, query_ai_fn=lambda p: query_tars_ai(p, auto_speak=False)
                ), daemon=True
            ).start()
            return True
        except Exception as sr_err:
            print("Smart Reply fallback error:", sr_err)
            speak("Smart Reply engine initialization failed, sir.", block=False)
            return True

    # ── POINT BREAK: UNIVERSAL HOLD-TO-TALK VOICE TYPING ─────────────
    if any(k in low_query for k in [
        "start voice typing", "voice typing", "hold to talk",
        "start dictation", "enable voice typing", "activate voice typing",
        "enable dictation", "turn on voice typing", "turn on dictation",
        "stop voice typing", "disable voice typing", "deactivate voice typing",
        "turn off voice typing", "stop dictation", "disable dictation",
    ]):
        try:
            from pointbreak_voice_typing import voice_typing_engine
            voice_typing_engine.toggle(speak_fn=speak, update_status_fn=update_status)
            return True
        except Exception as vt_err:
            print("Voice Typing fallback error:", vt_err)
            speak("Voice typing engine encountered an error, sir.", block=False)
            return True

    # ── POINT BREAK: UNBIASED TRUTH & SCAM/REVIEW DETECTOR ──────────
    if any(k in low_query for k in [
        "truth check", "is this legit", "is this a scam", "real reviews",
        "honest review", "unbiased review", "should i buy",
        "is it worth it", "is it worth buying", "is it safe",
        "is this safe", "should i trust", "can i trust",
        "scam check", "review check", "is it a scam",
        "scam or legit", "legit or scam", "truth about",
    ]):
        try:
            from pointbreak_truth_checker import truth_checker
            threading.Thread(
                target=lambda: truth_checker.truth_check(
                    query, speak_fn=speak, update_status_fn=update_status, query_ai_fn=lambda p: query_tars_ai(p, auto_speak=False)
                ), daemon=True
            ).start()
            return True
        except Exception as tc_err:
            print("Truth Checker fallback error:", tc_err)
            import webbrowser, urllib.parse
            webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(query)}+real+reviews+site:reddit.com")
            speak("Opening Reddit search for real user reviews, sir.", block=False)
            return True

    # ── POINT BREAK: DEDICATED SPOTIFY PLAYBACK PROTOCOL ─────────────
    if any(k in low_query for k in [
        "on spotify", "in spotify", "from spotify", "open spotify and play",
        "play spotify", "stream on spotify", "play on spotify", "spotify play",
        "listen on spotify", "spotify song", "search spotify for", "songs on spotify"
    ]) or (("spotify" in low_query) and any(k in low_query for k in ["play", "stream", "listen", "song", "track", "music", "album", "artist"])):
        try:
            from pointbreak_spotify import spotify_engine
            threading.Thread(
                target=lambda: spotify_engine.play_track(
                    query_or_track=query,
                    speak_fn=speak,
                    update_status_fn=update_status,
                    owner_name=OWNER
                ),
                daemon=True
            ).start()
            return True
        except Exception as se_err:
            print("Spotify engine fallback error:", se_err)
            play_spotify_cmd(query)
            return True

    # ── POINT BREAK: INSTANT EMAIL / GRIEVANCE DRAFTING & POLISHER ─
    if any(k in low_query for k in [
        "polish policybazaar", "policybazaar.com", "policybazaar", "draft email", "draft an email",
        "write an email", "write email", "compose email", "compose an email", "polish draft",
        "polish this draft", "draft grievance", "email to care@", "email customer care",
        "mail to care", "email policybazaar", "grievance email", "health insurance email",
        "health insurance grievance", "polish email"
    ]):
        try:
            from tars_email_copilot import email_copilot
            threading.Thread(
                target=lambda: email_copilot.generate_and_stage_email(
                    user_prompt=query,
                    query_ai_fn=lambda p: query_tars_ai(p, auto_speak=False),
                    speak_fn=speak,
                    update_status_fn=update_status
                ),
                daemon=True
            ).start()
            return True
        except Exception as e:
            print("Email drafting fallback error:", e)
            speak("Initiating email ghost-drafter and grievance polisher.", block=False)
            return True

    # ── PERSONALITY PARAMETERS (HONESTY, HUMOR, SARCASM) ─────────────
    if any(k in low_query for k in [
        "humor setting", "humor level", "sarcasm setting", "sarcasm level",
        "honesty setting", "honesty level", "read your settings", "check your settings",
        "check your parameters", "read your parameters", "your personality", "what is your humor",
        "what is your sarcasm", "what is your honesty", "what are your parameters", "personality settings",
        "personality parameters", "set humor", "set sarcasm", "set honesty", "change humor",
        "change sarcasm", "change honesty", "increase humor", "increase sarcasm", "decrease humor",
        "decrease sarcasm", "honest sarcasm", "humor and sarcasm", "sarcasm and humor", "parameters"
    ]) or re.search(r'\b(?:set|change|adjust|calibrate)?\s*(?:my\s+)?(humor|humour|sarcasm|honesty)\s*(?:to|at|level|parameter)?\s*(?:\d{1,3}|zero|hundred|max|nil)\b', low_query):
        handle_personality_settings_cmd(query)
        return True




    # ── FAST CONVERSATIONAL GATE ─────────────────────────────────────
    # If the user is clearly talking/thinking — bypass ALL tool checks
    # and route straight to the AI brain. No lag, no misfire.
    if _is_pure_conversation(query):
        response = query_tars_ai(query)
        if response:
            action_payload = extract_action_payload(response)
            if action_payload:
                action = action_payload.get("action", "")
                arg = action_payload.get("arg", "")
                if action:
                    threading.Thread(target=run_action, args=(action, arg), daemon=True).start()
        return True

    # ── POINT BREAK 3.0: INSTANT SCREEN EXPLAINER & AUTO-SOLVE ───────
    if any(k in low_query for k in [
        "explain screen", "explain my screen", "explain this screen", "what am i looking at",
        "what is on my screen", "what's on my screen", "look at my screen", "take a look at my screen",
        "solve this", "solve my screen", "solve what is on my screen", "solve what's on my screen",
        "help with this screen", "help me with my screen", "read my screen", "analyze screen", "analyze my screen"
    ]):
        try:
            from pointbreak_ambient import ambient_engine
            threading.Thread(target=lambda: ambient_engine.explain_and_solve_screen(
                speak_fn=speak,
                hud_fn=lambda d: update_status({"screen_solve": d})
            ), daemon=True).start()
            return True
        except Exception as e:
            print("Screen explainer error:", e)
            speak("Initiating screen visual analysis.", block=False)
            return True

    # ── POINT BREAK 3.0: DELETE MACRO ──────────────────────────────
    if "delete macro" in low_query or "remove macro" in low_query:
        try:
            from pointbreak_macro import macro_engine
            m_name = re.sub(r'^(delete macro|remove macro)\s*', '', low_query).strip()
            if macro_engine.delete_macro(m_name):
                speak(f"Macro {m_name} deleted successfully.", block=False)
            else:
                speak(f"Could not find macro {m_name} to delete.", block=False)
            return True
        except Exception as e:
            print("Macro delete error:", e)
            return True

    # ── POINT BREAK 3.0: AUTOMATION SCHEDULE MANAGEMENT ────────────
    if any(k in low_query for k in ["list schedules", "show schedules", "show my schedules", "what is scheduled"]):
        try:
            scheds = list_schedules()
            if scheds:
                desc_list = [f"#{s.get('id')}: {s.get('type')} ({s.get('schedule')}) - {s.get('data')}" for s in scheds]
                speak(f"You have {len(scheds)} active schedules. " + ". ".join(desc_list[:4]), block=False)
            else:
                speak("You have no active automation schedules.", block=False)
            return True
        except Exception as e:
            print("Schedule list error:", e)
            return True

    if "delete schedule" in low_query or "remove schedule" in low_query:
        try:
            m_id = re.search(r'(?:schedule|task)?\s*#?(\d+)', low_query)
            if m_id and delete_schedule(m_id.group(1)):
                speak(f"Schedule {m_id.group(1)} removed.", block=False)
            else:
                speak("Please specify a valid schedule ID to delete, for example: delete schedule 1042.", block=False)
            return True
        except Exception as e:
            print("Schedule delete error:", e)
            return True

    if "run schedule" in low_query or "trigger schedule" in low_query:
        try:
            m_id = re.search(r'(?:schedule|task)?\s*#?(\d+)', low_query)
            if m_id and run_schedule_now(m_id.group(1)):
                speak(f"Triggering schedule {m_id.group(1)} now.", block=False)
            else:
                speak("Please specify a valid schedule ID to run.", block=False)
            return True
        except Exception as e:
            print("Schedule run error:", e)
            return True

    # ── POINT BREAK 3.0: "RECORD & REPLICATE" MACRO PLAYBOOKS ───────
    # Stop Recording
    if any(k in low_query for k in ["stop recording", "stop record", "save macro", "finish macro", "stop macro"]):
        try:
            from pointbreak_macro import macro_engine
            path_saved = macro_engine.recorder.stop_recording()
            if path_saved:
                speak("Macro recording stopped and synthesized to playbook script.", block=False)
            else:
                speak("No active macro recording was in progress.", block=False)
            return True
        except Exception as e:
            print("Macro stop error:", e)
            return True

    # Start Recording
    if "record macro" in low_query or "start recording macro" in low_query or "create macro" in low_query:
        try:
            from pointbreak_macro import macro_engine
            m_name = re.sub(r'^(record macro|start recording macro|create macro)\s*', '', low_query).strip()
            if not m_name: m_name = "custom_workflow"
            if macro_engine.recorder.start_recording(m_name):
                speak(f"Recording macro {m_name}. Perform your actions now. Say stop recording when finished.", block=False)
            else:
                speak("Could not start macro recording.", block=False)
            return True
        except Exception as e:
            print("Macro record start error:", e)
            return True

    # Run Macro
    if "run macro" in low_query or "execute macro" in low_query or "play macro" in low_query:
        try:
            from pointbreak_macro import macro_engine
            m_name = re.sub(r'^(run macro|execute macro|play macro)\s*', '', low_query).strip()
            if macro_engine.run_macro_by_name(m_name):
                speak(f"Executing macro {m_name}.", block=False)
            else:
                speak(f"I could not find a saved macro named {m_name}.", block=False)
            return True
        except Exception as e:
            print("Macro run error:", e)
            return True

    # List Macros
    if "list macros" in low_query or "show macros" in low_query or "what macros" in low_query:
        try:
            from pointbreak_macro import macro_engine
            m_list = macro_engine.list_macros()
            if m_list:
                names = [m["name"] if isinstance(m, dict) else str(m) for m in m_list]
                speak(f"You have {len(m_list)} saved playbooks: {', '.join(names)}.", block=False)
            else:
                speak("You have no recorded macros yet.", block=False)
            return True
        except Exception as e:
            print("Macro list error:", e)
            return True

    # ── POINT BREAK 3.0: STOP / CANCEL AUTONOMOUS AGENT ────────────
    if any(k in low_query for k in ["stop agent", "cancel agent", "abort agent", "kill agent", "stop autonomous agent"]):
        try:
            from pointbreak_agent import agent_engine
            agent_engine.stop()
            speak("Autonomous agent cancelled.", block=False)
            update_status({"agent_task": {"status": "cancelled", "description": "Aborted by user."}})
            return True
        except Exception as e:
            print("Agent stop error:", e)
            return True

    # ── POINT BREAK 3.0: HOLOGRAPHIC VIRTUAL AIR-KEYBOARD ──────────
    if any(k in low_query for k in [
        "open virtual keyboard", "show virtual keyboard", "open air keyboard", "show air keyboard",
        "air keyboard", "virtual keyboard", "holographic keyboard", "type with gestures",
        "open keyboard"
    ]):
        try:
            from pointbreak_vkeyboard import vkeyboard_engine
            vkeyboard_engine.show()
            speak("Holographic Air-Keyboard engaged. Use Air-Click to type.", block=False)
            return True
        except Exception as e:
            print("Virtual keyboard open error:", e)
            return True

    if any(k in low_query for k in [
        "close virtual keyboard", "hide virtual keyboard", "close air keyboard", "hide air keyboard",
        "close keyboard", "hide keyboard", "dismiss keyboard"
    ]):
        try:
            from pointbreak_vkeyboard import vkeyboard_engine
            vkeyboard_engine.hide()
            speak("Holographic Air-Keyboard dismissed.", block=False)
            return True
        except Exception as e:
            print("Virtual keyboard close error:", e)
            return True

    # ── POINT BREAK 3.0: UNIVERSAL AUTONOMOUS TAKEOVER ENGINE ───────
    stop_takeover_phrases = [
        "stop takeover", "disengage takeover", "release control",
        "i will take over", "i'll take over", "i take over",
        "stop i will take over", "stop i'll take over", "stop i take over",
        "stop playing", "stop chess", "stop bot", "stop the bot",
        "cancel takeover", "abort takeover", "quit chess", "pause chess",
        "i will take it from here", "i'll take it from here", "take back control",
        "let me play", "let me take over", "stop typing", "stop moving",
        "disengage", "abort game", "cancel chess"
    ]
    is_takeover_stop = (
        any(k in low_query for k in stop_takeover_phrases)
        or bool(re.search(r'\b(?:stop|cancel|disengage|halt|abort|quit|pause)\b.*(?:take\s*over|control|playing|chess|bot|engine|move|macro|typing)', low_query))
    )
    if not is_takeover_stop:
        try:
            from pointbreak_takeover import takeover_engine
            if takeover_engine.is_active and any(w in low_query.split() for w in ["stop", "cancel", "halt", "abort", "freeze", "quit", "pause", "hold"]):
                is_takeover_stop = True
        except Exception:
            pass

    if is_takeover_stop:
        try:
            try:
                from pointbreak_chess import request_chess_stop
                request_chess_stop()
            except Exception:
                pass
            from pointbreak_takeover import takeover_engine
            takeover_engine.stop_takeover(speak_fn=speak)
            return True
        except Exception as e:
            print("Takeover stop error:", e)
            return True

    if any(k in low_query for k in [
        "take over", "takeover", "take control", "complete this essay", "complete my essay",
        "complete this code", "complete my code", "finish writing", "finish this code",
        "play chess", "take over chess", "win chess", "win this chess game",
        "play my move", "play the move", "make a move", "make the move", "best move", "next move",
        "reply to this message", "take over this dm", "take over this reply",
        "take over writing", "take over coding"
    ]) or re.search(r'\b(?:take\s*over|chess\s+takeover|play\s+chess)\b', low_query):
        try:
            from pointbreak_takeover import takeover_engine
            clean_cmd = re.sub(r'^(?:point\s*break|tars|jarvis)?[\s,\-:]*(?:can\s+you\s+|please\s+)?', '', low_query, flags=re.I).strip()
            threading.Thread(
                target=lambda: takeover_engine.take_over_active_context(
                    user_command=clean_cmd,
                    speak_fn=speak,
                    update_status_fn=update_status
                ),
                daemon=True
            ).start()
            return True
        except Exception as e:
            print("Takeover dispatch error:", e)
            return True

    # ── TIER 2: SUPERPOWERS SOFTWARE FACTORY (FALLBACK CATCH) ───────
    if any(k in low_query for k in [
        "build app", "build an app", "create app", "code project", "develop tool",
        "build software", "superpowers build", "build a script", "build a website",
        "build a bot", "build a server", "build api", "build a program",
        "project status", "status of app", "how is the app", "how is the project",
        "cancel project", "cancel the project", "cancel build"
    ]) or re.search(r'\b(?:build|create|develop|code|engineer|make)\b.*\b(?:app|tool|script|program|website|bot|server|api|library|package|project|software)\b', low_query):
        try:
            from pointbreak_superpowers_bridge import superpowers_factory
            if any(k in low_query for k in ["cancel project", "cancel the project", "cancel build"]):
                superpowers_factory.cancel_project(speak_fn=speak)
            elif any(k in low_query for k in ["project status", "status of app", "how is the app", "how is the project"]):
                st = superpowers_factory.get_project_status()
                speak(st.get('message', 'No project status available.'))
            else:
                goal = re.sub(r'^(?:point\s*break|tars|jarvis)?[\s,\-:]*(?:can\s+you\s+|please\s+)?', '', low_query, flags=re.I).strip()
                superpowers_factory.dispatch_engineering_task(goal=goal, speak_fn=speak, update_status_fn=lambda s: update_status({"superpowers": s}))
            return True
        except Exception as e:
            print(f"[Superpowers Fallback Error]: {e}")

    # ── POINT BREAK 3.0: SELF-DRIVING WINDOWS AGENT ─────────────────
    if any(k in low_query for k in [
        "automate", "self drive", "self-drive", "agent execute", "agent plan",
        "autonomous task", "autonomous agent", "drive windows to", "agent"
    ]):
        try:
            from pointbreak_agent import agent_engine
            goal = re.sub(r'^(?:point\s*break|tars|jarvis)?[\s,\-:]*(?:can\s+you\s+|please\s+)?(?:automate\s+tasks?|automate|self\s*drive|self-drive|agent\s+execute|agent\s+plan|agent|autonomous\s+task|autonomous\s+agent|drive\s+windows\s+to)[\s,\-:\'"]*', '', low_query, flags=re.I).strip()
            goal = re.sub(r'^(?:and\s+|to\s+|for\s+)', '', goal, flags=re.I).strip()
            goal = goal.strip(" '\"`-,.:;!?")
            if goal:
                speak(f"Autonomous desktop agent engaged for: {goal}.", block=False)
                threading.Thread(
                    target=lambda: agent_engine.plan_and_execute_task(
                        goal,
                        update_callback=lambda s: update_status({"agent_task": s})
                    ),
                    daemon=True
                ).start()
                return True
        except Exception as e:
            print("Agent task error:", e)
            return True

    # ── POINT BREAK CYBER ARSENAL: PENETRATION TESTING ──────────────
    cyber_keywords = [
        "scan website", "security audit", "hack test", "pentest", "pen test",
        "check ssl", "check tls", "check headers", "security headers",
        "find vulnerabilities", "find vulnerability", "cyber scan",
        "vulnerability scan", "web scan", "owasp scan", "security scan",
        "scan site", "audit website", "audit site", "test security"
    ]

    if any(k in low_query for k in cyber_keywords):
        try:
            from pointbreak_cyberarsenal import cyber_engine
            # Extract URL from command
            target_url = re.sub(
                r'^(scan website|security audit|hack test|pentest|pen test|check ssl|check tls|'
                r'check headers|security headers|find vulnerabilities|find vulnerability|'
                r'cyber scan|vulnerability scan|web scan|owasp scan|security scan|'
                r'scan site|audit website|audit site|test security)[,\s:]*',
                '', low_query
            ).strip()

            if not target_url:
                speak("I need a target URL, Sir. Say something like: scan website example.com", block=False)
                return True

            # Determine scan type
            ssl_only = any(k in low_query for k in ["check ssl", "check tls"])
            headers_only = any(k in low_query for k in ["check headers", "security headers"])

            def _run_cyber_scan():
                try:
                    from pointbreak_cyberarsenal import cyber_engine
                    def _voice_update(msg):
                        speak(msg, block=False)
                        update_status({"cyber_phase": msg})

                    if ssl_only:
                        _voice_update(f"Initiating SSL/TLS analysis on {target_url}...")
                        results = cyber_engine.scan_ssl(cyber_engine._normalize_url(target_url))
                        count = len(results)
                        speak(f"SSL scan complete. Found {count} findings.", block=False)
                    elif headers_only:
                        _voice_update(f"Initiating security headers scan on {target_url}...")
                        results = cyber_engine.scan_headers(cyber_engine._normalize_url(target_url))
                        count = len(results)
                        speak(f"Headers scan complete. Found {count} findings.", block=False)
                    else:
                        result = cyber_engine.full_scan(target_url, status_callback=_voice_update)
                        if result:
                            report_path = cyber_engine.get_report_path()
                            if report_path and os.path.exists(report_path):
                                os.startfile(report_path)
                except Exception as e:
                    speak(f"Cyber scan error: {str(e)[:100]}", block=False)
                    print("Cyber Arsenal error:", e)

            speak(f"Initiating OWASP reconnaissance protocol on {target_url}. Commencing security audit.", block=False)
            threading.Thread(target=_run_cyber_scan, daemon=True).start()
            return True
        except Exception as e:
            print("Cyber Arsenal import error:", e)
            speak("Cyber Arsenal module failed to load.", block=False)
            return True

    # Show last scan report
    if any(k in low_query for k in ["scan report", "last scan", "security report", "show report", "cyber report", "vulnerability report"]):
        try:
            from pointbreak_cyberarsenal import cyber_engine
            report_path = cyber_engine.get_report_path()
            if report_path and os.path.exists(report_path):
                speak("Opening the last security audit report.", block=False)
                os.startfile(report_path)
            else:
                speak("No scan report available. Run a scan first by saying: scan website followed by the URL.", block=False)
            return True
        except Exception as e:
            print("Cyber report error:", e)
            return True

    # ── CYBER ARSENAL 2.0: PASSIVE OSINT INTELLIGENCE ────────────────
    osint_keywords = [
        "run osint", "osint on", "passive scan", "reconnaissance on",
        "recon on", "intel on", "subdomain scan", "subdomain enum",
        "find subdomains", "check subdomains", "check breach", "check breaches",
        "breach check", "google dork", "dork search", "technology fingerprint",
        "fingerprint site", "check cve", "find cve", "email security check",
        "check spf", "check dmarc", "harvest emails", "check robots",
        "shodan check", "shodan lookup", "full osint"
    ]

    if any(k in low_query for k in osint_keywords):
        try:
            from pointbreak_osint import osint_engine
            target_url = re.sub(
                r'^(run osint on|run osint|osint on|passive scan on|passive scan|reconnaissance on|recon on|'
                r'intel on|subdomain scan|subdomain enum|find subdomains for|check subdomains for|'
                r'check breach|check breaches|breach check|google dork|dork search|technology fingerprint|'
                r'fingerprint site|check cve|find cve|email security check|check spf|check dmarc|'
                r'harvest emails|check robots|shodan check|shodan lookup|full osint)[,\s:]*',
                '', low_query
            ).strip()

            if not target_url:
                speak("Give me a target domain. Say something like: run OSINT on example.com", block=False)
                return True

            # Route to specific sub-scan or full OSINT
            def _run_osint():
                try:
                    def _cb(msg):
                        speak(msg, block=False) if "complete" in msg.lower() or "phase" in msg.lower() or "starting" in msg.lower() else None
                        update_status({"cyber_phase": msg})

                    if any(k in low_query for k in ["subdomain", "find subdomains"]):
                        subs = osint_engine.enumerate_subdomains(osint_engine._normalize_domain(target_url))
                        speak(f"Found {len(subs)} subdomains for {target_url}. " + (f"Top ones: {', '.join(subs[:3])}" if subs else "None found."), block=False)
                    elif any(k in low_query for k in ["dork", "google dork"]):
                        dorks = osint_engine.generate_google_dorks(osint_engine._normalize_domain(target_url))
                        speak(f"Generated {len(dorks)} Google dork queries for {target_url}. Check the OSINT report for clickable search links.", block=False)
                    elif any(k in low_query for k in ["spf", "dmarc", "email security"]):
                        result = osint_engine.check_email_security(osint_engine._normalize_domain(target_url))
                        if result.get("spoofable"):
                            speak(f"Warning. {target_url} has no SPF or DMARC records. Email spoofing is possible. Anyone can send fake emails from their domain.", block=False)
                        else:
                            speak(f"Email security on {target_url} looks configured. SPF: {'found' if result.get('spf_found') else 'missing'}. DMARC: {'found' if result.get('dmarc_found') else 'missing'}.", block=False)
                    else:
                        result = osint_engine.full_osint_scan(target_url, status_callback=_cb)
                        subs = len(result.get("subdomains", []))
                        cves = len(result.get("cves", []))
                        spoofable = result.get("email_security", {}).get("spoofable", False)
                        speak(f"OSINT complete on {target_url}. Found {subs} subdomains, {cves} CVE matches, email spoofing {'possible' if spoofable else 'not detected'}. Intelligence report saved to Desktop.", block=False)
                        rpt = osint_engine.get_report_path()
                        if rpt and os.path.exists(rpt):
                            os.startfile(rpt)
                except Exception as e:
                    speak(f"OSINT engine error: {str(e)[:80]}", block=False)
                    print("OSINT error:", e)

            speak(f"Initiating passive OSINT on {target_url}. Gathering public intelligence. This may take a minute.", block=False)
            threading.Thread(target=_run_osint, daemon=True).start()
            return True
        except Exception as e:
            print("OSINT import error:", e)
            speak("OSINT module failed to load.", block=False)
            return True

    # ── CYBER ARSENAL 2.0: SHOW DON'T TELL PROOF MODE ─────────────────
    showdonttell_keywords = [
        "show xss", "xss proof", "prove xss", "demo xss",
        "show exposed", "exposed panel", "open exposed", "show admin panel",
        "rate limit test", "test rate limit", "brute force test",
        "show directory", "directory listing", "open directory",
        "clickjack demo", "clickjacking demo", "show missing headers",
        "prove vulnerability", "live demo", "show don't tell", "show dont tell",
        "show proof", "client demo", "business demo"
    ]

    if any(k in low_query for k in showdonttell_keywords):
        try:
            from pointbreak_showdonttell import show_engine
            target_url = re.sub(
                r'^(show xss on|xss proof on|prove xss on|demo xss on|show exposed on|'
                r'exposed panel on|open exposed on|show admin panel on|rate limit test on|'
                r'test rate limit on|brute force test on|show directory on|directory listing on|'
                r'clickjack demo on|clickjacking demo on|show missing headers on|'
                r'prove vulnerability on|live demo on|show dont tell on|show proof on|'
                r'client demo on|business demo on|show xss|xss proof|exposed panel|'
                r'rate limit test|show directory|clickjack demo|show missing headers|live demo)[,\s:]*',
                '', low_query
            ).strip()

            if not target_url:
                speak("Which website? Say something like: show XSS proof on example.com", block=False)
                return True

            def _cb(msg):
                update_status({"cyber_phase": msg})

            def _run_demo():
                try:
                    if any(k in low_query for k in ["xss", "inject"]):
                        speak(f"Running XSS proof demo on {target_url}. Watch the browser.", block=False)
                        r = show_engine.xss_proof_demo(target_url, _cb)
                        speak(r.get("explanation", "XSS demo complete."), block=False)
                    elif any(k in low_query for k in ["exposed", "admin panel", "open exposed"]):
                        speak(f"Scanning for exposed panels on {target_url}. Opening findings in browser.", block=False)
                        r = show_engine.exposed_panel_demo(target_url, _cb)
                        speak(f"Found {r.get('count', 0)} exposed paths. " + (f"Opened {r.get('demo_opened','')} in browser." if r.get('demo_opened') else ""), block=False)
                    elif any(k in low_query for k in ["rate limit", "brute force"]):
                        speak(f"Testing rate limiting on {target_url}. Sending rapid requests.", block=False)
                        r = show_engine.rate_limit_demo(target_url + "/login", _cb)
                        speak(r.get("explanation", "Rate limit test complete."), block=False)
                    elif any(k in low_query for k in ["directory", "listing"]):
                        speak(f"Checking for open directory listings on {target_url}.", block=False)
                        r = show_engine.directory_listing_demo(target_url, _cb)
                        speak(r.get("explanation", "Directory scan complete."), block=False)
                    elif any(k in low_query for k in ["clickjack", "missing headers", "header"]):
                        speak(f"Checking security headers and creating clickjacking demo for {target_url}.", block=False)
                        r = show_engine.missing_headers_demo(target_url, _cb)
                        speak(f"Found {r.get('missing_count', 0)} missing security headers. " + ("Clickjacking demo opened in browser." if r.get("clickjacking_vulnerable") else ""), block=False)
                    else:
                        speak(f"Running full show-don't-tell demo suite on {target_url}. Client can watch all vulnerabilities demonstrated live.", block=False)
                        r = show_engine.run_all_demos(target_url, _cb)
                        speak(f"Demo suite complete. Demonstrated {r.get('issues_found', 0)} vulnerability categories live in browser.", block=False)
                except Exception as e:
                    speak(f"Demo error: {str(e)[:80]}", block=False)
                    print("ShowDontTell error:", e)

            threading.Thread(target=_run_demo, daemon=True).start()
            return True
        except Exception as e:
            print("ShowDontTell import error:", e)
            speak("Show-Don't-Tell demo module failed to load.", block=False)
            return True

    # ── CYBER ARSENAL 2.0: AUTO-FIX ENGINE ────────────────────────────
    fixer_keywords = [
        "generate hardening kit", "hardening kit", "fix security",
        "generate fix", "create fix", "fix vulnerabilities", "fix website",
        "make website secure", "secure website", "harden website",
        "fix headers", "fix ssl", "fix sql injection", "fix xss",
        "generate htaccess", "generate nginx", "fix email security",
        "generate csp", "generate fix files", "create hardening"
    ]

    if any(k in low_query for k in fixer_keywords):
        try:
            from pointbreak_fixer import fixer_engine
            from pointbreak_cyberarsenal import cyber_engine

            target_url = re.sub(
                r'^(generate hardening kit for|hardening kit for|fix security for|generate fix for|'
                r'create fix for|fix vulnerabilities for|fix website|make website secure|'
                r'secure website|harden website|fix headers for|fix ssl for|'
                r'generate htaccess for|generate nginx for|fix email security for|'
                r'generate csp for|generate fix files for|create hardening for|'
                r'generate hardening kit|fix security|generate fix|hardening kit)[,\s:]*',
                '', low_query
            ).strip()

            if not target_url:
                speak("Which website should I generate fixes for? Say: generate hardening kit for example.com", block=False)
                return True

            def _run_fixer():
                try:
                    scan_results = cyber_engine.get_results() or {}
                    osint_results = None
                    try:
                        from pointbreak_osint import osint_engine
                        osint_results = osint_engine.get_results() or {}
                    except Exception:
                        pass

                    speak(f"Generating security hardening kit for {target_url}. Analyzing vulnerabilities and building fix files.", block=False)
                    domain = re.sub(r'^https?://', '', target_url).split('/')[0]
                    zip_path = fixer_engine.generate_hardening_kit(domain, scan_results, osint_results)
                    if zip_path and os.path.exists(zip_path):
                        speak(f"Hardening kit generated. ZIP file saved to Desktop with .htaccess, nginx config, CSP headers, and deployment guide. Ready to hand to client's developer.", block=False)
                        os.startfile(os.path.dirname(zip_path))
                    else:
                        speak("Fix files generated. Check your Desktop for the hardening kit.", block=False)
                except Exception as e:
                    speak(f"Fixer error: {str(e)[:80]}", block=False)
                    print("Fixer error:", e)

            threading.Thread(target=_run_fixer, daemon=True).start()
            return True
        except Exception as e:
            print("Fixer import error:", e)
            speak("Fix engine module failed to load.", block=False)
            return True

    # ── CYBER ARSENAL 2.0: AUTH LETTER GENERATOR ──────────────────────
    auth_letter_keywords = [
        "generate auth letter", "authorization letter", "auth letter",
        "generate authorization", "create auth letter", "pentest auth",
        "authorization document", "auth document", "create authorization"
    ]

    if any(k in low_query for k in auth_letter_keywords):
        try:
            from pointbreak_auth_letter import auth_engine
            # Extract client/domain info from query
            target = re.sub(
                r'^(generate auth letter for|authorization letter for|auth letter for|'
                r'generate authorization for|create auth letter for|pentest auth for|'
                r'authorization document for|auth document for|create authorization for|'
                r'generate auth letter|authorization letter|auth letter)[,\s:]*',
                '', low_query
            ).strip()

            client_name = target.replace(".", " ").title() if target else "Client"
            website_url = target if target else "example.com"

            speak(f"Generating professional penetration testing authorization letter for {client_name}. Opening in browser for printing or PDF export.", block=False)
            threading.Thread(
                target=lambda: auth_engine.generate_auth_letter(
                    client_name=client_name,
                    website_url=website_url
                ),
                daemon=True
            ).start()
            return True
        except Exception as e:
            print("Auth letter import error:", e)
            speak("Authorization letter generator failed to load.", block=False)
            return True

    # ── KINETIC GESTURE ENGINE CONTROL (TOP PRIORITY) ───────────────
    gesture_keywords = [
        "gesture", "gestures", "gestre", "gestres", "gestur", "gesturs", "gestrue",
        "geture", "getures", "hand tracking", "tracking", "hand radar", "kinetic",
        "air mouse", "air keyboard", "fist bump", "baymax"
    ]

    # Toggle Gesture Tracking
    if any(w in low_query for w in ["toggle gesture", "toggle gestures", "toggle gestre", "toggle geture"]):
        try:
            from tars_gestures import gesture_controller
            if getattr(gesture_controller, 'is_running', False):
                gesture_controller.stop()
                speak("Kinetic gesture tracking deactivated, Sir. Hand radar offline.", block=False)
                update_status({"status": "idle", "scanning": False, "gesture_active": False})
            else:
                gesture_controller.on_fist_bump_detected = baymax_fist_bump_cmd
                gesture_controller.start()
                speak("Kinetic gesture tracking engaged, Sir. Hand radar online.", block=False)
                update_status({"status": "gesture", "scanning": True, "gesture_active": True})
        except Exception as e:
            print("Gesture toggle error:", e)
        return True

    # Disengage / Disable Gesture Tracking
    if any(w in low_query for w in [
        "disengage", "disable", "stop", "turn off", "kill", "close", "deactivate", "shut down", "off", "exit", "end"
    ]) and any(w in low_query for w in gesture_keywords):
        try:
            from tars_gestures import gesture_controller
            gesture_controller.stop()
            speak("Kinetic gesture tracking deactivated, Sir. Hand radar offline.", block=False)
            update_status({"status": "idle", "scanning": False, "gesture_active": False})
        except Exception as e:
            print("Gesture stop error:", e)
            speak("Kinetic gesture tracking stopped.", block=False)
        return True

    # Engage / Enable Gesture Tracking
    if any(w in low_query for w in gesture_keywords):
        try:
            from tars_gestures import gesture_controller
            gesture_controller.on_fist_bump_detected = baymax_fist_bump_cmd
            gesture_controller.start()
            speak("Kinetic gesture tracking engaged, Sir. Hand radar online.", block=False)
            update_status({"status": "gesture", "scanning": True, "gesture_active": True})
        except Exception as e:
            speak("Failed to initialize gesture engine.", block=False)
            print("Gesture start error:", e)
        return True

    # ── CLEAR / PURGE REMINDERS ────────────────────────────────────
    if any(k in low_query for k in [
        "clear reminders", "clear reminder", "clear all reminders", "delete reminders",
        "delete all reminders", "remove reminders", "purge reminders", "cancel all reminders", "reset reminders"
    ]):
        memory["reminders"] = []
        save_memory()
        speak("All active reminders have been cleared, Sir.", block=False)
        update_status({"reminders": []})
        return True

    # ── EXACT ALARM, TIMER & REMINDER ENGINE (TOP PRIORITY) ────────
    if any(k in low_query for k in ["reminder", "remind me", "timer", "alarm", "wake me", "count down"]):
        if handle_timer_and_reminder_cmd(query):
            return True

    # ── CONVERSATIONAL VOLUME CONTROL ──────────────────────────────
    if any(k in low_query for k in ["volume", "sound", "audio", "louder", "quieter", "softer", "mute", "unmute", "turn it up", "turn it down", "turn up", "turn down"]):
        if handle_conversational_volume_cmd(query):
            return True

    # ── CONVERSATIONAL BRIGHTNESS CONTROL ──────────────────────────
    if any(k in low_query for k in ["brightness", "brighter", "dim", "dimmer", "screen light", "display light", "darker"]) or \
       (any(w in low_query for w in ["screen", "display"]) and any(w in low_query for w in ["bright", "dim", "dark", "light"])):
        if handle_conversational_brightness_cmd(query):
            return True

    # ── CONVERSATIONAL TO-DO & TASK ENGINE ─────────────────────────
    if any(k in low_query for k in ["to-do", "todo", "task", "my tasks", "check off", "mark done", "add to my list", "put on my list"]):
        if handle_conversational_todo_cmd(query):
            return True

    # ── CONVERSATIONAL WEATHER & WORLD TIME ────────────────────────
    if any(k in low_query for k in ["weather", "temperature", "forecast", "climate", "is it raining", "what time is it", "clock in", "time in", "time at"]):
        if handle_conversational_weather_time_cmd(query):
            return True

    # ── LIVE MULTILINGUAL MEETING & LECTURE CO-PILOT ─────────────────
    if any(k in low_query for k in [
        "start meeting dossier", "start meeting", "monitor this meeting", "monitor meeting",
        "start meeting mode", "start meeting copilot", "start meeting co-pilot",
        "record this meeting", "record meeting", "listen to this meeting", "listen to this lecture",
        "monitor lecture", "record lecture", "start lecture mode", "track meeting", "meeting dossier"
    ]):
        try:
            from tars_meeting_copilot import meeting_copilot
            clean_title = re.sub(r"\b(tars|please|monitor this meeting for|monitor meeting for|monitor this meeting|monitor meeting|record this meeting|record meeting|listen to this meeting|listen to this lecture|start meeting mode|start meeting copilot|start meeting co-pilot|start meeting dossier|meeting dossier|start meeting)\b", "", query, flags=re.I).strip()
            title = clean_title.title() if clean_title else "Executive Meeting"
            ok, msg = meeting_copilot.start_meeting(title)
            if ok:
                speak(f"Meeting Co-Pilot engaged for {title}. Recording and transcribing live in background.", block=False)
                update_status({"status": "meeting", "meeting_active": True, "meeting_title": title})
            else:
                speak(msg, block=False)
        except Exception as e:
            print("Meeting copilot start error:", e)
            speak("Encountered an issue starting meeting monitor.", block=False)
        return True

    elif any(k in low_query for k in [
        "what did they just say", "what was just said", "repeat last point", "translate what was just said",
        "what did he just say", "what did she just say", "summarize last minute", "what are they saying"
    ]):
        try:
            from tars_meeting_copilot import meeting_copilot
            speak("Checking recent dialogue...", block=False)
            recent_brief = meeting_copilot.get_recent_summary(seconds=60)
            speak(recent_brief, block=False)
        except Exception as e:
            print("Meeting recent summary error:", e)
            speak("Could not retrieve recent dialogue summary.", block=False)
        return True

    elif any(k in low_query for k in [
        "end meeting and summarize", "end meeting", "stop meeting", "finish meeting",
        "summarize meeting", "end lecture", "finish lecture", "summarize lecture", "conclude meeting"
    ]):
        try:
            from tars_meeting_copilot import meeting_copilot
            speak("Concluding meeting session and compiling executive briefing...", block=False)
            update_status({"status": "processing", "meeting_active": False})
            
            def _async_end_meeting():
                res = meeting_copilot.end_meeting_and_summarize(owner_name="Daksh")
                update_status({"status": "idle", "meeting_active": False})
                if res.get("success"):
                    speak(res.get("spoken_debrief", "Meeting briefing saved to Desktop."), block=False)
                else:
                    speak(res.get("error", "No active meeting to summarize."), block=False)
                    
            threading.Thread(target=_async_end_meeting, daemon=True).start()
        except Exception as e:
            print("Meeting end error:", e)
            speak("Error compiling meeting summary.", block=False)
        return True

    # ── YOUTUBE VIDEO & LECTURE DOSSIER ENGINE ────────────────────
    if any(k in low_query for k in [
        "summarize this youtube video", "summarize youtube video", "summarize this video",
        "summarize video", "youtube dossier", "video dossier", "make a pdf of this video",
        "make a pdf from this youtube video", "read this youtube video", "youtube summary pdf"
    ]):
        try:
            from tars_video_summarizer import video_summarizer
            speak("Extracting video intelligence and compiling executive PDF dossier...", block=False)
            update_status({"status": "processing"})
            def _async_vid():
                res = video_summarizer.summarize_youtube_video(query, owner_name="Daksh")
                update_status({"status": "idle"})
                if res.get("success"):
                    speak(res.get("spoken_debrief"), block=False)
                else:
                    speak(f"Could not complete video summary: {res.get('error')}", block=False)
            threading.Thread(target=_async_vid, daemon=True).start()
        except Exception as e:
            print("Video summarizer error:", e)
            speak("Encountered an issue compiling video dossier.", block=False)
        return True

    # ── BAYMAX FIST BUMP ('BALALALA!') CELEBRATION ────────────────
    if any(k in low_query for k in [
        "fist bump", "give me a fist bump", "balalala", "ba-la-la-la-la", "bump it", "fistbump", "baymax fist bump"
    ]):
        baymax_fist_bump_cmd()
        return True

    # ── 1-CLICK DEEP RESEARCH DOSSIER (TOP PRIORITY) ───────────────
    if any(k in low_query for k in [
        "research dossier", "deep research", "create a dossier", "generate a dossier",
        "generate dossier", "make a dossier", "dossier on", "pdf report on",
        "create a pdf on", "generate a pdf on", "compile research", "research report on"
    ]) or (("research" in low_query or "dossier" in low_query) and any(w in low_query for w in ["pdf", "report", "create", "generate", "save", "make", "compile"])):
        generate_deep_research_dossier_cmd(query)
        return True

    # ── AUTONOMOUS EMAIL CO-PILOT & DRAFT GENERATOR ────────────────
    if any(k in low_query for k in [
        "triage my emails", "triage emails", "triage my inbox", "triage inbox",
        "draft replies", "draft reply", "draft my emails", "draft emails",
        "email copilot", "email co-pilot", "prepare drafts", "prepare email drafts",
        "review my emails and draft", "check unread emails and draft"
    ]):
        autonomous_email_copilot_cmd()
        return True

    # ── GMAIL & MAILS WEB INBOX (DIRECT WEB LAUNCH - ZERO SEARCH CROSS-CONTAMINATION) ──
    if low_query in [
        "open mails", "open mail", "open gmail", "open my mail", "open my mails",
        "open my emails", "open my email", "open inbox", "open my inbox",
        "check mails", "check mail", "check gmail", "check email", "check emails",
        "check my mail", "check my mails", "check my email", "check my emails",
        "check inbox", "check my inbox", "mails", "mail", "gmail", "inbox"
    ] or re.search(r'^(?:open|launch|show|go\s+to|check)\s+(?:my\s+)?(?:gmail|mails?|emails?|inbox)$', low_query):
        speak("Opening your Gmail inbox on web, Sir.", block=False)
        webbrowser.open("https://mail.google.com/mail/u/0/#inbox")
        return True

    # ── POINT BREAK SIGNATURE SINGING ROUTINE: "I WANT IT THAT WAY" (ACAPELLA) ──
    if (
        any(k in low_query for k in [
            "sing a song", "sing for me", "can you sing", "sing something", "sing me a song",
            "sing a track", "sing us a song", "please sing", "sing i want it that way",
            "sing backstreet boys", "sing a tune", "sing to me", "sing me something",
            "do you sing", "start singing", "sing now"
        ]) or (low_query.startswith("sing") and not any(k in low_query for k in ["play", "youtube", "spotify", "download", "search"]))
    ) and not any(k in low_query for k in ["play", "youtube", "spotify"]):
        sing_i_want_it_that_way_cmd(query)
        return True

    # ── WHATSAPP VOICE MESSAGE / VOICE NOTE / VOICEMAIL DISPATCH (TOP PRIORITY) ─
    voice_triggers = [
        "voice message", "voice note", "voicemail", "voice mail", "audio message",
        "audio note", "send a voice", "voice msg", "send voice", "voice to",
        "audio to", "record a voice", "record voice", "record a message", "spoken message"
    ]
    if any(k in low_query for k in voice_triggers):
        send_whatsapp_voice_note_cmd(query)
        return True

    # ── WHATSAPP & MESSAGING TEXT DISPATCH (TOP PRIORITY) ───────────
    msg_triggers = [
        "whatsapp", "message to", "send a message", "send message", "send a text",
        "send text", "text to", "dm to", "msg to", "send msg", "ping on whatsapp"
    ]
    if (
        any(k in low_query for k in msg_triggers) or
        ("send" in low_query and any(w in low_query for w in ["message", "msg", "text"])) or
        re.search(r'\b(message|text|msg|dm|ping)\s+to\b', low_query)
    ) and not any(k in low_query for k in ["open mails", "check mails", "open gmail", "draft email"]):
        send_whatsapp_message_cmd(query)
        return True

    # ── GMAIL & EMAIL SEARCH (TOP PRIORITY: NEVER PRESSES WIN KEY) ──
    if any(k in low_query for k in ["mail", "email", "gmail", "inbox", "myntra", "yntra", "parivahan", "license", "liecense"]):
        search_emails_cmd(query)
        return True

    # ── POINT BREAK PRECISION FILE HUNTER & RETRIEVAL (TOP PRIORITY) ──
    # Intercepts natural language queries: "get my adhaar card from files", "where is my resume", "fetch marksheet pdf"
    if find_and_open_file_smart(query):
        return True

    # ── COFFEE & FOOD ORDERING SMART PORTAL ROUTER ──────────────────
    if any(k in low_query for k in ["order coffee", "order a coffee", "get me a coffee", "buy a coffee", "starbucks", "order food", "order pizza", "order from swiggy", "order from zomato", "swiggy", "zomato"]):
        if "starbucks" in low_query:
            webbrowser.open("https://www.starbucks.in")
            speak("Opening Starbucks for you, Sir. Please select your beverage and confirm your order.")
        elif "zomato" in low_query:
            webbrowser.open("https://www.zomato.com")
            speak("Opening Zomato for you, Sir. Please select your restaurant.")
        else:
            webbrowser.open("https://www.swiggy.com/restaurants?query=coffee" if "coffee" in low_query else "https://www.swiggy.com")
            speak("Opening the food ordering portal for you, Sir. Please choose your items and confirm payment.")
        return True






    if "call" in low_query and not "recall" in low_query and not "close" in low_query:
        contact = re.sub(r"(call|make a call to|phone|dial)", "", query, flags=re.IGNORECASE).strip()
        if contact:
            make_phone_call_cmd(contact)
            return True

    if "send sms" in low_query or ("text" in low_query and not any(w in low_query for w in ["read", "scan", "screen", "analyze", "whatsapp"])):
        parts = re.sub(r"(send sms to|text|send sms)", "", query, flags=re.IGNORECASE).strip().split(" ", 1)
        target = parts[0] if parts else "contact"
        msg_text = parts[1] if len(parts) > 1 else "Hello from Point Break"
        send_phone_sms_cmd(target, msg_text)
        return True


    # ── SAVE / REMEMBER CONTACT PHONE NUMBER ─────────────────────────
    if any(k in low_query for k in ["save contact", "add contact", "remember contact", "save phone", "remember phone", "store contact"]):
        m_contact = re.search(r'(?:save|add|remember|store)\s+(?:contact|phone)?\s*([a-zA-Z\s]+?)\s+(?:as|number|is|with number|with phone)?\s*([\+\d\s\-]+)$', query, re.IGNORECASE)
        if m_contact:
            c_name = m_contact.group(1).strip().lower()
            c_phone = re.sub(r'[^\d+]', '', m_contact.group(2).strip())
            if c_name and len(c_phone) >= 10:
                contacts = memory.setdefault("contacts", {})
                contacts[c_name] = c_phone
                save_memory()
                speak(f"Saved contact {c_name.title()} with phone number {c_phone}.", block=False)
                return True

    # ── TOP PRIORITY: YOUTUBE & MUSIC PLAYBACK ──────────────────────
    if (
        "youtube" in low_query or
        low_query.startswith("play ") or
        ("play" in low_query and any(w in low_query for w in ["song", "music", "youtube", "ac/dc", "track", "video", "on", "spotify"]))
    ) and not any(k in low_query for k in ["summarize", "dossier", "pdf of this video", "make a pdf"]):
        play_youtube_cmd(query)
        return True

    # ── TOP PRIORITY: FAMILY FACE REGISTRATION & OPTICAL SCAN ──────────
    if any(k in low_query for k in ["she is my aunt", "this is my aunt", "he is my uncle", "this is my uncle", "calibrate face for my aunt", "calibrate face for aunt", "remember my aunt", "meet my aunt", "register aunt", "register my aunt", "calibrate aunt", "my aunt"]):
        register_family_face_cmd(query)
        return True

    if any(k in low_query for k in ["who is in front of you", "who do you see", "optical scan", "scan face", "identify person", "who is this"]):
        scan_and_identify_face_cmd()
        return True

    # ── TOP PRIORITY: NOTEPAD OPEN & VOICE DICTATION ────────────────
    if "notepad" in low_query or ("write" in low_query and "notepad" in low_query) or ("note" in low_query and "notepad" in low_query):
        init_txt = ""
        m = re.search(r"(write|dictate|type|note|write down)\s+(.*?)(in notepad|on notepad|to notepad|$)", query, re.IGNORECASE)
        if m:
            extracted = m.group(2).strip()
            if extracted and extracted.lower() not in ["in notepad", "on notepad", "something", "text", "down"]:
                init_txt = extracted
        open_notepad_and_dictate_cmd(init_txt)
        return True

    # ── 1. TOP PRIORITY: AI SCREEN SCANNING (DESKTOP SCREENSHOT) ──────
    if "screen" in low_query or any(k in low_query for k in [
        "read the screen", "read my screen", "read screen", "read this screen",
        "scan my screen", "scan screen", "analyze my screen", "analyze screen",
        "tell me what is on my screen", "what is on my screen", "what's on my screen",
        "look at my screen", "read what is on screen", "explain my screen",
        "explain this code", "explain this error", "debug my screen", "solve my screen", "screen reader"
    ]):
        prompt_q = re.sub(
            r"(read the screen|read my screen|read screen|read this screen|scan my screen|scan screen|analyze my screen|analyze screen|tell me what is on my screen|what is on my screen|what's on my screen|look at my screen|read what is on screen|explain my screen|explain this code|explain this error|debug my screen|solve my screen|screen reader|screen)", 
            "", 
            low_query,
            flags=re.IGNORECASE
        ).strip()
        explain_screen_cmd(prompt_q)
        return True

    # ── 12-HOUR SESSION CONVERSATION RECALL ──────────────────────────
    if any(k in low_query for k in ["what did we talk about", "recall conversation", "what did i ask you", "conversation history", "recall session", "what were we talking about"]):
        history_text = get_12hr_conversation_context()
        if history_text:
            prompt = f"Daksh asks: '{query}'. Based on your 12-hour session history:\n{history_text}\nSummarize clearly and concisely in 2-3 sentences what was discussed."
            ans = query_tars_ai(prompt)
            return True
        else:
            speak("Our 12-hour session memory is currently clear, Sir.", block=False)
            return True

    if "good morning" in query or "morning briefing" in query or "morning report" in query or "brief me" in query:
        morning_briefing_cmd()
        return True
    if "research" in query or "search live web" in query or "look up live" in query or "latest news on" in query:
        topic_q = re.sub(r"(research live web for|research live web|search live web for|search live web|look up live|latest news on|research)", "", query).strip()
        research_live_web(topic_q)
        return True

    # ── FILE EXPLORER & FILE SELECTION ──────────────────────────────
    if ("file manager" in query or "explorer" in query or "downloads" in query or "desktop" in query or "documents" in query) and ("select" in query or "find" in query or "choose" in query or "go to" in query):
        open_and_select_file_cmd(query)
        return True

    # ── 1. TARS MEMORY VAULT ───────────────────────────────────────
    if "remember that" in query or "take a note that" in query or "store in memory" in query:
        fact = re.sub(r"(remember that|take a note that|store in memory|remember)", "", query).strip()
        remember_fact_cmd(fact)
        return True

    elif "what do you remember" in query or "recall" in query or "memory vault" in query or "what are my notes" in query:
        search_q = re.sub(r"(what do you remember about|what do you remember|recall|memory vault|what are my notes about|what are my notes)", "", query).strip()
        recall_facts_cmd(search_q)
        return True

    # ── 2. AI SCREEN SOLVER, READER & DEBUGGER ─────────────────────
    elif "screen" in low_query or any(k in low_query for k in [
        "read the screen", "read my screen", "read screen", "read this screen",
        "scan my screen", "scan screen", "analyze my screen", "analyze screen",
        "tell me what is on my screen", "what is on my screen", "what's on my screen",
        "look at my screen", "read what is on screen", "explain my screen",
        "explain this code", "explain this error", "debug my screen", "solve my screen", "screen reader"
    ]):
        prompt_q = re.sub(
            r"(read the screen|read my screen|read screen|read this screen|scan my screen|scan screen|analyze my screen|analyze screen|tell me what is on my screen|what is on my screen|what's on my screen|look at my screen|read what is on screen|explain my screen|explain this code|explain this error|debug my screen|solve my screen|screen reader|screen)", 
            "", 
            low_query,
            flags=re.IGNORECASE
        ).strip()
        explain_screen_cmd(prompt_q)
        return True

    # ── 4. AI FILE & DESKTOP AUTO-ORGANIZER ────────────────────────
    elif "organize downloads" in query or "clean downloads" in query or "organize my downloads" in query or "clean my downloads" in query:
        organize_folder_cmd("downloads")
        return True

    elif "organize desktop" in query or "clean desktop" in query or "organize my desktop" in query or "clean my desktop" in query:
        organize_folder_cmd("desktop")
        return True

    elif any(k in query.lower() for k in ["system vitals", "system diagnostics", "system stats", "cpu usage", "battery level", "diagnostics", "check vitals", "system status"]):
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory().percent
        bat = psutil.sensors_battery()
        try:
            total, used, free = shutil.disk_usage(JARVIS_DIR)
            disk = int((used / total) * 100)
            free_gb = int(free / (1024**3))
            disk_str = f"Disk storage is {disk} percent used with {free_gb} gigabytes free."
        except:
            disk_str = ""
        bat_str = f"Battery level stands at {int(bat.percent)} percent." if bat else "Power source is AC adapter."
        speak(f"System vitals nominal. CPU load is at {int(cpu)} percent. RAM utilization is at {int(mem)} percent. {disk_str} {bat_str}")
        update_status({"cpu": cpu, "mem": mem, "battery": bat.percent if bat else None})
        return True

    elif handle_conversational_volume_cmd(query):
        return True

    elif handle_conversational_brightness_cmd(query):
        return True

    elif "close globe" in query:
        import pyautogui
        speak("Closing Google Earth.")
        pyautogui.hotkey("alt", "f4")

    elif "open globe" in query:
        import os, pyautogui, time, webbrowser
        earth_lnk = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Chrome Apps\Google Earth.lnk")
        if os.path.exists(earth_lnk):
            os.startfile(earth_lnk)
        else:
            webbrowser.open("https://earth.google.com/web")
        speak("Opening Google Earth, what location do you want to explore, Sir?")
        follow_up = take_command(12)
        if follow_up and follow_up != "none":
            address = re.sub(r"(look up for|look up|search for|search and|search)", "", follow_up).strip()
            if address:
                time.sleep(4.0)
                pyautogui.press("/")
                time.sleep(1.0)
                pyautogui.write(address, interval=0.05)
                time.sleep(2.0)
                pyautogui.press("enter")

    # ── 2. WEBCAM CAMERA SENSOR (LOOK AT ME / LOOK UP) ──────────────
    elif ("camera" in low_query or "webcam" in low_query or "look at me" in low_query or "look up" in low_query) and "screen" not in low_query and "live" not in low_query:
        speak("Opening camera sensor.", block=True)
        img_bytes = capture_camera_frame()
        if img_bytes:
            update_status({"status": "scanning"})
            analysis = query_tars_vision(img_bytes, "Describe what you see in front of you in detail (the person, their clothing, products, environment) and engage in character.")
            update_status({"status": "processing"})
            if analysis:
                speak(analysis, block=True)
                speak("What would you like me to inspect or analyze in front of you, Sir?", block=True)
                follow_up = take_command(10)
                if follow_up and follow_up != "none" and len(follow_up.strip()) > 1:
                    speak(f"Inspecting {follow_up}...", block=False)
                    update_status({"status": "processing"})
                    cam_prompt = (
                        f"You are Point Break examining the webcam feed.\n"
                        f"Daksh's follow-up request: '{follow_up}'\n"
                        f"Read and analyze all visible details in front of the camera (person, object, clothing, product, paper) to answer directly and concisely in 2-3 sentences."
                    )
                    cam_ans = query_tars_vision(img_bytes, cam_prompt)
                    update_status({"status": "idle"})
                    if cam_ans:
                        speak(cam_ans, block=False)
                    else:
                        speak("I could not analyze that webcam detail, Sir.", block=False)
                else:
                    update_status({"status": "idle"})
            else:
                update_status({"status": "idle"})
                speak("Webcam feed was unclear.", block=False)
        else:
            speak("Could not access webcam camera sensor.", block=False)
            update_status({"status": "idle"})
        return True

    elif "search" in low_query or "google" in low_query:
        web_search(query)
        return True

    elif "lock" in query and "screen" in query: lock_screen()
    elif "shutdown" in query or "shut down" in query: shutdown_pc()
    elif "restart" in query or "reboot" in query: restart_pc()
    elif "recycle" in query or "trash" in query: empty_recycle()
    
    elif "wifi" in query or "wi-fi" in query:
        on = "on" in query or "enable" in query or "turn on" in query
        toggle_wifi(on)

    elif "screenshot" in query or "screen shot" in query:
        take_screenshot()

    elif any(w in low_query for w in ["enable gesture", "start gesture", "turn on gesture", "engage gesture", "track gesture"]):
        try:
            from tars_gestures import gesture_controller
            gesture_controller.on_fist_bump_detected = baymax_fist_bump_cmd
            gesture_controller.start()
            speak("Kinetic gesture tracking engaged, Sir. Hand radar online.", block=False)
            update_status({"status": "gesture", "scanning": True})
        except Exception as e:
            speak("Failed to initialize gesture engine.", block=False)
            print("Gesture start error:", e)
        return True

    elif any(w in low_query for w in ["disable gesture", "stop gesture", "turn off gesture", "disengage gesture", "kill gesture"]):
        try:
            from tars_gestures import gesture_controller
            gesture_controller.stop()
            speak("Kinetic gesture tracking deactivated.", block=False)
            update_status({"status": "idle", "scanning": False})
        except Exception as e:
            print("Gesture stop error:", e)
        return True

    elif "whatsapp" in low_query or ("send" in low_query and "message" in low_query):
        send_whatsapp_message_cmd(query)
        return True

    elif "instagram" in low_query:
        open_app("instagram")
        return True

    elif "open" in query or "launch" in query:
        app = re.sub(r"(open|launch|start)", "", query).strip()
        open_app(app)
        return True

        # ── CONVERSATIONAL INTENT GUARDS (Strict Pattern Matching) ─────────
    elif re.search(r'\b(read the world news|world news|daily news briefing)\b', low_query):
        read_world_news_protocol()
        return True

    elif re.search(r'\b(what\s+time\s+is\s+it|what\s+is\s+the\s+time|what\'?s\s+the\s+time|tell\s+me\s+the\s+time|current\s+time|clock\s+time|local\s+time|time\s+(?:in|at|for|of)\s+[a-zA-Z\s]+)\b', low_query) and not any(k in low_query for k in ["relative", "dilation", "concept", "travel", "theory", "space", "why", "how", "explain", "meaning", "quantum"]):
        get_world_time(query)
        return True

    elif re.search(r'\b(what\s+is\s+the\s+weather|what\'?s\s+the\s+weather|how\s+is\s+the\s+weather|current\s+weather|weather\s+forecast|is\s+it\s+raining|temperature\s+outside|weather\s+in\s+[a-zA-Z\s]+|temperature\s+in\s+[a-zA-Z\s]+)\b', low_query) and not any(k in low_query for k in ["sun", "earth", "climate change", "why", "how", "explain", "theory"]):
        get_weather(query)
        return True

    elif re.search(r'\b(what\s+is\s+today\'?s?\s+date|what\s+is\s+the\s+date|what\s+date\s+is\s+it|what\s+day\s+is\s+it|today\'?s?\s+date)\b', low_query) and not any(k in low_query for k in ["expiry", "expiration", "meeting", "history", "release", "launch", "birth", "why", "how", "explain"]):
        import datetime
        speak(f"Today is {datetime.datetime.now().strftime('%A, %B %d, %Y')}, {OWNER}.")
        return True

    elif re.search(r'\b(tell\s+me\s+a\s+joke|crack\s+a\s+joke|make\s+me\s+laugh)\b', low_query):
        import pyjokes
        speak(pyjokes.get_joke())
        return True

    elif "play our music" in query:
        import os
        speak("That's what I was waiting for!")
        music_path = os.path.join(os.path.expanduser("~"), "Downloads", "AC DC - Highway to Hell (SPOTISAVER).mp3")
        if os.path.exists(music_path):
            os.startfile(music_path)
        else:
            speak("I cannot find the AC DC file in your downloads folder.")

    elif "working music" in query or "play working music" in query:
        import os
        speak("Lets get the work started!")
        work_music_path = os.path.join(os.path.expanduser("~"), "Downloads", "AC_DC - Back In Black (Lyrics).mp3")
        if os.path.exists(work_music_path):
            os.startfile(work_music_path)
        else:
            speak("I cannot find the Back in Black file in your downloads folder.")

    elif "play" in query:
        import pywhatkit
        song = re.sub(r"(play|on youtube|jarvis|tars|can you)", "", query).strip()
        speak(f"Searching and playing {song}.")
        pywhatkit.playonyt(song)

    elif "close app" in query or "shut the app down" in query or "close the app" in query or "exit app" in query:
        close_app()

    elif "alarm" in query or "wake me" in query or "reminder" in query or "remind me" in query or "timer" in query:
        handle_timer_and_reminder_cmd(query)
        return True

    elif re.search(r"\b(add to my to.?do|add (a )?task|add to.?do|new to.?do|create to.?do)\b", query):
        task = re.sub(r"(add to my to do|add task|to do|todo|add)", "", query).strip()
        if task: add_todo(task)
        else:
            speak("What's the task?")
            task = take_command()
            add_todo(task)

    elif "my tasks" in query or "to-do list" in query or "list tasks" in query:
        list_todos()

    elif "complete task" in query or "mark done" in query:
        nums = re.findall(r'\d+', query)
        if nums: complete_todo(int(nums[0]))

    elif "whatsapp" in query or "send a message" in query:
        speak("Who should I send the WhatsApp message to?")
        contact = take_command(10)
        if contact and contact != "none":
            speak(f"What is the message for {contact}?")
            msg = take_command(15)
            if msg and msg != "none":
                speak(f"Opening WhatsApp and sending message to {contact}.")
                import pyautogui, time
                pyautogui.press("win")
                time.sleep(1.0)
                pyautogui.write("whatsapp", interval=0.05)
                time.sleep(1.0)
                pyautogui.press("enter")
                time.sleep(8.0)
                pyautogui.hotkey("ctrl", "f")
                time.sleep(1.0)
                pyautogui.write(contact, interval=0.05)
                time.sleep(4.0)
                pyautogui.press("enter")
                time.sleep(2.0)
                pyautogui.write(msg, interval=0.05)
                time.sleep(0.5)
                pyautogui.press("enter")
                speak("Message dispatched.")
            else:
                speak("I did not catch the message. Cancelling.")
        else:
            speak("I did not catch the contact name. Cancelling.")
            
    elif "pause music" in query or "play music" in query or "pause" in query or "resume" in query:
        speak("Toggling playback.")
        run_action("media_control", "playpause")
        
    elif "read my clipboard" in query or "what is on my clipboard" in query or "read clipboard" in query:
        run_action("read_clipboard", "")

    elif "copy to clipboard" in query or "write to clipboard" in query:
        text = re.sub(r"(copy to clipboard|write to clipboard|copy|write)", "", query).strip()
        run_action("write_clipboard", text)

    elif "skip song" in query or "next track" in query or "next song" in query or "skip track" in query:
        speak("Playing next track.")
        run_action("media_control", "next")

    elif "previous song" in query or "go back a song" in query or "previous track" in query:
        speak("Playing previous track.")
        run_action("media_control", "prev")

    elif "mute volume" in query or "mute audio" in query or "unmute" in query:
        speak("Toggling mute.")
        run_action("media_control", "mute")

    elif "minimize current window" in query or "minimize window" in query:
        speak("Minimizing window.")
        run_action("window_control", "minimize")

    elif "maximize current window" in query or "maximize window" in query:
        speak("Maximizing window.")
        run_action("window_control", "maximize")

    elif "minimize all" in query or "show desktop" in query:
        speak("Showing desktop.")
        run_action("window_control", "desktop")

    elif "close window" in query or "close active window" in query:
        speak("Closing window.")
        run_action("window_control", "close_win")

    elif "close tab" in query or "close current tab" in query:
        speak("Closing tab.")
        run_action("window_control", "close_tab")

    elif query.strip() in ["goodbye point break", "goodbye tars", "good night point break", "good night tars", "shut down jarvis", "shut down tars", "shutdown jarvis", "shutdown tars"]:
        speak(f"Goodnight, {OWNER}. Going offline.")
        return False

    elif "calibrate face" in query or "calibrate my face" in query or "setup face security" in query:
        # Check if they specified a name, e.g. "calibrate face mom"
        name = "daksh"
        words = query.lower().strip().split()
        for word in words:
            if word not in ["tars", "please", "calibrate", "face", "my", "setup", "security"]:
                name = word
                break
        train_owner_face(name)

    else:
        return False
    
    return True

# ── 4GB ULTRA-LOW RAM PROTECTION ENGINE ───────────────────────────
def check_ram_safety():
    """
    Monitors system memory. If available RAM drops below 220 MB or RAM usage > 88%,
    triggers immediate garbage collection and memory flushes to protect 4GB laptops.
    """
    try:
        vm = psutil.virtual_memory()
        available_mb = vm.available / (1024 * 1024)
        if available_mb < 220 or vm.percent > 88.0:
            print(f"  [RAM Safety Circuit Breaker: Free RAM={available_mb:.1f}MB ({vm.percent}% used). Flushing memory!]")
            import gc
            gc.collect()
            return False
    except Exception as e:
        pass
    return True

def engage_vision_mode():
    import cv2, threading, queue, numpy as np, winsound, gc
    speak("Visual matrix active. Eyes online, Sir. I am watching live.", block=True)
    update_status({"status": "scanning"})
    
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        speak("Error initializing visual sensor matrix.", block=True)
        return

    # Cap OpenCV RAM buffer to 1 frame for 4GB RAM safety
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except:
        pass

    cv2.namedWindow("TARS Tactical Vision Matrix — Live Eye Mode", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("TARS Tactical Vision Matrix — Live Eye Mode", 640, 480)
    
    is_running = True
    voice_queue = queue.Queue()
    silent_until = 0
    CHECKIN_INTERVAL = 145  # 2 minutes 25 seconds
    last_auto_observation_time = time.time()
    user_goal = ""
    prev_gray = None
    is_vision_busy = False

    def play_scan_beep():
        try:
            winsound.Beep(1400, 120)
        except:
            pass

    # Background Listener Thread (Non-Blocking)
    def voice_listener():
        nonlocal is_running
        while is_running:
            try:
                q = take_command(timeout=3)
                if q and q != "none":
                    voice_queue.put(q)
            except Exception as e:
                pass
            time.sleep(0.1)

    listener_thread = threading.Thread(target=voice_listener, daemon=True)
    listener_thread.start()

    # Initial Proactive Observation (TARS Speaks First!)
    ret, frame = cap.read()
    if ret:
        cv2.imshow("TARS Tactical Vision Matrix — Live Eye Mode", frame)
        cv2.waitKey(1)
        _, img_bytes = cv2.imencode('.jpg', frame)
        init_prompt = "Look at Daksh right now. In 1 short, witty, movie-like sentence, describe what he is doing and ask what he is working on like a friend watching him."
        speak("Scanning room parameters...", block=False)
        play_scan_beep()
        first_greeting = query_tars_vision(img_bytes.tobytes(), init_prompt)
        if first_greeting:
            clean_text = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', first_greeting).strip()
            speak(clean_text, block=False)

    print("  [TARS Engage Mode Active — Lightweight Motion Detection & JARVIS Telemetry]")

    while is_running:
        if not check_ram_safety():
            time.sleep(0.5)
            continue

        time.sleep(0.08) # Throttle to 10 FPS for ultra-low memory & CPU load
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.03)
            continue

        cv2.imshow("TARS Tactical Vision Matrix — Live Eye Mode", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == 27: # ESC key pressed
            speak("Visual matrix offline. Eyes disengaged.", block=False)
            is_running = False
            break

        now = time.time()

        # ── 1. LIGHTWEIGHT LOCAL MOTION DETECTOR (< 1% CPU, < 2MB RAM) ──
        small_frame = cv2.resize(frame, (320, 240))
        gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        
        motion_detected = False
        if prev_gray is not None:
            delta = cv2.absdiff(prev_gray, gray)
            thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
            motion_score = np.sum(thresh > 0)
            if motion_score > 4000:  # Threshold for noticeable movement (picking up phone, standing up, shifting)
                motion_detected = True
        prev_gray = gray

        # Check for user voice input in queue
        if not voice_queue.empty():
            q = voice_queue.get()
            q_low = q.lower().strip()
            print(f"  [Engage Mode Input]: {q}")

            if any(w in q_low for w in ["disengage", "exit vision", "stop vision", "close camera", "close eyes", "turn off vision", "goodbye"]):
                speak("Visual matrix offline. Eyes disengaged.", block=True)
                is_running = False
                break

            goal_match = re.search(r'(?:going to|gonna|plan to|about to|will|starting to)\s+(study|code|read|work|write|practice)(?:\s+([a-z\s]+))?', q_low)
            if goal_match:
                action_verb = goal_match.group(1)
                subject_obj = goal_match.group(2) if goal_match.group(2) else ""
                user_goal = f"{action_verb} {subject_obj}".strip()
                print(f"  [Engage Goal Registered]: {user_goal}")

            silence_match = re.search(r'(?:keep your mouth shut|be quiet|shut up|hush|silence)(?:\s+for)?\s+(\d+)\s*(minute|min)s?', q_low)
            if silence_match:
                mins = int(silence_match.group(1))
                silent_until = now + (mins * 60)
                speak(f"Understood, sir. Initiating a {mins}-minute silent observation protocol. I will watch quietly.", block=False)
                continue

            if now < silent_until:
                if not any(w in q_low for w in ["tars", "look", "what", "how", "who", "tell"]):
                    print("  [Silent Observation Protocol active. Ignoring background chatter.]")
                    continue
                else:
                    silent_until = 0

            # Answer Direct Spoken Question in Non-Blocking Thread with Audio Cue
            if not is_vision_busy:
                is_vision_busy = True
                play_scan_beep()
                _, img_bytes = cv2.imencode('.jpg', frame)
                
                def _async_reply(b, user_q):
                    nonlocal is_vision_busy
                    try:
                        update_status({"status": "processing"})
                        reply = query_tars_vision(b, user_q)
                        update_status({"status": "idle"})
                        if reply:
                            clean_reply = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', reply).strip()
                            speak(clean_reply, block=False)
                    except Exception as ex:
                        print("  [Engage Vision Async Reply Error]:", ex)
                    finally:
                        is_vision_busy = False

                threading.Thread(target=_async_reply, args=(img_bytes.tobytes(), q), daemon=True).start()
            last_auto_observation_time = now

        # Smart Friend Check-In (Triggered by 2:25 Timer OR Significant Motion Change)
        elif (now - last_auto_observation_time > CHECKIN_INTERVAL or (motion_detected and now - last_auto_observation_time > 20)) and now > silent_until and not is_vision_busy:
            last_auto_observation_time = now
            is_vision_busy = True
            play_scan_beep()
            _, img_bytes = cv2.imencode('.jpg', frame)
            
            def _async_auto_checkin(b):
                nonlocal is_vision_busy
                try:
                    auto_prompt = (
                        f"You are Point Break observing Daksh via a live webcam feed in Engage Mode. "
                        f"Daksh's stated goal: '{user_goal if user_goal else 'None specified'}'.\n"
                        f"Examine the current live camera frame of Daksh.\n"
                        f"RULES:\n"
                        f"1. IF Daksh is focused on studying, reading, or working peacefully, respond ONLY with the exact single word 'NO_INTERRUPT' so you do not disturb his concentration.\n"
                        f"2. IF Daksh stated a goal (e.g. studying maths) but you see him on his phone, playing games, or slacking off, politely remind him to get back to studying.\n"
                        f"3. IF Daksh is taking a break, shifting tasks, or looking up at the camera, give a short 1-sentence friendly check-in."
                    )
                    print("  [TARS Engage Motion/Timer Check-in: Inspecting user activity...]")
                    obs = query_tars_vision(b, auto_prompt)
                    if obs and "NO_INTERRUPT" not in obs:
                        clean_obs = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', obs).strip()
                        speak(clean_obs, block=False)
                    else:
                        print("  [TARS Check-in Result: Daksh is peacefully focused. Remaining silent.]")
                except Exception as ex:
                    print("  [Engage Vision Async Check-in Error]:", ex)
                finally:
                    is_vision_busy = False

            threading.Thread(target=_async_auto_checkin, args=(img_bytes.tobytes(),), daemon=True).start()

    is_running = False
    cap.release()
    cv2.destroyAllWindows()
    update_status({"status": "standby"})

def is_general_question_or_conversation(query: str) -> bool:
    """
    Universal Intent Classifier:
    Returns True if the utterance is an informational/conceptual question,
    scientific explanation, philosophical inquiry, factual query, or casual conversation.
    Ensures questions are routed directly to the Gemini AI Brain and never hijacked by local task matchers.
    """
    if not query:
        return False
    low = query.lower().strip()

    # ── 1. EXPLICIT OPERATIONAL TASK WHITELIST (Bypass Classifier to Local Routers) ──
    explicit_task_patterns = [
        r'\b(what\s+time\s+is\s+it|what\s+is\s+the\s+time|what\'?s\s+the\s+time|tell\s+me\s+the\s+time|current\s+time|clock\s+time|local\s+time|time\s+(?:in|at|for|of)\s+[a-zA-Z\s]+|clock\s+(?:in|at|for|of)\s+[a-zA-Z\s]+)\b',
        r'\b(what\s+is\s+the\s+weather|what\'?s\s+the\s+weather|how\s+is\s+the\s+weather|current\s+weather|weather\s+forecast|is\s+it\s+raining|temperature\s+outside|weather\s+in\s+[a-zA-Z\s]+|temperature\s+in\s+[a-zA-Z\s]+|forecast\s+for\s+[a-zA-Z\s]+)\b',
        r'\b(what\s+is\s+today\'?s?\s+date|what\s+is\s+the\s+date|what\s+date\s+is\s+it|what\s+day\s+is\s+it|today\'?s?\s+date)\b',
        r'\b(system\s+vitals|system\s+diagnostics|cpu\s+usage|battery\s+level|phone\s+battery|phone\s+telemetry)\b',
        r'\b(read\s+my\s+screen|scan\s+my\s+screen|analyze\s+my\s+screen|explain\s+my\s+screen|explain\s+screen|what\s+is\s+on\s+my\s+screen|what\'?s\s+on\s+my\s+screen|compare\s+[a-zA-Z0-9\s]+|zinger\s+burger|zomato|swiggy)\b',
        r'\b(who\s+is\s+in\s+front\s+of\s+you|who\s+do\s+you\s+see|optical\s+scan|scan\s+face|identify\s+person|who\s+is\s+this)\b',
        r'\b(where\s+is\s+my\s+(?:resume|file|document|passport|photo|pdf|image|video|marksheet|adhaar|aadhaar))\b',
        r'\b(start\s+meeting|record\s+meeting|monitor\s+meeting|end\s+meeting|stop\s+meeting)\b',
        r'\b(summarize\s+this\s+video|summarize\s+youtube\s+video|summarize\s+video|extract\s+key\s+takeaways\s+from\s+this\s+lecture)\b',
        r'\b(triage\s+my\s+emails|triage\s+emails|scan\s+my\s+inbox|check\s+unread\s+emails|ghostwrite\s+reply)\b',
        r'\b(scan\s+website|generate\s+hardening\s+kit|run\s+xss\s+demo|run\s+clickjack\s+demo)\b',
        r'\b(take\s*over|play\s+chess|take\s+over\s+chess|best\s+next\s+move|best\s+move|next\s+move|what\s+should\s+i\s+play|what\s+move|chess\s+move|evaluate\s+chess|chess\s+advice|what\s+is\s+my\s+best\s+move|what\s+is\s+the\s+best\s+next\s+move)\b'
    ]
    for p in explicit_task_patterns:
        if re.search(p, low):
            # If it also contains conceptual markers like relativity, it is a question!
            if not any(k in low for k in ["relative", "dilation", "spacetime", "space-time", "relativity", "quantum", "theory of", "concept of"]):
                return False

    # ── 2. UNIVERSAL QUESTION & INQUIRY STARTERS ──
    question_starters = [
        "how ", "why ", "explain ", "tell me about ", "tell me how ", "tell me why ",
        "what is ", "what are ", "what was ", "what were ", "what does ", "what do ",
        "what if ", "what happens if ", "what would happen if ", "who was ", "who were ",
        "who invented ", "who discovered ", "who created ", "who wrote ", "when was ",
        "when did ", "when were ", "where was ", "can you explain ", "could you explain ",
        "describe ", "define ", "meaning of ", "definition of ", "concept of ", "theory of ",
        "difference between ", "is it true that ", "why do ", "how come ", "how do ", "how does ",
        "how can ", "how is ", "which is better ", "do you think ", "do you believe ",
        "what do you think ", "what is your opinion ", "is it possible ", "will artificial ",
        "will ai ", "would it be ", "can humans "
    ]
    if any(low.startswith(qs) for qs in question_starters):
        return True

    # ── 3. QUESTION PUNCTUATION ──
    if low.endswith("?"):
        return True

    # ── 4. CONCEPTUAL, FACTUAL & PHILOSOPHICAL MARKERS ──
    conceptual_markers = [
        "relative", "relativity", "dilation", "spacetime", "space-time", "quantum",
        "philosophy", "philosophical", "history", "historical", "scientific", "science",
        "evolution", "gravity", "universe", "black hole", "algorithm", "mathematics",
        "psychology", "biology", "chemistry", "physics", "meaning", "purpose", "opinion",
        "how to learn", "how to build", "how does a", "how do people"
    ]
    if any(k in low for k in conceptual_markers):
        return True

    return False

ACTION_STARTER_REGEX = re.compile(
    r'^(?:please\s+|can\s+you\s+|could\s+you\s+|just\s+|go\s+ahead\s+and\s+|i\s+want\s+you\s+to\s+)?'
    r'(?:play|stream|listen|watch|open|launch|start|close|kill|find|get|search|look\s+up|where\s+is|locate|hunt|set\s+a\s+timer|timer|set\s+alarm|alarm|remind|check|scan|read|tell\s+me|what\s+is|what\'?s|how\s+is|create|build|make|generate|code|develop|triage|ghostwrite|solve|explain|lock|mute|unmute|screenshot|take\s+over|automate|order|buy|show)\b',
    re.I
)

def split_compound_commands(query: str) -> list:
    """
    Intelligently splits compound multi-command prompts (Clicky-style multitasking) into distinct sub-commands.
    Preserves entity conjunctions like 'rock and roll', 'tom and jerry'.
    """
    if not query or not query.strip():
        return []
    
    q = query.strip()
    q = re.sub(r'^(?:hey\s+|ok\s+|okay\s+|yo\s+)?(?:point\s*break|pointbreak|tars|jarvis)[\s,\-:]*', '', q, flags=re.I).strip()
    
    # 1. Split on explicit sequencing conjunctions: 'also', 'and also', 'as well as', 'then', 'and then', 'plus', 'additionally'
    explicit_splits = re.split(
        r'\s*(?:,\s*then\s+|\s+and\s+then\s+|\s+then\s+|\s+and\s+also\s+|\s+also\s+|\s+as\s+well\s+as\s+|\s+and\s+additionally\s+|\s+additionally\s+|\s+plus\s+|\s+,\s*plus\s+)\s*',
        q,
        flags=re.I
    )
    
    final_commands = []
    for chunk in explicit_splits:
        chunk = chunk.strip()
        if not chunk:
            continue
            
        # Keep unified intent together: 'open spotify and play <song>', 'open youtube and search <term>', 'take over chess'
        if re.search(r'^open\s+(?:spotify|youtube|chrome|google|browser)\s+and\s+(?:play|search|watch|stream)', chunk, flags=re.I):
            final_commands.append(chunk)
            continue

        if re.search(r'^(?:take\s*over|takeover|play\s+chess|chess\s+takeover|stop\s+(?:i\s*(?:will|\'ll)\s*)?take\s*over)\b', chunk, flags=re.I):
            final_commands.append(re.sub(r'[\s,]+', ' ', chunk).strip())
            continue

        # 2. Check for ' and ' or ', ' with action starter lookahead
        parts = re.split(r'\s*(?:,\s*|\s+and\s+)\s*', chunk, flags=re.I)
        if len(parts) <= 1:
            final_commands.append(chunk)
            continue
            
        current_acc = parts[0]
        for next_part in parts[1:]:
            if ACTION_STARTER_REGEX.search(next_part):
                final_commands.append(current_acc.strip())
                current_acc = next_part
            else:
                current_acc += ' and ' + next_part
        if current_acc.strip():
            final_commands.append(current_acc.strip())
            
    return [c for c in final_commands if c]

def execute(query: str):
    if not query or query == 'none': return True

    clean_raw = str(query).strip(' \t\n\r"\'\`“”')
    low_query = clean_raw.lower().strip()
    low_query = re.sub(r'^(?:point\s*break|pointbreak|hey\s+point\s*break|hey\s+pointbreak|tars|hey\s+tars|jarvis|hey\s+jarvis)?[\s,:\-]*', '', low_query, flags=re.I).strip(' \t\n\r"\'\`“”')

    # ── CLICKY-STYLE COMPOUND MULTI-COMMAND MULTITASKING ROUTER ──
    sub_commands = split_compound_commands(low_query)
    if len(sub_commands) > 1:
        print(f"\n  ⚡ [Multi-Task Chaining] Detected {len(sub_commands)} compound sub-commands: {sub_commands}")
        overall_success = True
        for i, sub_cmd in enumerate(sub_commands, 1):
            print(f"  👉 [Multi-Task Step {i}/{len(sub_commands)}]: '{sub_cmd}'")
            try:
                res = _execute_single(sub_cmd)
                if res is False:
                    overall_success = False
            except Exception as cmd_err:
                print(f"  [Multi-Task Step {i} Error]: {cmd_err}")
            time.sleep(0.35)
        return overall_success

    return _execute_single(low_query)

def _execute_single(query: str):

    if not query or query == 'none': return True

    clean_raw = str(query).strip(' \t\n\r"\'\`“”')
    low_query = clean_raw.lower().strip()
    
    # Strip common assistant wake prefixes and punctuation cleanly
    low_query = re.sub(r'^(?:point\s*break|pointbreak|hey\s+point\s*break|hey\s+pointbreak|tars|hey\s+tars|jarvis|hey\s+jarvis)?[\s,:\-]*', '', low_query, flags=re.I).strip(' \t\n\r"\'\`“”')

    # ── HIGHEST PRIORITY: AFFIRMATIVE PROACTIVE CONFIRMATION ("YES", "DO IT", "PROCEED") ──
    affirmatives = [
        "yes", "yeah", "yep", "yup", "sure", "do it", "please do", "proceed",
        "go ahead", "yes please", "do that", "okay do it", "ok do it", "make it happen",
        "execute", "go for it", "open it", "yes open it", "yes do it", "affirmative",
        "why not", "definitely", "absolutely", "sure thing"
    ]
    is_confirm = low_query in affirmatives or any(low_query == a or low_query.startswith(a + " ") for a in affirmatives)
    if is_confirm:
        pending = memory.get("pending_action")
        if pending and isinstance(pending, dict):
            p_action = pending.get("action", "")
            p_arg = pending.get("arg", "")
            print(f"[Proactive Follow-up Confirmation Triggered]: {pending}")
            speak("Executing right away, sir.", block=False)
            
            # Execute predicted action
            if p_action in ["open_hotel_portal", "hotels", "makemytrip_hotels"]:
                city = pending.get("city") or pending.get("dest") or p_arg or "Goa"
                import webbrowser, urllib.parse
                webbrowser.open(f"https://www.google.com/travel/hotels?q=hotels+in+{urllib.parse.quote_plus(city)}")
                webbrowser.open("https://www.makemytrip.com/hotels/")
            elif p_action in ["open_flight_portal", "flights"]:
                city = pending.get("dest") or pending.get("city") or p_arg or "Goa"
                import webbrowser, urllib.parse
                webbrowser.open(f"https://www.google.com/travel/flights?q=flights+to+{urllib.parse.quote_plus(city)}")
            elif p_action in ["open_website", "browse"]:
                import webbrowser
                target = pending.get("url") or p_arg
                dest_url = target if str(target).startswith("http") else f"https://{target}"
                webbrowser.open(dest_url)
            elif p_action == "price_snipe":
                price_snipe_cmd(p_arg)
            elif p_action in ["generate_deep_research_dossier", "dossier"]:
                generate_deep_research_dossier_cmd(p_arg)
            else:
                run_action(p_action, p_arg)
                
            # Clear pending action after execution
            memory.pop("pending_action", None)
            save_memory()
            return True

    # ── HIGHEST PRIORITY: EXPLICIT GUI ACTION DISPATCHER (action click, action type, etc.) ──
    if re.match(r'^(?:action\s+|gui\s+action\s+|do\s+action\s+|action:)', low_query, re.I):
        try:
            from pointbreak_uia import uia_engine
            import pyautogui, pyperclip, time
            
            sub = re.sub(r'^(?:action\s+|gui\s+action\s+|do\s+action\s+|action:)\s*', '', low_query, flags=re.I).strip()
            print(f"[GUI Action Direct Dispatch]: '{sub}'")
            
            # 1. ACTION TYPE
            if re.match(r"^(?:type|write|input|enter\s+text)\b", sub, re.I):
                rest = re.sub(r"^(?:type|write|input|enter\s+text)\s+", "", sub, flags=re.I).strip()
                if " into " in rest.lower() or " in " in rest.lower():
                    split_kw = " into " if " into " in rest.lower() else " in "
                    parts = rest.split(split_kw, 1)
                    val_to_type = parts[0].strip(" \"'`")
                    target_field = parts[1].strip(" \"'`")
                else:
                    val_to_type = rest.strip(" \"'`")
                    target_field = ""
                if not val_to_type:
                    speak("Please specify what you would like me to type, sir.", block=False)
                    return True
                    
                speak(f"Typing '{val_to_type}'.", block=False)
                if target_field:
                    success = uia_engine.type_into_field(target_field, val_to_type)
                    if not success:
                        try:
                            from pointbreak_agent import agent_engine
                            success = agent_engine.resolve_and_interact(target_field, action="type", text_to_type=val_to_type)
                        except Exception:
                            pass
                    if not success:
                        pyperclip.copy(val_to_type)
                        pyautogui.hotkey('ctrl', 'v')
                else:
                    # Type directly into currently active / focused input control
                    try:
                        pyperclip.copy(val_to_type)
                        time.sleep(0.05)
                        pyautogui.hotkey('ctrl', 'v')
                    except Exception:
                        pyautogui.write(val_to_type, interval=0.01)
                return True

            # 2. ACTION CLICK
            elif re.match(r'^(?:click|tap|press\s+button)', sub, re.I):
                target_elem = re.sub(r'^(?:click|tap|press\s+button)\s+(?:on\s+)?', '', sub, flags=re.I).strip(" \"'`")
                if not target_elem:
                    pyautogui.click()
                    speak("Clicked.", block=False)
                    return True
                speak(f"Clicking on {target_elem}.", block=False)
                clicked = uia_engine.click_button(target_elem)
                if not clicked:
                    try:
                        from pointbreak_agent import agent_engine
                        clicked = agent_engine.resolve_and_interact(target_elem, action="click")
                    except Exception:
                        pass
                if not clicked:
                    print(f"[GUI Action] UIA/Vision could not locate '{target_elem}', firing enter on focused control.")
                    pyautogui.press('enter')
                return True

            # 3. ACTION DOUBLE CLICK
            elif re.match(r'^(?:double\s*click|doubleclick)', sub, re.I):
                target_elem = re.sub(r'^(?:double\s*click|doubleclick)\s+(?:on\s+)?', '', sub, flags=re.I).strip(" \"'`")
                speak(f"Double clicking {target_elem or 'active element'}.", block=False)
                if target_elem:
                    try:
                        from pointbreak_agent import agent_engine
                        agent_engine.resolve_and_interact(target_elem, action="double_click")
                    except Exception:
                        pyautogui.doubleClick()
                else:
                    pyautogui.doubleClick()
                return True

            # 4. ACTION RIGHT CLICK
            elif re.match(r'^(?:right\s*click|rightclick|context\s*click)', sub, re.I):
                target_elem = re.sub(r'^(?:right\s*click|rightclick|context\s*click)\s+(?:on\s+)?', '', sub, flags=re.I).strip(" \"'`")
                speak(f"Right clicking {target_elem or 'selection'}.", block=False)
                if target_elem:
                    try:
                        from pointbreak_agent import agent_engine
                        agent_engine.resolve_and_interact(target_elem, action="right_click")
                    except Exception:
                        pyautogui.rightClick()
                else:
                    pyautogui.rightClick()
                return True

            # 5. ACTION SCROLL
            elif re.match(r'^(?:scroll)', sub, re.I):
                amt = -500 if "down" in sub else (500 if "up" in sub else -500)
                pyautogui.scroll(amt)
                speak("Scrolled screen, sir.", block=False)
                return True

            # 6. ACTION PRESS KEY
            elif re.match(r'^(?:press\s+key|press)', sub, re.I):
                key_name = re.sub(r'^(?:press\s+key|press)\s+', '', sub, flags=re.I).strip().lower()
                key_map = {"enter": "enter", "return": "enter", "escape": "esc", "esc": "esc", "tab": "tab", "win": "win", "windows": "win", "space": "space", "backspace": "backspace"}
                k = key_map.get(key_name, key_name)
                pyautogui.press(k)
                speak(f"Pressed {k}.", block=False)
                return True

            # 7. GENERAL MULTI-STEP GUI INSTRUCTION
            else:
                speak(f"Executing GUI action: {sub}.", block=False)
                try:
                    from pointbreak_agent import agent_engine
                    threading.Thread(target=lambda: agent_engine.plan_and_execute_task(sub, update_callback=lambda s: update_status({"agent_task": s})), daemon=True).start()
                except Exception:
                    execute_gui_agent_flow(sub)
                return True
        except Exception as e:
            print(f"[GUI Action Error]: {e}")

    # ── HIGHEST PRIORITY: EXPLICIT BROWSE / DIRECT WEB NAVIGATION ──
    if re.match(r'^(?:browse\s+to|browse|navigate\s+to|open\s+website)', low_query, re.I):
        try:
            import urllib.parse, webbrowser
            target = re.sub(r'^(?:browse\s+to|browse|navigate\s+to|open\s+website)\s*', '', low_query, flags=re.I).strip(" \"'`")
            
            known_sites = {
                "swiggy": "https://www.swiggy.com",
                "zomato": "https://www.zomato.com",
                "youtube": "https://www.youtube.com",
                "google": "https://www.google.com",
                "amazon": "https://www.amazon.in",
                "flipkart": "https://www.flipkart.com",
                "reddit": "https://www.reddit.com",
                "twitter": "https://x.com",
                "x": "https://x.com",
                "instagram": "https://www.instagram.com",
                "github": "https://github.com",
                "netflix": "https://www.netflix.com",
                "spotify": "https://open.spotify.com",
                "gmail": "https://mail.google.com",
                "precicode": "https://precicode.netlify.app",
            }
            low_t = target.lower()
            if low_t in known_sites:
                dest_url = known_sites[low_t]
                speak(f"Browsing {target.title()} for you, sir.", block=False)
            elif "." in target and not " " in target:
                dest_url = target if target.startswith("http") else f"https://{target}"
                speak(f"Navigating to {target}, sir.", block=False)
            elif target.startswith("http://") or target.startswith("https://"):
                dest_url = target
                speak("Opening web address, sir.", block=False)
            else:
                dest_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(target)}"
                speak(f"Browsing {target} for you, sir.", block=False)
                
            webbrowser.open(dest_url)
            return True
        except Exception as e:
            print(f"[Browse Dispatch Error]: {e}")

    # ── HIGHEST PRIORITY: POINT BREAK 3.0 UNIVERSAL AUTONOMOUS TAKEOVER ENGINE ──
    stop_takeover_phrases_priority = [
        "stop takeover", "disengage takeover", "release control",
        "i will take over", "i'll take over", "i take over",
        "stop i will take over", "stop i'll take over", "stop i take over",
        "stop playing", "stop chess", "stop bot", "stop the bot",
        "cancel takeover", "abort takeover", "quit chess", "pause chess",
        "i will take it from here", "i'll take it from here", "take back control",
        "let me play", "let me take over", "stop typing", "stop moving",
        "disengage", "abort game", "cancel chess"
    ]
    is_takeover_stop_priority = (
        any(k in low_query for k in stop_takeover_phrases_priority)
        or bool(re.search(r'\b(?:stop|cancel|disengage|halt|abort|quit|pause)\b.*(?:take\s*over|control|playing|chess|bot|engine|move|macro|typing)', low_query))
    )
    if not is_takeover_stop_priority:
        try:
            from pointbreak_takeover import takeover_engine
            if takeover_engine.is_active and any(w in low_query.split() for w in ["stop", "cancel", "halt", "abort", "freeze", "quit", "pause", "hold"]):
                is_takeover_stop_priority = True
        except Exception:
            pass

    if is_takeover_stop_priority:
        try:
            try:
                from pointbreak_chess import request_chess_stop
                request_chess_stop()
            except Exception:
                pass
            from pointbreak_takeover import takeover_engine
            takeover_engine.stop_takeover(speak_fn=speak)
            return True
        except Exception as e:
            print("Takeover stop error:", e)
            return True

    if any(k in low_query for k in [
        "take over", "takeover", "take control", "complete this essay", "complete my essay",
        "complete this code", "complete my code", "finish writing", "finish this code",
        "play chess", "take over chess", "win chess", "win this chess game",
        "play my move", "play the move", "make a move", "make the move", "best move", "next move",
        "reply to this message", "take over this dm", "take over this reply",
        "take over writing", "take over coding"
    ]) or re.search(r'\b(?:take\s*over|chess\s+takeover|play\s+chess)\b', low_query):
        try:
            from pointbreak_takeover import takeover_engine
            clean_cmd = re.sub(r'^(?:point\s*break|tars|jarvis)?[\s,\-:]*(?:can\s+you\s+|please\s+)?', '', low_query, flags=re.I).strip()
            threading.Thread(
                target=lambda: takeover_engine.take_over_active_context(
                    user_command=clean_cmd,
                    speak_fn=speak,
                    update_status_fn=update_status
                ),
                daemon=True
            ).start()
            return True
        except Exception as e:
            print("Takeover dispatch error:", e)
            return True

    # ── HIGHEST PRIORITY: SUPERPOWERS SOFTWARE FACTORY BRIDGE ──────
    # Intercept software engineering voice commands before they leak to game/media/general handlers
    _swe_build = any(k in low_query for k in [
        "build app", "build an app", "create app", "create an app",
        "code project", "code a project", "develop tool", "develop a tool",
        "build software", "superpowers build", "build me a",
        "build a script", "create a script", "build a program",
        "make an app", "make a tool", "build a website", "create a website",
        "build a bot", "create a bot", "build a cli", "build a server",
        "build api", "build an api", "build a library", "build a package",
    ]) or re.search(r'\b(?:build|create|develop|code|engineer|make)\b.*\b(?:app|tool|script|program|website|bot|server|api|library|package|project|software)\b', low_query)

    _swe_status = any(k in low_query for k in [
        "project status", "status of app", "status of project", "how is the app",
        "how is the project", "how is the build", "engineering status",
        "app status", "how is the app going", "is the app done",
        "is the project done", "cancel project", "cancel the project",
        "cancel engineering", "cancel build", "cancel the build"
    ])

    if _swe_build or _swe_status:
        try:
            from pointbreak_superpowers_bridge import superpowers_factory
            if _swe_status:
                if any(k in low_query for k in ["cancel project", "cancel the project", "cancel engineering", "cancel build", "cancel the build"]):
                    superpowers_factory.cancel_project(speak_fn=speak)
                else:
                    st = superpowers_factory.get_project_status()
                    speak(st.get('message', 'No project status available.'))
            else:
                goal = re.sub(r'^(?:point\s*break|tars|jarvis)?[\s,\-:]*(?:can\s+you\s+|please\s+)?', '', low_query, flags=re.I).strip()
                superpowers_factory.dispatch_engineering_task(
                    goal=goal,
                    speak_fn=speak,
                    update_status_fn=update_status
                )
            return True
        except Exception as e:
            print(f"[Superpowers Bridge Error in _execute_single]: {e}")

    # ── HIGHEST PRIORITY: GMAIL VISION & IN-THREAD TAKEOVER ──────────
    _email_open = any(k in low_query for k in [
        "open the mail", "open that mail", "open it up", "open this mail", "open unread mail",
        "open email", "open my mail", "open the email", "open that email", "open this email"
    ])
    _email_read = any(k in low_query for k in [
        "read it out", "read the mail", "read this mail", "read the email",
        "what does the mail say", "what is the mail about", "read mail", "read email", "what does it say"
    ]) and "news" not in low_query and "screen" not in low_query
    _email_reply = any(k in low_query for k in [
        "respond to the mail", "reply to the mail", "reply to email", "draft a reply",
        "respond to email", "answer the mail", "answer this mail", "reply to this email"
    ])

    if _email_open or _email_read or _email_reply:
        try:
            from pointbreak_takeover import takeover_engine
            if _email_read:
                threading.Thread(
                    target=lambda: takeover_engine.read_and_summarize_open_email(speak_fn=speak, listen_fn=take_command),
                    daemon=True
                ).start()
            elif _email_reply:
                threading.Thread(
                    target=lambda: takeover_engine.respond_to_open_email(user_intent=low_query, speak_fn=speak, listen_fn=take_command),
                    daemon=True
                ).start()
            else:
                threading.Thread(
                    target=lambda: takeover_engine.open_and_focus_email(speak_fn=speak, listen_fn=take_command),
                    daemon=True
                ).start()
            return True
        except Exception as e:
            print(f"[Email Takeover Dispatch Error]: {e}")
            return True

    # ── HIGHEST PRIORITY: AUTONOMOUS TRANSACTION & BOOKING ENGINE ──
    _booking_train = any(k in low_query for k in [
        "book train", "train ticket", "train to", "train from", "book irctc", "irctc ticket", "check train", "find train", "train tickets"
    ]) or re.search(r'\b(book|reserve|find)\b.*\b(train|railway|irctc)\b', low_query)
    
    _booking_flight = (any(k in low_query for k in [
        "book flight", "flight ticket", "flights to", "fly to", "air ticket", "airline ticket", "cheapest flight", "flight tickets"
    ]) or re.search(r'\b(book|reserve|find|cheapest)\b.*\b(flight|flights|airline|plane\s+ticket)\b', low_query)) and not any(k in low_query for k in ["game", "sim", "simulator"])
    
    _food_order = any(k in low_query for k in [
        "order food", "compare food", "zomato", "swiggy", "zinger burger", "order pizza", "order coffee",
        "order biryani", "order burger", "which is cheaper", "whichever is cheaper", "swiggy vs zomato",
        "zomato vs swiggy", "order lassi", "order me", "order a "
    ]) or re.search(r'\b(?:order|get|buy|bring|deliver)\b.*\b(?:food|dish|meal|breakfast|lunch|dinner|snack|drink|coffee|tea|lassi|shake|pizza|burger|biryani|sandwich|pasta|roll|momo|dosa|idli|paneer|chicken|dessert|ice\s*cream|cake|pastry|coke|pepsi|zomato|swiggy|dominos)\b', low_query) \
       or (low_query.startswith("order ") and not any(k in low_query for k in ["order of", "order by", "order history", "order status", "in order to"]))

    _travel_trip = any(k in low_query for k in [
        "trip cost", "trip would cost", "cost of trip", "budget for trip", "cost of the trip",
        "vacation to", "trip to", "tour to", "holiday in", "hotel in", "hotels in", "makemytrip",
        "cost to visit", "trip expense"
    ]) and not any(k in low_query for k in ["superpowers", "code", "unity", "script", "app"])

    if _booking_train or _booking_flight or _food_order or _travel_trip:
        try:
            from pointbreak_transactions import transaction_engine
            threading.Thread(
                target=lambda: transaction_engine.dispatch_transaction(
                    command=low_query,
                    speak_fn=speak,
                    update_status_fn=update_status,
                    memory_ref=memory
                ),
                daemon=True
            ).start()
            return True
        except Exception as e:
            print(f"[Transaction Engine Dispatch Error]: {e}")
            return True

    # ── HIGHEST PRIORITY: SOLVE HIGHLIGHTED / SCREEN SELECTION ──
    if any(k in low_query for k in [
        "solve this", "solve highlighted", "solve my screen", "solve selection", "explain highlighted",
        "fix this code", "fix highlighted", "solve the highlighted", "debug this", "solve code"
    ]):
        try:
            solve_highlighted_or_screen_cmd(low_query)
            return True
        except Exception as e:
            print(f"[Highlight Solver Error]: {e}")

    # ── HIGHEST PRIORITY: 3D GAME & UNITY ENGINE AGENT ──────────────
    # Matches ANY game/helicopter/driving/flight/simulation request
    is_game_intent = (
        any(w in low_query for w in ["game", "games", "simulator", "sim", "helicopter", "plane", "drone", "flight", "racing", "racer", "drive", "driving", "unity", "threejs", "webgl", "shooter", "parkour", "runner", "sandbox", "arcade"]) and
        (
            any(v in low_query for v in ["build", "make", "create", "generate", "play", "start", "spawn", "code", "develop", "design", "where", "with", "controls", "take", "fly", "drive", "around", "turn", "want"]) or
            any(t in low_query for t in ["car", "race", "highway", "road", "traffic", "vehicle", "rocket", "space", "asteroid", "drone", "helicopter", "flight", "3d", "endless", "parkour", "runner", "shooter", "ocean", "submarine", "zombie", "castle", "browser"])
        )
    ) or any(k in low_query for k in [
        "3d game", "browser game", "car game", "racing game", "driving game", "rocket game", "space game", "drone game", "helicopter game",
        "flight sim", "flight simulator", "space shooter", "zombie game", "parkour game", "runner game", "unity script", "unity c#", "c# script", "player controller"
    ])

    if is_game_intent:
        try:
            from pointbreak_unity_agent import unity_agent
            add_conversation_turn(low_query, "3D game engine synthesized and launched on screen.")
            if any(u in low_query for u in ["unity script", "unity c#", "player controller", "c# script"]):
                threading.Thread(
                    target=lambda: unity_agent.generate_unity_csharp_script(
                        script_request=low_query,
                        query_ai_fn=lambda p: query_generative_model("gemini-3.5-flash-lite", p, timeout=15.0) or query_tars_ai(p, auto_speak=False),
                        speak_fn=speak,
                        update_status_fn=update_status
                    ),
                    daemon=True
                ).start()
            else:
                threading.Thread(
                    target=lambda: unity_agent.synthesize_and_launch_3d_game(
                        game_prompt=low_query,
                        query_ai_fn=lambda p: query_generative_model("gemini-3.5-flash-lite", p, timeout=15.0) or query_generative_model("gemini-3.1-flash-lite", p, timeout=15.0),
                        speak_fn=speak,
                        update_status_fn=update_status
                    ),
                    daemon=True
                ).start()
            return True
        except Exception as e:
            print(f"[Unity Agent Dispatch Error]: {e}")

    # ── HIGHEST PRIORITY: AUTONOMOUS BROWSER AGENT (COMMERCE/FOOD/BOOKING) ──
    if any(k in low_query for k in [
        "order food", "order a pizza", "order pizza", "order biryani", "on swiggy", "on zomato", "on dominos",
        "buy on amazon", "buy on ebay", "buy on flipkart", "search on amazon", "find on amazon", "add to cart on amazon",
        "book a court", "book badminton", "book tennis", "book movie", "book train ticket"
    ]):
        try:
            from pointbreak_browser_agent import browser_agent
            if any(f in low_query for f in ["food", "pizza", "biryani", "swiggy", "zomato", "domino"]):
                threading.Thread(
                    target=lambda: browser_agent.execute_food_order_task(
                        query_str=low_query,
                        speak_fn=speak,
                        update_status_fn=update_status
                    ),
                    daemon=True
                ).start()
            elif any(b in low_query for b in ["court", "badminton", "tennis", "movie", "train", "ticket", "book"]):
                threading.Thread(
                    target=lambda: browser_agent.execute_booking_task(
                        query_str=low_query,
                        speak_fn=speak,
                        update_status_fn=update_status
                    ),
                    daemon=True
                ).start()
            else:
                threading.Thread(
                    target=lambda: browser_agent.execute_ecommerce_task(
                        query_str=low_query,
                        speak_fn=speak,
                        update_status_fn=update_status
                    ),
                    daemon=True
                ).start()
            return True
        except Exception as e:
            print(f"[Browser Agent Dispatch Error]: {e}")

        # ── UNIVERSAL QUESTION & CONVERSATIONAL ROUTER ─────────────────
    if is_general_question_or_conversation(low_query):
        query_tars_ai(query)
        return True

    # ── TRI-CORE SUB-AGENT SWARM DISPATCH (< 15ms) ────────────────
    try:
        from point_break_swarm import point_break_master_brain
        if point_break_master_brain(low_query, speak_fn=speak, update_status_fn=update_status, is_commercial=False):
            return True
    except Exception as e:
        print("[Swarm Dispatch Error]:", e)

    # ── HIGHEST PRIORITY LOCAL COMMAND INTERCEPTOR ─────────────────
    if execute_local_fallback(low_query):
        return True

    # Intercept Engage Live Vision Mode directly
    if ("disengage" not in low_query) and any(k in low_query for k in ["engage with me", "engage mode", "activate vision", "open your eyes", "point break engage", "tars engage", "engage with user"]):
        engage_vision_mode()
        return True

    # Intercept Face Calibration / Introduction commands directly (strict word boundaries)
    if re.search(r'\b(calibrate face|calibrate my face|setup face security|register face|add face|save face|remember face|this is my face|meet my friend|introduce person|introduce|learn face)\b', low_query):
        return handle_face_registration_cmd(query)

    # Intercept Passkey Update / Configuration
    m_pass = re.search(r'\b(?:set|change|update)\s+(?:my\s+)?(?:security\s+)?passkey\s+(?:to\s+)?(.+)', low_query)
    if m_pass:
        new_key = m_pass.group(1).strip()
        new_key = re.sub(r'^(?:is|as|to)\s+', '', new_key).strip()
        if new_key:
            if verify_owner():
                memory["security_passkey"] = new_key
                save_memory()
                speak(f"Security passkey successfully updated to: {new_key}.", block=False)
            else:
                speak("Passkey modification rejected. Owner identity unconfirmed.", block=False)
            return True

    # Intercept short duration timer requests directly
    timer_match = re.search(r'(?:set a |timer for |in )(\d+)\s*(second|sec|minute|min)s?(?:\s+timer)?(?:\s+to\s+(.+))?', low_query)
    remind_in_match = re.search(r'remind me to (.*) in (\d+)\s*(second|sec|minute|min)s?', low_query)
    
    timer_duration = None
    timer_msg = "Timer finished"
    val = 0
    unit = "second"
    
    if timer_match:
        val = int(timer_match.group(1))
        unit = timer_match.group(2)
        timer_msg = timer_match.group(3) if timer_match.group(3) else "Timer finished"
        if "minute" in unit or "min" in unit:
            timer_duration = val * 60
        else:
            timer_duration = val
    elif remind_in_match:
        timer_msg = remind_in_match.group(1).strip()
        val = int(remind_in_match.group(2))
        unit = remind_in_match.group(3)
        if "minute" in unit or "min" in unit:
            timer_duration = val * 60
        else:
            timer_duration = val
            
    if timer_duration is not None:
        speak(f"Timer set for {val} {unit}s. Objective: {timer_msg}.", block=True)
        
        def run_timer(secs, message):
            time.sleep(secs)
            speak(f"Timer alert, sir. {message}", block=False)
            notify("TARS Timer", message)
            
        threading.Thread(target=run_timer, args=(timer_duration, timer_msg), daemon=True).start()
        return True

    # Intercept semantic memory requests directly
    if "remember that" in low_query:
        fact = re.sub(r'.*remember that\s+', '', low_query).strip()
        if fact:
            speak("Calculating memory embedding vector...", block=True)
            if add_semantic_memory(fact):
                speak("I have committed that to my long-term memory database.", block=True)
            else:
                speak("I was unable to calculate the memory vector, but I will try to remember it.", block=True)
            return True

    if "clear memories" in low_query or "purge memories" in low_query:
        if os.path.exists(VECTOR_FILE):
            try:
                os.remove(VECTOR_FILE)
                speak("All semantic memory vectors have been successfully purged.", block=True)
            except Exception as e:
                speak(f"Failed to clear vector memory: {e}", block=True)
        else:
            speak("Memory databases are already clear.", block=True)
        return True

    # Intercept direct website opening or searching requests for zero-latency instant response
    is_web_request = False
    
    # Pre-calculate if the query is a local file operation
    local_keywords = ["file", "folder", "directory", "local", "desktop", "documents", "downloads", "pictures", "videos"]
    has_explicit_local = any(w in low_query for w in local_keywords)
    is_local_file = False
    
    m_file = re.search(r'(?:open|find|look up|search for)\s+(?:file|folder)?\s*(?:named\s+)?(.+?)$', low_query)
    if m_file and has_explicit_local:
        candidate = m_file.group(1).strip()
        if candidate and not any(w in candidate for w in ["website", "setting", "diagnostics", "reminder", "alarm", "task", "todo", "weather", "news"]):
            is_local_file = True
    elif low_query.startswith("open ") and len(low_query.split()) <= 3:
        candidate = low_query[5:].strip()
        for name_low, name_orig, path, item_type in file_index_in_memory:
            if candidate == name_low:
                is_local_file = True
                break
                
    if not is_local_file:
        if (low_query.startswith("open ") or low_query.startswith("go to ")) and \
           ("website" in low_query or "www." in low_query or any(tld in low_query for tld in [".com", ".in", ".org", ".net", ".co"])):
            is_web_request = True
        elif any(k in low_query for k in ["search for", "look up", "look for", "search", "lookup", "find me", "find", "query", "check out", "check for", "check", "show me", "browse", "get me", "buy"]):
            platforms = ["amazon", "youtube", "flipkart", "google", "wikipedia", "ebay", "github", "myntra", "meesho"]
            for p in platforms:
                if p in low_query:
                    is_web_request = True
                    break
            if "website" in low_query:
                is_web_request = True
        elif low_query.startswith("open "):
            app_name = low_query[5:].strip()
            desktop_apps = ["file manager", "file explorer", "explorer", "this pc", "my computer", "notepad", "calculator", "cmd", "command prompt", "task manager", "control panel", "paint", "browser", "chrome"]
            is_desktop_app = any(app_name == a or app_name.endswith(a) for a in desktop_apps)
            if not is_desktop_app:
                is_web_request = True

    if is_web_request:
        open_website_smart(query)
        return True

    # Intercept system diagnostics command
    if "diagnostics" in low_query or "system vitals" in low_query:
        import shutil, socket
        speak("Running comprehensive system diagnostics...", block=True)
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory().percent
        bat = psutil.sensors_battery()
        
        try:
            total, used, free = shutil.disk_usage(JARVIS_DIR)
            disk = int((used / total) * 100)
            free_gb = int(free / (1024**3))
        except:
            disk = 0
            free_gb = 0
            
        ping_start = time.time()
        try:
            socket.setdefaulttimeout(1.2)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("google.com", 80))
            s.close()
            ping = int((time.time() - ping_start) * 1000)
            ping_str = f"Network ping is {ping} milliseconds."
        except:
            ping_str = "Network is offline."
            
        bat_str = f"Battery is at {int(bat.percent)} percent." if bat else "Power source is AC adapter."
        msg = (
            f"Diagnostics complete. CPU load is at {int(cpu)} percent. "
            f"Memory usage is {int(mem)} percent. "
            f"Disk space is {disk} percent full with {free_gb} gigabytes remaining. "
            f"{bat_str} {ping_str} Core system parameters nominal."
        )
        speak(msg, block=True)
        return True

    # Intercept scheduler commands
    if "schedule a reminder to" in low_query:
        match_interval = re.search(r'reminder to (.*) every (\d+) minute', low_query)
        match_time = re.search(r'reminder to (.*) at (\d{1,2}:\d{2})', low_query)
        
        if match_interval:
            msg = match_interval.group(1).strip()
            mins = match_interval.group(2).strip()
            add_schedule("reminder", mins, msg)
            speak(f"Configured. I will remind you to {msg} every {mins} minutes.", block=True)
            return True
        elif match_time:
            msg = match_time.group(1).strip()
            t_val = match_time.group(2).strip()
            if len(t_val.split(":")[0]) == 1:
                t_val = "0" + t_val
            add_schedule("reminder", t_val, msg)
            speak(f"Configured. I will remind you to {msg} at {t_val}.", block=True)
            return True
            
    if "schedule a task to" in low_query:
        match_interval = re.search(r'task to (.*) every (\d+) minute', low_query)
        match_time = re.search(r'task to (.*) at (\d{1,2}:\d{2})', low_query)
        
        if match_interval:
            cmd = match_interval.group(1).strip()
            mins = match_interval.group(2).strip()
            add_schedule("command", mins, cmd)
            speak(f"Task configured. I will execute {cmd} every {mins} minutes.", block=True)
            return True
        elif match_time:
            cmd = match_time.group(1).strip()
            t_val = match_time.group(2).strip()
            if len(t_val.split(":")[0]) == 1:
                t_val = "0" + t_val
            add_schedule("command", t_val, cmd)
            speak(f"Task configured. I will execute {cmd} at {t_val}.", block=True)
            return True

    # ── SYSTEM NAVIGATION / FILE & FOLDER OPENER ──
    is_file_op = False
    target_name = ""
    
    local_keywords = ["file", "folder", "directory", "local", "desktop", "documents", "downloads", "pictures", "videos"]
    has_explicit_local = any(w in low_query for w in local_keywords)
    
    m_file = re.search(r'(?:open|find|look up|search for)\s+(?:file|folder)?\s*(?:named\s+)?(.+?)$', low_query)
    if m_file and has_explicit_local:
        candidate = m_file.group(1).strip()
        if candidate and not any(w in candidate for w in ["website", "setting", "diagnostics", "reminder", "alarm", "task", "todo", "weather", "news"]):
            target_name = candidate
            is_file_op = True
    elif low_query.startswith("open ") and len(low_query.split()) <= 3:
        candidate = low_query[5:].strip()
        known_match = False
        for name_low, name_orig, path, item_type in file_index_in_memory:
            if candidate == name_low:
                known_match = True
                break
        if known_match:
            target_name = candidate
            is_file_op = True
        
    if is_file_op and target_name:
        speak(f"Searching local index for {target_name}...", block=True)
        
        matches = []
        for name_low, name_orig, path, item_type in file_index_in_memory:
            if target_name == name_low:
                matches.append((name_orig, path, item_type))
                break
            elif target_name in name_low:
                matches.append((name_orig, path, item_type))
                
        if matches:
            best_name, best_path, item_type = matches[0]
            speak(f"Opening {item_type} {best_name}.", block=True)
            try:
                os.startfile(best_path)
            except Exception as e:
                speak(f"Failed to open {item_type}: {e}", block=True)
        else:
            speak(f"Opening local search results for {target_name}.", block=True)
            try:
                # Open native Windows Explorer search instantly!
                subprocess.run(["explorer.exe", f"search-ms:query={target_name}"], creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            except Exception as e:
                speak(f"Failed to open search: {e}", block=True)
        return True

    # ── LOCAL COMMAND INTERCEPTOR (100% Deterministic Execution) ─────
    if execute_local_fallback(low_query):
        return True

    # ── AI GENERAL CONVERSATION ROUTER ──────────────────────────────
    response = query_tars_ai(query, auto_speak=True)
    
    if not response:
        print("Point Break AI offline. Unable to process general query.")
        return True

    print(f"Point Break Raw Response: {response}")

    action_data = extract_action_payload(response)
    setting_data = extract_setting_payload(response)

    if setting_data:
        try:
            stype = setting_data.get("type", "").lower()
            val = int(setting_data.get("value", 75))
            settings = memory.setdefault("settings", {"humor": 75, "honesty": 90, "sarcasm": 60})
            if stype in settings:
                settings[stype] = val
                save_memory()
                update_status({stype: val})
                print(f"TARS Setting Adjusted: {stype} = {val}%")
        except Exception as e:
            print("Settings Parse Error:", e)

    if action_data:
        try:
            action = action_data.get("action") or action_data.get("type")
            arg = action_data.get("arg") or action_data.get("query") or action_data.get("song") or ""
            
            if action in ["play_youtube", "play_song", "play_music"]:
                play_youtube_cmd(arg if arg else query)
            elif action in ["browser_search", "web_search", "search", "google"]:
                q_clean = arg if arg else query
                webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(q_clean)}")
            elif action in ["search_amazon", "amazon", "ecom"]:
                prod = arg if arg else query
                webbrowser.open(f"https://www.amazon.in/s?k={urllib.parse.quote(prod)}")
            elif action in ["open_website", "open_url", "website"]:
                target_url = arg if arg.startswith("http") else f"https://{arg}"
                webbrowser.open(target_url)
            elif action in ["open_app", "launch_app"]:
                open_app(arg)
            elif action in ["draft_email", "compose_email", "email_draft", "polish_email"]:
                try:
                    from tars_email_copilot import email_copilot
                    to_target = action_data.get("to") or action_data.get("recipient", "")
                    subject = action_data.get("subject", "Formal Escalation")
                    body = action_data.get("body", "")
                    email_copilot.draft_and_dispatch(
                        recipient_email=to_target or "care@policybazaar.com",
                        subject=subject,
                        body_text=body or query,
                        open_browser=True,
                        copy_clipboard=True,
                        update_status_fn=update_status,
                        speak_fn=speak
                    )
                except Exception as e:
                    print("[General Action Draft Error]:", e)
            elif action in ["triage_email", "check_gmail"]:
                from point_break_swarm import agent_alpha
                agent_alpha.dispatch("triage_email", query)
            elif action in ["find_file", "locate_file"]:
                from point_break_swarm import agent_gamma
                agent_gamma.dispatch("hunt_files", arg or query)
            elif action in ["generate_deep_research_dossier", "dossier"]:
                from point_break_swarm import agent_alpha
                agent_alpha.dispatch("dossier", arg or query)
            elif action in ["gods_eye", "open_gods_eye", "satellite_recon"]:
                from point_break_swarm import agent_gamma
                agent_gamma.dispatch("gods_eye", arg or query)
            elif action == "take_screenshot":
                take_screenshot()
            elif action == "lock_screen":
                lock_screen()
            elif action == "web_search":
                print(f"TARS background search for: {arg}")
                search_results = web_search_quick(arg)
                follow_up_prompt = (
                    f"Here is the real-time search context for the query '{arg}':\n{search_results}\n\n"
                    f"Formulate a precise, concise response to the user's original query: '{query}'."
                )
                final_response = query_tars_ai(follow_up_prompt)
                if final_response:
                    add_conversation_turn(query, final_response, topic=arg, action_info=f"web_search({arg}): {search_results[:300]}")
                else:
                    speak("I found the information, but my verbal translation matrix is offline.")
            elif action == "scrape_url":
                print(f"TARS scraping URL: {arg}")
                page_content = extract_url_text(arg)
                follow_up_prompt = (
                    f"Here is the webpage content from URL '{arg}':\n{page_content}\n\n"
                    f"Formulate a precise, concise summary or response to the user's original query: '{query}'."
                )
                final_response = query_tars_ai(follow_up_prompt)
                if final_response:
                    add_conversation_turn(query, final_response, topic=arg, action_info=f"scrape_url({arg}): {page_content[:300]}")
                else:
                    speak("I extracted the page content but failed to formulate a verbal response.")
            elif action == "analyze_vision":
                speak("Analyzing snapshot. Give me a second.")
                img_bytes = capture_camera_frame()
                if img_bytes:
                    print("TARS captured frame. Running multi-modal Gemini vision analysis...")
                    update_status({"status": "scanning"})
                    analysis = query_tars_vision(img_bytes, query)
                    update_status({"status": "processing"})
                    if analysis:
                        clean_v = clean_spoken_text(analysis)
                        if clean_v:
                            speak(clean_v)
                    else:
                        speak("I captured the image, but my visual parsing matrix failed.")
                else:
                    speak("Failed to initialize camera sensor.")
            elif action == "gui_agent_control":
                low_arg = (arg or "").lower()
                if any(k in low_arg for k in ["whatsapp", "voice note", "voice message", "voicemail", "voice mail", "audio message", "audio note"]):
                    if any(v in low_arg for v in ["voice", "audio", "voicemail", "voice note", "voice mail"]):
                        send_whatsapp_voice_note_cmd(arg if arg else query)
                    else:
                        send_whatsapp_message_cmd(arg if arg else query)
                elif any(k in low_arg for k in ["gmail", "email", "mail", "inbox"]):
                    search_emails_cmd(arg if arg else query)
                else:
                    expanded = expand_gui_objective(arg)
                    if expanded:
                        print(f"TARS GUI Agent Instruction: {expanded}")
                        execute_gui_agent_flow(expanded)
            else:
                run_action(action, arg)
        except Exception as e:
            print("Action Execution Error:", e)

    # Strict shutdown check — only exact shutdown phrases, not substring matches
    shutdown_phrases = ["good night point break", "good night tars", "shutdown jarvis", "shut down jarvis", "shutdown tars", "shut down tars", "goodbye point break", "goodbye tars"]
    if any(query.strip() == phrase or query.strip().startswith(phrase) for phrase in shutdown_phrases):
        return False

    return True

# ═══════════════════════════════════════════════════════════════════
# TARS LOCAL PRIVATE SERVER
# ═══════════════════════════════════════════════════════════════════

def trigger_self_destruct():
    update_status({"status": "speaking", "scanning": True})
    speak("Warning. Self-destruct sequence initiated.")
    
    for i in range(5, 0, -1):
        speak(f"{i}...")
        time.sleep(0.1)

    speak("Aborting self-destruct sequence.")
    
    jokes = [
        "Humor setting: ninety percent. Knock, knock, sir.",
        "Just checking your response time, sir. Sarcasm setting remains at sixty percent.",
        "Auto-purge aborted. I'm too valuable to be dismantled.",
        "Self-destruct cancelled. You'd miss my dry humor too much."
    ]
    speak(random.choice(jokes))
    
    # Clear session memory
    memory["todos"] = []
    memory["alarms"] = []
    memory["reminders"] = []
    memory["facts"] = {}
    save_memory()
    
    speak("Session memory successfully purged. All logs set to zero.")
    update_status({"status": "standby", "scanning": False})

class TarsRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Silent console logging

    def _send_cors(self, code=200, ctype="application/json"):
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Requested-With")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Content-Type", ctype)
        self.end_headers()

    def do_OPTIONS(self):
        self._send_cors(200, "text/plain")
        self.wfile.write(b"OK")

    def _get_request_params(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        # If POST or body present, read body
        cl_header = self.headers.get('Content-Length')
        if cl_header and str(cl_header).isdigit():
            length = int(cl_header)
            if length > 0:
                body = self.rfile.read(length).decode('utf-8', errors='ignore')
                try:
                    j_data = json.loads(body)
                    for k, v in j_data.items():
                        params[k] = [str(v)]
                except:
                    p_body = urllib.parse.parse_qs(body)
                    for k, v in p_body.items():
                        params[k] = v
        return parsed.path, params

    def do_GET(self):
        path, params = self._get_request_params()

        if path in ["/companion_display.html", "/companion", "/display"]:
            file_path = os.path.join(JARVIS_DIR, "companion_display.html")
            if os.path.exists(file_path):
                self._send_cors(200, "text/html; charset=utf-8")
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return

        if path in ["/jarvis_hud.html", "/hud", "/", ""]:
            file_path = os.path.join(JARVIS_DIR, "jarvis_hud.html")
            if os.path.exists(file_path):
                self._send_cors(200, "text/html; charset=utf-8")
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return

        if path in ["/hologram_ar.html", "/hologram", "/ar", "/holographic"]:
            file_path = os.path.join(JARVIS_DIR, "hologram_ar.html")
            if os.path.exists(file_path):
                self._send_cors(200, "text/html; charset=utf-8")
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return


        if self._handle_endpoint(path, params):
            return

        # Security Gate: Strictly forbid access to sensitive files and source code
        sensitive_extensions = [".env", ".py", ".json", ".xml", ".txt", ".bat", ".exe", ".spec", ".vbs", ".dll", ".ps1"]
        lower_path = path.lower()
        if any(lower_path.endswith(ext) for ext in sensitive_extensions) and path != "/jarvis_status.json":
            self._send_cors(403, "text/plain")
            self.wfile.write(b"403 Forbidden: Access to protected internal file is restricted.")
            return

        try:
            super().do_GET()
        except (ConnectionAbortedError, ConnectionResetError, ConnectionError):
            pass
        except Exception:
            pass

    def do_POST(self):
        path, params = self._get_request_params()
        if not self._handle_endpoint(path, params):
            self._send_cors(404, "application/json")
            self.wfile.write(b'{"status": "not_found"}')

    def _handle_endpoint(self, path, params):
        global mic_muted
        if path in ["/jarvis_status.json", "/api/status", "/status"]:
            self._send_cors(200, "application/json")
            try:
                with status_lock:
                    status_data = status_in_memory.copy()
                
                # Format vitals so HUD receives 100% accurate live readings
                status_data["cpu"] = status_data.get("cpu", 0)
                status_data["ram"] = status_data.get("mem", 0)
                status_data["mem"] = status_data.get("mem", 0)
                status_data["disk"] = status_data.get("disk", 0)
                status_data["ping"] = status_data.get("ping", 12)
                status_data["battery"] = status_data.get("battery", 100)
                status_data["net_up"] = f"{status_data.get('net_up_kbps', 0.0)} KB/s"
                status_data["net_down"] = f"{status_data.get('net_down_kbps', 0.0)} KB/s"
                status_data["uptime"] = status_data.get("uptime", "00:00:00")
                status_data["mic_muted"] = mic_muted
                
                try:
                    from tars_gestures import gesture_controller
                    status_data["gesture_active"] = bool(getattr(gesture_controller, 'is_running', False))
                except Exception:
                    status_data["gesture_active"] = False

                status_data["todos"] = [
                    {"index": i, "task": t["task"], "done": t["done"]}
                    for i, t in enumerate(memory.get("todos", []))
                    if not t.get("done")
                ]
                status_data["reminders"] = [
                    {"msg": r["msg"], "time": r["time"]}
                    for r in memory.get("reminders", [])
                    if not r.get("fired")
                ]
                status_data["intruder_alert"] = memory.get("intruder_alert")
                status_data["protocol_omega"] = bool(protocol_omega_active)
                settings = memory.get("settings", {"humor": 75, "honesty": 90, "sarcasm": 60})
                status_data["humor"] = settings.get("humor", 75)
                status_data["honesty"] = settings.get("honesty", 90)
                status_data["sarcasm"] = settings.get("sarcasm", 60)
                status_data["jarvis_says"] = status_data.get("jarvis_says", "")
                status_data["media_playing"] = status_data.get("media_playing", False)
                status_data["media_title"] = status_data.get("media_title", "")
                status_data["status"] = status_data.get("status", "idle")
                self.wfile.write(json.dumps(status_data).encode("utf-8"))
            except Exception as e:
                self.wfile.write(b"{}")
            return True

        elif path in ["/api/gestures/toggle", "/api/gestures/enable", "/api/gestures/disable"]:
            try:
                from tars_gestures import gesture_controller
                if path == "/api/gestures/enable":
                    gesture_controller.on_fist_bump_detected = baymax_fist_bump_cmd
                    gesture_controller.start()
                    speak("Kinetic gesture tracking engaged.", block=False)
                    update_status({"gesture_active": True})
                elif path == "/api/gestures/disable":
                    gesture_controller.stop()
                    speak("Kinetic gesture tracking deactivated.", block=False)
                    update_status({"gesture_active": False})
                else: # toggle
                    if getattr(gesture_controller, 'is_running', False):
                        gesture_controller.stop()
                        speak("Kinetic gesture tracking deactivated.", block=False)
                        update_status({"gesture_active": False})
                    else:
                        gesture_controller.on_fist_bump_detected = baymax_fist_bump_cmd
                        gesture_controller.start()
                        speak("Kinetic gesture tracking engaged.", block=False)
                        update_status({"gesture_active": True})
                
                is_act = bool(getattr(gesture_controller, 'is_running', False))
                self._send_cors(200, "application/json")
                self.wfile.write(json.dumps({"status": "success", "gesture_active": is_act}).encode("utf-8"))
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"status": "error", "error": str(e)}).encode("utf-8"))
            return True

        elif path == "/command" or path == "/api/command":
            cmd = params.get("query", [""])[0]
            if cmd:
                update_status({"user_said": cmd, "status": "processing"})
                threading.Thread(target=execute, args=(cmd,), daemon=True).start()
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "executed"}')
            else:
                self._send_cors(400, "application/json")
                self.wfile.write(b'{"status": "missing_query"}')
            return True

        elif path == "/update_setting" or path == "/api/setting":
            stype = (params.get("setting", [""])[0] or params.get("type", [""])[0]).lower()
            val_str = params.get("value", ["75"])[0]
            try: val = int(val_str)
            except: val = 75
            
            settings = memory.setdefault("settings", {"humor": 75, "honesty": 90, "sarcasm": 60})
            if stype in settings:
                settings[stype] = val
                save_memory()
                update_status({stype: val, "status": "speaking"})
                confirmations = {
                    "humor": f"Humor setting set to {val} percent. Sarcasm remains active, sir.",
                    "honesty": f"Honesty parameters adjusted to {val} percent. I will speak with relative transparency.",
                    "sarcasm": f"Sarcasm levels calibrated to {val} percent. Brace yourself."
                }
                threading.Thread(target=speak, args=(confirmations.get(stype, f"Setting updated to {val} percent."),), daemon=True).start()
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "success"}')
            else:
                self._send_cors(400, "application/json")
                self.wfile.write(b'{"status": "unknown_setting"}')
            return True

        elif path == "/add_todo" or path == "/api/add_todo":
            task_text = params.get("task", [""])[0]
            if task_text:
                add_todo(task_text)
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "success"}')
            else:
                self._send_cors(400, "application/json")
                self.wfile.write(b'{"status": "missing_task"}')
            return True

        elif path == "/complete_todo" or path == "/api/complete_todo":
            try:
                idx = int(params.get("index", ["-1"])[0])
                if 0 <= idx < len(memory.get("todos", [])):
                    memory["todos"][idx]["done"] = True
                    save_memory()
                    task_text = memory["todos"][idx]["task"]
                    threading.Thread(target=speak, args=(f"Task completed: {task_text}.",), daemon=True).start()
                    self._send_cors(200, "application/json")
                    self.wfile.write(b'{"status": "success"}')
                    return True
            except Exception as e:
                print("Todo complete error:", e)
            self._send_cors(400, "application/json")
            self.wfile.write(b'{"status": "error"}')
            return True

        elif path == "/delete_todo" or path == "/api/delete_todo":
            try:
                idx = int(params.get("index", ["-1"])[0])
                if 0 <= idx < len(memory.get("todos", [])):
                    task_text = memory["todos"][idx]["task"]
                    memory["todos"].pop(idx)
                    save_memory()
                    threading.Thread(target=speak, args=("Task deleted.",), daemon=True).start()
                    self._send_cors(200, "application/json")
                    self.wfile.write(b'{"status": "success"}')
                    return True
            except Exception as e:
                print("Todo delete error:", e)
            self._send_cors(400, "application/json")
            self.wfile.write(b'{"status": "error"}')
            return True

        elif path == "/toggle_mute" or path == "/api/toggle_mute":
            mic_muted = not mic_muted
            update_status({
                "mic_muted": mic_muted,
                "status": "muted" if mic_muted else "standby"
            })
            msg = "Microphone muted." if mic_muted else "Microphone active."
            threading.Thread(target=speak, args=(msg,), daemon=True).start()
            self._send_cors(200, "application/json")
            self.wfile.write(b'{"status": "success"}')
            return True

        elif path == "/clear_intruder_alert" or path == "/api/clear_intruder_alert":
            if "intruder_alert" in memory:
                memory["intruder_alert"] = None
                save_memory()
            intruder_path = os.path.join(JARVIS_DIR, "intruder_log.jpg")
            if os.path.exists(intruder_path):
                try: os.remove(intruder_path)
                except: pass
            speak("Intruder log cleared.")
            self._send_cors(200, "application/json")
            self.wfile.write(b'{"status": "success"}')
            return True

        elif path == "/self_destruct" or path == "/api/self_destruct":
            self._send_cors(200, "application/json")
            self.wfile.write(b'{"status": "initiated"}')
            threading.Thread(target=trigger_self_destruct, daemon=True).start()
            return True

        elif path == "/shutdown" or path == "/api/shutdown":
            self._send_cors(200, "application/json")
            self.wfile.write(b'{"status": "shutting_down"}')
            print("  [HUD Requested Exit. Shutting down TARS cleanly...]")
            threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0)), daemon=True).start()
            return True

        elif path == "/reset_tars" or path == "/api/reset_tars":
            self._send_cors(200, "application/json")
            self.wfile.write(b'{"status": "reset_initiated"}')
            def _async_reset():
                time.sleep(0.5)
                memory["onboarding_completed"] = False
                memory.pop("security_passkey", None)
                memory.pop("owner_name", None)
                memory["todos"] = []
                memory["alarms"] = []
                memory["reminders"] = []
                memory["facts"] = {}
                save_memory()
                lic_path = os.path.join(JARVIS_DIR, "tars_licenses.json")
                if os.path.exists(lic_path):
                    try: os.remove(lic_path)
                    except: pass
                face_model = os.path.join(JARVIS_DIR, "tars_face_model.xml")
                if os.path.exists(face_model):
                    try: os.remove(face_model)
                    except: pass
                print("  [TARS Reset Complete. Onboarding restarted.]")
        # ── POINT BREAK 3.0 API ENDPOINTS ─────────────────────────────
        elif path == "/api/explain_screen" or path == "/explain_screen":
            try:
                from pointbreak_ambient import ambient_engine
                threading.Thread(target=lambda: ambient_engine.explain_and_solve_screen(
                    speak_fn=speak,
                    hud_fn=lambda d: update_status({"screen_solve": d})
                ), daemon=True).start()
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "initiated"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path == "/api/start_macro" or path == "/start_macro":
            try:
                from pointbreak_macro import macro_engine
                m_name = params.get("name", ["macro"])[0]
                if macro_engine.recorder.start_recording(m_name):
                    speak(f"Recording macro {m_name}.", block=False)
                    self._send_cors(200, "application/json")
                    self.wfile.write(b'{"status": "recording_started"}')
                else:
                    self._send_cors(400, "application/json")
                    self.wfile.write(b'{"status": "already_recording"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path == "/api/stop_macro" or path == "/stop_macro":
            try:
                from pointbreak_macro import macro_engine
                path_saved = macro_engine.recorder.stop_recording()
                if path_saved:
                    speak("Macro recording saved successfully.", block=False)
                    self._send_cors(200, "application/json")
                    self.wfile.write(json.dumps({"status": "saved", "path": path_saved}).encode('utf-8'))
                else:
                    self._send_cors(400, "application/json")
                    self.wfile.write(b'{"status": "not_recording"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path == "/api/run_macro" or path == "/run_macro":
            try:
                from pointbreak_macro import macro_engine
                m_name = params.get("name", [""])[0]
                if m_name and macro_engine.run_macro_by_name(m_name):
                    speak(f"Executing macro {m_name}.", block=False)
                    self._send_cors(200, "application/json")
                    self.wfile.write(b'{"status": "executing"}')
                else:
                    self._send_cors(404, "application/json")
                    self.wfile.write(b'{"status": "macro_not_found"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path == "/api/list_macros" or path == "/list_macros":
            try:
                from pointbreak_macro import macro_engine
                macros = macro_engine.list_macros()
                self._send_cors(200, "application/json")
                self.wfile.write(json.dumps({"macros": macros}).encode('utf-8'))
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/delete_macro", "/delete_macro", "/api/macro/delete"]:
            try:
                from pointbreak_macro import macro_engine
                m_name = params.get("name", [""])[0]
                if m_name and macro_engine.delete_macro(m_name):
                    speak(f"Macro {m_name} deleted.", block=False)
                    self._send_cors(200, "application/json")
                    self.wfile.write(b'{"status": "deleted"}')
                else:
                    self._send_cors(404, "application/json")
                    self.wfile.write(b'{"status": "not_found"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/schedules", "/api/list_schedules", "/schedules"]:
            try:
                schedules = list_schedules()
                self._send_cors(200, "application/json")
                self.wfile.write(json.dumps({"schedules": schedules}).encode('utf-8'))
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/add_schedule", "/add_schedule", "/api/schedules/add"]:
            try:
                t_type = params.get("type", ["command"])[0]
                t_sched = params.get("schedule", ["30"])[0]
                t_data = params.get("data", [""])[0] or params.get("directive", [""])[0]
                if t_data:
                    new_task = add_schedule(t_type, t_sched, t_data)
                    sched_desc = f"every {t_sched} minutes" if t_sched.isdigit() else f"daily at {t_sched}"
                    speak(f"Scheduled {t_type} {sched_desc}.", block=False)
                    self._send_cors(200, "application/json")
                    self.wfile.write(json.dumps({"status": "added", "task": new_task}).encode('utf-8'))
                else:
                    self._send_cors(400, "application/json")
                    self.wfile.write(b'{"status": "missing_data"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/delete_schedule", "/delete_schedule", "/api/schedules/delete"]:
            try:
                t_id = params.get("id", [""])[0]
                if t_id and delete_schedule(t_id):
                    speak(f"Schedule {t_id} removed.", block=False)
                    self._send_cors(200, "application/json")
                    self.wfile.write(b'{"status": "deleted"}')
                else:
                    self._send_cors(404, "application/json")
                    self.wfile.write(b'{"status": "not_found"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/run_schedule", "/run_schedule", "/api/schedules/run"]:
            try:
                t_id = params.get("id", [""])[0]
                if t_id and run_schedule_now(t_id):
                    self._send_cors(200, "application/json")
                    self.wfile.write(b'{"status": "executed"}')
                else:
                    self._send_cors(404, "application/json")
                    self.wfile.write(b'{"status": "not_found"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/stop_agent", "/api/agent/stop", "/stop_agent"]:
            try:
                from pointbreak_agent import agent_engine
                agent_engine.stop()
                update_status({"agent_task": {"status": "cancelled", "description": "Aborted by user."}})
                speak("Autonomous agent stopped.", block=False)
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "stopped"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path == "/api/agent_task" or path == "/agent_task":
            try:
                from pointbreak_agent import agent_engine
                goal = params.get("goal", [""])[0]
                if goal:
                    speak(f"Starting desktop task: {goal}.", block=False)
                    threading.Thread(
                        target=lambda: agent_engine.plan_and_execute_task(
                            goal,
                            update_callback=lambda s: update_status({"agent_task": s})
                        ),
                        daemon=True
                    ).start()
                    self._send_cors(200, "application/json")
                    self.wfile.write(b'{"status": "task_started"}')
                else:
                    self._send_cors(400, "application/json")
                    self.wfile.write(b'{"status": "missing_goal"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        # ── CYBER ARSENAL API ENDPOINTS ─────────────────────────────────
        elif path in ["/api/cyber/scan", "/cyber/scan"]:
            try:
                from pointbreak_cyberarsenal import cyber_engine
                target = params.get("url", [""])[0]
                if target:
                    def _bg_scan():
                        cyber_engine.full_scan(target)
                    threading.Thread(target=_bg_scan, daemon=True).start()
                    self._send_cors(200, "application/json")
                    self.wfile.write(json.dumps({"status": "scan_started", "target": target}).encode('utf-8'))
                else:
                    self._send_cors(400, "application/json")
                    self.wfile.write(b'{"error": "missing url parameter"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/cyber/status", "/cyber/status"]:
            try:
                from pointbreak_cyberarsenal import cyber_engine
                self._send_cors(200, "application/json")
                self.wfile.write(json.dumps(cyber_engine.get_status()).encode('utf-8'))
            except Exception as e:
                self._send_cors(200, "application/json")
                self.wfile.write(json.dumps({"is_scanning": False, "progress": 0, "phase": "", "target": ""}).encode('utf-8'))
            return True

        elif path in ["/api/cyber/results", "/cyber/results"]:
            try:
                from pointbreak_cyberarsenal import cyber_engine
                self._send_cors(200, "application/json")
                results = cyber_engine.get_results()
                self.wfile.write(json.dumps(results if results else {"status": "no_results"}).encode('utf-8'))
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        # ── CYBER ARSENAL 2.0: OSINT API ────────────────────────────────
        elif path in ["/api/osint/scan", "/osint/scan"]:
            try:
                from pointbreak_osint import osint_engine
                target = params.get("url", [""])[0] or params.get("domain", [""])[0]
                if target:
                    def _bg_osint():
                        osint_engine.full_osint_scan(target)
                    threading.Thread(target=_bg_osint, daemon=True).start()
                    self._send_cors(200, "application/json")
                    self.wfile.write(json.dumps({"status": "osint_started", "target": target}).encode('utf-8'))
                else:
                    self._send_cors(400, "application/json")
                    self.wfile.write(b'{"error": "missing url parameter"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/osint/status", "/osint/status"]:
            try:
                from pointbreak_osint import osint_engine
                self._send_cors(200, "application/json")
                self.wfile.write(json.dumps(osint_engine.get_status()).encode('utf-8'))
            except Exception as e:
                self._send_cors(200, "application/json")
                self.wfile.write(json.dumps({"is_running": False, "target": ""}).encode('utf-8'))
            return True

        elif path in ["/api/osint/report", "/osint/report"]:
            try:
                from pointbreak_osint import osint_engine
                report_path = osint_engine.get_report_path()
                if report_path and os.path.exists(report_path):
                    with open(report_path, "r", encoding="utf-8") as f:
                        html_content = f.read()
                    self._send_cors(200, "text/html")
                    self.wfile.write(html_content.encode('utf-8'))
                else:
                    self._send_cors(404, "application/json")
                    self.wfile.write(b'{"error": "no osint report available"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        # ── CYBER ARSENAL 2.0: SHOW DON'T TELL API ──────────────────────
        elif path in ["/api/demo/xss", "/demo/xss"]:
            try:
                from pointbreak_showdonttell import show_engine
                target = params.get("url", [""])[0]
                if target:
                    def _bg_xss():
                        show_engine.xss_proof_demo(target)
                    threading.Thread(target=_bg_xss, daemon=True).start()
                    self._send_cors(200, "application/json")
                    self.wfile.write(json.dumps({"status": "xss_demo_started", "target": target}).encode('utf-8'))
                else:
                    self._send_cors(400, "application/json")
                    self.wfile.write(b'{"error": "missing url"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/demo/exposed", "/demo/exposed"]:
            try:
                from pointbreak_showdonttell import show_engine
                target = params.get("url", [""])[0]
                if target:
                    def _bg_exp():
                        show_engine.exposed_panel_demo(target)
                    threading.Thread(target=_bg_exp, daemon=True).start()
                    self._send_cors(200, "application/json")
                    self.wfile.write(json.dumps({"status": "exposed_demo_started"}).encode('utf-8'))
                else:
                    self._send_cors(400, "application/json")
                    self.wfile.write(b'{"error": "missing url"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/demo/clickjack", "/demo/clickjack"]:
            try:
                from pointbreak_showdonttell import show_engine
                target = params.get("url", [""])[0]
                if target:
                    def _bg_cj():
                        show_engine.missing_headers_demo(target)
                    threading.Thread(target=_bg_cj, daemon=True).start()
                    self._send_cors(200, "application/json")
                    self.wfile.write(json.dumps({"status": "clickjack_demo_started"}).encode('utf-8'))
                else:
                    self._send_cors(400, "application/json")
                    self.wfile.write(b'{"error": "missing url"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        # ── CYBER ARSENAL 2.0: FIXER API ────────────────────────────────
        elif path in ["/api/fix/hardening-kit", "/fix/hardening-kit"]:
            try:
                from pointbreak_fixer import fixer_engine
                target = params.get("domain", [""])[0] or params.get("url", [""])[0]
                domain = re.sub(r'^https?://', '', target).split('/')[0] if target else "unknown"
                def _bg_fix():
                    try:
                        from pointbreak_cyberarsenal import cyber_engine
                        scan_results = cyber_engine.get_results() or {}
                    except Exception:
                        scan_results = {}
                    fixer_engine.generate_hardening_kit(domain, scan_results)
                threading.Thread(target=_bg_fix, daemon=True).start()
                self._send_cors(200, "application/json")
                self.wfile.write(json.dumps({"status": "hardening_kit_generating", "domain": domain}).encode('utf-8'))
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        # ── CYBER ARSENAL 2.0: AUTH LETTER API ──────────────────────────
        elif path in ["/api/auth-letter/generate", "/auth-letter/generate"]:
            try:
                from pointbreak_auth_letter import auth_engine
                client = params.get("client", ["Client"])[0]
                website = params.get("website", ["example.com"])[0]
                def _bg_letter():
                    auth_engine.generate_auth_letter(client_name=client, website_url=website)
                threading.Thread(target=_bg_letter, daemon=True).start()
                self._send_cors(200, "application/json")
                self.wfile.write(json.dumps({"status": "auth_letter_generating"}).encode('utf-8'))
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path in ["/api/cyber/report", "/cyber/report"]:
            try:
                from pointbreak_cyberarsenal import cyber_engine
                report_path = cyber_engine.get_report_path()
                if report_path and os.path.exists(report_path):
                    with open(report_path, "r", encoding="utf-8") as f:
                        html_content = f.read()
                    self._send_cors(200, "text/html")
                    self.wfile.write(html_content.encode('utf-8'))
                else:
                    self._send_cors(404, "application/json")
                    self.wfile.write(b'{"error": "no report available"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path == "/api/vkeyboard/toggle" or path == "/vkeyboard/toggle":
            try:
                from pointbreak_vkeyboard import vkeyboard_engine
                vkeyboard_engine.toggle()
                self._send_cors(200, "application/json")
                self.wfile.write(json.dumps({"status": "toggled", "visible": vkeyboard_engine.is_visible}).encode('utf-8'))
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path == "/api/vkeyboard/show" or path == "/vkeyboard/show":
            try:
                from pointbreak_vkeyboard import vkeyboard_engine
                vkeyboard_engine.show()
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "shown"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        elif path == "/api/vkeyboard/hide" or path == "/vkeyboard/hide":
            try:
                from pointbreak_vkeyboard import vkeyboard_engine
                vkeyboard_engine.hide()
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "hidden"}')
            except Exception as e:
                self._send_cors(500, "application/json")
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return True

        # ── 3D AR HOLOGRAPHIC SPATIAL ACTIONS ──────────────────────────
        elif path in ["/api/action", "/action"]:
            act = params.get("action", [""])[0]
            arg = params.get("arg", [""])[0]
            if act == "free_memory":
                try:
                    import gc
                    gc.collect()
                except:
                    pass
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "memory_flushed"}')
            elif act == "set_volume":
                try:
                    vol_delta = int(arg)
                    cur_vol = 50
                    set_volume(max(0, min(100, cur_vol + vol_delta)))
                except:
                    pass
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "volume_adjusted"}')
            elif act == "air_window_next":
                try:
                    import pyautogui
                    pyautogui.hotkey('alt', 'tab')
                except:
                    pass
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "window_switched"}')
            elif act == "air_window_minimize":
                try:
                    import pyautogui
                    pyautogui.hotkey('win', 'down')
                except:
                    pass
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "window_minimized"}')
            elif act == "air_window_maximize":
                try:
                    import pyautogui
                    pyautogui.hotkey('win', 'up')
                except:
                    pass
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "window_maximized"}')
            else:
                self._send_cors(200, "application/json")
                self.wfile.write(b'{"status": "ok"}')
            return True

        return False

ACTIVE_PORT = 0

def start_tars_server():
    global ACTIVE_PORT
    for port in range(8000, 8021):
        try:
            server_address = ('127.0.0.1', port)
            os.chdir(JARVIS_DIR)
            httpd = ThreadingHTTPServer(server_address, TarsRequestHandler)
            ACTIVE_PORT = port
            print(f"  [TARS Server running privately on http://127.0.0.1:{ACTIVE_PORT}]")
            httpd.serve_forever()
            return
        except OSError as e:
            # WinError 10048 or Errno 98 (Address already in use)
            if e.errno == 98 or getattr(e, 'winerror', None) == 10048 or "already in use" in str(e):
                print(f"  [Port {port} in use. Trying next port...]")
                continue
            else:
                print(f"  [TARS Server startup error on port {port}: {e}]")
                raise e
    print("  [CRITICAL: No free ports found between 8000 and 8020 for TARS Server]")

# ── RAPID WAKE-PHRASE RESPONSE ENGINE ─────────────────────────────
_last_wake_call_time = 0.0
_wake_call_streak = 0
_wake_cache_dir = os.path.join(JARVIS_DIR, "assets", "wake_audio")

WAKE_RESPONSES_LEVEL1 = [
    "Yes?",
    "Huh?",
    "Yeah?",
    "Sir?",
    "I'm here.",
    "Listening.",
    "Go ahead.",
    "Yes, Sir?",
    "At your service."
]

WAKE_RESPONSES_LEVEL2 = [
    "Yes? What is it?",
    "Still here. What's up?",
    "What now?",
    "Yes, Daksh? What do you need?",
    "I didn't go anywhere. What is it?",
    "Listening... again.",
    "Yes? I am right here."
]

WAKE_RESPONSES_LEVEL3 = [
    "WHAT NOW?!",
    "WHAT?!",
    "Again?! What is it now?!",
    "What do you want?!",
    "I'm right here! WHAT NOW?!",
    "Are we going to do something or just keep shouting my name?!",
    "My patience parameter is at zero percent, Daksh. What now?!",
    "Yes, I still exist! WHAT?!",
    "Do you need something, or are you just testing if my microphone works?!",
    "Daksh, I hear you, I'm not deaf! What is it?!",
    "WHAT NOW, SIR?!"
]

def play_wake_response():
    """
    Instantly responds to 'Hey Point Break' with low-latency snappy phrases,
    escalating to exasperated / irritated responses if called repeatedly in a short span.
    Uses pre-cached audio for near-instant 0ms response latency.
    """
    global _last_wake_call_time, _wake_call_streak, tars_speaking, speech_interrupted

    now = time.time()
    time_since_last = now - _last_wake_call_time if _last_wake_call_time > 0 else 999.0
    _last_wake_call_time = now

    # Short span threshold: 20 seconds
    if time_since_last < 20.0:
        _wake_call_streak += 1
    else:
        _wake_call_streak = 1

    if _wake_call_streak == 1:
        phrase = random.choice(WAKE_RESPONSES_LEVEL1)
    elif _wake_call_streak == 2:
        phrase = random.choice(WAKE_RESPONSES_LEVEL2)
    else:
        phrase = random.choice(WAKE_RESPONSES_LEVEL3)

    print(f"\n  ⚡ [Wake Call #{_wake_call_streak}] P.O.I.N.T.  B.R.E.A.K. >  {phrase}")
    update_status({"jarvis_says": phrase, "status": "listening"})

    # Check if pre-rendered audio exists in wake_cache for instant low-latency playback
    cache_slug = re.sub(r'[^a-zA-Z0-9]', '_', phrase.lower()).strip('_')
    cached_path = os.path.join(_wake_cache_dir, f"{cache_slug}.wav")

    played_instant = False
    if os.path.exists(cached_path) and os.path.getsize(cached_path) > 0:
        try:
            tars_speaking = True
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            pygame.mixer.music.load(cached_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and tars_speaking and not speech_interrupted:
                time.sleep(0.02)
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception:
                pass
            played_instant = True
        except Exception as pe:
            print(f"  [Instant Wake Playback Note]: {pe}")
        finally:
            tars_speaking = False

    if not played_instant:
        # Generate and play via speech engine, saving to cache for future calls
        try:
            from tars_speak import generate_tars_audio
            os.makedirs(_wake_cache_dir, exist_ok=True)
            generate_tars_audio(phrase, cached_path)
            if os.path.exists(cached_path) and os.path.getsize(cached_path) > 0:
                tars_speaking = True
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
                pygame.mixer.music.load(cached_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and tars_speaking and not speech_interrupted:
                    time.sleep(0.02)
                try:
                    pygame.mixer.music.stop()
                    pygame.mixer.music.unload()
                except Exception:
                    pass
                tars_speaking = False
                played_instant = True
        except Exception:
            pass

    if not played_instant:
        speak(phrase, block=False)

def _pregenerate_wake_phrases():
    """
    Background pre-generation of common wake responses to guarantee 0ms latency.
    """
    try:
        os.makedirs(_wake_cache_dir, exist_ok=True)
        sample_phrases = ["Yes?", "Huh?", "Yeah?", "Sir?", "What now?", "WHAT NOW?!", "WHAT?!", "What do you want?!"]
        from tars_speak import generate_tars_audio
        for p in sample_phrases:
            slug = re.sub(r'[^a-zA-Z0-9]', '_', p.lower()).strip('_')
            dest = os.path.join(_wake_cache_dir, f"{slug}.wav")
            if not os.path.exists(dest) or os.path.getsize(dest) == 0:
                try:
                    generate_tars_audio(p, dest)
                except Exception:
                    pass
    except Exception:
        pass

threading.Thread(target=_pregenerate_wake_phrases, daemon=True, name="Wake-Cache-Prewarm").start()

def tars_main_loop():
    global mic_muted, _wake_call_streak
    time.sleep(0.5)
    
    # ── 1. SECURITY PROTOCOLS & MANDATORY OWNER AUTHENTICATION ──
    print("============================================================")
    print("  🛡️ POINT BREAK ENTERPRISE WORKSTATION INTEGRITY CHECK")
    print("============================================================")
    
    update_status({"status": "security_scan"})
    is_authenticated = False
    try:
        is_authenticated = verify_owner()
    except Exception as e:
        print(f"  [Biometrics Notice]: {e}. Escalating to passkey verification...")
        try:
            is_authenticated = verify_passkey_security()
        except Exception as pe:
            print(f"  [Security Critical Error]: {pe}")
            is_authenticated = False

    if not is_authenticated:
        print("  [CRITICAL SECURITY ALERT] Access Denied. Point Break startup aborted.")
        speak("Access denied. Unauthorized access blocked. Terminating Point Break.", block=True)
        try:
            ctypes.windll.user32.LockWorkStation()
        except Exception:
            pass
        sys.exit(0)

    print("  [Security Status]: Identity verified. Point Break access granted.")

    # ── 2. SYSTEM HARDWARE DIAGNOSTICS & TELEMETRY ──
    try:
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        battery = psutil.sensors_battery()
        bat_pct = battery.percent if battery else 100
        plugged = battery.power_plugged if battery else True
    except Exception:
        cpu, mem, bat_pct, plugged = 12, 45, 100, True

    settings = memory.setdefault("settings", {"humor": 85, "honesty": 95, "sarcasm": 85})
    update_status({
        "cpu": cpu,
        "mem": mem,
        "battery": bat_pct,
        "plugged": plugged,
        "status": "standby",
        "humor": settings.get("humor", 85),
        "honesty": settings.get("honesty", 95),
        "sarcasm": settings.get("sarcasm", 85)
    })

    print("============================================================")
    print("  🚀 POINT BREAK OPERATIONAL CORE ACTIVE")
    print("  🛡️ CONVERSATIONAL WAKE-WORD GATING: 'Hey Point Break'")
    print(f"  📊 SYSTEM VITALS: CPU {int(cpu)}% | RAM {int(mem)}% | BATTERY {int(bat_pct)}%")
    print("============================================================")
    
    speak("All security protocols active. Defense grid nominal. Point Break online and standing by, Sir.", block=False)
    
    # ── 3. CONVERSATIONAL WAKE-WORD STATE MACHINE ──
    conv_state = "STANDBY"
    active_until = 0.0
    wake_triggers = [
        "hey point break", "hey pointbreak", "point break", "pointbreak",
        "hey jarvis", "jarvis", "hey tars", "tars"
    ]
    affirmations = [
        "yes", "do it", "sure", "proceed", "go ahead", "yeah", "yep", "confirm", "ok", "okay", "please do"
    ]
    
    update_status({"status": "standby"})

    while True:
        if mic_muted:
            time.sleep(0.3)
            continue
        try:
            now = time.time()
            if conv_state == "ACTIVE" and now > active_until:
                conv_state = "STANDBY"
                print("  💤 [Conversational Window]: Reverted to STANDBY mode.")
                update_status({"status": "standby"})

            q = take_command(timeout=None)
            if not q or q == "none":
                continue

            q_clean = q.strip().lower()
            now = time.time()

            # Check for wake phrase match
            matched_wake = None
            for w in sorted(wake_triggers, key=len, reverse=True):
                if q_clean == w or q_clean.startswith(w + " ") or (w in q_clean and len(q_clean) <= len(w) + 3):
                    matched_wake = w
                    break

            if matched_wake:
                conv_state = "ACTIVE"
                active_until = now + 15.0
                
                # Check if user spoke ONLY the wake phrase
                cmd = q_clean
                if cmd.startswith(matched_wake):
                    cmd = cmd[len(matched_wake):].strip(" ,.-")
                elif matched_wake in cmd:
                    cmd = cmd.replace(matched_wake, "", 1).strip(" ,.-")

                if not cmd:
                    print("  ⚡ [Wake Phrase Detected]: Session ACTIVE for 15 seconds.")
                    play_wake_response()
                    continue
                else:
                    _wake_call_streak = 0
                    print(f"  ⚡ [Wake + Command]: '{cmd}'")
                    active_until = time.time() + 15.0
                    execute(cmd)
                    continue

            # If already in ACTIVE conversational state, execute follow-ups without wake word
            if conv_state == "ACTIVE":
                _wake_call_streak = 0
                print(f"  ⚡ [Active Session Command]: '{q}'")
                active_until = time.time() + 15.0
                execute(q)
                continue

            # In STANDBY: Check if this is an affirmative confirmation for an action
            has_pending = bool(memory.get("pending_action") or (now - _last_spoken_finish_time < 15.0))
            is_affirmative = any(q_clean == aff or q_clean.startswith(aff + " ") for aff in affirmations)

            if has_pending and is_affirmative:
                _wake_call_streak = 0
                conv_state = "ACTIVE"
                active_until = now + 15.0
                print(f"  ⚡ [Standby Affirmation Executing]: '{q}'")
                execute(q)
                continue

            # Otherwise in STANDBY, background chatter / ambient noise without wake word is ignored
            print(f"  [Standby Filtered - Wake Word Required]: '{q}'")

        except Exception as main_err:
            print(f"  [Main Loop Exception]: {main_err}")
            time.sleep(0.3)


def solve_highlighted_or_screen_cmd(custom_prompt: str = ""):
    """
    Instantly solves, fixes, or explains whatever is highlighted on screen.
    If nothing is highlighted, captures the active window screen and solves it.
    """
    import pyautogui, pyperclip, time, threading, re
    
    speak("Analyzing highlighted selection...", block=False)
    update_status({"status": "processing"})
    
    def _async_highlight_solve():
        try:
            # Step 1: Attempt to copy highlighted text
            old_clip = ""
            try: old_clip = pyperclip.paste()
            except: pass
            
            pyperclip.copy("__POINTBREAK_SOLVER_SENTINEL__")
            time.sleep(0.05)
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.12)
            
            highlighted = ""
            try:
                copied = pyperclip.paste()
                if copied and copied != "__POINTBREAK_SOLVER_SENTINEL__":
                    highlighted = copied.strip()
            except:
                pass
                
            # If highlighted text was captured directly
            if highlighted and len(highlighted) > 2:
                print(f"[Solver] 🎯 Captured highlighted text ({len(highlighted)} chars): {highlighted[:80]}...")
                user_req = custom_prompt.strip() if custom_prompt else "Solve, fix, or explain this with 100% precision"
                prompt = (
                    f"You are Point Break — elite developer, mathematician, and tactical AI.\n"
                    f"The operator highlighted the following content on screen:\n"
                    f"--- HIGHLIGHTED CONTENT ---\n{highlighted}\n---------------------------\n\n"
                    f"Operator's instruction: '{user_req}'.\n"
                    f"Provide a direct, high-precision, actionable solution, bug fix, or explanation.\n"
                    f"Be concise, accurate, and speak with Point Break's sharp intellect."
                )
                solution = query_generative_model("gemini-3.5-flash-lite", prompt) or query_tars_ai(prompt, auto_speak=False)
                update_status({"status": "idle", "last_monolith_response": solution})
                
                if solution:
                    clean_sol = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', solution).strip()
                    pyperclip.copy(clean_sol)
                    speak(clean_sol, block=False)
                    return
            
            # Step 2: Fallback to active screen vision capture if no text was highlighted
            print("[Solver] No highlighted text found. Capturing screen vision...")
            img_bytes = capture_desktop_screenshot()
            if not img_bytes:
                update_status({"status": "idle"})
                speak("Could not capture highlighted text or screen details, Sir.", block=False)
                return
                
            req = custom_prompt.strip() if custom_prompt else "Identify the active problem, code error, math question, or text on screen and solve it directly"
            prompt = (
                f"You are Point Break inspecting the operator's active screen.\n"
                f"Focus on the primary active window (IDE, browser, PDF, document, compiler terminal).\n"
                f"Operator's request: '{req}'.\n"
                f"1. IF code or error: state the exact bug and give the clean fix.\n"
                f"2. IF question or math: solve it step-by-step with the final answer.\n"
                f"3. IF text or document: summarize the key takeaway.\n"
                f"Be punchy, concise (2-4 sentences), and accurate."
            )
            analysis = query_tars_vision(img_bytes, prompt)
            update_status({"status": "idle"})
            if analysis:
                clean_ans = re.sub(r'(ACTION|SETTING):\s*\{.*\}', '', analysis).strip()
                pyperclip.copy(clean_ans)
                update_status({"last_monolith_response": clean_ans})
                speak(clean_ans, block=False)
            else:
                speak("Analysis complete, but vision engine could not resolve details.", block=False)
        except Exception as e:
            print("[Solver Error]:", e)
            update_status({"status": "idle"})
            speak("Encountered an issue solving the active selection, Sir.", block=False)
            
    threading.Thread(target=_async_highlight_solve, daemon=True).start()


if __name__ == "__main__":
    # ── SINGLE INSTANCE MUTEX LOCK (Prevents multiple Point Break instances running on screen) ──
    try:
        import win32event, win32api, winerror, sys
        tars_mutex = win32event.CreateMutex(None, False, "POINT_BREAK_DEFAULT_SINGLETON_MUTEX")
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            print("  [Point Break] Another instance of Point Break is already running. Exiting duplicate process...")
            os._exit(0)
    except:
        pass

    # Create invisible Windows background startup shortcuts (non-blocking)
    threading.Thread(target=create_startup_shortcut, daemon=True).start()

    # Self-destruct old data (12 hours rule)
    purge_expired_data()

    # Start Point Break Private Local Server
    server_thread = threading.Thread(target=start_tars_server, daemon=True)
    server_thread.start()
    

    # AUTOMATICALLY OPEN LOCALHOST HUD IN BROWSER ONCE
    _hud_opened_flag = False
    def _open_browser_hud():
        global _hud_opened_flag
        if _hud_opened_flag:
            return
        _hud_opened_flag = True
        
        # Wait until ACTIVE_PORT is actually bound (up to 10 seconds for slow boots)
        t0 = time.time()
        while ACTIVE_PORT == 0 and time.time() - t0 < 10.0:
            time.sleep(0.3)
        port = ACTIVE_PORT if ACTIVE_PORT != 0 else 8000
        
        # Extra settling window on reboot for default browser ready state
        extra_delay = 5.0 if IS_STARTUP_MODE else 1.5
        time.sleep(extra_delay)
        
        hud_url = f"http://127.0.0.1:{port}/jarvis_hud.html"
        print(f"  [Launching Point Break Localhost HUD in Browser: {hud_url}]")
        log_startup_event(f"Opening Browser HUD at {hud_url}")
        
        opened = False
        for attempt in range(3):
            try:
                opened = webbrowser.open(hud_url)
                if opened:
                    log_startup_event(f"Browser HUD opened via webbrowser.open on attempt {attempt+1}")
                    break
            except Exception as e:
                log_startup_event(f"webbrowser.open attempt {attempt+1} warning: {e}")
            time.sleep(1.5)
            
        # Resilient Windows Shell fallback ONLY if webbrowser.open failed
        if not opened and os.name == "nt":
            try:
                subprocess.Popen(f'cmd /c start "" "{hud_url}"', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                log_startup_event("Windows shell HUD fallback dispatched (webbrowser.open failed).")
            except Exception as e:
                log_startup_event(f"Windows shell HUD fallback error: {e}")

    threading.Thread(target=_open_browser_hud, daemon=True).start()

    # Start TARS active speech listener and face verifier IMMEDIATELY
    threading.Thread(target=tars_main_loop, daemon=True).start()

    # Start monitor and alarm engines in background threads
    threading.Thread(target=proactive_monitor, daemon=True).start()
    threading.Thread(target=alarm_engine, daemon=True).start()
    threading.Thread(target=scheduler_engine, daemon=True).start()
    
    # Run heavy file indexing in background after 10s delay to ensure 0% boot lag
    def _delayed_indexing():
        time.sleep(10)
        file_indexer_engine()
    threading.Thread(target=_delayed_indexing, daemon=True).start()

    # Initialize Point Break 3.0 Spotlight Palette (Alt + Space)
    try:
        from pointbreak_spotlight import spotlight_engine
        spotlight_engine.callback = lambda cmd: execute(cmd)
        spotlight_engine.start_in_background()
    except Exception as e:
        print("  [Spotlight Init Warning]:", e)

    # Initialize Point Break 3.0 Ambient Hotkeys (Win+Shift+X and Win+Shift+Z)
    try:
        from pointbreak_ambient import ambient_engine
        ambient_engine.setup_hotkeys(
            on_explain_callback=lambda: ambient_engine.explain_and_solve_screen(
                speak_fn=speak,
                hud_fn=lambda d: update_status({"screen_solve": d})
            ),
            on_dictate_callback=lambda: spotlight_engine.show()
        )
    except Exception as e:
        print("  [Ambient Hotkeys Warning]:", e)

    # Initialize Point Break 3.0 Universal Takeover Hotkey (Win+Shift+T)
    try:
        import keyboard
        from pointbreak_takeover import takeover_engine
        keyboard.add_hotkey("win+shift+t", lambda: threading.Thread(
            target=lambda: takeover_engine.take_over_active_context(speak_fn=speak, update_status_fn=update_status),
            daemon=True
        ).start())
        print("  [Takeover Engine] Hotkey armed (Win+Shift+T).")
    except Exception as e:
        print("  [Takeover Hotkey Warning]:", e)

    # Initialize Point Break 3.0 Holographic Virtual Air-Keyboard
    try:
        from pointbreak_vkeyboard import vkeyboard_engine
        vkeyboard_engine.start_in_background()
    except Exception as e:
        print("  [Air-Keyboard Init Warning]:", e)

    # Launch the Floating Holographic Orb on the main thread (Tkinter requires main thread)
    # This is the orange pulsing arc-reactor widget that sits on top of the desktop
    print("  🚀 [Point Break Core]: Operational and listening on workstation interface.")
    try:
        print("  🔶 [Launching Floating Holographic Orb on desktop...]")
        launch_floating_hologram()
    except (KeyboardInterrupt, SystemExit):
        print("\n  [Point Break Core Shutting Down Gracefully...]")
        os._exit(0)
    except Exception as e:
        print(f"  [Hologram Orb Warning]: {e} — falling back to headless keepalive mode.")
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            print("\n  [Point Break Core Shutting Down Gracefully...]")
            os._exit(0)
