"""
Point Break Authorization Letter Generator
==========================================
Generates a professional penetration testing authorization
letter for clients to sign before active scanning begins.

This protects both the consultant (Daksh) and the client legally.
All active scanning must have this authorization.
"""

import os
import datetime
import webbrowser
import html
from pathlib import Path

REPORT_DIR = Path(os.path.expanduser("~")) / "Desktop"

class AuthLetterEngine:
    def __init__(self):
        self.last_letter_path = None

    def generate_auth_letter(self, client_name, website_url, scope_description='Full website security audit', consultant_name='Daksh', company_name='Point Break Security'):
        # Generate date strings
        now = datetime.datetime.now()
        date_str_formatted = now.strftime("%B %d, %Y")
        file_date_str = now.strftime("%Y%m%d_%H%M%S")
        end_date = now + datetime.timedelta(days=30)
        end_date_str_formatted = end_date.strftime("%B %d, %Y")
        
        # Escape HTML inputs
        safe_client = html.escape(client_name)
        safe_url = html.escape(website_url)
        safe_scope = html.escape(scope_description)
        safe_consultant = html.escape(consultant_name)
        safe_company = html.escape(company_name)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Penetration Testing Authorization</title>
    <style>
        :root {{
            --bg-color: #121212;
            --text-color: #e0e0e0;
            --accent-color: #d4af37; /* Gold/Amber */
            --box-bg: #1e1e1e;
            --border-color: #333;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 40px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background-color: var(--box-bg);
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
            border-top: 5px solid var(--accent-color);
        }}
        h1 {{
            color: var(--accent-color);
            text-align: center;
            text-transform: uppercase;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 15px;
            margin-bottom: 30px;
            letter-spacing: 2px;
        }}
        h2 {{
            color: var(--accent-color);
            margin-top: 30px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 5px;
        }}
        .header-info {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 30px;
            font-weight: bold;
        }}
        ul {{
            margin-top: 10px;
        }}
        li {{
            margin-bottom: 8px;
        }}
        .signatures {{
            display: flex;
            justify-content: space-between;
            margin-top: 60px;
        }}
        .sig-block {{
            width: 45%;
        }}
        .sig-line {{
            border-bottom: 1px solid var(--text-color);
            margin-top: 40px;
            margin-bottom: 10px;
        }}
        .sig-label {{
            font-size: 0.9em;
            color: #aaa;
        }}
        .footer {{
            text-align: center;
            margin-top: 50px;
            font-size: 0.8em;
            color: #666;
            border-top: 1px solid var(--border-color);
            padding-top: 20px;
        }}
        .print-btn-container {{
            text-align: center;
            margin-top: 30px;
        }}
        button {{
            background-color: var(--accent-color);
            color: #000;
            border: none;
            padding: 12px 24px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            border-radius: 4px;
            text-transform: uppercase;
            transition: background-color 0.3s;
        }}
        button:hover {{
            background-color: #f3c74c;
        }}
        
        @media print {{
            body {{
                background-color: white;
                color: black;
                padding: 0;
            }}
            .container {{
                background-color: white;
                box-shadow: none;
                border: none;
                padding: 20px;
            }}
            h1, h2 {{
                color: black;
                border-bottom-color: black;
            }}
            .sig-line {{
                border-bottom-color: black;
            }}
            .sig-label {{
                color: black;
            }}
            button, .print-btn-container {{
                display: none;
            }}
            .footer {{
                color: black;
                border-top-color: black;
            }}
            @page {{
                margin: 2cm;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Penetration Testing Authorization Agreement</h1>
        
        <div class="header-info">
            <div>Date: {date_str_formatted}</div>
            <div>Company: {safe_company}</div>
        </div>

        <p>This document serves as formal authorization for <strong>{safe_company}</strong> (represented by {safe_consultant}) to conduct security assessment activities on the web applications and infrastructure owned or operated by <strong>{safe_client}</strong>.</p>

        <h2>1. Parties Involved</h2>
        <ul>
            <li><strong>Client:</strong> {safe_client}</li>
            <li><strong>Target URL/Domain:</strong> {safe_url}</li>
            <li><strong>Consulting Firm:</strong> {safe_company}</li>
            <li><strong>Lead Consultant:</strong> {safe_consultant}</li>
        </ul>

        <h2>2. Scope of Testing</h2>
        <p>{safe_scope}. The assessment will focus exclusively on the targeted web application and its immediate supporting infrastructure.</p>

        <h2>3. Duration of Authorization</h2>
        <p>This authorization is valid for a period of 30 days, beginning on <strong>{date_str_formatted}</strong> and expiring on <strong>{end_date_str_formatted}</strong>.</p>

        <h2>4. What IS Authorized</h2>
        <p>The following activities are explicitly permitted during the assessment period:</p>
        <ul>
            <li>HTTP request analysis and manipulation</li>
            <li>Security header review and configuration assessment</li>
            <li>SSL/TLS certificate inspection and validation</li>
            <li>Directory and file enumeration</li>
            <li>SQL injection testing (strictly non-destructive, read-only verification)</li>
            <li>Cross-site scripting (XSS) testing</li>
            <li>Cross-Site Request Forgery (CSRF) vulnerability assessment</li>
            <li>Authentication and session management mechanism review</li>
            <li>API endpoint discovery and security analysis</li>
            <li>Open port scanning on provided domain/IP</li>
            <li>Vulnerability reporting and remediation guidance</li>
        </ul>

        <h2>5. What is NOT Authorized</h2>
        <p>The following activities are strictly prohibited under this agreement:</p>
        <ul>
            <li>Accessing, copying, or exfiltrating any sensitive, personal, or proprietary client data</li>
            <li>Intentional Denial of Service (DoS/DDoS) attacks</li>
            <li>Physical security testing of facilities</li>
            <li>Social engineering attacks against employees or customers</li>
            <li>Testing third-party services, hosters, or platforms not explicitly owned by the client</li>
            <li>Sharing vulnerability details or findings with any unauthorized third party</li>
            <li>Exploiting vulnerabilities beyond the minimal proof-of-concept necessary to demonstrate risk</li>
        </ul>

        <h2>6. Confidentiality</h2>
        <p>All information obtained during the assessment, including vulnerability details, system configurations, and proprietary client information, shall remain strictly confidential. {safe_company} agrees not to disclose such information to any third party without explicit written consent from the client.</p>

        <h2>7. Liability Limitation</h2>
        <p>While {safe_company} agrees to perform all testing with the utmost care to avoid disruption to the client's operations, security testing carries inherent risks. The client acknowledges these risks and agrees to hold {safe_company} harmless for any unintended downtime, data loss, or systemic issues directly or indirectly resulting from authorized testing activities.</p>

        <div class="signatures">
            <div class="sig-block">
                <div class="sig-line"></div>
                <div class="sig-label">Authorized Client Representative Name (Printed)</div>
                <div class="sig-line"></div>
                <div class="sig-label">Client Signature</div>
                <div class="sig-line"></div>
                <div class="sig-label">Date</div>
            </div>
            <div class="sig-block">
                <div class="sig-line"></div>
                <div class="sig-label">Consultant Name (Printed): {safe_consultant}</div>
                <div class="sig-line"></div>
                <div class="sig-label">Consultant Signature</div>
                <div class="sig-line"></div>
                <div class="sig-label">Date</div>
            </div>
        </div>

        <div class="footer">
            This document was generated by Point Break Security System
        </div>

        <div class="print-btn-container">
            <button onclick="window.print()">Print / Save as PDF</button>
        </div>
    </div>
</body>
</html>
"""
        
        safe_client_filename = "".join(c for c in client_name if c.isalnum() or c in " _-").strip().replace(" ", "_").lower()
        if not safe_client_filename:
            safe_client_filename = "client"
            
        filename = f"pointbreak_auth_letter_{safe_client_filename}_{file_date_str}.html"
        
        # Ensure desktop exists
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        
        file_path = REPORT_DIR / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        self.last_letter_path = str(file_path)
        
        # Open in browser
        webbrowser.open('file://' + str(file_path.absolute()).replace('\\', '/'))
        
        return self.last_letter_path

    def get_last_letter_path(self):
        return self.last_letter_path

auth_engine = AuthLetterEngine()
