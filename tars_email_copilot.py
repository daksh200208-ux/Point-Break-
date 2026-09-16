"""
Point Break — High-Speed Native IMAP/SMTP Email Copilot, Grievance Polisher & Ghost-Drafter
===========================================================================================
1. Direct IMAP SSL connection (< 0.4s) — zero browser/screen capture lag.
2. Unread & priority email filtering across all categories.
3. Automated Ghost-Drafting: Injects draft replies directly into Gmail Drafts folder.
4. Live Web Compose Pre-fill: Launches pre-populated Gmail compose tab with 1-click send.
5. Clipboard & HUD Response Monolith Sync: Copies polished text to clipboard and renders on HUD.
6. Intelligent Company & Grievance Resolution: Maps domains/brands to verified customer care desks.
"""

import os
import sys
import time
import json
import email
import imaplib
import smtplib
import re
import urllib.parse
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any, Optional, Tuple, Callable
import webbrowser
import requests
import pyperclip
from dotenv import load_dotenv

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(JARVIS_DIR, ".env"))

KNOWN_COMPANY_EMAILS = {
    "policybazaar": "care@policybazaar.com",
    "policybazaar.com": "care@policybazaar.com",
    "policybazaar health": "care@policybazaar.com",
    "amazon": "cs-reply@amazon.in",
    "amazon.in": "cs-reply@amazon.in",
    "amazon.com": "cis@amazon.com",
    "flipkart": "support@flipkart.com",
    "flipkart.com": "support@flipkart.com",
    "swiggy": "support@swiggy.in",
    "zomato": "order@zomato.com",
    "hdfc": "support@hdfcbank.com",
    "hdfc bank": "support@hdfcbank.com",
    "sbi": "customercare@sbi.co.in",
    "icici": "care@icicibank.com",
    "airtel": "121@in.airtel.com",
    "jio": "care@jio.com",
    "uber": "support@uber.com",
    "ola": "support@olacabs.com",
    "makemytrip": "service@makemytrip.com",
    "irctc": "care@irctc.co.in",
    "apple": "support@apple.com",
    "google": "support@google.com",
    "microsoft": "support@microsoft.com",
    "netflix": "info@netflix.com",
    "spotify": "support@spotify.com",
    "cred": "support@cred.club",
    "paytm": "care@paytm.com",
    "phonepe": "support@phonepe.com"
}

def decode_mime_words(raw_header: str) -> str:
    """Decodes MIME encoded subject/from header strings."""
    if not raw_header:
        return ""
    decoded_fragments = []
    for fragment, encoding in decode_header(raw_header):
        if isinstance(fragment, bytes):
            try:
                decoded_fragments.append(fragment.decode(encoding or "utf-8", errors="ignore"))
            except Exception:
                decoded_fragments.append(fragment.decode("latin1", errors="ignore"))
        else:
            decoded_fragments.append(str(fragment))
    return " ".join(decoded_fragments)


def resolve_recipient_email(raw_target: str) -> str:
    """Intelligently translates brand names, domains, or raw strings into active care emails."""
    if not raw_target:
        return "care@policybazaar.com"
    target_clean = raw_target.lower().strip().strip("'").strip('"').strip("`-,.:;!? ")
    if "@" in target_clean:
        return target_clean
    for comp, em in KNOWN_COMPANY_EMAILS.items():
        if comp in target_clean:
            return em
    if "." in target_clean and " " not in target_clean:
        return f"care@{target_clean}"
    return f"support@{target_clean.replace(' ', '')}.com"


class EmailCopilot:
    def __init__(self, jarvis_dir=None):
        self.jarvis_dir = jarvis_dir or JARVIS_DIR
        self.imap_server = "imap.gmail.com"
        self.smtp_server = "smtp.gmail.com"

    def _get_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """Retrieves Gmail credentials from memory or .env."""
        email_addr = os.getenv("GMAIL_USER") or os.getenv("EMAIL_USER")
        app_pwd = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("GMAIL_APP_PASS") or os.getenv("EMAIL_PASS")

        if not email_addr or not app_pwd:
            try:
                mem_path = os.path.join(self.jarvis_dir, "jarvis_memory.json")
                if os.path.exists(mem_path):
                    with open(mem_path, "r", encoding="utf-8") as f:
                        mem = json.load(f)
                        cfg = mem.get("gmail_config", {})
                        email_addr = email_addr or cfg.get("email")
                        app_pwd = app_pwd or cfg.get("app_password")
            except Exception:
                pass

        return email_addr, app_pwd

    def triage_inbox(self, max_emails: int = 8) -> Dict[str, Any]:
        """
        Connects via native IMAP SSL, filters high-priority emails,
        and generates an executive voice summary.
        """
        email_addr, app_pwd = self._get_credentials()
        if not email_addr or not app_pwd:
            webbrowser.open("https://mail.google.com/mail/u/0/#search/is%3Aunread+category%3Aprimary")
            return {
                "success": False,
                "needs_config": True,
                "spoken_debrief": "Opening your unread priority emails in Gmail.",
                "emails": []
            }

        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, port=993, timeout=6)
            mail.login(email_addr, app_pwd)
            mail.select("INBOX", readonly=True)

            status, response = mail.search(None, 'UNSEEN')
            msg_ids = response[0].split() if response and response[0] else []
            
            if not msg_ids:
                status, response = mail.search(None, 'ALL')
                msg_ids = response[0].split() if response and response[0] else []
                msg_ids = msg_ids[-max_emails:]
            else:
                msg_ids = msg_ids[-max_emails:]

            emails_data = []
            for mid in reversed(msg_ids):
                res, data = mail.fetch(mid, '(RFC822.HEADER BODY.PEEK[TEXT])')
                if res != 'OK': continue
                raw_msg = None
                for part in data:
                    if isinstance(part, tuple) and len(part) >= 2:
                        raw_msg = email.message_from_bytes(part[1])
                        break

                if not raw_msg: continue

                sender = decode_mime_words(raw_msg.get("From", ""))
                subject = decode_mime_words(raw_msg.get("Subject", "(No Subject)"))
                date_str = raw_msg.get("Date", "")
                is_bulk = bool(raw_msg.get("List-Unsubscribe") or raw_msg.get("Precedence") == "bulk")
                
                body_snippet = ""
                if raw_msg.is_multipart():
                    for p in raw_msg.walk():
                        if p.get_content_type() == "text/plain":
                            try:
                                body_snippet = p.get_payload(decode=True).decode("utf-8", errors="ignore")[:300]
                                break
                            except: pass
                else:
                    try:
                        body_snippet = raw_msg.get_payload(decode=True).decode("utf-8", errors="ignore")[:300]
                    except: pass

                emails_data.append({
                    "id": mid.decode(),
                    "sender": sender,
                    "subject": subject,
                    "date": date_str,
                    "is_bulk": is_bulk,
                    "snippet": body_snippet.strip().replace("\r", " ").replace("\n", " ")[:200]
                })

            mail.logout()

            priority_emails = [e for e in emails_data if not e["is_bulk"]]
            if not priority_emails:
                priority_emails = emails_data[:4]

            if not priority_emails:
                spoken = "Your inbox is completely clear. Zero unread priority emails."
            else:
                top = priority_emails[:3]
                summaries = []
                for idx, em in enumerate(top, 1):
                    s_clean = em['sender'].split('<')[0].replace('"', '').strip()
                    summaries.append(f"{s_clean} regarding '{em['subject']}'")
                spoken = f"You have {len(priority_emails)} priority messages. Notable: " + "; and ".join(summaries) + "."

            return {
                "success": True,
                "count": len(priority_emails),
                "emails": priority_emails,
                "spoken_debrief": spoken
            }

        except Exception as e:
            print(f"[Email Copilot] IMAP error: {e}")
            webbrowser.open("https://mail.google.com/mail/u/0/#search/is%3Aunread+category%3Aprimary")
            return {
                "success": False,
                "error": str(e),
                "spoken_debrief": "Opening your unread emails in Gmail.",
                "emails": []
            }

    def create_draft(self, recipient_email: str, subject: str, body_text: str, reply_to: Optional[str] = None) -> bool:
        """
        Directly injects a drafted reply into your Gmail Drafts folder via IMAP SSL.
        """
        email_addr, app_pwd = self._get_credentials()
        if not email_addr or not app_pwd:
            return False

        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, port=993, timeout=8)
            mail.login(email_addr, app_pwd)

            msg = MIMEMultipart()
            msg['From'] = email_addr
            msg['To'] = recipient_email
            msg['Subject'] = subject
            msg['Date'] = email.utils.formatdate(localtime=True)
            if reply_to:
                msg['In-Reply-To'] = reply_to
                msg['References'] = reply_to

            msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
            raw_msg_bytes = msg.as_bytes()

            draft_folder = "[Gmail]/Drafts"
            status, _ = mail.append(draft_folder, '\\Draft', imaplib.Time2Internaldate(time.time()), raw_msg_bytes)
            if status != 'OK':
                mail.append("Drafts", '\\Draft', imaplib.Time2Internaldate(time.time()), raw_msg_bytes)

            mail.logout()
            print(f"[Email Copilot] [DRAFT] Draft injected into Gmail Drafts folder for: {recipient_email}")
            return True
        except Exception as e:
            print(f"[Email Copilot] IMAP draft injection error: {e}")
            return False

    def open_web_compose(self, recipient_email: str, subject: str, body_text: str):
        """Opens Gmail web compose with pre-filled fields for immediate 1-click review/send."""
        encoded_to = urllib.parse.quote(recipient_email)
        encoded_su = urllib.parse.quote(subject)
        encoded_body = urllib.parse.quote(body_text)
        compose_url = f"https://mail.google.com/mail/u/0/?view=cm&fs=1&to={encoded_to}&su={encoded_su}&body={encoded_body}"
        print(f"[Email Copilot] [WEB COMPOSE] Launching Gmail Web Compose: {compose_url[:120]}...")
        webbrowser.open(compose_url)

    def draft_and_dispatch(
        self,
        recipient_email: str,
        subject: str,
        body_text: str,
        open_browser: bool = True,
        copy_clipboard: bool = True,
        update_status_fn: Optional[Callable[[Dict[str, Any]], None]] = None,
        speak_fn: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Complete end-to-end draft handling:
        1. Injects into Gmail IMAP drafts folder (if credentials exist).
        2. Copies full text to Windows clipboard.
        3. Renders full draft into HUD Response Monolith.
        4. Launches browser with pre-filled Gmail compose tab.
        5. Speaks verbal confirmation.
        """
        recipient_clean = resolve_recipient_email(recipient_email)
        
        # 1. Clipboard Copy
        if copy_clipboard:
            try:
                pyperclip.copy(body_text)
            except Exception:
                pass

        # 2. IMAP Draft Injection
        imap_success = self.create_draft(recipient_clean, subject, body_text)

        # 3. Web Compose Launch
        if open_browser:
            self.open_web_compose(recipient_clean, subject, body_text)

        # 4. HUD Monolith Update
        if update_status_fn:
            update_status_fn({
                "last_monolith_response": f"### DRAFT EMAIL CREATED\n**To:** {recipient_clean}\n**Subject:** {subject}\n\n---\n\n{body_text}",
                "email_draft_ready": True,
                "email_to": recipient_clean,
                "email_subject": subject
            })

        # 5. Spoken Confirmation
        if speak_fn:
            speak_fn(f"I have drafted and polished your email to {recipient_clean}, Sir. It is pre-loaded in your Gmail compose window and copied to your clipboard ready to send.")

        return {
            "success": True,
            "to": recipient_clean,
            "subject": subject,
            "body": body_text,
            "imap_saved": imap_success,
            "browser_opened": open_browser
        }

    def generate_and_stage_email(
        self,
        user_prompt: str,
        query_ai_fn: Optional[Callable[[str], str]] = None,
        speak_fn: Optional[Callable[[str], None]] = None,
        update_status_fn: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Synthesizes an executive, legally sound, polished email draft using AI,
        then stages it into Gmail Drafts + Browser Compose + Clipboard.
        """
        print(f"[Email Copilot] [DRAFTING] Generating polished email for prompt: '{user_prompt}'")
        
        if speak_fn:
            speak_fn("Drafting and polishing your email with high-priority grievance formatting, Sir...")

        # Extract recipient hint
        recipient = "care@policybazaar.com"
        for comp, em in KNOWN_COMPANY_EMAILS.items():
            if comp in user_prompt.lower():
                recipient = em
                break
        
        raw_email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', user_prompt)
        if raw_email_match:
            recipient = raw_email_match.group(0)

        ai_prompt = f"""You are Point Break — Daksh's Lead Executive Chief of Staff and Communication Strategist.
Generate a formal, high-impact, legally articulate, and impeccably polished email based on this request:
"{user_prompt}"

Target Company/Recipient: {recipient}

Requirements:
1. SUBJECT LINE: Must be razor-sharp, urgent, and include policy/ticket escalation placeholders (e.g. "URGENT: Escalation Regarding Health Insurance Policy Service & Immediate Resolution Required - [Policy/Ref #]").
2. SALUTATION: Professional (e.g. "Dear PolicyBazaar Grievance & Customer Response Team,").
3. BODY:
   - State the core issue and frustration with utmost professionalism and authority.
   - Demand immediate direct connection with the specialized health insurance response team.
   - Provide clean placeholders for Policy Number, Registered Mobile, and Transaction Reference.
   - Outline expectations for response within 24-48 hours.
4. SIGN-OFF: Professional closing from Daksh.

FORMAT YOUR RESPONSE EXACTLY AS VALID JSON (no markdown formatting around it, just JSON):
{{
  "to": "{recipient}",
  "subject": "<Subject Line>",
  "body": "<Complete Email Body Text with newlines>"
}}"""

        api_key = os.getenv("GEMINI_API_KEY")
        json_data = None

        if api_key:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": ai_prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048}
            }
            try:
                res = requests.post(url, json=payload, timeout=8.0)
                if res.status_code == 200:
                    data = res.json()
                    raw_text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    clean_j = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.I)
                    clean_j = re.sub(r"\s*```$", "", clean_j.strip())
                    json_data = json.loads(clean_j)
            except Exception as e:
                print(f"[Email Copilot] Direct API generation error: {e}")

        if not json_data and query_ai_fn:
            try:
                raw_resp = query_ai_fn(ai_prompt)
                clean_j = re.sub(r"^```(?:json)?\s*", "", raw_resp.strip(), flags=re.I)
                clean_j = re.sub(r"\s*```$", "", clean_j.strip())
                json_data = json.loads(clean_j)
            except Exception:
                pass

        if not json_data:
            # High-grade fallback template
            sub = "URGENT: Formal Escalation Regarding Health Insurance Policy Support & Response Required - [Ref: Policy #]"
            body = (
                "Dear PolicyBazaar Customer Support & Grievance Redressal Team,\n\n"
                "I am writing to formally escalate critical issues encountered with my health insurance policy services facilitated through your platform.\n\n"
                "Despite previous communication attempts, the resolution remains pending, causing undue operational delay and inconvenience. "
                "I hereby request immediate escalation and direct connection with your senior Health Insurance Response & Claims Support Team.\n\n"
                "Policy & Account Details for Immediate Verification:\n"
                "- Registered Name: Daksh\n"
                "- Policy / Application Reference Number: [PLEASE INSERT POLICY NUMBER]\n"
                "- Registered Mobile Number: [PLEASE INSERT MOBILE NUMBER]\n"
                "- Registered Email: [PLEASE INSERT REGISTERED EMAIL]\n"
                "- Health Insurance Provider / Plan: [PLEASE INSERT INSURER NAME]\n\n"
                "Grievance Summary:\n"
                "- Critical delay / discrepancy in policy issuance / endorsement / claims response.\n"
                "- Lack of timely updates from the allocated support representative.\n\n"
                "Please have a dedicated senior representative from your health insurance response desk connect with me directly within 24 hours to resolve this matter.\n\n"
                "Sincerely,\n"
                "Daksh\n"
                "Founder, PreciCode\n"
            )
            json_data = {
                "to": recipient,
                "subject": sub,
                "body": body
            }

        return self.draft_and_dispatch(
            recipient_email=json_data.get("to", recipient),
            subject=json_data.get("subject", "Formal Support Escalation"),
            body_text=json_data.get("body", ""),
            open_browser=True,
            copy_clipboard=True,
            update_status_fn=update_status_fn,
            speak_fn=speak_fn
        )


# Global singleton
email_copilot = EmailCopilot()
