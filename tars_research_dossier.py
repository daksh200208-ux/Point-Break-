"""
Point Break Research Dossier Engine
===================================
Compiles deep multi-source intelligence dossiers on any topic, person, or company,
extracts web data, and renders a professional HTML/PDF report directly on Desktop.
"""

import os
import re
import time
import json
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime

REPORT_DIR = os.path.join(os.path.expanduser("~"), "Desktop")

class DossierEngine:
    def __init__(self):
        pass

    def generate_dossier_pdf(self, query: str, owner_name: str = "Daksh") -> dict:
        topic = re.sub(r'(?i)\b(research\s+dossier|generate\s+dossier|compile\s+research|dossier\s+on|pdf\s+report\s+on|dossier|about|for|on)\b', ' ', query)
        topic = re.sub(r'\s+', ' ', topic).strip()
        if not topic:
            topic = "Artificial Intelligence & Autonomous Swarms"

        print(f"[Dossier Engine] Synthesizing comprehensive intelligence for: '{topic}'...")

        # 1. Gather live intelligence via Google Gemini or Search
        analysis_text = ""
        try:
            from dotenv import load_dotenv
            jarvis_dir = os.path.dirname(os.path.abspath(__file__))
            load_dotenv(os.path.join(jarvis_dir, ".env"))
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

            import google.generativeai as genai
            if api_key:
                genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")
            prompt = (
                f"You are Point Break Intelligence Directorate preparing a Classified Strategic Dossier for {owner_name}.\n"
                f"Topic: '{topic}'.\n\n"
                f"Structure your response cleanly with these exact sections in clean text (NO markdown hashes):\n"
                f"1. EXECUTIVE SUMMARY: High-level overview, key implications, and core thesis.\n"
                f"2. KEY PLAYERS & ARCHITECTURE: Critical entities, technologies, or stakeholders involved.\n"
                f"3. STRATEGIC VULNERABILITIES & OPPORTUNITIES: Strategic advantages, failure points, and competitive vectors.\n"
                f"4. TACTICAL ACTION PLAN: Specific, prioritized recommendations for {owner_name}.\n"
                f"5. RAW INTELLIGENCE DATA POINTS: 4-5 bullet facts with quantitative metrics or verified benchmarks.\n\n"
                f"Write with authoritative, deep, high-level tactical insight. Be thorough and analytical."
            )
            resp = model.generate_content(prompt)
            if resp and resp.text:
                analysis_text = resp.text.strip()
        except Exception as e:
            print(f"[Dossier AI Error]: {e}")

        if not analysis_text:
            analysis_text = (
                f"EXECUTIVE SUMMARY\n"
                f"Preliminary reconnaissance report on '{topic}'. Live neural synthesis matrix was operating in offline contingency mode.\n\n"
                f"KEY PLAYERS & ARCHITECTURE\n"
                f"Target sector comprises emerging distributed architectures, high-impact technologies, and automated agent swarms.\n\n"
                f"TACTICAL ACTION PLAN\n"
                f"1. Conduct active deep-scan probing.\n"
                f"2. Establish persistent intelligence feeds.\n"
                f"3. Deploy sub-agents Alpha, Beta, and Gamma for continuous reconnaissance."
            )

        # 2. Build tactical dark-theme HTML Dossier
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = re.sub(r'[^a-zA-Z0-9_-]', '_', topic)[:25]
        filename = f"PointBreak_Dossier_{safe_topic}_{timestamp}.html"
        file_path = os.path.join(REPORT_DIR, filename)

        # Convert plain text sections to styled HTML blocks
        sections_html = ""
        current_title = "Strategic Overview"
        current_body = []

        for line in analysis_text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            if re.match(r'^(?:[0-9]+\.|\b[A-Z\s]{4,}:?\b)', line_str) and len(line_str) < 60:
                if current_body:
                    body_p = "".join(f"<p>{p}</p>" for p in current_body)
                    sections_html += f"""
                    <div class="intel-block">
                        <div class="block-header">{current_title}</div>
                        <div class="block-content">{body_p}</div>
                    </div>
                    """
                    current_body = []
                current_title = re.sub(r'^[0-9.]+\s*', '', line_str).rstrip(':')
            else:
                current_body.append(line_str)

        if current_body:
            body_p = "".join(f"<p>{p}</p>" for p in current_body)
            sections_html += f"""
            <div class="intel-block">
                <div class="block-header">{current_title}</div>
                <div class="block-content">{body_p}</div>
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>POINT BREAK INTELLIGENCE DOSSIER: {topic.upper()}</title>
<style>
    body {{
        background-color: #050b14;
        color: #d1d5db;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        margin: 0;
        padding: 40px;
        line-height: 1.6;
    }}
    .container {{
        max-width: 900px;
        margin: 0 auto;
        background: #0a1120;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 40px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.8), 0 0 20px rgba(0, 240, 255, 0.1);
    }}
    .header {{
        border-bottom: 2px solid #00f0ff;
        padding-bottom: 20px;
        margin-bottom: 30px;
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
    }}
    .header h1 {{
        color: #00f0ff;
        margin: 0;
        font-size: 26px;
        letter-spacing: 2px;
        text-transform: uppercase;
    }}
    .meta {{
        color: #64748b;
        font-size: 13px;
        text-align: right;
    }}
    .badge {{
        display: inline-block;
        background: rgba(255, 51, 102, 0.15);
        color: #ff3366;
        border: 1px solid #ff3366;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: bold;
        letter-spacing: 1px;
        margin-bottom: 8px;
    }}
    .intel-block {{
        background: #0f172a;
        border: 1px solid #1e293b;
        border-left: 3px solid #00f0ff;
        border-radius: 4px;
        margin-bottom: 24px;
        padding: 20px;
    }}
    .block-header {{
        color: #38bdf8;
        font-weight: bold;
        font-size: 16px;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 12px;
        border-bottom: 1px solid #1e293b;
        padding-bottom: 6px;
    }}
    .block-content p {{
        margin: 0 0 10px 0;
        font-size: 14px;
        color: #94a3b8;
    }}
    .footer {{
        border-top: 1px solid #1e293b;
        padding-top: 20px;
        margin-top: 40px;
        text-align: center;
        color: #475569;
        font-size: 12px;
    }}
    @media print {{
        body {{ background: #fff; color: #000; padding: 0; }}
        .container {{ background: #fff; border: none; box-shadow: none; padding: 20px; }}
        .intel-block {{ background: #f8fafc; border: 1px solid #ccc; color: #000; }}
        .block-header {{ color: #0284c7; }}
        .block-content p {{ color: #333; }}
    }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <div>
            <div class="badge">TOP SECRET // CLASSIFIED</div>
            <h1>Point Break Intel Dossier</h1>
            <div style="color: #94a3b8; font-size: 15px; margin-top: 4px;">TARGET: <strong style="color: #fff;">{topic}</strong></div>
        </div>
        <div class="meta">
            <div>CLEARANCE: LEVEL 5</div>
            <div>OPERATOR: {owner_name}</div>
            <div>DATE: {datetime.now().strftime('%d %b %Y %H:%M')}</div>
        </div>
    </div>

    {sections_html}

    <div class="footer">
        Synthesized autonomously by Point Break 3.0 Sub-Agent Swarm (Alpha Core). Certified for {owner_name}.
    </div>
</div>
</body>
</html>
"""

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"[Dossier Engine] Dossier generated successfully at: {file_path}")
            return {
                "success": True,
                "file_path": file_path,
                "topic": topic
            }
        except Exception as e:
            print(f"[Dossier Engine Save Error]: {e}")
            return {
                "success": False,
                "error": str(e)
            }

dossier_engine = DossierEngine()
