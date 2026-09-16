"""
Point Break Cyber Arsenal — Penetration Testing & Web Vulnerability Scanner
===========================================================================
Professional-grade security auditing engine for Default Point Break.
Provides 6 integrated scanners and generates executive HTML threat reports.

LEGAL: All scans require written authorization from the target owner.
       Unauthorized scanning is illegal.

Author: Daksh (Point Break Systems)
"""

import requests
import ssl
import socket
import re
import json
import time
import datetime
import html as html_module
import threading
import os
import urllib.parse
from bs4 import BeautifulSoup
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

SCAN_TIMEOUT = 8          # seconds per request
MAX_THREADS = 4           # concurrent probe threads
USER_AGENT = "PointBreak-CyberArsenal/1.0 (Security Audit)"
REPORT_DIR = Path(os.path.expanduser("~")) / "Desktop"

# Common directory/file paths to probe
SENSITIVE_PATHS = [
    "/.env", "/.git/HEAD", "/.git/config", "/.gitignore",
    "/wp-admin/", "/wp-login.php", "/administrator/",
    "/admin/", "/admin/login", "/login", "/dashboard",
    "/phpinfo.php", "/info.php", "/server-status", "/server-info",
    "/backup.sql", "/backup.zip", "/db.sql", "/database.sql",
    "/.htaccess", "/.htpasswd", "/web.config",
    "/robots.txt", "/sitemap.xml", "/crossdomain.xml",
    "/api/", "/api/v1/", "/swagger.json", "/api-docs",
    "/.well-known/security.txt", "/security.txt",
    "/wp-config.php.bak", "/config.php.bak", "/config.yml",
    "/.DS_Store", "/thumbs.db",
    "/xmlrpc.php", "/wp-json/wp/v2/users",
    "/cgi-bin/", "/phpmyadmin/", "/pma/",
    "/console", "/debug", "/trace",
]

# SQL Injection test payloads (benign, detection-only)
SQLI_PAYLOADS = [
    "' OR '1'='1",
    "' OR '1'='1'--",
    "\" OR \"1\"=\"1",
    "' UNION SELECT NULL--",
    "1; DROP TABLE test--",
    "' AND 1=CONVERT(int, @@version)--",
    "admin'--",
]

# SQL error signatures that indicate vulnerability
SQL_ERROR_SIGNATURES = [
    "you have an error in your sql syntax",
    "warning: mysql_",
    "unclosed quotation mark",
    "quoted string not properly terminated",
    "microsoft ole db provider for sql server",
    "ora-01756",
    "postgresql query failed",
    "sqlite3.operationalerror",
    "pg_query",
    "mysql_fetch",
    "sql syntax",
    "sqlstate",
    "odbc sql server driver",
    "syntax error at or near",
    "unterminated string",
    "microsoft jet database engine",
]

# XSS test payloads
XSS_PAYLOADS = [
    '<script>alert("PB_XSS_TEST")</script>',
    '"><img src=x onerror=alert("PB_XSS")>',
    "javascript:alert('PB_XSS')",
    '<svg onload=alert("PB_XSS")>',
    "'\"><svg/onload=alert('PB_XSS')>",
]

# Security headers to check
SECURITY_HEADERS = {
    "Strict-Transport-Security": {
        "name": "HSTS",
        "severity": "HIGH",
        "description": "Prevents protocol downgrade attacks and cookie hijacking",
        "fix": "Add header: Strict-Transport-Security: max-age=31536000; includeSubDomains"
    },
    "Content-Security-Policy": {
        "name": "CSP",
        "severity": "HIGH",
        "description": "Prevents XSS, clickjacking, and code injection attacks",
        "fix": "Add a Content-Security-Policy header restricting script and resource origins"
    },
    "X-Frame-Options": {
        "name": "X-Frame-Options",
        "severity": "MEDIUM",
        "description": "Prevents clickjacking by controlling iframe embedding",
        "fix": "Add header: X-Frame-Options: DENY or SAMEORIGIN"
    },
    "X-Content-Type-Options": {
        "name": "X-Content-Type-Options",
        "severity": "MEDIUM",
        "description": "Prevents MIME-sniffing attacks",
        "fix": "Add header: X-Content-Type-Options: nosniff"
    },
    "X-XSS-Protection": {
        "name": "X-XSS-Protection",
        "severity": "LOW",
        "description": "Legacy XSS filter (still useful for older browsers)",
        "fix": "Add header: X-XSS-Protection: 1; mode=block"
    },
    "Referrer-Policy": {
        "name": "Referrer-Policy",
        "severity": "LOW",
        "description": "Controls referrer information sent with requests",
        "fix": "Add header: Referrer-Policy: strict-origin-when-cross-origin"
    },
    "Permissions-Policy": {
        "name": "Permissions-Policy",
        "severity": "LOW",
        "description": "Controls browser feature access (camera, microphone, geolocation)",
        "fix": "Add header: Permissions-Policy: camera=(), microphone=(), geolocation=()"
    },
}

# ═══════════════════════════════════════════════════════════════════════
# SEVERITY LEVELS
# ═══════════════════════════════════════════════════════════════════════

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"
SEVERITY_INFO = "INFO"

SEVERITY_COLORS = {
    SEVERITY_CRITICAL: "#ff1744",
    SEVERITY_HIGH: "#ff6d00",
    SEVERITY_MEDIUM: "#ffab00",
    SEVERITY_LOW: "#2979ff",
    SEVERITY_INFO: "#00e676",
}

SEVERITY_ICONS = {
    SEVERITY_CRITICAL: "🔴",
    SEVERITY_HIGH: "🟠",
    SEVERITY_MEDIUM: "🟡",
    SEVERITY_LOW: "🔵",
    SEVERITY_INFO: "🟢",
}

# ═══════════════════════════════════════════════════════════════════════
# VULNERABILITY DATA CLASS
# ═══════════════════════════════════════════════════════════════════════

class Vulnerability:
    """Represents a single discovered vulnerability."""
    def __init__(self, title, severity, category, description, evidence="", fix="", owasp=""):
        self.title = title
        self.severity = severity
        self.category = category
        self.description = description
        self.evidence = evidence
        self.fix = fix
        self.owasp = owasp
        self.timestamp = datetime.datetime.now().isoformat()

    def to_dict(self):
        return {
            "title": self.title,
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "evidence": self.evidence,
            "fix": self.fix,
            "owasp": self.owasp,
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════════
# CYBER ARSENAL ENGINE
# ═══════════════════════════════════════════════════════════════════════

class CyberArsenalEngine:
    """Point Break Cyber Arsenal — Penetration Testing Engine."""

    def __init__(self):
        self.is_scanning = False
        self.scan_progress = 0
        self.scan_phase = ""
        self.current_target = ""
        self.vulnerabilities = []
        self.last_results = {}
        self.last_report_path = ""
        self.authorized = False
        self._lock = threading.Lock()
        self._session = None
        self._status_callback = None

    def _get_session(self):
        """Create a requests session with sensible defaults."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
            })
            self._session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return self._session

    def _emit(self, message):
        """Send status update to callback (voice/HUD)."""
        self.scan_phase = message
        if self._status_callback:
            try:
                self._status_callback(message)
            except Exception:
                pass

    def _normalize_url(self, url):
        """Ensure URL has a scheme."""
        url = url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        return url.rstrip("/")

    def _extract_domain(self, url):
        """Extract domain from URL."""
        parsed = urllib.parse.urlparse(url)
        return parsed.hostname or url

    # ───────────────────────────────────────────────────────────────
    # SCANNER 1: SSL/TLS SECURITY GRADER
    # ───────────────────────────────────────────────────────────────

    def scan_ssl(self, url):
        """Analyze SSL/TLS certificate and configuration."""
        findings = []
        domain = self._extract_domain(url)
        self._emit(f"Phase 1: SSL/TLS certificate analysis on {domain}...")
        self.scan_progress = 5

        try:
            context = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=SCAN_TIMEOUT) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()
                    protocol = ssock.version()
                    cipher = ssock.cipher()

                    # Check protocol version
                    if protocol in ("TLSv1", "TLSv1.1"):
                        findings.append(Vulnerability(
                            title=f"Deprecated TLS Version: {protocol}",
                            severity=SEVERITY_CRITICAL,
                            category="SSL/TLS",
                            description=f"Server supports {protocol} which is deprecated and vulnerable to POODLE/BEAST attacks.",
                            evidence=f"Negotiated protocol: {protocol}",
                            fix="Disable TLS 1.0 and 1.1. Configure server to only support TLS 1.2 and 1.3.",
                            owasp="A02:2021 Cryptographic Failures"
                        ))
                    elif protocol == "TLSv1.2":
                        findings.append(Vulnerability(
                            title=f"TLS Version: {protocol} (Acceptable)",
                            severity=SEVERITY_INFO,
                            category="SSL/TLS",
                            description=f"Server uses {protocol}. Consider upgrading to TLS 1.3 for improved security.",
                            evidence=f"Negotiated protocol: {protocol}",
                            fix="Enable TLS 1.3 support on the server.",
                            owasp="A02:2021 Cryptographic Failures"
                        ))

                    # Check certificate expiry
                    if cert.get("notAfter"):
                        expire_date = ssl.cert_time_to_seconds(cert["notAfter"])
                        now = time.time()
                        days_left = (expire_date - now) / 86400

                        if days_left < 0:
                            findings.append(Vulnerability(
                                title="SSL Certificate EXPIRED",
                                severity=SEVERITY_CRITICAL,
                                category="SSL/TLS",
                                description=f"Certificate expired {abs(int(days_left))} days ago.",
                                evidence=f"Expiry: {cert['notAfter']}",
                                fix="Renew the SSL certificate immediately.",
                                owasp="A02:2021 Cryptographic Failures"
                            ))
                        elif days_left < 30:
                            findings.append(Vulnerability(
                                title=f"SSL Certificate Expiring Soon ({int(days_left)} days)",
                                severity=SEVERITY_HIGH,
                                category="SSL/TLS",
                                description=f"Certificate expires in {int(days_left)} days.",
                                evidence=f"Expiry: {cert['notAfter']}",
                                fix="Renew the SSL certificate before expiry. Consider Let's Encrypt for auto-renewal.",
                                owasp="A02:2021 Cryptographic Failures"
                            ))

                    # Check cipher strength
                    if cipher:
                        cipher_name = cipher[0]
                        if any(w in cipher_name.upper() for w in ["RC4", "DES", "MD5", "NULL", "EXPORT"]):
                            findings.append(Vulnerability(
                                title=f"Weak Cipher Suite: {cipher_name}",
                                severity=SEVERITY_HIGH,
                                category="SSL/TLS",
                                description="Server uses a weak or deprecated cipher suite.",
                                evidence=f"Cipher: {cipher_name}, Bits: {cipher[2]}",
                                fix="Disable weak ciphers. Use AES-256-GCM or ChaCha20-Poly1305.",
                                owasp="A02:2021 Cryptographic Failures"
                            ))

                    # Check hostname match
                    try:
                        ssl.match_hostname(cert, domain)
                    except ssl.CertificateError:
                        findings.append(Vulnerability(
                            title="SSL Certificate Hostname Mismatch",
                            severity=SEVERITY_HIGH,
                            category="SSL/TLS",
                            description="Certificate hostname does not match the target domain.",
                            evidence=f"Domain: {domain}, Cert Subject: {cert.get('subject', 'N/A')}",
                            fix="Obtain a certificate for the correct domain name.",
                            owasp="A02:2021 Cryptographic Failures"
                        ))

        except ssl.SSLCertVerificationError as e:
            findings.append(Vulnerability(
                title="SSL Certificate Verification Failed",
                severity=SEVERITY_CRITICAL,
                category="SSL/TLS",
                description=f"Certificate verification failed: {str(e)[:200]}",
                evidence=str(e)[:300],
                fix="Install a valid certificate from a trusted CA. Avoid self-signed certs in production.",
                owasp="A02:2021 Cryptographic Failures"
            ))
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            findings.append(Vulnerability(
                title="SSL/TLS Connection Failed",
                severity=SEVERITY_HIGH,
                category="SSL/TLS",
                description=f"Could not establish SSL connection to {domain}:443. Site may not support HTTPS.",
                evidence=str(e)[:200],
                fix="Enable HTTPS on the server with a valid SSL certificate.",
                owasp="A02:2021 Cryptographic Failures"
            ))

        self.scan_progress = 15
        return findings

    # ───────────────────────────────────────────────────────────────
    # SCANNER 2: SECURITY HEADERS ANALYZER
    # ───────────────────────────────────────────────────────────────

    def scan_headers(self, url):
        """Check for presence and quality of security headers."""
        findings = []
        self._emit(f"Phase 2: Security headers reconnaissance...")
        self.scan_progress = 20

        try:
            session = self._get_session()
            resp = session.get(url, timeout=SCAN_TIMEOUT, allow_redirects=True)
            headers = resp.headers

            for header_name, info in SECURITY_HEADERS.items():
                value = headers.get(header_name)
                if not value:
                    findings.append(Vulnerability(
                        title=f"Missing Security Header: {info['name']}",
                        severity=info["severity"],
                        category="Security Headers",
                        description=info["description"],
                        evidence=f"Header '{header_name}' not present in HTTP response.",
                        fix=info["fix"],
                        owasp="A05:2021 Security Misconfiguration"
                    ))
                else:
                    if header_name == "Content-Security-Policy":
                        if "unsafe-inline" in value or "unsafe-eval" in value:
                            findings.append(Vulnerability(
                                title="Weak Content-Security-Policy",
                                severity=SEVERITY_MEDIUM,
                                category="Security Headers",
                                description="CSP contains 'unsafe-inline' or 'unsafe-eval' which weakens XSS protection.",
                                evidence=f"CSP: {value[:200]}",
                                fix="Remove 'unsafe-inline' and 'unsafe-eval'. Use nonce-based or hash-based CSP.",
                                owasp="A05:2021 Security Misconfiguration"
                            ))
                        if "*" in value:
                            findings.append(Vulnerability(
                                title="Overly Permissive CSP Wildcard",
                                severity=SEVERITY_MEDIUM,
                                category="Security Headers",
                                description="CSP uses wildcard '*' which allows loading resources from any domain.",
                                evidence=f"CSP: {value[:200]}",
                                fix="Replace wildcards with specific trusted domains.",
                                owasp="A05:2021 Security Misconfiguration"
                            ))

            # Check for information disclosure headers
            server_header = headers.get("Server", "")
            if server_header and any(v in server_header.lower() for v in ["apache/", "nginx/", "iis/", "php/"]):
                findings.append(Vulnerability(
                    title=f"Server Version Disclosure: {server_header}",
                    severity=SEVERITY_LOW,
                    category="Security Headers",
                    description="Server header reveals software version, aiding targeted attacks.",
                    evidence=f"Server: {server_header}",
                    fix="Configure server to hide version info. Apache: ServerTokens Prod. Nginx: server_tokens off.",
                    owasp="A05:2021 Security Misconfiguration"
                ))

            x_powered = headers.get("X-Powered-By", "")
            if x_powered:
                findings.append(Vulnerability(
                    title=f"Technology Disclosure: X-Powered-By: {x_powered}",
                    severity=SEVERITY_LOW,
                    category="Security Headers",
                    description="X-Powered-By header reveals backend technology stack.",
                    evidence=f"X-Powered-By: {x_powered}",
                    fix="Remove the X-Powered-By header from server responses.",
                    owasp="A05:2021 Security Misconfiguration"
                ))

        except requests.RequestException as e:
            findings.append(Vulnerability(
                title="HTTP Connection Failed",
                severity=SEVERITY_INFO,
                category="Security Headers",
                description=f"Could not connect to {url} for header analysis.",
                evidence=str(e)[:200],
                fix="Ensure the target URL is accessible.",
                owasp=""
            ))

        self.scan_progress = 30
        return findings

    # ───────────────────────────────────────────────────────────────
    # SCANNER 3: DIRECTORY & SENSITIVE FILE DISCOVERY
    # ───────────────────────────────────────────────────────────────

    def scan_directories(self, url):
        """Probe for exposed directories and sensitive files."""
        findings = []
        self._emit(f"Phase 3: Directory and sensitive file discovery... probing {len(SENSITIVE_PATHS)} paths...")
        self.scan_progress = 35

        session = self._get_session()
        total = len(SENSITIVE_PATHS)

        for i, path in enumerate(SENSITIVE_PATHS):
            try:
                probe_url = url + path
                resp = session.get(probe_url, timeout=SCAN_TIMEOUT, allow_redirects=False)

                if resp.status_code == 200:
                    body_len = len(resp.content)
                    body_preview = resp.text[:200].strip()

                    if any(s in path for s in [".env", ".git", "backup", ".sql", "config", ".htpasswd"]):
                        severity = SEVERITY_CRITICAL
                        title = f"CRITICAL: Sensitive file exposed: {path}"
                        owasp = "A01:2021 Broken Access Control"
                    elif any(s in path for s in ["admin", "phpmyadmin", "console", "debug"]):
                        severity = SEVERITY_HIGH
                        title = f"Admin panel accessible: {path}"
                        owasp = "A01:2021 Broken Access Control"
                    elif any(s in path for s in ["phpinfo", "server-status", "server-info", "trace"]):
                        severity = SEVERITY_HIGH
                        title = f"Information disclosure endpoint: {path}"
                        owasp = "A05:2021 Security Misconfiguration"
                    elif any(s in path for s in ["wp-json/wp/v2/users", "xmlrpc", "swagger", "api-docs"]):
                        severity = SEVERITY_MEDIUM
                        title = f"API/Information endpoint exposed: {path}"
                        owasp = "A05:2021 Security Misconfiguration"
                    else:
                        severity = SEVERITY_INFO
                        title = f"Accessible path: {path}"
                        owasp = "A05:2021 Security Misconfiguration"

                    findings.append(Vulnerability(
                        title=title,
                        severity=severity,
                        category="Directory Exposure",
                        description=f"Path {path} returned HTTP 200 with {body_len} bytes of content.",
                        evidence=f"URL: {probe_url}\nStatus: 200\nPreview: {body_preview[:100]}",
                        fix=f"Restrict access to {path}. Add authentication or remove from production.",
                        owasp=owasp
                    ))
                elif resp.status_code == 403:
                    if any(s in path for s in [".env", ".git", "backup", ".sql", "config"]):
                        findings.append(Vulnerability(
                            title=f"Sensitive path exists but blocked: {path}",
                            severity=SEVERITY_LOW,
                            category="Directory Exposure",
                            description=f"Path {path} returned 403 Forbidden. File exists but access denied.",
                            evidence=f"URL: {probe_url}\nStatus: 403",
                            fix=f"Consider removing {path} entirely rather than just blocking access.",
                            owasp="A05:2021 Security Misconfiguration"
                        ))

            except requests.RequestException:
                pass

            self.scan_progress = 35 + int((i / total) * 15)

        self.scan_progress = 50
        return findings

    # ───────────────────────────────────────────────────────────────
    # SCANNER 4: SQL INJECTION DETECTION
    # ───────────────────────────────────────────────────────────────

    def scan_sqli(self, url):
        """Test for SQL injection vulnerabilities."""
        findings = []
        self._emit(f"Phase 4: SQL injection vector testing...")
        self.scan_progress = 55

        session = self._get_session()

        try:
            resp = session.get(url, timeout=SCAN_TIMEOUT)
            soup = BeautifulSoup(resp.text, "html.parser")
            forms = soup.find_all("form")

            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)

            form_count = len(forms)
            self._emit(f"Phase 4: SQL injection testing on {form_count} forms and URL params...")

            for form in forms:
                action = form.get("action", "")
                method = form.get("method", "get").lower()
                form_url = urllib.parse.urljoin(url, action) if action else url

                inputs = form.find_all(["input", "textarea"])
                for payload in SQLI_PAYLOADS[:4]:
                    form_data = {}
                    for inp in inputs:
                        name = inp.get("name", "")
                        if not name:
                            continue
                        inp_type = inp.get("type", "text").lower()
                        if inp_type in ("submit", "button", "image", "reset", "hidden"):
                            form_data[name] = inp.get("value", "")
                        else:
                            form_data[name] = payload

                    try:
                        if method == "post":
                            test_resp = session.post(form_url, data=form_data, timeout=SCAN_TIMEOUT, allow_redirects=True)
                        else:
                            test_resp = session.get(form_url, params=form_data, timeout=SCAN_TIMEOUT, allow_redirects=True)

                        response_text = test_resp.text.lower()

                        for sig in SQL_ERROR_SIGNATURES:
                            if sig in response_text:
                                findings.append(Vulnerability(
                                    title=f"SQL Injection Detected on {form_url}",
                                    severity=SEVERITY_CRITICAL,
                                    category="SQL Injection",
                                    description=f"Form at {form_url} is vulnerable to SQL injection. Database error leaked in response.",
                                    evidence=f"Payload: {payload}\nError signature: '{sig}' found in response\nForm method: {method.upper()}",
                                    fix="Use parameterized queries / prepared statements. Never concatenate user input into SQL queries. Implement input validation and WAF.",
                                    owasp="A03:2021 Injection"
                                ))
                                break

                    except requests.RequestException:
                        pass

            if params:
                for param_name in params:
                    for payload in SQLI_PAYLOADS[:3]:
                        test_params = dict(params)
                        test_params[param_name] = payload
                        try:
                            test_url = parsed._replace(query=urllib.parse.urlencode(test_params, doseq=True)).geturl()
                            test_resp = session.get(test_url, timeout=SCAN_TIMEOUT, allow_redirects=True)
                            response_text = test_resp.text.lower()

                            for sig in SQL_ERROR_SIGNATURES:
                                if sig in response_text:
                                    findings.append(Vulnerability(
                                        title=f"SQL Injection via URL Parameter: {param_name}",
                                        severity=SEVERITY_CRITICAL,
                                        category="SQL Injection",
                                        description=f"URL parameter '{param_name}' is vulnerable to SQL injection.",
                                        evidence=f"Payload: {payload}\nError: '{sig}'\nURL: {test_url[:200]}",
                                        fix="Use parameterized queries. Validate and sanitize all URL parameters.",
                                        owasp="A03:2021 Injection"
                                    ))
                                    break
                        except requests.RequestException:
                            pass

        except requests.RequestException as e:
            self._emit(f"SQL injection scan: connection issue — {str(e)[:80]}")

        self.scan_progress = 65
        return findings

    # ───────────────────────────────────────────────────────────────
    # SCANNER 5: XSS (CROSS-SITE SCRIPTING) DETECTION
    # ───────────────────────────────────────────────────────────────

    def scan_xss(self, url):
        """Test for reflected XSS vulnerabilities."""
        findings = []
        self._emit(f"Phase 5: Cross-site scripting probe on input fields...")
        self.scan_progress = 68

        session = self._get_session()

        try:
            resp = session.get(url, timeout=SCAN_TIMEOUT)
            soup = BeautifulSoup(resp.text, "html.parser")
            forms = soup.find_all("form")

            for form in forms:
                action = form.get("action", "")
                method = form.get("method", "get").lower()
                form_url = urllib.parse.urljoin(url, action) if action else url
                inputs = form.find_all(["input", "textarea"])

                for payload in XSS_PAYLOADS[:3]:
                    form_data = {}
                    for inp in inputs:
                        name = inp.get("name", "")
                        if not name:
                            continue
                        inp_type = inp.get("type", "text").lower()
                        if inp_type in ("submit", "button", "image", "reset", "hidden"):
                            form_data[name] = inp.get("value", "")
                        else:
                            form_data[name] = payload

                    try:
                        if method == "post":
                            test_resp = session.post(form_url, data=form_data, timeout=SCAN_TIMEOUT, allow_redirects=True)
                        else:
                            test_resp = session.get(form_url, params=form_data, timeout=SCAN_TIMEOUT, allow_redirects=True)

                        if payload in test_resp.text:
                            findings.append(Vulnerability(
                                title=f"Reflected XSS Detected on {form_url}",
                                severity=SEVERITY_HIGH,
                                category="Cross-Site Scripting",
                                description=f"Form at {form_url} reflects user input without sanitization.",
                                evidence=f"Payload: {payload}\nReflected unescaped in response body.\nForm method: {method.upper()}",
                                fix="Sanitize and HTML-encode all user input before rendering. Implement Content-Security-Policy header.",
                                owasp="A07:2021 Cross-Site Scripting"
                            ))
                            break

                    except requests.RequestException:
                        pass

            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            if params:
                for param_name in params:
                    for payload in XSS_PAYLOADS[:2]:
                        test_params = dict(params)
                        test_params[param_name] = payload
                        try:
                            test_url = parsed._replace(query=urllib.parse.urlencode(test_params, doseq=True)).geturl()
                            test_resp = session.get(test_url, timeout=SCAN_TIMEOUT, allow_redirects=True)
                            if payload in test_resp.text:
                                findings.append(Vulnerability(
                                    title=f"Reflected XSS via URL Parameter: {param_name}",
                                    severity=SEVERITY_HIGH,
                                    category="Cross-Site Scripting",
                                    description=f"URL parameter '{param_name}' reflects input without encoding.",
                                    evidence=f"Payload: {payload}\nReflected in response.",
                                    fix="HTML-encode all reflected URL parameters.",
                                    owasp="A07:2021 Cross-Site Scripting"
                                ))
                                break
                        except requests.RequestException:
                            pass

        except requests.RequestException:
            pass

        self.scan_progress = 75
        return findings

    # ───────────────────────────────────────────────────────────────
    # SCANNER 6: CSRF & AUTHENTICATION ANALYSIS
    # ───────────────────────────────────────────────────────────────

    def scan_auth_csrf(self, url):
        """Check CSRF protection and authentication security."""
        findings = []
        self._emit(f"Phase 6: Authentication and session security audit...")
        self.scan_progress = 78

        session = self._get_session()

        try:
            resp = session.get(url, timeout=SCAN_TIMEOUT)
            soup = BeautifulSoup(resp.text, "html.parser")
            forms = soup.find_all("form")

            for form in forms:
                method = form.get("method", "get").lower()
                if method != "post":
                    continue

                action = form.get("action", url)
                inputs = form.find_all("input")
                has_csrf = False
                for inp in inputs:
                    name = (inp.get("name", "") or "").lower()
                    if any(t in name for t in ["csrf", "token", "_token", "authenticity", "nonce", "xsrf"]):
                        has_csrf = True
                        break

                if not has_csrf:
                    findings.append(Vulnerability(
                        title=f"Missing CSRF Protection on POST Form",
                        severity=SEVERITY_MEDIUM,
                        category="CSRF",
                        description=f"POST form at {action} has no CSRF token, allowing cross-site request forgery.",
                        evidence=f"Form action: {action}\nNo csrf/token/_token/nonce hidden field found.",
                        fix="Add a CSRF token to all POST forms. Use framework-provided CSRF middleware.",
                        owasp="A01:2021 Broken Access Control"
                    ))

            for cookie in session.cookies:
                issues = []
                if not cookie.secure:
                    issues.append("Missing 'Secure' flag")
                if not cookie.has_nonstandard_attr("HttpOnly") and "session" in cookie.name.lower():
                    issues.append("Missing 'HttpOnly' flag")
                if issues and ("session" in cookie.name.lower() or "auth" in cookie.name.lower()):
                    findings.append(Vulnerability(
                        title=f"Insecure Cookie: {cookie.name}",
                        severity=SEVERITY_MEDIUM,
                        category="Session Security",
                        description=f"Cookie '{cookie.name}' is missing security flags: {', '.join(issues)}.",
                        evidence=f"Cookie: {cookie.name}={cookie.value[:20]}...\nDomain: {cookie.domain}\nIssues: {', '.join(issues)}",
                        fix="Set 'Secure', 'HttpOnly', and 'SameSite=Strict' flags on all session cookies.",
                        owasp="A02:2021 Cryptographic Failures"
                    ))

        except requests.RequestException:
            pass

        self.scan_progress = 85
        return findings

    # ───────────────────────────────────────────────────────────────
    # FULL SCAN ORCHESTRATOR
    # ───────────────────────────────────────────────────────────────

    def full_scan(self, target_url, status_callback=None):
        """Run all 6 scanners sequentially and generate report."""
        with self._lock:
            if self.is_scanning:
                if status_callback:
                    status_callback("A scan is already in progress. Please wait.")
                return None

            self.is_scanning = True
            self.scan_progress = 0
            self.vulnerabilities = []
            self._status_callback = status_callback

        url = self._normalize_url(target_url)
        self.current_target = url
        domain = self._extract_domain(url)

        self._emit(f"Commencing full-spectrum security audit on {domain}...")
        start_time = time.time()

        try:
            self.vulnerabilities.extend(self.scan_ssl(url))
            self.vulnerabilities.extend(self.scan_headers(url))
            self.vulnerabilities.extend(self.scan_directories(url))
            self.vulnerabilities.extend(self.scan_sqli(url))
            self.vulnerabilities.extend(self.scan_xss(url))
            self.vulnerabilities.extend(self.scan_auth_csrf(url))

            elapsed = time.time() - start_time
            self.scan_progress = 90

            severity_counts = {
                SEVERITY_CRITICAL: 0, SEVERITY_HIGH: 0,
                SEVERITY_MEDIUM: 0, SEVERITY_LOW: 0, SEVERITY_INFO: 0
            }
            for v in self.vulnerabilities:
                severity_counts[v.severity] = severity_counts.get(v.severity, 0) + 1

            self.last_results = {
                "target": url,
                "domain": domain,
                "scan_time": round(elapsed, 2),
                "total_vulnerabilities": len(self.vulnerabilities),
                "severity_counts": severity_counts,
                "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
                "timestamp": datetime.datetime.now().isoformat(),
            }

            self._emit("Generating executive threat assessment report...")
            report_path = self._generate_html_report(self.last_results)
            self.last_report_path = report_path
            self.scan_progress = 100

            c, h, m = severity_counts[SEVERITY_CRITICAL], severity_counts[SEVERITY_HIGH], severity_counts[SEVERITY_MEDIUM]
            summary = f"Scan complete on {domain}. Found {c} critical, {h} high, {m} medium vulnerabilities in {round(elapsed, 1)}s. Report saved to Desktop."
            self._emit(summary)

            return self.last_results

        except Exception as e:
            self._emit(f"Scan error: {str(e)[:200]}")
            return None
        finally:
            with self._lock:
                self.is_scanning = False

    # ───────────────────────────────────────────────────────────────
    # HTML REPORT GENERATOR
    # ───────────────────────────────────────────────────────────────

    def _generate_html_report(self, results):
        """Generate a professional HTML security audit report."""
        domain = results["domain"]
        timestamp = results["timestamp"]
        total = results["total_vulnerabilities"]
        counts = results["severity_counts"]
        vulns = results["vulnerabilities"]
        scan_time = results["scan_time"]

        if counts.get(SEVERITY_CRITICAL, 0) > 0:
            grade, grade_color = "F", "#ff1744"
        elif counts.get(SEVERITY_HIGH, 0) > 2:
            grade, grade_color = "D", "#ff6d00"
        elif counts.get(SEVERITY_HIGH, 0) > 0:
            grade, grade_color = "C", "#ffab00"
        elif counts.get(SEVERITY_MEDIUM, 0) > 2:
            grade, grade_color = "B-", "#ffab00"
        elif counts.get(SEVERITY_MEDIUM, 0) > 0:
            grade, grade_color = "B", "#2979ff"
        elif counts.get(SEVERITY_LOW, 0) > 0:
            grade, grade_color = "A-", "#00c853"
        else:
            grade, grade_color = "A+", "#00e676"

        vuln_rows = ""
        severity_order = [SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO]
        for i, v in enumerate(sorted(vulns, key=lambda x: severity_order.index(x["severity"]) if x["severity"] in severity_order else 99), 1):
            sev = v["severity"]
            color = SEVERITY_COLORS.get(sev, "#aaa")
            icon = SEVERITY_ICONS.get(sev, "⚪")
            owasp_html = ""
            if v.get("owasp"):
                owasp_html = f'<div class="vuln-owasp"><strong>OWASP:</strong> {html_module.escape(v["owasp"])}</div>'
            vuln_rows += f"""
            <div class="vuln-card" style="border-left: 4px solid {color};">
                <div class="vuln-header">
                    <span class="vuln-id">#{i}</span>
                    <span class="vuln-severity" style="background:{color};">{icon} {sev}</span>
                    <span class="vuln-category">{html_module.escape(v['category'])}</span>
                </div>
                <h3 class="vuln-title">{html_module.escape(v['title'])}</h3>
                <p class="vuln-desc">{html_module.escape(v['description'])}</p>
                <div class="vuln-evidence">
                    <strong>Evidence:</strong>
                    <pre>{html_module.escape(v['evidence'])}</pre>
                </div>
                <div class="vuln-fix">
                    <strong>Recommended Fix:</strong>
                    <p>{html_module.escape(v['fix'])}</p>
                </div>
                {owasp_html}
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Point Break Security Audit - {html_module.escape(domain)}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@300;400;500;600;700;800&display=swap');
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background: #0a0e17;
            color: #c8d6e5;
            line-height: 1.7;
        }}
        .report-header {{
            background: linear-gradient(135deg, #0a0e17 0%, #1a1f35 50%, #0d1117 100%);
            padding: 48px 60px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        .report-header h1 {{
            font-size: 28px; font-weight: 800; color: #ffffff;
            letter-spacing: -0.5px; margin-bottom: 6px;
        }}
        .report-header .subtitle {{
            font-size: 14px; color: #8892b0;
            letter-spacing: 2px; text-transform: uppercase;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px; margin-top: 24px;
        }}
        .meta-item {{
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 8px; padding: 14px 18px;
        }}
        .meta-item .label {{
            font-size: 11px; color: #8892b0;
            text-transform: uppercase; letter-spacing: 1.5px;
        }}
        .meta-item .value {{
            font-size: 18px; font-weight: 700; color: #ffffff; margin-top: 4px;
        }}
        .grade-badge {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 64px; height: 64px; border-radius: 50%;
            font-size: 24px; font-weight: 800; color: #fff;
            background: {grade_color};
            box-shadow: 0 0 24px {grade_color}44;
        }}
        .report-body {{
            max-width: 960px; margin: 0 auto; padding: 40px 32px;
        }}
        .severity-grid {{
            display: grid; grid-template-columns: repeat(5, 1fr);
            gap: 12px; margin-bottom: 40px;
        }}
        .sev-card {{
            text-align: center; padding: 18px 12px; border-radius: 10px;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
        }}
        .sev-card .sev-count {{ font-size: 32px; font-weight: 800; }}
        .sev-card .sev-label {{
            font-size: 11px; text-transform: uppercase;
            letter-spacing: 1.5px; margin-top: 4px; color: #8892b0;
        }}
        .section-title {{
            font-size: 18px; font-weight: 700; color: #ffffff;
            margin: 32px 0 16px; padding-bottom: 8px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }}
        .vuln-card {{
            background: rgba(255,255,255,0.02);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px; padding: 20px 24px; margin-bottom: 16px;
        }}
        .vuln-header {{
            display: flex; align-items: center; gap: 10px; margin-bottom: 8px;
        }}
        .vuln-id {{
            font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #8892b0;
        }}
        .vuln-severity {{
            font-size: 11px; font-weight: 700; color: #fff;
            padding: 3px 10px; border-radius: 4px;
            text-transform: uppercase; letter-spacing: 0.5px;
        }}
        .vuln-category {{ font-size: 12px; color: #8892b0; margin-left: auto; }}
        .vuln-title {{ font-size: 15px; font-weight: 600; color: #e2e8f0; margin-bottom: 6px; }}
        .vuln-desc {{ font-size: 13px; color: #8892b0; margin-bottom: 12px; }}
        .vuln-evidence {{
            background: rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.04);
            border-radius: 6px; padding: 12px 16px; margin-bottom: 12px;
        }}
        .vuln-evidence strong {{
            font-size: 12px; color: #ffab00;
            text-transform: uppercase; letter-spacing: 1px;
        }}
        .vuln-evidence pre {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px; color: #c8d6e5;
            white-space: pre-wrap; word-break: break-all; margin-top: 6px;
        }}
        .vuln-fix {{
            padding: 10px 14px;
            background: rgba(0, 200, 83, 0.06);
            border: 1px solid rgba(0, 200, 83, 0.15);
            border-radius: 6px; margin-bottom: 8px;
        }}
        .vuln-fix strong {{ font-size: 12px; color: #00c853; }}
        .vuln-fix p {{ font-size: 13px; margin-top: 4px; color: #a8d8b9; }}
        .vuln-owasp {{
            font-size: 12px; color: #8892b0;
            font-family: 'JetBrains Mono', monospace;
        }}
        .report-footer {{
            text-align: center; padding: 32px;
            border-top: 1px solid rgba(255,255,255,0.06);
            font-size: 12px; color: #4a5568;
        }}
        @media print {{
            body {{ background: #fff; color: #1a202c; }}
            .vuln-card {{ border: 1px solid #e2e8f0; }}
            .report-header {{ background: #f7fafc; }}
        }}
    </style>
</head>
<body>
    <div class="report-header">
        <div class="subtitle">Point Break Cyber Arsenal &mdash; Security Audit Report</div>
        <h1>Threat Assessment: {html_module.escape(domain)}</h1>
        <div class="meta-grid">
            <div class="meta-item">
                <div class="label">Target</div>
                <div class="value" style="font-size:14px;">{html_module.escape(results['target'])}</div>
            </div>
            <div class="meta-item">
                <div class="label">Overall Grade</div>
                <div class="value"><span class="grade-badge">{grade}</span></div>
            </div>
            <div class="meta-item">
                <div class="label">Vulnerabilities</div>
                <div class="value">{total}</div>
            </div>
            <div class="meta-item">
                <div class="label">Scan Duration</div>
                <div class="value">{scan_time}s</div>
            </div>
            <div class="meta-item">
                <div class="label">Auditor</div>
                <div class="value" style="font-size:14px;">Point Break OS</div>
            </div>
            <div class="meta-item">
                <div class="label">Date</div>
                <div class="value" style="font-size:14px;">{timestamp[:10]}</div>
            </div>
        </div>
    </div>

    <div class="report-body">
        <h2 class="section-title">Severity Overview</h2>
        <div class="severity-grid">
            <div class="sev-card">
                <div class="sev-count" style="color:{SEVERITY_COLORS[SEVERITY_CRITICAL]}">{counts.get(SEVERITY_CRITICAL, 0)}</div>
                <div class="sev-label">Critical</div>
            </div>
            <div class="sev-card">
                <div class="sev-count" style="color:{SEVERITY_COLORS[SEVERITY_HIGH]}">{counts.get(SEVERITY_HIGH, 0)}</div>
                <div class="sev-label">High</div>
            </div>
            <div class="sev-card">
                <div class="sev-count" style="color:{SEVERITY_COLORS[SEVERITY_MEDIUM]}">{counts.get(SEVERITY_MEDIUM, 0)}</div>
                <div class="sev-label">Medium</div>
            </div>
            <div class="sev-card">
                <div class="sev-count" style="color:{SEVERITY_COLORS[SEVERITY_LOW]}">{counts.get(SEVERITY_LOW, 0)}</div>
                <div class="sev-label">Low</div>
            </div>
            <div class="sev-card">
                <div class="sev-count" style="color:{SEVERITY_COLORS[SEVERITY_INFO]}">{counts.get(SEVERITY_INFO, 0)}</div>
                <div class="sev-label">Info</div>
            </div>
        </div>

        <h2 class="section-title">Vulnerability Details ({total} Findings)</h2>
        {vuln_rows if vuln_rows else '<p style="color:#4a5568;">No vulnerabilities detected. The target appears to have solid security configuration.</p>'}

        <h2 class="section-title">OWASP Top 10 Coverage</h2>
        <div class="vuln-card" style="border-left:4px solid #2979ff;">
            <p style="font-size:13px; color:#8892b0;">This scan covers the following OWASP Top 10 (2021) categories:</p>
            <ul style="margin-top:8px; padding-left:20px; color:#c8d6e5; font-size:13px;">
                <li><strong>A01:</strong> Broken Access Control - Directory exposure, CSRF</li>
                <li><strong>A02:</strong> Cryptographic Failures - SSL/TLS, cookie security</li>
                <li><strong>A03:</strong> Injection - SQL Injection</li>
                <li><strong>A05:</strong> Security Misconfiguration - Headers, info disclosure</li>
                <li><strong>A07:</strong> Cross-Site Scripting - Reflected XSS</li>
            </ul>
        </div>

        <h2 class="section-title">Disclaimer</h2>
        <p style="font-size:12px; color:#4a5568; line-height:1.8;">
            This security audit was performed with authorized consent. Findings are based on automated scanning
            and should be verified manually. This report does not guarantee complete security coverage.
            Point Break Cyber Arsenal is a reconnaissance tool; advanced manual penetration testing
            is recommended for production systems.
        </p>
    </div>

    <div class="report-footer">
        <p>Generated by Point Break Cyber Arsenal v1.0 &mdash; {timestamp}</p>
        <p>&copy; {datetime.datetime.now().year} Point Break Systems. All rights reserved.</p>
    </div>
</body>
</html>"""

        safe_domain = re.sub(r'[^a-zA-Z0-9._-]', '_', domain)
        date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"POINTBREAK_SECURITY_AUDIT_{safe_domain}_{date_str}.html"
        report_path = str(REPORT_DIR / filename)

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html_content)
        except OSError:
            report_path = filename
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html_content)

        return report_path

    # ───────────────────────────────────────────────────────────────
    # PUBLIC API
    # ───────────────────────────────────────────────────────────────

    def get_status(self):
        """Get current scan status as dict."""
        return {
            "is_scanning": self.is_scanning,
            "progress": self.scan_progress,
            "phase": self.scan_phase,
            "target": self.current_target,
        }

    def get_results(self):
        """Get last scan results."""
        return self.last_results

    def get_report_path(self):
        """Get path to the last generated report."""
        return self.last_report_path


# ═══════════════════════════════════════════════════════════════════════
# MODULE SINGLETON
# ═══════════════════════════════════════════════════════════════════════

cyber_engine = CyberArsenalEngine()
