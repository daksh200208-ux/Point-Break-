"""
Point Break Auto-Fix Engine
===========================
Generates ready-to-deploy security fix files for websites.
After Point Break finds vulnerabilities, this module generates
the actual configuration files that fix them.

Outputs a ZIP file containing all fix files + INSTALL.md guide.
"""

import os
import re
import json
import zipfile
import datetime
from pathlib import Path

REPORT_DIR = Path(os.path.expanduser("~")) / "Desktop"

class FixerEngine:
    def __init__(self):
        self.last_kit_path = None

    def generate_htaccess_security(self, findings) -> str:
        content = [
            "# ======================================================================",
            "# Point Break Security - Optimized .htaccess",
            "# ======================================================================",
            "",
            "# 1. Security Headers",
            "<IfModule mod_headers.c>",
            "    Header set X-Frame-Options \"SAMEORIGIN\"",
            "    Header set X-XSS-Protection \"1; mode=block\"",
            "    Header set X-Content-Type-Options \"nosniff\"",
            "    Header set Referrer-Policy \"strict-origin-when-cross-origin\"",
            "    # HSTS - Enable if HTTPS is in use",
            "    Header set Strict-Transport-Security \"max-age=31536000; includeSubDomains; preload\"",
            "    # Content-Security-Policy",
            "    Header set Content-Security-Policy \"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; object-src 'none'; frame-ancestors 'self'\"",
            "    # Hide PHP Version",
            "    Header unset X-Powered-By",
            "</IfModule>",
            "",
            "# 2. Disable Directory Listing",
            "Options -Indexes",
            "",
            "# 3. Block Access to Sensitive Files",
            "<FilesMatch \"^\\.(env|git|svn)|^(wp-config\\.php|docker-compose\\.yml|composer\\.json|\\.htaccess|\\.htpasswd)$\">",
            "    Require all denied",
            "</FilesMatch>",
            "",
            "# Block Backup files",
            "<FilesMatch \"\\.(bak|config|sql|fla|psd|ini|log|sh|inc|swp|dist)$\">",
            "    Require all denied",
            "</FilesMatch>",
            "",
            "# 4. Block Bad Bots and Scanners",
            "<IfModule mod_rewrite.c>",
            "    RewriteEngine On",
            "    RewriteCond %{HTTP_USER_AGENT} ^.*(sqlmap|nikto|nmap|dirbuster|wpscan|masscan|zgrab).*$ [NC,OR]",
            "    RewriteCond %{HTTP_USER_AGENT} ^.*(Acunetix|Netsparker|AppScan|Nessus).*$ [NC]",
            "    RewriteRule ^(.*)$ - [F,L]",
            "",
            "    # 5. Block Common Attack Patterns in Query Strings (SQLi/XSS/LFI)",
            "    RewriteCond %{QUERY_STRING} (\\<|%3C).*script.*(\\>|%3E) [NC,OR]",
            "    RewriteCond %{QUERY_STRING} GLOBALS(=|\\[|\\%[0-9A-Z]{0,2}) [OR]",
            "    RewriteCond %{QUERY_STRING} _REQUEST(=|\\[|\\%[0-9A-Z]{0,2}) [OR]",
            "    RewriteCond %{QUERY_STRING} (base64_encode|localhost|loopback) [NC,OR]",
            "    RewriteCond %{QUERY_STRING} (boot\\.ini|etc/passwd|self/environ) [NC,OR]",
            "    RewriteCond %{QUERY_STRING} (concat|insert|union|select|drop|update) [NC]",
            "    RewriteRule ^(.*)$ - [F,L]",
            "</IfModule>",
            ""
        ]
        return "\n".join(content)

    def generate_nginx_security(self, findings) -> str:
        content = [
            "# ======================================================================",
            "# Point Break Security - Nginx Server Block Additions",
            "# ======================================================================",
            "",
            "# 1. Hide Nginx Version",
            "server_tokens off;",
            "",
            "# 2. Security Headers",
            "add_header X-Frame-Options \"SAMEORIGIN\" always;",
            "add_header X-XSS-Protection \"1; mode=block\" always;",
            "add_header X-Content-Type-Options \"nosniff\" always;",
            "add_header Referrer-Policy \"strict-origin-when-cross-origin\" always;",
            "add_header Strict-Transport-Security \"max-age=31536000; includeSubDomains; preload\" always;",
            "",
            "# 3. SSL/TLS Hardening",
            "ssl_protocols TLSv1.2 TLSv1.3;",
            "ssl_prefer_server_ciphers on;",
            "ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;",
            "ssl_session_timeout 1d;",
            "ssl_session_cache shared:MozSSL:10m;",  
            "ssl_session_tickets off;",
            "",
            "# 4. Block Sensitive Files",
            "location ~ /\\.(?!well-known).* {",
            "    deny all;",
            "    access_log off;",
            "    log_not_found off;",
            "}",
            "location ~* /(?:uploads|files)/.*\\.php$ {",
            "    deny all;",
            "}",
            "location ~* \\.(env|log|sql|bak|config|ini|sh|dist)$ {",
            "    deny all;",
            "}",
            "",
            "# 5. Rate Limiting Example (Requires configuring limit_req_zone in http block)",
            "# http block: limit_req_zone $binary_remote_addr zone=mylimit:10m rate=10r/s;",
            "# location /login {",
            "#     limit_req zone=mylimit burst=20 nodelay;",
            "# }"
        ]
        return "\n".join(content)

    def generate_csp_header(self, domain, tech_dict) -> str:
        is_wp = tech_dict.get('wordpress', False)
        
        csp_rules = [
            "default-src 'self'",
            "img-src 'self' data: https:",
            "object-src 'none'",
            "frame-ancestors 'self'"
        ]
        
        if is_wp:
            csp_rules.append("script-src 'self' 'unsafe-inline' 'unsafe-eval' https://s.w.org https://c0.wp.com")
            csp_rules.append("style-src 'self' 'unsafe-inline' https://fonts.googleapis.com")
            csp_rules.append("font-src 'self' data: https://fonts.gstatic.com")
        else:
            csp_rules.append("script-src 'self'")
            csp_rules.append("style-src 'self' 'unsafe-inline'")
            
        csp_string = "; ".join(csp_rules)
        
        content = [
            "# ======================================================================",
            "# Content Security Policy Header",
            "# ======================================================================",
            "",
            "## Apache .htaccess snippet ##",
            f"Header set Content-Security-Policy \"{csp_string}\"",
            "",
            "## Nginx configuration snippet ##",
            f"add_header Content-Security-Policy \"{csp_string}\" always;"
        ]
        return "\n".join(content)

    def generate_wp_hardening(self, findings) -> str:
        content = [
            "<?php",
            "/**",
            " * Point Break Security - WordPress Hardening Additions",
            " *",
            " * INSTRUCTIONS:",
            " * Add the following constants to your wp-config.php file, just before the line:",
            " * /* That's all, stop editing! Happy publishing. */",
            " */",
            "",
            "// 1. Disable File Editor",
            "// Prevents plugins/themes from being edited through the WP dashboard",
            "define( 'DISALLOW_FILE_EDIT', true );",
            "",
            "// 2. Disable Debugging (Ensure no errors are printed to the screen)",
            "define( 'WP_DEBUG', false );",
            "define( 'WP_DEBUG_DISPLAY', false );",
            "@ini_set( 'display_errors', 0 );",
            "define( 'WP_DEBUG_LOG', false );",
            "",
            "// 3. Force SSL for Admin Area",
            "define( 'FORCE_SSL_ADMIN', true );",
            "",
            "/*",
            " * OTHER RECOMMENDATIONS:",
            " * ",
            " * - Database Prefix: Ensure `$table_prefix` is NOT 'wp_'. Change it to something random like 'wp_xk93_'.",
            " * - Auth Keys: Go to https://api.wordpress.org/secret-key/1.1/salt/ and refresh the keys in wp-config.php.",
            " */",
            "",
            "/**",
            " * FUNCTIONS.PHP ADDITIONS:",
            " * Add these to your active theme's functions.php file (preferably a child theme).",
            " */",
            "",
            "// Disable WP REST API for logged-out users",
            "add_filter( 'rest_authentication_errors', function( $result ) {",
            "    if ( ! empty( $result ) ) {",
            "        return $result;",
            "    }",
            "    if ( ! is_user_logged_in() ) {",
            "        return new WP_Error( 'rest_not_logged_in', 'REST API restricted to authenticated users.', array( 'status' => 401 ) );",
            "    }",
            "    return $result;",
            "});",
            "",
            "// Hide WP version from meta tags",
            "remove_action('wp_head', 'wp_generator');",
            "",
            "/**",
            " * .HTACCESS XML-RPC BLOCKING:",
            " * Add this to your .htaccess to block XML-RPC attacks.",
            " *",
            " * <Files xmlrpc.php>",
            " *     Require all denied",
            " * </Files>",
            " */"
        ]
        return "\n".join(content)

    def generate_sql_injection_fix(self, tech_dict) -> str:
        content = [
            "<?php",
            "/**",
            " * Point Break Security - SQL Injection Prevention Guide",
            " *",
            " * Below are examples of how to safely interact with your database",
            " * to prevent SQL Injection vulnerabilities.",
            " */",
            "",
            "// ======================================================================",
            "// 1. PDO Prepared Statements (Recommended)",
            "// ======================================================================",
            "$pdo = new PDO('mysql:host=localhost;dbname=testdb', 'user', 'pass');",
            "$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);",
            "",
            "// INSECURE:",
            "// $sql = \"SELECT * FROM users WHERE username = '\" . $_POST['username'] . \"'\";",
            "// $stmt = $pdo->query($sql);",
            "",
            "// SECURE:",
            "$sql = \"SELECT * FROM users WHERE username = :username AND status = :status\";",
            "$stmt = $pdo->prepare($sql);",
            "// The data is sent separately from the query, so it cannot be executed as code.",
            "$stmt->execute([",
            "    ':username' => $_POST['username'],",
            "    ':status' => 'active'",
            "]);",
            "$user = $stmt->fetch();",
            "",
            "// ======================================================================",
            "// 2. MySQLi Prepared Statements",
            "// ======================================================================",
            "$mysqli = new mysqli('localhost', 'user', 'pass', 'testdb');",
            "",
            "// SECURE:",
            "$sql = \"SELECT id, email FROM users WHERE username = ?\";",
            "$stmt = $mysqli->prepare($sql);",
            "$stmt->bind_param(\"s\", $_POST['username']); // 's' means string",
            "$stmt->execute();",
            "$result = $stmt->get_result();",
            "",
            "// ======================================================================",
            "// 3. Whitelist Validation for Table/Column Names",
            "// Table and column names CANNOT be parameterized. You must use whitelisting.",
            "// ======================================================================",
            "$allowed_sort_columns = ['username', 'created_at', 'status'];",
            "$sort_by = in_array($_GET['sort'], $allowed_sort_columns) ? $_GET['sort'] : 'username';",
            "",
            "$sql = \"SELECT * FROM users ORDER BY `\" . $sort_by . \"` ASC\";",
            "$stmt = $pdo->query($sql);",
            "",
            "// ======================================================================",
            "// 4. Output Encoding (Prevent XSS when echoing DB content)",
            "// ======================================================================",
            "// Always escape data when outputting it to HTML.",
            "// echo htmlspecialchars($user['username'], ENT_QUOTES, 'UTF-8');",
            "?>"
        ]
        return "\n".join(content)

    def generate_email_security_dns(self, domain, email_sec_dict) -> str:
        content = [
            "======================================================================",
            "Point Break Security - Email Security DNS Records",
            f"Target Domain: {domain}",
            "======================================================================",
            "",
            "To prevent email spoofing and improve deliverability, add the following",
            "TXT records to your domain's DNS settings.",
            "",
            "1. SPF (Sender Policy Framework)",
            "--------------------------------",
            "Name/Host: @ (or leave blank)",
            "Type: TXT",
            "Value: v=spf1 a mx ~all",
            "Note: If you use external services like Google Workspace or Office 365,",
            "you must include them, e.g., v=spf1 include:_spf.google.com ~all",
            "",
            "2. DMARC (Domain-based Message Authentication, Reporting, and Conformance)",
            "--------------------------------------------------------------------------",
            "Name/Host: _dmarc",
            "Type: TXT",
            f"Value: v=DMARC1; p=quarantine; rua=mailto:dmarc@{domain}",
            "Note: This tells receivers to quarantine emails that fail SPF/DKIM checks.",
            "",
            "3. DKIM (DomainKeys Identified Mail)",
            "------------------------------------",
            "DKIM involves cryptographic keys and must be generated by your email provider.",
            "- If using Google Workspace: Go to Admin Console -> Apps -> Google Workspace -> Gmail -> Authenticate email.",
            "- If using cPanel: Go to Email Deliverability and click 'Manage' next to your domain to enable DKIM.",
            "- After generating the key, you will add a TXT record with the provided Name (selector) and Value."
        ]
        return "\n".join(content)

    def generate_rate_limiting_guide(self, domain) -> str:
        content = [
            "======================================================================",
            "Point Break Security - Rate Limiting Implementation Guide",
            "======================================================================",
            "",
            "1. Nginx Rate Limiting",
            "----------------------",
            "Add the limit_req_zone to your http { ... } block (usually in nginx.conf):",
            "    limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;",
            "",
            "Add the limit_req directive to your location block:",
            "    location /login {",
            "        limit_req zone=login_limit burst=5 nodelay;",
            "        # ... your php/proxy pass settings",
            "    }",
            "",
            "2. Apache mod_evasive",
            "---------------------",
            "Install mod_evasive (e.g., apt-get install libapache2-mod-evasive).",
            "Configure in evasive.conf:",
            "    <IfModule mod_evasive20.c>",
            "        DOSHashTableSize    3097",
            "        DOSPageCount        2",
            "        DOSSiteCount        50",
            "        DOSPageInterval     1",
            "        DOSSiteInterval     1",
            "        DOSBlockingPeriod   10",
            "        DOSEmailNotify      admin@example.com",
            "    </IfModule>",
            "",
            "3. PHP Session-based Rate Limiting (Basic Example)",
            "--------------------------------------------------",
            "<?php",
            "session_start();",
            "if (!isset($_SESSION['requests'])) {",
            "    $_SESSION['requests'] = 0;",
            "    $_SESSION['first_request_time'] = time();",
            "}",
            "$_SESSION['requests']++;",
            "",
            "// Allow 10 requests per minute",
            "if ($_SESSION['requests'] > 10) {",
            "    if (time() - $_SESSION['first_request_time'] < 60) {",
            "        http_response_code(429);",
            "        die(\"Too Many Requests. Please try again later.\");",
            "    } else {",
            "        // Reset counter",
            "        $_SESSION['requests'] = 1;",
            "        $_SESSION['first_request_time'] = time();",
            "    }",
            "}",
            "?>",
            "",
            "4. Cloudflare WAF (If applicable)",
            "---------------------------------",
            "If using Cloudflare, go to Security -> WAF -> Rate Limiting Rules.",
            "Create a rule targeting your login or API endpoints to block IPs",
            "that exceed a reasonable threshold (e.g., 5 requests per minute)."
        ]
        return "\n".join(content)

    def generate_ssl_hardening(self, domain) -> str:
        content = [
            "======================================================================",
            "Point Break Security - SSL/TLS Hardening",
            "======================================================================",
            "",
            "Nginx Configuration",
            "-------------------",
            "Update your server block with these modern, secure settings:",
            "",
            "ssl_protocols TLSv1.2 TLSv1.3;",
            "ssl_prefer_server_ciphers on;",
            "ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;",
            "",
            "# Optimize SSL Session Cache",
            "ssl_session_timeout 1d;",
            "ssl_session_cache shared:MozSSL:10m;",
            "ssl_session_tickets off;",
            "",
            "# Enable HSTS (Strict-Transport-Security)",
            "add_header Strict-Transport-Security \"max-age=63072000; includeSubDomains; preload\" always;",
            "",
            "# OCSP Stapling",
            "ssl_stapling on;",
            "ssl_stapling_verify on;",
            "resolver 8.8.8.8 8.8.4.4 valid=300s;",
            "resolver_timeout 5s;",
            "",
            "Apache Configuration",
            "--------------------",
            "Update your SSL VirtualHost config:",
            "",
            "SSLProtocol             all -SSLv3 -TLSv1 -TLSv1.1",
            "SSLCipherSuite          ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384",
            "SSLHonorCipherOrder     off",
            "SSLSessionTickets       off",
            "",
            "# HSTS",
            "Header always set Strict-Transport-Security \"max-age=63072000; includeSubDomains; preload\"",
            "",
            "General Reminders",
            "-----------------",
            "- If you use Let's Encrypt, ensure your cron job is set up for automatic renewal:",
            "  0 0,12 * * * root certbot renew -q"
        ]
        return "\n".join(content)

    def generate_install_guide(self, domain, fixes_included) -> str:
        content = [
            f"# Point Break Security Hardening Kit: {domain}",
            "",
            "**IMPORTANT: ALWAYS BACKUP YOUR FILES AND DATABASE BEFORE APPLYING THESE FIXES.**",
            "",
            "## Included Fixes",
        ]
        for fix in fixes_included:
            content.append(f"- {fix}")
        
        content.extend([
            "",
            "## Deployment Instructions",
            "",
            "### .htaccess",
            "1. Locate your site's root directory (e.g., public_html, /var/www/html).",
            "2. Back up your existing `.htaccess` file: `cp .htaccess .htaccess.backup`",
            "3. Append the contents of the generated `.htaccess` to your existing file, or replace it if empty.",
            "",
            "### Nginx Security (`nginx_security.conf`)",
            "1. Open your site's nginx server block configuration (e.g., `/etc/nginx/sites-available/your-site`).",
            "2. Paste the provided snippets inside your `server { ... }` block.",
            "3. Test config: `nginx -t`",
            "4. Reload nginx: `systemctl reload nginx`",
            "",
            "### WordPress Hardening (`wp_hardening_additions.php`)",
            "1. Open `wp-config.php` in your WP root.",
            "2. Paste the constants just before the `/* That's all, stop editing! */` line.",
            "3. Add the functions.php snippets to your active theme's `functions.php`.",
            "",
            "### DNS / Email Security (`email_security_dns_records.txt`)",
            "1. Log in to your domain registrar or DNS provider (e.g., Cloudflare, GoDaddy).",
            "2. Navigate to DNS Management.",
            "3. Add the TXT records as specified in the file.",
            "",
            "## Post-Deployment Testing",
            "1. Visit your website to ensure it loads properly and styles aren't broken.",
            "2. Test admin logins and forms.",
            "3. Check developer console for Content-Security-Policy blocks (you may need to tweak the CSP rules).",
            "",
            "---",
            "*Generated by Point Break Security — Contact your security consultant for assistance*"
        ])
        return "\n".join(content)

    def generate_xss_fix(self, tech_dict) -> str:
        content = [
            "<?php",
            "/**",
            " * Point Break Security - XSS Prevention Guide",
            " */",
            "",
            "// ======================================================================",
            "// 1. PHP Contexts",
            "// ======================================================================",
            "// When echoing user input into HTML body or attributes, always use htmlspecialchars.",
            "$user_input = \"<script>alert('xss')</script>\";",
            "",
            "// SECURE HTML Output:",
            "echo \"<div>\" . htmlspecialchars($user_input, ENT_QUOTES, 'UTF-8') . \"</div>\";",
            "",
            "// SECURE HTML Attribute Output:",
            "echo \"<input type='text' value='\" . htmlspecialchars($user_input, ENT_QUOTES, 'UTF-8') . \"'>\";",
            "",
            "// Removing tags entirely (if HTML is not allowed at all):",
            "echo strip_tags($user_input);",
            "?>",
            "",
            "<!-- ",
            "// ======================================================================",
            "// 2. JavaScript Contexts",
            "// ======================================================================",
            "-->",
            "<script>",
            "    const userInput = \"<img src=x onerror=alert(1)>\";",
            "",
            "    // INSECURE (XSS Vulnerable):",
            "    // document.getElementById('myDiv').innerHTML = userInput;",
            "",
            "    // SECURE (Encodes as text):",
            "    document.getElementById('myDiv').textContent = userInput;",
            "",
            "    // If you MUST render HTML, use a sanitization library like DOMPurify:",
            "    // import DOMPurify from 'dompurify';",
            "    // const cleanHTML = DOMPurify.sanitize(userInput);",
            "    // document.getElementById('myDiv').innerHTML = cleanHTML;",
            "</script>",
            "",
            "<!-- ",
            "// ======================================================================",
            "// 3. Content-Security-Policy (CSP)",
            "// ======================================================================",
            "// The best defense in depth against XSS is a strong CSP.",
            "// Implement the CSP generated in the csp_headers.txt file.",
            "// A strict CSP blocks inline scripts and untrusted external sources.",
            "-->"
        ]
        return "\n".join(content)

    def generate_hardening_kit(self, domain, scan_results, osint_results=None) -> str:
        # Create REPORT_DIR if it doesn't exist
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"pointbreak_hardening_kit_{domain.replace('.', '_')}_{timestamp}.zip"
        zip_path = REPORT_DIR / zip_filename
        
        # Analyze findings to determine tech and what needs fixing
        scan_str = str(scan_results).lower()
        is_wp = 'wordpress' in scan_str or 'wp' in scan_str
        has_sqli = 'sqli' in scan_str or 'sql injection' in scan_str
        has_email_issues = 'email' in scan_str or 'dmarc' in scan_str or 'spf' in scan_str
        has_ssl_issues = 'ssl' in scan_str or 'tls' in scan_str
        has_xss = 'xss' in scan_str or 'cross site' in scan_str
        
        tech_dict = {'wordpress': is_wp}
        fixes_included = []
        files_to_zip = {}
        
        files_to_zip['.htaccess'] = self.generate_htaccess_security(scan_results)
        fixes_included.append(".htaccess Security Rules")
        
        files_to_zip['nginx_security.conf'] = self.generate_nginx_security(scan_results)
        fixes_included.append("Nginx Security Config")
        
        files_to_zip['csp_headers.txt'] = self.generate_csp_header(domain, tech_dict)
        fixes_included.append("Content-Security-Policy Header")
        
        if is_wp:
            files_to_zip['wp_hardening_additions.php'] = self.generate_wp_hardening(scan_results)
            fixes_included.append("WordPress Hardening snippets")
            
        if has_sqli:
            files_to_zip['sql_injection_prevention.php'] = self.generate_sql_injection_fix(tech_dict)
            fixes_included.append("SQL Injection Prevention Snippets")
            
        if has_email_issues:
            files_to_zip['email_security_dns_records.txt'] = self.generate_email_security_dns(domain, {})
            fixes_included.append("Email Security DNS Records")
            
        if has_ssl_issues:
            files_to_zip['ssl_hardening.conf'] = self.generate_ssl_hardening(domain)
            fixes_included.append("SSL/TLS Hardening Config")
            
        files_to_zip['rate_limiting_guide.txt'] = self.generate_rate_limiting_guide(domain)
        fixes_included.append("Rate Limiting Guide")
        
        if has_xss:
            files_to_zip['xss_prevention.php'] = self.generate_xss_fix(tech_dict)
            fixes_included.append("XSS Prevention Snippets")
            
        files_to_zip['INSTALL.md'] = self.generate_install_guide(domain, fixes_included)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename, content in files_to_zip.items():
                zipf.writestr(filename, content)
                
        self.last_kit_path = str(zip_path)
        return self.last_kit_path

    def get_last_kit_path(self) -> str:
        return self.last_kit_path

fixer_engine = FixerEngine()
