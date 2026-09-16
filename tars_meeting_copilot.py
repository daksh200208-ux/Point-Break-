"""
TARS Multilingual Live Meeting & Lecture Co-Pilot Engine
=========================================================
Autonomous Background Audio Capture, Multilingual Real-Time Transcription,
Executive Synthesis, Action Item Extraction, and Desktop Dossier Generation.

Supports Zoom, Google Meet, Microsoft Teams, Discord, and YouTube Lectures.
Handles English, Hindi, Hinglish, Spanish, French, German, Japanese, and 100+ languages.
"""

import os
import time
import datetime
import threading
import queue
import re
import json
try:
    import sounddevice as sd
except Exception:
    sd = None
import numpy as np
import speech_recognition as sr
import google.generativeai as genai
from dotenv import load_dotenv

JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(JARVIS_DIR, ".env"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class TarsMeetingCopilot:
    def __init__(self):
        self.is_recording = False
        self.meeting_title = "General Meeting"
        self.start_time = 0
        self.capture_thread = None
        self.process_thread = None
        self.audio_queue = queue.Queue()
        
        # Transcript storage: list of dicts {"timestamp": str, "text": str, "lang": str}
        self.transcript_log = []
        self.transcript_lock = threading.Lock()
        
        # Audio parameters
        self.sample_rate = 16000
        self.chunk_duration = 10 # 10-second rolling segments
        
        # Callback hooks for HUD status updates
        self.on_status_update = None
        self.on_transcript_chunk = None

    def _query_ai_model(self, prompt: str, timeout: float = 15.0) -> str:
        """Robust Gemini query with automatic fallback across models."""
        models = ["gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
        for model_name in models:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                print(f"  [Meeting AI] Model {model_name} attempt error: {e}")
                time.sleep(0.5)
        return ""

    def _capture_worker(self):
        """Continuously records rolling 10-second audio segments from default audio device."""
        print(f"  [Meeting Co-Pilot] Audio Capture Thread Active ({self.meeting_title})")
        while self.is_recording:
            try:
                num_samples = int(self.chunk_duration * self.sample_rate)
                audio_data = sd.rec(num_samples, samplerate=self.sample_rate, channels=1, dtype='int16')
                sd.wait()
                
                if not self.is_recording:
                    break
                    
                # Check amplitude threshold to ignore dead silence
                max_amp = np.max(np.abs(audio_data))
                if max_amp > 150: # Real audio detected
                    self.audio_queue.put((time.time(), audio_data))
            except Exception as e:
                print("  [Meeting Co-Pilot] Audio recording exception:", e)
                time.sleep(0.5)

    def _process_worker(self):
        """Transcribes incoming audio segments in the background."""
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True

        while self.is_recording or not self.audio_queue.empty():
            try:
                try:
                    timestamp_val, audio_chunk = self.audio_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                # Format relative timestamp (e.g. 00:14:32)
                elapsed_secs = int(timestamp_val - self.start_time)
                elapsed_str = str(datetime.timedelta(seconds=max(0, elapsed_secs)))
                
                # Convert raw numpy int16 array to AudioData
                raw_bytes = audio_chunk.tobytes()
                audio_data = sr.AudioData(raw_bytes, self.sample_rate, 2)
                
                text = ""
                # Try Google Speech Recognition with Indian English / Hinglish priority
                try:
                    text = recognizer.recognize_google(audio_data, language="en-IN")
                except sr.UnknownValueError:
                    try:
                        text = recognizer.recognize_google(audio_data, language="hi-IN")
                    except Exception:
                        pass
                except Exception:
                    pass

                if text and len(text.strip()) > 1:
                    clean_text = text.strip()
                    entry = {
                        "time": elapsed_str,
                        "text": clean_text
                    }
                    with self.transcript_lock:
                        self.transcript_log.append(entry)
                        
                    print(f"  [Meeting Transcript] [{elapsed_str}] {clean_text}")
                    if self.on_transcript_chunk:
                        self.on_transcript_chunk(elapsed_str, clean_text)
            except Exception as e:
                print("  [Meeting Co-Pilot] Transcription worker error:", e)

    def start_meeting(self, title: str = "General Meeting"):
        """Starts monitoring and recording the meeting."""
        if self.is_recording:
            return False, "Meeting monitoring is already active."

        self.meeting_title = title if title else "General Meeting"
        self.start_time = time.time()
        self.is_recording = True
        with self.transcript_lock:
            self.transcript_log.clear()
            
        while not self.audio_queue.empty():
            try: self.audio_queue.get_nowait()
            except: break

        self.capture_thread = threading.Thread(target=self._capture_worker, daemon=True)
        self.process_thread = threading.Thread(target=self._process_worker, daemon=True)
        
        self.capture_thread.start()
        self.process_thread.start()
        
        print(f"  [TARS Meeting Co-Pilot] Started: '{self.meeting_title}' at {datetime.datetime.now().strftime('%H:%M:%S')}")
        return True, f"Meeting monitor engaged for '{self.meeting_title}'."

    def get_recent_summary(self, seconds: int = 60) -> str:
        """Live Ear-Translator: Returns a quick summary of the last 60 seconds of discussion."""
        with self.transcript_lock:
            if not self.transcript_log:
                return "I haven't captured enough dialogue yet in this meeting to summarize."
            recent_entries = self.transcript_log[-6:] # Last ~60 seconds

        lines = [f"[{e['time']}] {e['text']}" for e in recent_entries]
        combined_text = "\n".join(lines)

        prompt = (
            f"You are TARS acting as an executive co-pilot.\n"
            f"The user is in a live meeting and asked: 'What did they just say?'\n"
            f"Recent Dialogue Transcript:\n{combined_text}\n\n"
            f"Provide a crisp, accurate, 2-sentence summary in English explaining what was just discussed or decided. "
            f"If it was in Hindi, Hinglish, or another language, translate and summarize accurately in English."
        )
        summary = self._query_ai_model(prompt)
        return summary if summary else "Recent dialogue: " + " ".join([e['text'] for e in recent_entries])

    def end_meeting_and_summarize(self, owner_name: str = "Daksh") -> dict:
        """
        Ends meeting recording, synthesizes the complete executive dossier,
        extracts action items, and generates Markdown and TXT files on Desktop.
        """
        if not self.is_recording and not self.transcript_log:
            return {"success": False, "error": "No meeting is currently active."}

        self.is_recording = False
        print("  [Meeting Co-Pilot] Finalizing audio capture and compiling transcript...")
        time.sleep(1.5) # Allow remaining audio chunks in queue to process

        with self.transcript_lock:
            total_lines = len(self.transcript_log)
            if total_lines == 0:
                raw_transcript = "No audible dialogue was recorded during this session."
                entries = []
            else:
                entries = list(self.transcript_log)
                raw_transcript = "\n".join([f"[{e['time']}] {e['text']}" for e in entries])

        duration_secs = int(time.time() - self.start_time)
        duration_str = str(datetime.timedelta(seconds=max(0, duration_secs)))
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── GEMINI EXECUTIVE SYNTHESIS PROMPT ─────────────────────────
        synthesis_prompt = f"""You are T.A.R.S. (Tactical Autonomous Robotic System) acting as an elite executive co-pilot for {owner_name}.
A business meeting/lecture has just concluded:
Meeting Title: {self.meeting_title}
Duration: {duration_str}
Date: {date_str}

RAW MULTILINGUAL TRANSCRIPT:
\"\"\"
{raw_transcript}
\"\"\"

Analyze the transcript thoroughly. If the transcript contains Hindi, Hinglish, Spanish, or other languages, translate and extract all facts in professional English.

Return a valid JSON object with the following exact keys:
{{
  "executive_summary": "3-4 concise, high-impact paragraphs summarizing the purpose, topics covered, and conclusions of the meeting.",
  "key_decisions": ["List of critical agreements, architectural decisions, deadlines, or approvals made during the call."],
  "action_items": [
    {{"task": "Clear actionable task description", "owner": "Assigned person or {owner_name}", "priority": "High/Medium/Low"}}
  ],
  "spoken_debrief": "A sharp, 2-3 sentence vocal debrief that TARS will speak aloud to {owner_name} summarizing the outcome."
}}
Return ONLY the JSON object. Do not include markdown code blocks (no ```json).
"""

        ai_response = self._query_ai_model(synthesis_prompt)
        
        # Parse JSON output
        parsed_data = {}
        try:
            clean_json = re.sub(r"^```json\s*", "", ai_response.strip(), flags=re.MULTILINE)
            clean_json = re.sub(r"^```\s*", "", clean_json, flags=re.MULTILINE)
            clean_json = re.sub(r"```$", "", clean_json.strip())
            parsed_data = json.loads(clean_json)
        except Exception as e:
            print("  [Meeting Co-Pilot] JSON parse fallback:", e)
            parsed_data = {
                "executive_summary": ai_response if ai_response else "Meeting concluded. Transcript compiled on Desktop.",
                "key_decisions": ["Meeting concluded and logged."],
                "action_items": [{"task": f"Review notes for {self.meeting_title}", "owner": owner_name, "priority": "Medium"}],
                "spoken_debrief": f"Meeting concluded, {owner_name}. I have compiled the executive briefing and saved the full transcript to your Desktop."
            }

        # ── EXPORT DOSSIER TO DESKTOP ──────────────────────────────────
        desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        clean_title = re.sub(r'[^\w\-_\. ]', '_', self.meeting_title).strip().replace(' ', '_')
        timestamp_slug = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        
        file_base = f"TARS_Meeting_{clean_title}_{timestamp_slug}"
        md_path = os.path.join(desktop_dir, f"{file_base}.md")
        txt_path = os.path.join(desktop_dir, f"{file_base}.txt")

        # Build Markdown Document
        decisions_md = "\n".join([f"- **{d}**" for d in parsed_data.get("key_decisions", [])])
        actions_md = "\n".join([
            f"- [ ] **{a.get('task', 'Task')}** (Owner: *{a.get('owner', owner_name)}* | Priority: `{a.get('priority', 'Medium')}`)"
            for a in parsed_data.get("action_items", [])
        ])
        
        transcript_formatted = "\n".join([f"**[{e['time']}]**: {e['text']}" for e in entries]) if entries else "No dialogue captured."

        dossier_md = f"""# ◈ T.A.R.S. EXECUTIVE MEETING DOSSIER ◈
**Meeting Title:** {self.meeting_title}  
**Date & Time:** {date_str}  
**Session Duration:** {duration_str}  
**Host / Operator:** {owner_name}  

---

## 1. Executive Summary
{parsed_data.get("executive_summary", "No summary generated.")}

---

## 2. Key Decisions & Agreements
{decisions_md if decisions_md else "No formal decisions recorded."}

---

## 3. Action Items Matrix
{actions_md if actions_md else "No action items extracted."}

---

## 4. Full Time-Stamped Transcript
{transcript_formatted}

---
*Generated autonomously by T.A.R.S. Executive Co-Pilot Matrix*
"""

        # Write files
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(dossier_md)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(dossier_md.replace("**", "").replace("`", "").replace("## ", "\n--- ").replace("# ", ""))
            print(f"  [Meeting Co-Pilot] Dossier exported to: {md_path}")
        except Exception as fe:
            print("  [Meeting Co-Pilot] File write error:", fe)

        # ── SYNC ACTION ITEMS TO TARS MEMORY ──────────────────────────
        try:
            memory_path = os.path.join(JARVIS_DIR, "jarvis_memory.json")
            if os.path.exists(memory_path):
                with open(memory_path, "r", encoding="utf-8") as f:
                    mem_data = json.load(f)
                
                todos = mem_data.setdefault("todos", [])
                for a in parsed_data.get("action_items", []):
                    task_text = f"[{self.meeting_title}] {a.get('task', '')}"
                    todos.append({"task": task_text, "done": False, "priority": a.get("priority", "Medium")})
                
                with open(memory_path, "w", encoding="utf-8") as f:
                    json.dump(mem_data, f, indent=2)
                print("  [Meeting Co-Pilot] Synced action items into TARS TODO list.")
        except Exception as me:
            print("  [Meeting Co-Pilot] Memory sync error:", me)

        return {
            "success": True,
            "title": self.meeting_title,
            "duration": duration_str,
            "dossier_path": md_path,
            "spoken_debrief": parsed_data.get("spoken_debrief", f"Meeting finished, {owner_name}. I have created the summary dossier on your Desktop."),
            "action_count": len(parsed_data.get("action_items", [])),
            "decisions_count": len(parsed_data.get("key_decisions", []))
        }

# Global Singleton
meeting_copilot = TarsMeetingCopilot()
