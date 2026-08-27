"""
TARS Video & YouTube Intelligence Engine
=========================================
Extracts transcripts from YouTube videos/lectures/podcasts, synthesizes
executive briefings using Gemini 2.5, and compiles publication-grade PDF dossiers.
"""

import os
import sys
import time
import re
import json
import urllib.parse
from typing import Dict, Any, Optional, Tuple

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pyperclip
from dotenv import load_dotenv

JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(JARVIS_DIR, ".env"))

try:
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
except ImportError:
    genai = None

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None

def extract_youtube_video_id(url_or_text: str) -> Optional[str]:
    """Extracts 11-character YouTube video ID from various URL formats or text."""
    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for p in patterns:
        m = re.search(p, url_or_text)
        if m:
            return m.group(1)
    return None

def fetch_youtube_transcript(video_id: str) -> Tuple[bool, str, str]:
    """
    Fetches transcript for video_id.
    Returns (success, full_transcript_text, detected_lang).
    """
    if not YouTubeTranscriptApi:
        return False, "", "API unavailable"

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None
        try:
            transcript = transcript_list.find_manually_created_transcript(['en', 'en-US', 'hi', 'es', 'fr'])
        except Exception:
            pass

        if not transcript:
            try:
                transcript = transcript_list.find_generated_transcript(['en', 'en-US', 'hi', 'es', 'fr'])
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break

        if transcript:
            fetched_data = transcript.fetch()
            lines = []
            for entry in fetched_data:
                start_sec = int(entry.get('start', 0))
                mins = start_sec // 60
                secs = start_sec % 60
                ts_str = f"[{mins:02d}:{secs:02d}]"
                text = entry.get('text', '').strip()
                if text:
                    lines.append(f"{ts_str} {text}")
            return True, "\n".join(lines), transcript.language
    except Exception as e:
        print(f"[Video Intelligence] Transcript fetch notice: {e}")

    try:
        data = YouTubeTranscriptApi.get_transcript(video_id, languages=['en', 'en-US', 'hi'])
        lines = []
        for entry in data:
            start_sec = int(entry.get('start', 0))
            mins = start_sec // 60
            secs = start_sec % 60
            lines.append(f"[{mins:02d}:{secs:02d}] {entry.get('text', '').strip()}")
        return True, "\n".join(lines), "en"
    except Exception as e:
        return False, f"Could not extract auto-captions: {e}", "none"

def generate_video_summary_pdf(video_title: str, summary_data: Dict[str, Any], output_pdf_path: str) -> bool:
    """Generates an executive PDF report using ReportLab."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib import colors

        doc = SimpleDocTemplate(
            output_pdf_path,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor('#0F172A'),
            spaceAfter=6
        )
        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#64748B'),
            spaceAfter=12
        )
        h2_style = ParagraphStyle(
            'H2',
            parent=styles['Heading2'],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor('#0284C7'),
            spaceBefore=12,
            spaceAfter=6
        )
        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor('#334155'),
            spaceAfter=6
        )
        bullet_style = ParagraphStyle(
            'Bullet',
            parent=styles['Normal'],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#1E293B'),
            leftIndent=15,
            spaceAfter=4
        )

        story = []
        story.append(Paragraph("TARS COMMERCIAL // INTELLIGENCE DOSSIER", subtitle_style))
        clean_title_display = video_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(f"Executive Briefing: {clean_title_display}", title_style))
        story.append(Paragraph(f"Compiled on {time.strftime('%B %d, %Y at %I:%M %p')} | Engine: TARS Deep Intelligence", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284C7'), spaceAfter=14))

        exec_sum = summary_data.get("executive_summary", "")
        if exec_sum:
            story.append(Paragraph("Executive Summary", h2_style))
            safe_sum = exec_sum.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
            story.append(Paragraph(safe_sum, body_style))
            story.append(Spacer(1, 8))

        chapters = summary_data.get("key_points", [])
        if chapters:
            story.append(Paragraph("Key Chapters & Detailed Breakdown", h2_style))
            for pt in chapters:
                safe_pt = pt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(f"• {safe_pt}", bullet_style))
            story.append(Spacer(1, 8))

        takeaways = summary_data.get("action_items", [])
        if takeaways:
            story.append(Paragraph("Core Takeaways & Insights", h2_style))
            for item in takeaways:
                safe_item = item.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(f"✓ {safe_item}", bullet_style))
            story.append(Spacer(1, 8))

        doc.build(story)
        print(f"[Video Intelligence] ✅ Dossier PDF compiled at: {output_pdf_path}")
        return True
    except Exception as e:
        print(f"[Video Intelligence] PDF generation error: {e}")
        return False

class VideoSummarizerEngine:
    def __init__(self, gemini_model="models/gemini-2.5-flash"):
        self.gemini_model_name = gemini_model

    def summarize_youtube_video(self, url_or_query: str, owner_name: str = "Operator") -> Dict[str, Any]:
        """
        Extracts YouTube video transcript, analyzes content with Gemini 2.5,
        and produces an executive PDF dossier on the Desktop.
        """
        video_id = extract_youtube_video_id(url_or_query)
        if not video_id:
            clip_text = pyperclip.paste().strip()
            video_id = extract_youtube_video_id(clip_text)

        if not video_id:
            return {"success": False, "error": "No YouTube video URL or ID found in command or clipboard."}

        print(f"[Video Intelligence] Extracting transcript for Video ID: {video_id}...")
        ok, transcript_text, lang = fetch_youtube_transcript(video_id)
        
        if not ok or not transcript_text:
            return {"success": False, "error": f"Unable to fetch transcript: {transcript_text}"}

        trans_slice = transcript_text[:40000]

        prompt = f"""
You are the Executive Intelligence Synthesizer for TARS.
Analyze the following YouTube video transcript and produce a structured executive debriefing.

TRANSCRIPT:
{trans_slice}

OUTPUT ONLY VALID JSON with this exact schema:
{{
  "title": "Clear and descriptive video title",
  "executive_summary": "High-level 2-3 paragraph synthesis of the entire discussion, core thesis, and major themes.",
  "key_points": [
    "[Timestamp / Topic] Key point or argument discussed in detail.",
    "[Timestamp / Topic] Second major insight or topic discussed."
  ],
  "action_items": [
    "Core actionable takeaway or fundamental principle 1",
    "Core actionable takeaway or fundamental principle 2"
  ],
  "spoken_debrief": "A concise 2-sentence conversational spoken summary for {owner_name}."
}}
"""
        try:
            model = genai.GenerativeModel(self.gemini_model_name)
            res = model.generate_content(prompt)
            match = re.search(r'\{.*\}', res.text.strip(), re.DOTALL)
            if not match:
                return {"success": False, "error": "Failed to parse Gemini summary output."}

            data = json.loads(match.group(0))
            title = data.get("title", f"YouTube_Video_{video_id}")
            safe_filename = re.sub(r'[^\w\s-]', '', title).strip().replace(" ", "_")[:40]
            
            desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
            pdf_path = os.path.join(desktop_dir, f"{safe_filename}_Executive_Dossier.pdf")
            
            generate_video_summary_pdf(title, data, pdf_path)
            
            return {
                "success": True,
                "title": title,
                "pdf_path": pdf_path,
                "spoken_debrief": data.get("spoken_debrief", f"Executive dossier on {title} has been compiled and saved to your Desktop, {owner_name}.")
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

video_summarizer = VideoSummarizerEngine()
