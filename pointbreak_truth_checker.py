#!/usr/bin/env python3
"""
Point Break - Unbiased Truth & Scam/Review Detector Engine
==========================================================
Searches Reddit, Quora, consumer forums, Trustpilot for REAL user reviews.
Filters out sponsored blogs and paid content.
Delivers unfiltered verdicts with sources.
"""
import sys, os, re, json, threading, time, webbrowser, urllib.parse
sys.stdout.reconfigure(encoding="utf-8")

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


# Sponsored/paid content indicators to filter out
SPONSORED_INDICATORS = [
    "sponsored", "ad", "advertisement", "paid partnership", "affiliate",
    "this post contains affiliate links", "commission", "partnered with",
    "in collaboration with", "brand ambassador", "gifted", "pr sample",
    "this is a sponsored", "disclosure: this post",
]

# Trusted unbiased sources
TRUSTED_SOURCES = {
    "reddit": "site:reddit.com",
    "quora": "site:quora.com",
    "trustpilot": "site:trustpilot.com",
    "mouthshut": "site:mouthshut.com",
    "consumer_complaints": "site:consumercomplaints.in",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}


class TruthCheckerEngine:
    """Aggregates real user reviews and delivers unbiased verdicts."""

    def __init__(self):
        self.last_verdict = None
        self.last_sources = []

    def _search_reddit(self, query):
        """Search Reddit for real user discussions."""
        results = []
        try:
            url = f"https://old.reddit.com/search?q={urllib.parse.quote(query)}&sort=relevance&t=all"
            if requests and BeautifulSoup:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                soup = BeautifulSoup(resp.text, "html.parser")
                posts = soup.select("div.thing.link")
                for post in posts[:8]:
                    title_el = post.select_one("a.title")
                    if title_el:
                        title = title_el.get_text(strip=True)
                        link = title_el.get("href", "")
                        if not link.startswith("http"):
                            link = "https://old.reddit.com" + link
                        # Get comment count
                        comments_el = post.select_one("a.comments")
                        comment_count = 0
                        if comments_el:
                            cm_text = comments_el.get_text(strip=True)
                            nums = re.findall(r"\d+", cm_text)
                            if nums:
                                comment_count = int(nums[0])
                        # Check for score
                        score_el = post.select_one("div.score.unvoted")
                        score = 0
                        if score_el:
                            score_text = score_el.get("title", "0")
                            try:
                                score = int(score_text)
                            except ValueError:
                                pass
                        results.append({
                            "source": "Reddit",
                            "title": title[:100],
                            "url": link,
                            "comments": comment_count,
                            "score": score,
                        })
        except Exception as e:
            print(f"[Truth Checker] Reddit search error: {e}")
        return results

    def _search_google_for_source(self, query, site_filter):
        """Search Google with a site filter for unbiased sources."""
        results = []
        try:
            search_q = f"{query} reviews {site_filter}"
            url = f"https://www.google.com/search?q={urllib.parse.quote(search_q)}"
            if requests and BeautifulSoup:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.select("div.g a[href]")
                for a in links[:5]:
                    href = a.get("href", "")
                    title_el = a.select_one("h3")
                    if title_el and href.startswith("http"):
                        title = title_el.get_text(strip=True)
                        # Filter out sponsored content
                        if not any(indicator in title.lower() for indicator in SPONSORED_INDICATORS):
                            source_name = "Quora" if "quora.com" in href else \
                                         "Trustpilot" if "trustpilot.com" in href else \
                                         "MouthShut" if "mouthshut.com" in href else \
                                         "ConsumerComplaints" if "consumercomplaints.in" in href else \
                                         "Forum"
                            results.append({
                                "source": source_name,
                                "title": title[:100],
                                "url": href,
                            })
        except Exception as e:
            print(f"[Truth Checker] Google search error: {e}")
        return results

    def _generate_verdict(self, query, all_sources, query_ai_fn):
        """Use AI to aggregate sentiment and generate an unbiased verdict."""
        if not query_ai_fn:
            return self._fallback_verdict(query, all_sources)

        try:
            import google.generativeai as genai
            model = genai.GenerativeModel("gemini-2.0-flash")

            sources_text = "\n".join(
                f"  [{s.get('source')}] {s.get('title')} "
                f"({'Comments: ' + str(s.get('comments', 'N/A')) if 'comments' in s else ''})"
                for s in all_sources[:15]
            )

            prompt = (
                f"You are Point Break's Truth Checker. Based on these REAL user discussions and reviews about '{query}':\n\n"
                f"{sources_text}\n\n"
                f"Provide an unbiased, brutally honest verdict. You MUST:\n"
                f"1. Ignore ALL sponsored content, paid reviews, and affiliate blogs\n"
                f"2. Focus ONLY on real user experiences from Reddit, Quora, consumer forums\n"
                f"3. Give a clear VERDICT: WORTH IT / NOT WORTH IT / MIXED / SCAM ALERT / PROCEED WITH CAUTION\n"
                f"4. List the top 3 pros and top 3 cons from real users\n"
                f"5. Give your confidence level (Low/Medium/High) based on amount of data\n\n"
                f"Return ONLY a JSON object with keys: verdict, confidence, pros (array), cons (array), summary (2-3 sentences). "
                f"No markdown, no code fences."
            )

            response = model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            return json.loads(text)
        except Exception as e:
            print(f"[Truth Checker] AI verdict error: {e}")
            return self._fallback_verdict(query, all_sources)

    def _fallback_verdict(self, query, sources):
        """Simple fallback verdict without AI."""
        return {
            "verdict": "NEEDS MANUAL REVIEW",
            "confidence": "Low",
            "pros": ["Multiple sources found for review"],
            "cons": ["Could not perform automated sentiment analysis"],
            "summary": f"Found {len(sources)} discussion threads about {query}. Please review the opened sources manually for an informed decision.",
        }

    def truth_check(self, query, speak_fn=None, update_status_fn=None, query_ai_fn=None):
        """Main entry: search for real reviews and deliver verdict."""
        # Clean the query
        clean_query = query.lower()
        for prefix in [
            "truth check", "is this legit", "is this a scam", "real reviews for",
            "real reviews of", "honest review of", "honest review for",
            "unbiased review of", "unbiased review for", "should i buy",
            "is it worth it", "is it worth buying", "is it safe",
            "is this safe", "should i trust", "can i trust",
            "check if", "verify", "scam check", "review check",
        ]:
            if clean_query.startswith(prefix):
                clean_query = clean_query[len(prefix):].strip()
                break
        if not clean_query:
            clean_query = query

        topic = clean_query.strip()
        if speak_fn:
            speak_fn(
                f"Deploying the Truth Checker on {topic}, sir. "
                f"Scanning Reddit, Quora, Trustpilot, and consumer forums. "
                f"No sponsored garbage, only real user experiences.",
                block=False
            )
        if update_status_fn:
            update_status_fn({"status": "truth_checker", "topic": topic, "scanning": True})

        # Parallel source fetching
        all_sources = []
        threads = []

        def _fetch_reddit():
            all_sources.extend(self._search_reddit(topic))
        def _fetch_quora():
            all_sources.extend(self._search_google_for_source(topic, TRUSTED_SOURCES["quora"]))
        def _fetch_trustpilot():
            all_sources.extend(self._search_google_for_source(topic, TRUSTED_SOURCES["trustpilot"]))
        def _fetch_complaints():
            all_sources.extend(self._search_google_for_source(topic, TRUSTED_SOURCES["consumer_complaints"]))

        for fn in [_fetch_reddit, _fetch_quora, _fetch_trustpilot, _fetch_complaints]:
            t = threading.Thread(target=fn, daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=15)

        self.last_sources = all_sources
        total = len(all_sources)

        # Generate AI verdict
        verdict = self._generate_verdict(topic, all_sources, query_ai_fn)
        self.last_verdict = verdict

        # Speak the verdict
        if speak_fn:
            v = verdict.get("verdict", "INCONCLUSIVE")
            confidence = verdict.get("confidence", "Low")
            summary = verdict.get("summary", "")
            pros = verdict.get("pros", [])
            cons = verdict.get("cons", [])

            speak_text = (
                f"Sir, based on {total} real user discussions and reviews, "
                f"the verdict on {topic} is: {v}. Confidence: {confidence}. "
            )
            if summary:
                speak_text += f"{summary} "
            if pros:
                speak_text += f"Top pros: {', '.join(pros[:2])}. "
            if cons:
                speak_text += f"Top cons: {', '.join(cons[:2])}. "

            # Open the best Reddit thread
            reddit_sources = [s for s in all_sources if s.get("source") == "Reddit"]
            if reddit_sources:
                speak_text += "Opening the most discussed Reddit thread now."
                webbrowser.open(reddit_sources[0]["url"])
            elif all_sources:
                speak_text += "Opening the top source now."
                webbrowser.open(all_sources[0]["url"])

            speak_fn(speak_text, block=False)

        if update_status_fn:
            update_status_fn({"status": "standby", "scanning": False})

        return verdict


# Module-level singleton
truth_checker = TruthCheckerEngine()
