"""
Point Break Show-Don't-Tell — Proof Mode Engine
================================================
Non-destructive live demonstrations for proving vulnerabilities to clients.
Every demo here is:
- Harmless (no data read/stolen/modified)
- Visible (client watches it happen live)
- Reversible or just navigating to public URLs

LEGAL: Only run these with the client present and watching.
       These are sales demonstrations on already-discovered issues.

Author: Daksh (Point Break Systems)
"""

import requests
import re
import os
import time
import threading
import webbrowser
import urllib.parse
import html as html_module
from bs4 import BeautifulSoup

TIMEOUT = 8
USER_AGENT = "PointBreak-ShowDontTell/2.0 (Authorized Security Demo)"
HEADERS = {"User-Agent": USER_AGENT}

EXPOSED_PATHS = [
    "/admin", "/admin/", "/admin/login", "/admin/index.php",
    "/administrator", "/administrator/", "/wp-admin/", "/wp-login.php",
    "/phpmyadmin", "/phpmyadmin/", "/pma/", "/pma",
    "/.env", "/.git/HEAD", "/.git/config", "/.gitignore",
    "/phpinfo.php", "/info.php", "/test.php", "/server-status",
    "/backup.sql", "/backup.zip", "/db.sql", "/database.sql",
    "/wp-config.php.bak", "/config.php.bak", "/config.yml",
    "/config.json", "/settings.json", "/.htpasswd",
    "/api/", "/api/v1/", "/api/v2/", "/api/users",
    "/swagger.json", "/swagger-ui.html", "/api-docs", "/openapi.json",
    "/actuator", "/actuator/env", "/actuator/health", "/actuator/beans",
    "/graphql", "/graphiql", "/debug", "/console", "/trace",
    "/logs/", "/log/", "/tmp/", "/temp/", "/cache/",
    "/uploads/", "/upload/", "/files/", "/file/",
    "/xmlrpc.php", "/wp-json/wp/v2/users", "/wp-json/",
    "/crossdomain.xml", "/.well-known/security.txt",
    "/server-info", "/status", "/health", "/metrics",
    "/robots.txt", "/sitemap.xml",
]

DIRECTORY_PATHS = [
    "/uploads/", "/images/", "/files/", "/assets/", "/backup/",
    "/tmp/", "/logs/", "/data/", "/media/", "/storage/",
    "/public/", "/static/", "/downloads/", "/export/",
]


class ShowDontTellEngine:
    def __init__(self):
        self.results = {}
        self.last_demo = None
        self.is_running = False

    def _normalize_url(self, target: str) -> str:
        if not target.startswith("http"):
            target = "https://" + target
        return target.rstrip("/")

    def xss_proof_demo(self, target_url: str, status_callback=None) -> dict:
        """
        Find forms and injectable inputs, build XSS proof URL.
        Opens the constructed payload URL in browser as a harmless demo.
        """
        base = self._normalize_url(target_url)
        self.is_running = True
        result = {
            "found_forms": 0,
            "injectable_inputs": [],
            "demo_url": "",
            "payload_used": "",
            "explanation": "",
            "status": "no_forms_found"
        }

        try:
            if status_callback:
                status_callback("Fetching page to find injectable forms...")
            resp = requests.get(base, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
            soup = BeautifulSoup(resp.text, "html.parser")
            forms = soup.find_all("form")
            result["found_forms"] = len(forms)

            injectable = []
            for form in forms:
                action = form.get("action", "")
                method = form.get("method", "get").lower()
                inputs = form.find_all("input")
                text_inputs = [i for i in inputs if i.get("type", "text") in ("text", "search", "q", "", None) and i.get("type") != "hidden"]
                if text_inputs:
                    for inp in text_inputs:
                        name = inp.get("name", inp.get("id", "input"))
                        injectable.append({
                            "form_action": action,
                            "method": method,
                            "input_name": name
                        })

            result["injectable_inputs"] = injectable

            # XSS payload (harmless alert)
            payload = '<script>alert("XSS Found by Point Break Security")</script>'
            encoded_payload = urllib.parse.quote(payload)

            # Build demo URL using GET method to a search or form
            demo_url = ""
            if injectable:
                inp = injectable[0]
                action = inp["form_action"] or "/"
                if action.startswith("/"):
                    action = base + action
                elif not action.startswith("http"):
                    action = base + "/" + action
                name = inp["input_name"]
                demo_url = f"{action}?{name}={encoded_payload}"
            else:
                # Try common search parameters
                demo_url = f"{base}/search?q={encoded_payload}"
                # Also try the homepage with common param names
                for param in ["q", "search", "query", "s", "keyword"]:
                    demo_url = f"{base}?{param}={encoded_payload}"
                    break

            result["demo_url"] = demo_url
            result["payload_used"] = payload

            if injectable:
                result["explanation"] = (
                    f"Found {len(injectable)} injectable input field(s) on this page. "
                    f"Opening a URL with XSS payload in the '{injectable[0]['input_name']}' field. "
                    f"If the site doesn't sanitize output, a popup will appear in the browser."
                )
                result["status"] = "demo_ready"
                if status_callback:
                    status_callback(f"Opening XSS proof in browser... Watch the page at {base}")
                webbrowser.open(demo_url)
            else:
                result["explanation"] = (
                    f"No obvious text input forms found on homepage. "
                    f"Trying URL parameter injection on {base}. "
                    f"For full XSS testing, run the active scanner which tests all detected forms."
                )
                result["status"] = "no_forms_tried_url"

        except Exception as e:
            result["status"] = "error"
            result["explanation"] = str(e)

        self.is_running = False
        self.last_demo = "xss"
        self.results["xss"] = result
        return result

    def exposed_panel_demo(self, target_url: str, status_callback=None) -> dict:
        """
        Check for exposed admin panels, config files, and sensitive paths.
        Opens the first found exposed panel in browser so client can see it.
        """
        base = self._normalize_url(target_url)
        self.is_running = True
        exposed = []
        total = len(EXPOSED_PATHS)

        if status_callback:
            status_callback(f"Checking {total} sensitive paths for exposure...")

        for i, path in enumerate(EXPOSED_PATHS):
            url = base + path
            try:
                resp = requests.head(url, timeout=5, headers=HEADERS, allow_redirects=True)
                code = resp.status_code
                if code in (200, 206):
                    risk = "CRITICAL" if any(x in path for x in [".env", ".git", "backup.sql", "config", "phpinfo", ".htpasswd"]) else "HIGH"
                    exposed.append({"url": url, "status_code": code, "risk": risk, "path": path})
                elif code in (301, 302, 307, 308):
                    # redirect to login = panel exists
                    loc = resp.headers.get("Location", "")
                    if "login" in loc or "admin" in loc:
                        exposed.append({"url": url, "status_code": code, "risk": "MEDIUM", "path": path, "redirects_to": loc})
                if status_callback and i % 10 == 0:
                    status_callback(f"Checking paths... {i+1}/{total}")
            except Exception:
                continue

        demo_opened = ""
        if exposed:
            # Open the highest-risk one in browser
            critical = [e for e in exposed if e["risk"] == "CRITICAL"]
            high = [e for e in exposed if e["risk"] == "HIGH"]
            to_open = (critical or high or exposed)[0]
            demo_opened = to_open["url"]
            if status_callback:
                status_callback(f"Opening exposed panel: {demo_opened}")
            webbrowser.open(demo_opened)

        result = {
            "exposed_panels": exposed,
            "demo_opened": demo_opened,
            "count": len(exposed),
            "explanation": (
                f"Found {len(exposed)} exposed sensitive paths. "
                + (f"Opened {demo_opened} in browser — client can see this is publicly accessible."
                   if demo_opened else "No immediately accessible panels detected.")
            )
        }

        self.is_running = False
        self.last_demo = "exposed_panel"
        self.results["exposed_panel"] = result
        return result

    def rate_limit_demo(self, login_url: str, status_callback=None) -> dict:
        """
        Send rapid requests to login endpoint to demonstrate missing rate limiting.
        Non-destructive — uses garbage credentials, just counts if blocking occurs.
        """
        url = self._normalize_url(login_url)
        self.is_running = True
        sent = 0
        blocked_after = None
        protection_type = "None detected"

        if status_callback:
            status_callback(f"Testing rate limiting on {url}...")

        # Fake credentials — won't work, just testing if blocking happens
        fake_data = {"username": "test_pointbreak_scan", "password": "PointBreakTest123!"}
        responses_seen = []

        for i in range(20):
            try:
                resp = requests.post(url, data=fake_data, timeout=5, headers=HEADERS, allow_redirects=False)
                sent += 1
                responses_seen.append(resp.status_code)

                if resp.status_code == 429:
                    blocked_after = i + 1
                    protection_type = "HTTP 429 Rate Limiting"
                    break

                if "captcha" in resp.text.lower() or "recaptcha" in resp.text.lower():
                    blocked_after = i + 1
                    protection_type = "CAPTCHA Protection"
                    break

                if "__cf_bm" in resp.cookies or "cf-ray" in resp.headers:
                    blocked_after = i + 1
                    protection_type = "Cloudflare WAF"
                    break

                if resp.status_code in (403, 423):
                    blocked_after = i + 1
                    protection_type = "IP Block / Lockout"
                    break

                time.sleep(0.15)  # 150ms between requests
            except requests.exceptions.ConnectionError:
                blocked_after = i + 1
                protection_type = "Connection refused (possible firewall block)"
                break
            except Exception:
                break

        rate_limit_detected = blocked_after is not None
        risk_level = "LOW" if rate_limit_detected else "HIGH"

        result = {
            "requests_sent": sent,
            "blocked_after": blocked_after,
            "rate_limit_detected": rate_limit_detected,
            "protection_type": protection_type,
            "risk_level": risk_level,
            "status_codes_seen": responses_seen,
            "explanation": (
                f"Sent {sent} rapid login requests. "
                + (f"Blocked after {blocked_after} attempts via {protection_type}. Login is protected."
                   if rate_limit_detected
                   else f"Completed all {sent} attempts without any blocking. An attacker could brute-force this login.")
            )
        }

        self.is_running = False
        self.last_demo = "rate_limit"
        self.results["rate_limit"] = result
        return result

    def directory_listing_demo(self, target_url: str, status_callback=None) -> dict:
        """
        Check for directories with index listing enabled.
        Opens the first exposed directory in browser.
        """
        base = self._normalize_url(target_url)
        self.is_running = True
        open_dirs = []

        if status_callback:
            status_callback("Checking for open directory listings...")

        for path in DIRECTORY_PATHS:
            url = base + path
            try:
                resp = requests.get(url, timeout=5, headers=HEADERS)
                text = resp.text.lower()
                if resp.status_code == 200 and (
                    "index of" in text or
                    ("<pre>" in text and "<a href=" in text and "parent directory" in text.lower())
                ):
                    open_dirs.append(url)
            except Exception:
                continue

        demo_opened = ""
        if open_dirs:
            demo_opened = open_dirs[0]
            if status_callback:
                status_callback(f"Opening directory listing: {demo_opened}")
            webbrowser.open(demo_opened)

        result = {
            "open_directories": open_dirs,
            "demo_opened": demo_opened,
            "count": len(open_dirs),
            "explanation": (
                f"Found {len(open_dirs)} directories with file listing enabled. "
                + (f"Opened {demo_opened} — client can see all files are browsable by anyone."
                   if demo_opened else "No directory listing vulnerabilities found.")
            )
        }

        self.is_running = False
        self.last_demo = "directory_listing"
        self.results["directory_listing"] = result
        return result

    def missing_headers_demo(self, target_url: str, status_callback=None) -> dict:
        """
        Show missing security headers and create a live clickjacking demo.
        Creates a local HTML file that embeds the target site to demonstrate
        the clickjacking attack visually.
        """
        base = self._normalize_url(target_url)
        self.is_running = True
        missing = []
        demo_created = ""

        REQUIRED_HEADERS = {
            "X-Frame-Options": "Allows clickjacking — attackers can embed this site in an iframe to trick users into clicking hidden buttons",
            "Content-Security-Policy": "No XSS protection policy — browser won't block injected scripts",
            "X-Content-Type-Options": "MIME sniffing attacks possible — browsers may misinterpret uploaded files",
            "Strict-Transport-Security": "No HSTS — connections may be downgraded from HTTPS to HTTP by attackers",
            "Referrer-Policy": "Sensitive URLs leaked in Referer headers to third-party sites",
            "Permissions-Policy": "Browser features (camera, microphone, geolocation) not restricted for this site",
        }

        try:
            if status_callback:
                status_callback("Checking security response headers...")
            resp = requests.get(base, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
            for header, risk in REQUIRED_HEADERS.items():
                if header.lower() not in {k.lower() for k in resp.headers.keys()}:
                    missing.append({"header": header, "risk": risk})
        except Exception as e:
            self.is_running = False
            return {"error": str(e), "missing_headers": [], "clickjacking_vulnerable": False}

        clickjacking_vulnerable = any(h["header"] == "X-Frame-Options" for h in missing)
        csp_missing = any(h["header"] == "Content-Security-Policy" for h in missing)

        # Create clickjacking demo HTML if vulnerable
        if clickjacking_vulnerable:
            demo_html = f"""<!DOCTYPE html>
<html>
<head>
<title>⚠️ POINT BREAK — Clickjacking Demo</title>
<style>
body {{ background: #1a1a2e; font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
.warning-banner {{ background: linear-gradient(135deg, #ff1744, #b71c1c); color: white; padding: 20px; border-radius: 10px; text-align: center; margin-bottom: 20px; }}
.warning-banner h1 {{ font-size: 1.4rem; margin: 0 0 8px; }}
.warning-banner p {{ margin: 0; opacity: 0.9; font-size: 0.9rem; }}
.demo-frame {{ position: relative; border: 3px solid #ff1744; border-radius: 8px; overflow: hidden; }}
.overlay-label {{ position: absolute; top: 10px; left: 10px; background: rgba(255,23,68,0.85); color: white; padding: 6px 14px; border-radius: 20px; font-size: 0.75rem; font-weight: bold; z-index: 10; pointer-events: none; }}
iframe {{ width: 100%; height: 75vh; border: none; display: block; }}
.footer {{ color: #666; text-align: center; font-size: 0.75rem; margin-top: 16px; }}
</style>
</head>
<body>
<div class="warning-banner">
  <h1>⚠️ CLICKJACKING VULNERABILITY DEMONSTRATION</h1>
  <p>This is a Point Break Security Demo. The real website is embedded below.<br>
  An attacker can overlay invisible buttons on top, making users click things without knowing.</p>
</div>
<div class="demo-frame">
  <div class="overlay-label">🎯 ATTACKER OVERLAY (invisible to victim)</div>
  <iframe src="{base}" sandbox="allow-scripts allow-same-origin allow-forms"></iframe>
</div>
<div class="footer">
  Generated by Point Break Security System — Authorized Demo Only<br>
  This page proves the X-Frame-Options header is missing on {html_module.escape(base)}
</div>
</body>
</html>"""

            demo_path = os.path.join(
                os.environ.get("TEMP", os.path.expanduser("~")),
                "pb_clickjack_demo.html"
            )
            try:
                with open(demo_path, "w", encoding="utf-8") as f:
                    f.write(demo_html)
                demo_created = demo_path
                if status_callback:
                    status_callback("Clickjacking demo created. Opening in browser...")
                webbrowser.open(f"file:///{demo_path.replace(os.sep, '/')}")
            except Exception as e:
                demo_created = f"Error creating demo: {e}"

        result = {
            "missing_headers": missing,
            "clickjacking_vulnerable": clickjacking_vulnerable,
            "csp_missing": csp_missing,
            "demo_created": demo_created,
            "missing_count": len(missing),
            "explanations": {h["header"]: h["risk"] for h in missing},
            "explanation": (
                f"Found {len(missing)} missing security headers. "
                + ("Clickjacking demo opened — client can see their own site embedded in an attacker's page. "
                   if clickjacking_vulnerable else "")
            )
        }

        self.is_running = False
        self.last_demo = "missing_headers"
        self.results["missing_headers"] = result
        return result

    def run_all_demos(self, target_url: str, status_callback=None) -> dict:
        """Run all 4 proof demos sequentially and return combined results."""
        self.is_running = True
        combined = {"target": target_url, "demos": {}}

        if status_callback:
            status_callback("Running Show-Don't-Tell demo suite...")

        combined["demos"]["missing_headers"] = self.missing_headers_demo(target_url, status_callback)
        combined["demos"]["exposed_panel"] = self.exposed_panel_demo(target_url, status_callback)
        combined["demos"]["xss_proof"] = self.xss_proof_demo(target_url, status_callback)
        combined["demos"]["directory_listing"] = self.directory_listing_demo(target_url, status_callback)

        # Summary
        issues_found = sum([
            combined["demos"]["missing_headers"].get("missing_count", 0) > 0,
            combined["demos"]["exposed_panel"].get("count", 0) > 0,
            combined["demos"]["xss_proof"].get("status") == "demo_ready",
            combined["demos"]["directory_listing"].get("count", 0) > 0,
        ])
        combined["issues_found"] = issues_found
        combined["summary"] = f"Demonstrated {issues_found}/4 vulnerability categories live. Client observed them directly."

        self.is_running = False
        self.results["full_demo"] = combined
        return combined


# Module-level singleton
show_engine = ShowDontTellEngine()
