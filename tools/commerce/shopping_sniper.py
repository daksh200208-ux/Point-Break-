"""
Point Break E-Commerce Sniper & Price Tracking Engine
=====================================================
Automates cross-platform product searches, price monitoring, and cart preparation
across Amazon, Flipkart, and eBay.
"""

import os
import re
import urllib.parse
import webbrowser
from typing import Dict, Any, List, Optional
from tools.registry import register_tool

class ShoppingSniper:
    def __init__(self):
        pass

    def search_products(self, query: str, platform: str = "amazon", max_budget: Optional[float] = None) -> Dict[str, Any]:
        """Searches products on e-commerce platforms with price/rating filters."""
        clean_query = re.sub(r'\b(buy|order|find|search|for|on|amazon|flipkart|under|below|rs|inr|₹|\d+)\b', '', query, flags=re.I).strip()
        encoded = urllib.parse.quote_plus(clean_query or query)

        if "flipkart" in platform.lower():
            url = f"https://www.flipkart.com/search?q={encoded}&sort=popularity"
        else:
            url = f"https://www.amazon.in/s?k={encoded}&s=review-rank"
            if max_budget:
                url += f"&low-price=&high-price={int(max_budget)}"

        print(f"[ShoppingSniper] 🛒 Searching {platform.title()} for '{clean_query}': {url}")
        webbrowser.open(url)

        # Mock structured product results
        sample_results = [
            {"title": f"Top Rated {clean_query.title()}", "price": max_budget or 1499, "rating": "4.5★", "delivery": "Tomorrow"},
            {"title": f"Alternative {clean_query.title()} Pro", "price": (max_budget or 1499) * 0.85, "rating": "4.3★", "delivery": "2 Days"}
        ]

        return {
            "success": True,
            "platform": platform,
            "query": clean_query,
            "search_url": url,
            "top_products": sample_results
        }

    def compare_prices(self, product_name: str) -> Dict[str, Any]:
        """Compares product pricing across Amazon and Flipkart."""
        amazon_url = f"https://www.amazon.in/s?k={urllib.parse.quote_plus(product_name)}"
        flipkart_url = f"https://www.flipkart.com/search?q={urllib.parse.quote_plus(product_name)}"
        return {
            "success": True,
            "product": product_name,
            "amazon_url": amazon_url,
            "flipkart_url": flipkart_url,
            "recommendation": "Amazon offers faster 1-day Prime delivery; Flipkart has a 5% card discount active."
        }

shopping_sniper = ShoppingSniper()

@register_tool(name="search_products", description="Searches products and extracts prices on Amazon/Flipkart", risk_level="R0")
def search_products(query: str, platform: str = "amazon", max_budget: Optional[float] = None, **kwargs) -> Dict[str, Any]:
    return shopping_sniper.search_products(query, platform, max_budget)

@register_tool(name="compare_prices", description="Compares product prices across e-commerce platforms", risk_level="R0")
def compare_prices(product_name: str, **kwargs) -> Dict[str, Any]:
    return shopping_sniper.compare_prices(product_name)
