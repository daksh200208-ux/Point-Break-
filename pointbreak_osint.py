"""
Point Break OSINT Engine — Passive Intelligence Module
======================================================
Legally scans any website using ONLY public data.
No permission required for any function here.
All data sourced from public DNS, certificate transparency logs,
NVD vulnerability database, and publicly accessible web pages.

Author: Daksh (Point Break Systems)
Legal: All sources used are public APIs and public internet data.
"""

import requests
import socket
import ssl
import re
import json
import time
import datetime
import threading
import os
import subprocess
import urllib.parse
import html as html_module
from pathlib import Path

TIMEOUT = 10
USER_AGENT = "PointBreak-OSINT/2.0 (Security Research)"
REPORT_DIR = Path(os.path.expanduser("~")) / "Desktop"
HEADERS = {"User-Agent": USER_AGENT}

SENSITIVE_PATHS = [
    "/.env", "/.git/HEAD", "/.gitignore", "/wp-admin/", "/wp-login.php",
    "/administrator/", "/admin/", "/admin/login", "/login", "/dashboard",
    "/phpinfo.php", "/info.php", "/server-status", "/backup.sql", "/backup.zip",
    "/db.sql", "/.htaccess", "/.htpasswd", "/web.config", "/robots.txt",
    "/sitemap.xml", "/api/", "/api/v1/", "/swagger.json", "/api-docs",
    "/.well-known/security.txt", "/wp-config.php.bak", "/config.php.bak",
    "/config.yml", "/.DS_Store", "/xmlrpc.php", "/wp-json/wp/v2/users",
    "/cgi-bin/", "/phpmyadmin/", "/pma/", "/console", "/debug",
    "/actuator", "/actuator/env", "/actuator/health", "/graphql",
    "/swagger-ui.html", "/v2/api-docs", "/openapi.json",
]


class OSINTEngine:
    def __init__(self):
        self.results = {}
        self.target = ""
        self.is_running = False
        self.report_path = None
        self._status_cb = None

    def _status(self, msg):
        if self._status_cb:
            try:
                self._status_cb(msg)
            except Exception:
                pass
        print(f"[OSINT] {msg}")

    def _normalize_domain(self, target: str) -> str:
        """Strip http/https/www and return bare domain."""
        t = target.strip().lower()
        t = re.sub(r'^https?://', '', t)
        t = re.sub(r'^www\.', '', t)
        t = t.split('/')[0].split('?')[0].split(':')[0]
        return t

    def dns_recon(self, domain: str) -> dict:
        """Resolve IPs, reverse DNS, nameservers, WHOIS data."""
        result = {
            "ips": [], "reverse_dns": "", "nameservers": [],
            "whois_registrar": "", "whois_created": "",
            "whois_expires": "", "whois_org": ""
        }
        self._status(f"DNS recon on {domain}...")
        try:
            infos = socket.getaddrinfo(domain, None)
            ips = list(set(i[4][0] for i in infos))
            result["ips"] = ips
            if ips:
                try:
                    rdns = socket.gethostbyaddr(ips[0])
                    result["reverse_dns"] = rdns[0]
                except Exception:
                    pass
        except Exception as e:
            result["dns_error"] = str(e)

        # Nameservers via nslookup
        try:
            ns_proc = subprocess.run(
                ["nslookup", "-type=NS", domain],
                capture_output=True, text=True, timeout=10
            )
            ns_lines = ns_proc.stdout.splitlines()
            nss = []
            for line in ns_lines:
                if "nameserver" in line.lower() or "name server" in line.lower():
                    parts = line.split("=") if "=" in line else line.split()
                    if parts:
                        nss.append(parts[-1].strip().rstrip("."))
            result["nameservers"] = list(set(nss))
        except Exception:
            pass

        # WHOIS via free API
        try:
            resp = requests.get(
                f"https://api.whois.vu/?q={domain}",
                timeout=8, headers=HEADERS
            )
            if resp.status_code == 200:
                wdata = resp.json()
                result["whois_registrar"] = wdata.get("registrar", {}).get("name", "") if isinstance(wdata.get("registrar"), dict) else str(wdata.get("registrar", ""))
                result["whois_created"] = wdata.get("creation_date", wdata.get("registered", ""))
                result["whois_expires"] = wdata.get("expiration_date", wdata.get("expires", ""))
                result["whois_org"] = wdata.get("registrant", {}).get("organization", "") if isinstance(wdata.get("registrant"), dict) else ""
        except Exception:
            pass

        return result

    def enumerate_subdomains(self, domain: str) -> list:
        """Enumerate subdomains via crt.sh certificate transparency logs."""
        self._status(f"Subdomain enumeration for {domain}...")
        try:
            resp = requests.get(
                f"https://crt.sh/?q=%.{domain}&output=json",
                timeout=20, headers=HEADERS
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            subs = set()
            for entry in data:
                names = entry.get("name_value", "")
                for name in names.splitlines():
                    name = name.strip().lower().lstrip("*.")
                    if name and name.endswith(domain) and name != domain:
                        subs.add(name)
            return sorted(list(subs))
        except Exception as e:
            print(f"[OSINT] Subdomain enum error: {e}")
            return []

    def fingerprint_tech(self, domain: str) -> dict:
        """Detect technology stack from HTTP headers and page HTML."""
        self._status(f"Technology fingerprinting {domain}...")
        result = {
            "server": "", "cms": "", "cms_version": "",
            "php_version": "", "framework": "", "language": "",
            "raw_generator": "", "https": False
        }
        for scheme in ["https", "http"]:
            try:
                resp = requests.get(
                    f"{scheme}://{domain}",
                    timeout=TIMEOUT, headers=HEADERS,
                    allow_redirects=True
                )
                result["https"] = resp.url.startswith("https")
                h = resp.headers

                result["server"] = h.get("Server", "")
                result["php_version"] = ""
                xpb = h.get("X-Powered-By", "")
                if "PHP" in xpb:
                    m = re.search(r'PHP/([\d.]+)', xpb)
                    if m:
                        result["php_version"] = m.group(1)
                result["framework"] = xpb

                text = resp.text
                # Generator meta
                m = re.search(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', text, re.I)
                if m:
                    result["raw_generator"] = m.group(1)

                # WordPress
                if "/wp-content/" in text or "/wp-includes/" in text:
                    result["cms"] = "WordPress"
                    mv = re.search(r'wp-(?:content|includes)/[^?]*\?ver=([\d.]+)', text)
                    if mv:
                        result["cms_version"] = mv.group(1)

                # Joomla
                if "/components/com_" in text or "Joomla" in text:
                    result["cms"] = "Joomla"

                # Drupal
                if "Drupal" in h.get("X-Generator", "") or "drupal" in text.lower()[:2000]:
                    result["cms"] = "Drupal"

                # Django
                if "csrfmiddlewaretoken" in text or "django" in xpb.lower():
                    result["framework"] = "Django"
                    result["language"] = "Python"

                # Laravel
                if "laravel_session" in resp.cookies or "laravel" in text.lower()[:1000]:
                    result["framework"] = "Laravel"
                    result["language"] = "PHP"

                # Generator fallback
                if result["raw_generator"] and not result["cms"]:
                    result["cms"] = result["raw_generator"].split(" ")[0]

                break
            except Exception:
                continue
        return result

    def check_cve(self, tech_dict: dict) -> list:
        """Match detected tech versions to known CVEs via NVD NIST API."""
        self._status("Checking CVE database for known vulnerabilities...")
        results = []
        searches = []
        if tech_dict.get("cms") and tech_dict.get("cms_version"):
            searches.append(f"{tech_dict['cms']} {tech_dict['cms_version']}")
        elif tech_dict.get("cms"):
            searches.append(tech_dict["cms"])
        if tech_dict.get("server"):
            srv = tech_dict["server"].split("/")
            if len(srv) == 2:
                searches.append(f"{srv[0]} {srv[1]}")
        if tech_dict.get("php_version"):
            searches.append(f"PHP {tech_dict['php_version']}")

        for keyword in searches[:2]:
            try:
                resp = requests.get(
                    "https://services.nvd.nist.gov/rest/json/cves/2.0",
                    params={"keywordSearch": keyword, "resultsPerPage": 5},
                    timeout=15, headers=HEADERS
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("vulnerabilities", []):
                        cve = item.get("cve", {})
                        cve_id = cve.get("id", "")
                        desc = ""
                        for d in cve.get("descriptions", []):
                            if d.get("lang") == "en":
                                desc = d.get("value", "")[:250]
                                break
                        score = ""
                        severity = ""
                        metrics = cve.get("metrics", {})
                        for key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
                            if key in metrics and metrics[key]:
                                cvss = metrics[key][0].get("cvssData", {})
                                score = cvss.get("baseScore", "")
                                severity = cvss.get("baseSeverity", cvss.get("severity", ""))
                                break
                        if cve_id:
                            results.append({
                                "cve_id": cve_id,
                                "description": desc,
                                "score": score,
                                "severity": severity,
                                "keyword": keyword
                            })
                time.sleep(0.6)  # NVD rate limit
            except Exception as e:
                print(f"[OSINT] CVE check error for {keyword}: {e}")
        return results

    def generate_google_dorks(self, domain: str) -> list:
        """Generate 22 targeted Google dork search queries."""
        return [
            f"site:{domain} filetype:sql",
            f"site:{domain} filetype:env",
            f"site:{domain} filetype:log",
            f"site:{domain} filetype:xlsx",
            f"site:{domain} filetype:pdf confidential",
            f"site:{domain} filetype:xml",
            f"site:{domain} filetype:bak",
            f"site:{domain} inurl:admin",
            f"site:{domain} inurl:login",
            f"site:{domain} inurl:wp-admin",
            f"site:{domain} inurl:phpinfo",
            f"site:{domain} inurl:backup",
            f"site:{domain} inurl:config",
            f"site:{domain} inurl:api",
            f"site:{domain} inurl:swagger",
            f"site:{domain} inurl:.git",
            f"site:{domain} inurl:upload",
            f'site:{domain} intitle:"index of"',
            f'site:{domain} "db_password"',
            f'site:{domain} "api_key"',
            f'site:{domain} "password"',
            f'"@{domain}" email contact',
            f"site:{domain} inurl:phpmyadmin",
        ]

    def check_email_security(self, domain: str) -> dict:
        """Check SPF, DKIM, DMARC DNS records."""
        self._status(f"Checking email security (SPF/DKIM/DMARC) for {domain}...")
        result = {
            "spf_found": False, "spf_record": "",
            "dmarc_found": False, "dmarc_record": "",
            "dkim_found": False, "dkim_selector": "",
            "spoofable": True
        }

        def _nslookup_txt(name):
            try:
                proc = subprocess.run(
                    ["nslookup", "-type=TXT", name],
                    capture_output=True, text=True, timeout=10
                )
                return proc.stdout
            except Exception:
                return ""

        spf_out = _nslookup_txt(domain)
        if "v=spf1" in spf_out:
            result["spf_found"] = True
            m = re.search(r'"(v=spf1[^"]*)"', spf_out)
            result["spf_record"] = m.group(1) if m else "found"

        dmarc_out = _nslookup_txt(f"_dmarc.{domain}")
        if "v=DMARC1" in dmarc_out or "v=dmarc1" in dmarc_out.lower():
            result["dmarc_found"] = True
            m = re.search(r'"(v=DMARC1[^"]*)"', dmarc_out, re.I)
            result["dmarc_record"] = m.group(1) if m else "found"

        for selector in ["default", "google", "mail", "k1", "s1", "s2", "smtp"]:
            dkim_out = _nslookup_txt(f"{selector}._domainkey.{domain}")
            if "v=DKIM1" in dkim_out or "k=rsa" in dkim_out:
                result["dkim_found"] = True
                result["dkim_selector"] = selector
                break

        result["spoofable"] = not result["spf_found"] and not result["dmarc_found"]
        return result

    def harvest_emails(self, domain: str) -> list:
        """Scrape publicly listed email addresses from site pages."""
        self._status(f"Harvesting public emails from {domain}...")
        emails = set()
        email_re = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
        pages_to_check = [
            f"https://{domain}", f"https://{domain}/contact",
            f"https://{domain}/about", f"https://{domain}/contact-us",
            f"https://{domain}/about-us",
        ]
        for url in pages_to_check:
            try:
                resp = requests.get(url, timeout=8, headers=HEADERS, allow_redirects=True)
                found = email_re.findall(resp.text)
                for e in found:
                    if not re.search(r'@(example|test|domain|localhost|sentry|wix|wordpress)', e, re.I):
                        emails.add(e.lower())
            except Exception:
                continue
        return sorted(list(emails))

    def harvest_robots(self, domain: str) -> dict:
        """Extract Disallowed paths and sitemaps from robots.txt."""
        self._status(f"Harvesting robots.txt secrets for {domain}...")
        result = {"disallowed_paths": [], "sitemaps": [], "raw_content": ""}
        try:
            resp = requests.get(
                f"https://{domain}/robots.txt",
                timeout=8, headers=HEADERS
            )
            if resp.status_code == 200:
                raw = resp.text
                result["raw_content"] = raw[:3000]
                for line in raw.splitlines():
                    line = line.strip()
                    if line.lower().startswith("disallow:"):
                        path = line.split(":", 1)[1].strip()
                        if path and path != "/":
                            result["disallowed_paths"].append(path)
                    elif line.lower().startswith("sitemap:"):
                        url = line.split(":", 1)[1].strip()
                        if url:
                            result["sitemaps"].append(url)
        except Exception as e:
            result["error"] = str(e)
        return result

    def shodan_lookup(self, ip: str) -> dict:
        """Query Shodan for internet-facing service exposure."""
        api_key = os.environ.get("SHODAN_API_KEY", "").strip()
        if not api_key:
            return {"status": "no_api_key", "message": "Add SHODAN_API_KEY to your .env file for Shodan intelligence"}
        self._status(f"Querying Shodan for IP {ip}...")
        try:
            resp = requests.get(
                f"https://api.shodan.io/shodan/host/{ip}?key={api_key}",
                timeout=12, headers=HEADERS
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": "found",
                    "ports": data.get("ports", []),
                    "os": data.get("os", "Unknown"),
                    "org": data.get("org", ""),
                    "isp": data.get("isp", ""),
                    "country": data.get("country_name", ""),
                    "vulns": list(data.get("vulns", {}).keys()),
                    "hostnames": data.get("hostnames", []),
                    "tags": data.get("tags", []),
                }
            elif resp.status_code == 404:
                return {"status": "not_found", "message": "IP not in Shodan database"}
            else:
                return {"status": "error", "code": resp.status_code}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def full_osint_scan(self, target: str, status_callback=None) -> dict:
        """Run complete passive OSINT reconnaissance."""
        self._status_cb = status_callback
        self.is_running = True
        self.target = target
        self.results = {}

        self._status(f"Starting full OSINT on {target}...")
        domain = self._normalize_domain(target)
        self.results["domain"] = domain
        self.results["scan_time"] = datetime.datetime.now().isoformat()

        self._status("Phase 1/9: DNS Reconnaissance...")
        self.results["dns"] = self.dns_recon(domain)

        self._status("Phase 2/9: Subdomain Enumeration...")
        self.results["subdomains"] = self.enumerate_subdomains(domain)

        self._status("Phase 3/9: Technology Fingerprinting...")
        self.results["tech"] = self.fingerprint_tech(domain)

        self._status("Phase 4/9: CVE Database Matching...")
        self.results["cves"] = self.check_cve(self.results["tech"])

        self._status("Phase 5/9: Email Security Check (SPF/DKIM/DMARC)...")
        self.results["email_security"] = self.check_email_security(domain)

        self._status("Phase 6/9: Email Harvesting...")
        self.results["emails"] = self.harvest_emails(domain)

        self._status("Phase 7/9: robots.txt Intelligence...")
        self.results["robots"] = self.harvest_robots(domain)

        self._status("Phase 8/9: Shodan Intelligence...")
        first_ip = self.results["dns"].get("ips", [""])[0] if self.results["dns"].get("ips") else ""
        if first_ip:
            self.results["shodan"] = self.shodan_lookup(first_ip)
        else:
            self.results["shodan"] = {"status": "no_ip"}

        self._status("Phase 9/9: Google Dork Generation...")
        self.results["dorks"] = self.generate_google_dorks(domain)

        self._status("Generating OSINT Intelligence Report...")
        self._generate_osint_report()

        self.is_running = False
        self._status("OSINT scan complete. Report saved to Desktop.")
        return self.results

    def _sev_badge(self, ok: bool, ok_text="SECURE", bad_text="VULNERABLE") -> str:
        color = "#00ff88" if ok else "#ff3366"
        text = ok_text if ok else bad_text
        return f'<span style="background:{color}22;color:{color};border:1px solid {color}55;padding:2px 10px;border-radius:12px;font-size:0.72rem;font-weight:700;letter-spacing:1px;">{text}</span>'

    def _generate_osint_report(self) -> str:
        """Generate a beautiful dark-theme HTML OSINT report."""
        domain = self.results.get("domain", "unknown")
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dns = self.results.get("dns", {})
        subs = self.results.get("subdomains", [])
        tech = self.results.get("tech", {})
        cves = self.results.get("cves", [])
        email_sec = self.results.get("email_security", {})
        emails = self.results.get("emails", [])
        robots = self.results.get("robots", {})
        shodan = self.results.get("shodan", {})
        dorks = self.results.get("dorks", [])

        # Build dork links HTML
        dork_rows = ""
        for dork in dorks:
            encoded = urllib.parse.quote_plus(dork)
            link = f"https://www.google.com/search?q={encoded}"
            safe_dork = html_module.escape(dork)
            dork_rows += f'<tr><td style="padding:6px 10px;font-family:\'Fira Code\',monospace;font-size:0.78rem;color:#b0c4de;">{safe_dork}</td><td style="padding:6px 10px;"><a href="{link}" target="_blank" style="color:#00f0ff;text-decoration:none;font-size:0.72rem;border:1px solid #00f0ff44;padding:3px 10px;border-radius:10px;">SEARCH →</a></td></tr>\n'

        # Subdomain list
        sub_html = ""
        if subs:
            for s in subs[:50]:
                sub_html += f'<div style="font-family:\'Fira Code\',monospace;font-size:0.77rem;color:#7ec8e3;padding:3px 0;border-bottom:1px solid #0d1b2a;">{html_module.escape(s)}</div>'
        else:
            sub_html = '<div style="color:#8892b0;font-size:0.8rem;">No additional subdomains found via certificate transparency logs.</div>'

        # CVE table
        cve_html = ""
        if cves:
            for c in cves:
                score = c.get("score", "N/A")
                sev = c.get("severity", "")
                sev_color = {"CRITICAL": "#ff1744", "HIGH": "#ff6d00", "MEDIUM": "#ffab00", "LOW": "#2979ff"}.get(sev.upper(), "#8892b0")
                cve_html += f'''<tr>
                  <td style="padding:8px;color:#ff3366;font-family:'Fira Code',monospace;font-size:0.78rem;"><a href="https://nvd.nist.gov/vuln/detail/{c['cve_id']}" target="_blank" style="color:#ff3366;">{html_module.escape(c['cve_id'])}</a></td>
                  <td style="padding:8px;color:#b0c4de;font-size:0.77rem;">{html_module.escape(c.get('description','')[:200])}</td>
                  <td style="padding:8px;text-align:center;"><span style="color:{sev_color};font-weight:700;">{score}</span><br><small style="color:{sev_color};font-size:0.6rem;">{sev}</small></td>
                </tr>'''
        else:
            cve_html = '<tr><td colspan="3" style="padding:10px;color:#00ff88;text-align:center;">No matching CVEs found for detected technologies.</td></tr>'

        # Email security
        spf_badge = self._sev_badge(email_sec.get("spf_found", False), "SPF ✓", "NO SPF ✗")
        dmarc_badge = self._sev_badge(email_sec.get("dmarc_found", False), "DMARC ✓", "NO DMARC ✗")
        dkim_badge = self._sev_badge(email_sec.get("dkim_found", False), "DKIM ✓", "NO DKIM ✗")
        spoof_badge = self._sev_badge(not email_sec.get("spoofable", True), "NOT SPOOFABLE", "EMAIL SPOOFING POSSIBLE")

        # Shodan
        shodan_html = ""
        if shodan.get("status") == "found":
            ports = ", ".join(str(p) for p in shodan.get("ports", [])) or "None detected"
            vulns = ", ".join(shodan.get("vulns", [])) or "None listed"
            shodan_html = f'''
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
              <div><div style="color:#8892b0;font-size:0.68rem;letter-spacing:1px;margin-bottom:4px;">ORG / ISP</div><div style="color:#b0c4de;">{html_module.escape(shodan.get('org','') or shodan.get('isp','N/A'))}</div></div>
              <div><div style="color:#8892b0;font-size:0.68rem;letter-spacing:1px;margin-bottom:4px;">COUNTRY</div><div style="color:#b0c4de;">{html_module.escape(shodan.get('country','N/A'))}</div></div>
              <div><div style="color:#8892b0;font-size:0.68rem;letter-spacing:1px;margin-bottom:4px;">OPEN PORTS</div><div style="color:#ffab00;font-family:'Fira Code',monospace;">{html_module.escape(ports)}</div></div>
              <div><div style="color:#8892b0;font-size:0.68rem;letter-spacing:1px;margin-bottom:4px;">KNOWN VULNS (Shodan)</div><div style="color:#ff3366;font-family:'Fira Code',monospace;font-size:0.75rem;">{html_module.escape(vulns)}</div></div>
            </div>'''
        elif shodan.get("status") == "no_api_key":
            shodan_html = '<div style="color:#ffab00;font-size:0.82rem;">⚠ Add <code style="color:#00f0ff;">SHODAN_API_KEY=yourkey</code> to your .env file to enable Shodan intelligence. Free API key available at shodan.io</div>'
        else:
            shodan_html = f'<div style="color:#8892b0;">Status: {shodan.get("status","N/A")} {shodan.get("message","")}</div>'

        # robots.txt paths
        disallow_html = ""
        for p in robots.get("disallowed_paths", [])[:30]:
            disallow_html += f'<div style="font-family:\'Fira Code\',monospace;font-size:0.77rem;color:#ffab00;padding:3px 0;">{html_module.escape(p)}</div>'
        if not disallow_html:
            disallow_html = '<div style="color:#8892b0;">No special paths found in robots.txt</div>'

        # Email list
        email_html = ""
        for e in emails[:20]:
            email_html += f'<div style="font-family:\'Fira Code\',monospace;font-size:0.8rem;color:#7ec8e3;padding:3px 0;">{html_module.escape(e)}</div>'
        if not email_html:
            email_html = '<div style="color:#8892b0;">No public emails found on scanned pages.</div>'

        # Tech stack
        tech_items = []
        for k, v in tech.items():
            if v and k not in ("raw_generator", "https"):
                tech_items.append((k.replace("_", " ").upper(), str(v)))

        tech_html = ""
        for label, val in tech_items:
            tech_html += f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #0d1b2a;"><span style="color:#8892b0;font-size:0.75rem;">{label}</span><span style="color:#00f0ff;font-family:\'Fira Code\',monospace;font-size:0.78rem;">{html_module.escape(val)}</span></div>'
        if not tech_html:
            tech_html = '<div style="color:#8892b0;">Technology stack not identified.</div>'

        # DNS info
        dns_html = f'''
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div><div style="color:#8892b0;font-size:0.68rem;letter-spacing:1px;margin-bottom:4px;">IP ADDRESSES</div>
            <div style="color:#00f0ff;font-family:'Fira Code',monospace;">{html_module.escape(", ".join(dns.get("ips",[])) or "N/A")}</div></div>
          <div><div style="color:#8892b0;font-size:0.68rem;letter-spacing:1px;margin-bottom:4px;">REVERSE DNS</div>
            <div style="color:#b0c4de;font-family:'Fira Code',monospace;font-size:0.8rem;">{html_module.escape(dns.get("reverse_dns","N/A"))}</div></div>
          <div><div style="color:#8892b0;font-size:0.68rem;letter-spacing:1px;margin-bottom:4px;">NAMESERVERS</div>
            <div style="color:#b0c4de;font-size:0.8rem;">{html_module.escape(", ".join(dns.get("nameservers",[])) or "N/A")}</div></div>
          <div><div style="color:#8892b0;font-size:0.68rem;letter-spacing:1px;margin-bottom:4px;">REGISTRAR</div>
            <div style="color:#b0c4de;font-size:0.8rem;">{html_module.escape(dns.get("whois_registrar","N/A"))}</div></div>
          <div><div style="color:#8892b0;font-size:0.68rem;letter-spacing:1px;margin-bottom:4px;">REGISTERED</div>
            <div style="color:#b0c4de;font-size:0.8rem;">{html_module.escape(str(dns.get("whois_created","N/A")))}</div></div>
          <div><div style="color:#8892b0;font-size:0.68rem;letter-spacing:1px;margin-bottom:4px;">EXPIRES</div>
            <div style="color:#b0c4de;font-size:0.8rem;">{html_module.escape(str(dns.get("whois_expires","N/A")))}</div></div>
        </div>'''

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Point Break OSINT Report — {html_module.escape(domain)}</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@400;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet"/>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#02060d; color:#e2f1f8; font-family:'Rajdhani',sans-serif; min-height:100vh; }}
.report-wrapper {{ max-width:1100px; margin:0 auto; padding:32px 24px; }}
.report-header {{ background:linear-gradient(135deg,#030d1f,#060f28); border:1px solid rgba(0,240,255,0.2); border-radius:16px; padding:32px; margin-bottom:28px; }}
.report-title {{ font-family:'Orbitron',sans-serif; font-size:1.6rem; color:#00f0ff; letter-spacing:3px; font-weight:900; }}
.report-subtitle {{ color:#8892b0; font-size:0.9rem; margin-top:8px; letter-spacing:1px; }}
.report-meta {{ display:flex; gap:24px; margin-top:20px; flex-wrap:wrap; }}
.meta-item {{ background:rgba(0,240,255,0.05); border:1px solid rgba(0,240,255,0.15); border-radius:8px; padding:10px 16px; }}
.meta-label {{ color:#8892b0; font-size:0.65rem; letter-spacing:1.5px; text-transform:uppercase; }}
.meta-value {{ color:#00f0ff; font-family:'Fira Code',monospace; font-size:0.9rem; margin-top:2px; }}
.section {{ background:rgba(4,12,24,0.82); border:1px solid rgba(0,240,255,0.12); border-radius:12px; padding:24px; margin-bottom:20px; }}
.section-title {{ font-family:'Orbitron',sans-serif; font-size:0.7rem; color:#00f0ff; letter-spacing:2px; margin-bottom:16px; display:flex; align-items:center; gap:10px; }}
.section-title .count-badge {{ background:rgba(0,240,255,0.1); border:1px solid rgba(0,240,255,0.3); padding:2px 10px; border-radius:12px; font-size:0.75rem; color:#00f0ff; }}
.sub-scroll {{ max-height:200px; overflow-y:auto; padding-right:8px; }}
.sub-scroll::-webkit-scrollbar {{ width:4px; }} .sub-scroll::-webkit-scrollbar-track {{ background:#030d1f; }} .sub-scroll::-webkit-scrollbar-thumb {{ background:#00f0ff44; border-radius:2px; }}
table {{ width:100%; border-collapse:collapse; }}
th {{ color:#8892b0; font-size:0.65rem; letter-spacing:1.5px; text-transform:uppercase; padding:8px 10px; text-align:left; border-bottom:1px solid rgba(255,255,255,0.06); }}
tr:hover {{ background:rgba(255,255,255,0.02); }}
.email-sec-row {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px; }}
.footer {{ text-align:center; color:#3d4f6b; font-size:0.72rem; margin-top:32px; padding:16px; }}
a {{ color:#00f0ff; }}
</style>
</head>
<body>
<div class="report-wrapper">
  <div class="report-header">
    <div class="report-title">🏴‍☠️ POINT BREAK — OSINT INTELLIGENCE REPORT</div>
    <div class="report-subtitle">PASSIVE RECONNAISSANCE • PUBLIC DATA ONLY • NO AUTHORIZATION REQUIRED</div>
    <div class="report-meta">
      <div class="meta-item"><div class="meta-label">Target Domain</div><div class="meta-value">{html_module.escape(domain)}</div></div>
      <div class="meta-item"><div class="meta-label">Scan Time</div><div class="meta-value">{ts}</div></div>
      <div class="meta-item"><div class="meta-label">Subdomains</div><div class="meta-value">{len(subs)}</div></div>
      <div class="meta-item"><div class="meta-label">CVEs Found</div><div class="meta-value">{len(cves)}</div></div>
      <div class="meta-item"><div class="meta-label">Email Spoofable</div><div class="meta-value" style="color:{'#ff3366' if email_sec.get('spoofable') else '#00ff88'};">{'YES ⚠' if email_sec.get('spoofable') else 'NO ✓'}</div></div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">🌐 DNS INTELLIGENCE</div>
    {dns_html}
  </div>

  <div class="section">
    <div class="section-title">🔍 SUBDOMAIN ENUMERATION <span class="count-badge">{len(subs)} found</span></div>
    <div class="sub-scroll">{sub_html}</div>
  </div>

  <div class="section">
    <div class="section-title">🖥️ TECHNOLOGY FINGERPRINT</div>
    {tech_html}
  </div>

  <div class="section">
    <div class="section-title">⚠️ CVE VULNERABILITY MATCHES <span class="count-badge">{len(cves)} found</span></div>
    <table><thead><tr><th>CVE ID</th><th>Description</th><th>Score</th></tr></thead><tbody>{cve_html}</tbody></table>
  </div>

  <div class="section">
    <div class="section-title">📧 EMAIL SECURITY (SPF / DKIM / DMARC)</div>
    <div class="email-sec-row">{spf_badge} {dkim_badge} {dmarc_badge} {spoof_badge}</div>
    <div style="font-size:0.8rem;color:#8892b0;">SPF Record: <code style="color:#b0c4de;">{html_module.escape(email_sec.get('spf_record','Not configured'))}</code></div>
    <div style="font-size:0.8rem;color:#8892b0;margin-top:4px;">DMARC Record: <code style="color:#b0c4de;">{html_module.escape(email_sec.get('dmarc_record','Not configured'))}</code></div>
    {('<div style="margin-top:12px;padding:10px;background:rgba(255,51,102,0.08);border:1px solid #ff336644;border-radius:8px;color:#ff3366;font-size:0.82rem;">⚠️ <strong>EMAIL SPOOFING RISK:</strong> Anyone can send emails pretending to be from {html_module.escape(domain)}. This is used in phishing attacks targeting clients.</div>' if email_sec.get("spoofable") else '')}
  </div>

  <div class="section">
    <div class="section-title">📮 PUBLIC EMAILS FOUND <span class="count-badge">{len(emails)}</span></div>
    {email_html}
  </div>

  <div class="section">
    <div class="section-title">🤖 ROBOTS.TXT INTELLIGENCE <span class="count-badge">{len(robots.get('disallowed_paths', []))} hidden paths</span></div>
    <div style="color:#8892b0;font-size:0.75rem;margin-bottom:10px;">These paths were intentionally hidden from search engines — often the most sensitive areas.</div>
    {disallow_html}
  </div>

  <div class="section">
    <div class="section-title">🔌 SHODAN INTERNET EXPOSURE</div>
    {shodan_html}
  </div>

  <div class="section">
    <div class="section-title">🎯 GOOGLE DORK ARSENAL <span class="count-badge">{len(dorks)} queries</span></div>
    <div style="color:#8892b0;font-size:0.75rem;margin-bottom:12px;">Click any query to search Google for exposed sensitive data from this domain.</div>
    <table><thead><tr><th>Search Query</th><th>Action</th></tr></thead><tbody>{dork_rows}</tbody></table>
  </div>

  <div class="footer">Generated by Point Break Security System — Passive OSINT Intelligence<br>
  All data sourced from public APIs: crt.sh, NVD NIST, WHOIS, DNS. No unauthorized access performed.</div>
</div>
</body>
</html>"""

        fname = f"pointbreak_osint_{domain}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        report_path = str(REPORT_DIR / fname)
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            self.report_path = report_path
        except Exception as e:
            print(f"[OSINT] Report save error: {e}")
            self.report_path = None
        return report_path

    def get_status(self) -> dict:
        return {"is_running": self.is_running, "target": self.target}

    def get_report_path(self) -> str:
        return self.report_path

    def get_results(self) -> dict:
        return self.results


# Module-level singleton
osint_engine = OSINTEngine()
