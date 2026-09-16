#!/usr/bin/env python3
"""
Point Break - Shopping & Price Comparison Sniper Engine
=======================================================
Compares prices across Amazon, Flipkart, Google Shopping.
Detects bank card offers and coupon codes.
Opens the best deal directly in the browser.
"""
import sys, os, re, json, threading, time, webbrowser, urllib.parse
sys.stdout.reconfigure(encoding="utf-8")

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


# Known bank card offer patterns
BANK_OFFER_PATTERNS = {
    "HDFC": ["hdfc", "hdfc bank", "hdfc card", "hdfc cashback", "hdfc offer"],
    "ICICI": ["icici", "icici bank", "icici card", "icici cashback", "icici offer"],
    "SBI": ["sbi", "sbi card", "sbi cashback", "sbi offer", "state bank"],
    "Axis": ["axis", "axis bank", "axis card", "axis cashback", "axis offer"],
    "Kotak": ["kotak", "kotak bank", "kotak card", "kotak cashback"],
    "AMEX": ["amex", "american express"],
    "OneCard": ["onecard", "one card"],
    "RuPay": ["rupay"],
}

COUPON_SITES = [
    "https://www.coupondunia.in/search?q={}",
    "https://www.grabon.in/search/?q={}",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}


class PriceSniperEngine:
    """Compares prices across Indian e-commerce platforms."""

    def __init__(self):
        self.last_results = []

    def _search_amazon(self, product):
        """Search Amazon.in for product prices."""
        results = []
        try:
            url = f"https://www.amazon.in/s?k={urllib.parse.quote(product)}"
            if requests and BeautifulSoup:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select("div[data-component-type='s-search-result']")
                for item in items[:5]:
                    title_el = item.select_one("h2 a span")
                    price_el = item.select_one("span.a-price-whole")
                    link_el = item.select_one("h2 a")
                    if title_el and price_el:
                        title = title_el.get_text(strip=True)
                        price_text = price_el.get_text(strip=True).replace(",", "")
                        try:
                            price = float(price_text)
                        except ValueError:
                            continue
                        link = "https://www.amazon.in" + link_el.get("href", "") if link_el else url
                        # Check for bank offers in surrounding text
                        card_offers = []
                        offer_els = item.select("span.s-coupon-highlight-color, span.a-color-base")
                        offer_text = " ".join(el.get_text(strip=True).lower() for el in offer_els)
                        for bank, keywords in BANK_OFFER_PATTERNS.items():
                            if any(kw in offer_text for kw in keywords):
                                card_offers.append(bank)
                        results.append({
                            "platform": "Amazon",
                            "title": title[:80],
                            "price": price,
                            "url": link,
                            "card_offers": card_offers,
                        })
        except Exception as e:
            print(f"[Price Sniper] Amazon search error: {e}")
        if not results:
            results.append({
                "platform": "Amazon",
                "title": product,
                "price": 0,
                "url": f"https://www.amazon.in/s?k={urllib.parse.quote(product)}",
                "card_offers": [],
                "fallback": True,
            })
        return results

    def _search_flipkart(self, product):
        """Search Flipkart for product prices."""
        results = []
        try:
            url = f"https://www.flipkart.com/search?q={urllib.parse.quote(product)}"
            if requests and BeautifulSoup:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select("div._1AtVbE, div._4ddWXP, div._2kHMtA")
                for item in items[:5]:
                    title_el = item.select_one("div._4rR01T, a.s1Q9rs, a.IRpwTa")
                    price_el = item.select_one("div._30jeq3, div._25b18c")
                    link_el = item.select_one("a._1fQZEK, a.s1Q9rs, a.IRpwTa, a._2rpwqI")
                    if title_el and price_el:
                        title = title_el.get_text(strip=True)
                        raw_price = price_el.get_text(strip=True)
                        price_digits = re.sub(r"[^\d.]", "", raw_price)
                        try:
                            price = float(price_digits)
                        except ValueError:
                            continue
                        link = "https://www.flipkart.com" + link_el.get("href", "") if link_el else url
                        card_offers = []
                        offer_els = item.select("span._3j4Zjq, li._3DrUlq, div._3Ay6Sb")
                        offer_text = " ".join(el.get_text(strip=True).lower() for el in offer_els)
                        for bank, keywords in BANK_OFFER_PATTERNS.items():
                            if any(kw in offer_text for kw in keywords):
                                card_offers.append(bank)
                        results.append({
                            "platform": "Flipkart",
                            "title": title[:80],
                            "price": price,
                            "url": link,
                            "card_offers": card_offers,
                        })
        except Exception as e:
            print(f"[Price Sniper] Flipkart search error: {e}")
        if not results:
            results.append({
                "platform": "Flipkart",
                "title": product,
                "price": 0,
                "url": f"https://www.flipkart.com/search?q={urllib.parse.quote(product)}",
                "card_offers": [],
                "fallback": True,
            })
        return results

    def _search_google_shopping(self, product):
        """Google Shopping fallback."""
        return [{
            "platform": "Google Shopping",
            "title": product,
            "price": 0,
            "url": f"https://www.google.com/search?tbm=shop&q={urllib.parse.quote(product)}",
            "card_offers": [],
            "fallback": True,
        }]

    def snipe_best_deal(self, product_query, speak_fn=None, update_status_fn=None, query_ai_fn=None):
        """Main entry: compare prices and open the best deal."""
        # Clean the query
        clean_query = product_query.lower()
        for prefix in [
            "find me the best deal on", "find the best deal on", "best deal on",
            "compare prices for", "compare price of", "compare prices of",
            "price check", "price compare", "cheapest price for", "cheapest",
            "best price for", "best price of", "how much is", "how much does",
            "find me", "find the", "shop for", "buy", "purchase",
            "shopping sniper", "price sniper", "snipe",
        ]:
            if clean_query.startswith(prefix):
                clean_query = clean_query[len(prefix):].strip()
                break
        # Remove trailing filler
        for suffix in ["cost", "price", "cost in india", "in india", "online"]:
            if clean_query.endswith(suffix):
                clean_query = clean_query[:-len(suffix)].strip()
        if not clean_query:
            clean_query = product_query

        product = clean_query.strip()
        if speak_fn:
            speak_fn(f"Deploying the Price Sniper across Amazon, Flipkart, and Google Shopping for {product}, sir. Stand by.", block=False)
        if update_status_fn:
            update_status_fn({"status": "price_sniper", "product": product, "scanning": True})

        # Parallel price fetching
        all_results = []
        threads = []

        def _fetch_amazon():
            all_results.extend(self._search_amazon(product))
        def _fetch_flipkart():
            all_results.extend(self._search_flipkart(product))
        def _fetch_google():
            all_results.extend(self._search_google_shopping(product))

        for fn in [_fetch_amazon, _fetch_flipkart, _fetch_google]:
            t = threading.Thread(target=fn, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=15)

        # Filter out fallback-only results if we have real prices
        real_results = [r for r in all_results if not r.get("fallback") and r["price"] > 0]
        if real_results:
            real_results.sort(key=lambda x: x["price"])
            best = real_results[0]
            # Build spoken summary
            summary_parts = []
            for r in real_results[:3]:
                part = f"{r['platform']} has it at {int(r['price']):,} rupees"
                if r.get("card_offers"):
                    part += f" with {', '.join(r['card_offers'])} card offers"
                summary_parts.append(part)

            summary = ". ".join(summary_parts)
            if speak_fn:
                speak_fn(f"Sir, {summary}. Opening the best deal on {best['platform']} now.", block=False)

            webbrowser.open(best["url"])
            self.last_results = real_results
        else:
            # Fallback: open all three search pages
            if speak_fn:
                speak_fn(f"Sir, I could not extract exact prices programmatically. Opening Amazon, Flipkart, and Google Shopping search pages for {product} so you can compare manually.", block=False)
            for r in all_results:
                if r.get("fallback"):
                    webbrowser.open(r["url"])
                    time.sleep(0.5)
            self.last_results = all_results

        if update_status_fn:
            update_status_fn({"status": "standby", "scanning": False})

        return self.last_results


# Module-level singleton
price_sniper = PriceSniperEngine()
