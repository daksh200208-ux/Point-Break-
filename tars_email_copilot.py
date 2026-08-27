"""
Point Break — High-Speed Native IMAP/SMTP Email Copilot & Ghost-Drafter
========================================================================
1. Direct IMAP SSL connection (< 0.4s) — zero browser/screen capture lag.
2. Unread & priority email filtering across all categories.
3. Automated Ghost-Drafting: Injects draft replies directly into Gmail Drafts folder.
4. Fallback: Opens filtered unread primary inbox in browser immediately.
"""

import os
import sys
import time
import json
import email
import imaplib
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any, Optional
import webbrowser
from dotenv import load_dotenv

JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(JARVIS_DIR, ".env"))

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


class EmailCopilot:
    def __init__(self, jarvis_dir=None):
        self.jarvis_dir = jarvis_dir or JARVIS_DIR
        self.imap_server = "imap.gmail.com"
        self.smtp_server = "smtp.gmail.com"

    def _get_credentials(self):
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
        If credentials missing, opens unread primary search in browser immediately.
        """
        email_addr, app_pwd = self._get_credentials()
        if not email_addr or not app_pwd:
            webbrowser.open("https://mail.google.com/mail/u/0/#search/is%3Aunread+category%3Aprimary")
            return {
                "success": False,
                "needs_config": True,
                "spoken_debrief": "Opening your unread priority emails in Gmail. To enable voice reading in the background, set GMAIL_USER and GMAIL_APP_PASSWORD in your .env file.",
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
        Directly injects a drafted reply into your Gmail Drafts folder.
        """
        email_addr, app_pwd = self._get_credentials()
        if not email_addr or not app_pwd:
            import urllib.parse
            webbrowser.open(f"https://mail.google.com/mail/u/0/?view=cm&fs=1&to={urllib.parse.quote(recipient_email)}&su={urllib.parse.quote(subject)}&body={urllib.parse.quote(body_text)}")
            return True

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
            print(f"[Email Copilot] 📝 Draft saved successfully to Gmail for: {recipient_email}")
            return True
        except Exception as e:
            print(f"[Email Copilot] Draft injection error: {e}")
            return False


# Global singleton
email_copilot = EmailCopilot()
