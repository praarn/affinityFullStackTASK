import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional
from urllib.parse import urlencode, urljoin
 
import requests
from bs4 import BeautifulSoup
 
BASE_URL = "https://mdcomputers.in/"
SEARCH_ROUTE = "index.php?route=product/search"
 
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
 
PRICE_RE = re.compile(r"[\d,]+(?:\.\d+)?")
PRODUCT_HREF_RE = re.compile(r"/product/[a-z0-9\-]+", re.I)
PRICE_FULL_RE = re.compile(r"₹\s?[\d,]+(?:\.\d+)?")
DISCOUNT_RE = re.compile(r"-\s?\d+%")
SKIP_TEXTS = {"add to cart", "quick view", "add to wishlist", "compare", "", "product compare (%s)"}
 
 
@dataclass
class Product:
    name: str
    url: str
    image: Optional[str] = None
    regular_price: Optional[str] = None
    special_price: Optional[str] = None
    discount_pct: Optional[str] = None
    in_stock: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
 
 
class MDComputersScraper:
    def __init__(self, delay: float = 1.0, timeout: int = 20):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.delay = delay
        self.timeout = timeout
 
    # ------------------------------------------------------------------ #
    # Core fetch helpers
    # ------------------------------------------------------------------ #
    def _get(self, url: str, params: dict = None) -> BeautifulSoup:
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
 
    def _search_url(self, term: str, page: int) -> str:
        params = {"route": "product/search", "search": term}
        if page > 1:
            params["page"] = page
        return f"{BASE_URL}?{urlencode(params)}"
 
    # ------------------------------------------------------------------ #
    # Listing page parsing
    # ------------------------------------------------------------------ #
    @staticmethod
    def _clean_price(text: str) -> Optional[str]:
        if not text:
            return None
        match = PRICE_RE.search(text.replace("\xa0", " "))
        return f"₹{match.group(0)}" if match else text.strip()
 
    def _parse_card(self, card) -> Optional[Product]:
        title_tag = card.select_one(".caption h4 a") or card.select_one("h4 a")
        if not title_tag:
            return None
 
        name = title_tag.get_text(strip=True)
        url = urljoin(BASE_URL, title_tag.get("href", ""))
 
        img_tag = card.select_one("img")
        image = None
        if img_tag:
            image = img_tag.get("data-src") or img_tag.get("src")
            if image:
                image = urljoin(BASE_URL, image)
 
        # Price block usually has two <span> or <p> elements when discounted:
        # one with class price-old/was and one with price-new/special
        price_block = card.select_one(".price")
        regular_price = special_price = None
        if price_block:
            old_tag = price_block.select_one(".price-old, .price-tax, del")
            new_tag = price_block.select_one(".price-new, ins")
            if old_tag and new_tag:
                regular_price = self._clean_price(old_tag.get_text())
                special_price = self._clean_price(new_tag.get_text())
            else:
                # No discount: single price string
                special_price = self._clean_price(price_block.get_text())
 
        # Discount ribbon, e.g. "-41%"
        discount_tag = card.select_one(".sale, .special-tag, .discount")
        discount_pct = discount_tag.get_text(strip=True) if discount_tag else None
 
        return Product(
            name=name,
            url=url,
            image=image,
            regular_price=regular_price,
            special_price=special_price,
            discount_pct=discount_pct,
        )
 
    def _parse_generic(self, soup: BeautifulSoup) -> List[Product]:
        """Theme-agnostic fallback: locate product cards by following links
        that point at /product/<slug>, then walk up the DOM until we find a
        container that holds a rupee price. Works regardless of what CSS
        classes the current theme happens to use."""
        anchors = soup.find_all("a", href=PRODUCT_HREF_RE)
        by_href = {}
        for a in anchors:
            href = urljoin(BASE_URL, a.get("href", "")).split("?")[0]
            by_href.setdefault(href, []).append(a)
 
        products = []
        for href, tags in by_href.items():
            # Walk up from the first anchor until we hit a container that
            # actually contains a price - that's our "card".
            card = None
            node = tags[0]
            for _ in range(8):
                node = node.parent
                if node is None:
                    break
                if "₹" in node.get_text():
                    card = node
                    break
            if card is None:
                card = tags[0].parent or tags[0]
 
            # Prefer the anchor text sitting inside a heading tag (h2-h5);
            # otherwise fall back to the longest non-button anchor text.
            name = None
            for t in tags:
                if t.find_parent(["h1", "h2", "h3", "h4", "h5"]):
                    txt = t.get_text(strip=True)
                    if txt:
                        name = txt
                        break
            if not name:
                candidates = [t.get_text(strip=True) for t in tags]
                candidates = [c for c in candidates if c.lower() not in SKIP_TEXTS]
                if candidates:
                    name = max(candidates, key=len)
            if not name:
                img = tags[0].find("img")
                name = (img.get("alt", "").strip() if img else None)
            if not name:
                continue
 
            img_tag = card.find("img")
            image = None
            if img_tag:
                image = img_tag.get("data-src") or img_tag.get("src")
                if image:
                    image = urljoin(BASE_URL, image)
 
            text = card.get_text(" ", strip=True)
            prices = PRICE_FULL_RE.findall(text)
            regular_price = special_price = None
            if len(prices) >= 2:
                regular_price, special_price = prices[0], prices[1]
            elif len(prices) == 1:
                special_price = prices[0]
 
            discount_match = DISCOUNT_RE.search(text)
            discount_pct = discount_match.group(0) if discount_match else None
 
            products.append(
                Product(
                    name=name,
                    url=href,
                    image=image,
                    regular_price=regular_price,
                    special_price=special_price,
                    discount_pct=discount_pct,
                )
            )
        return products
 
    def _total_pages(self, soup: BeautifulSoup) -> int:
        """Read '<b>Showing 1 to 20 of 44 (3 Pages)</b>' style footer, or fall
        back to counting pagination links."""
        text = soup.get_text(" ", strip=True)
        m = re.search(r"\((\d+)\s+Pages?\)", text)
        if m:
            return int(m.group(1))
 
        page_links = soup.select("ul.pagination a, .pagination a")
        pages = set()
        for a in page_links:
            m = re.search(r"page=(\d+)", a.get("href", ""))
            if m:
                pages.add(int(m.group(1)))
        return max(pages) if pages else 1
 
    def search_page(self, term: str, page: int = 1, debug: bool = False) -> (List[Product], int):
        url = self._search_url(term, page)
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
 
        if debug:
            fname = f"debug_page_{page}.html"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(resp.text)
            print(f"[debug] saved raw HTML to {fname}")
 
        # First try theme-default OpenCart selectors (fast path if the site
        # ever reverts to a stock theme), then fall back to the generic,
        # class-name-agnostic parser that works on the current custom theme.
        cards = soup.select("div.product-thumb, div.product-layout")
        products = [p for p in (self._parse_card(c) for c in cards) if p]
        if not products:
            products = self._parse_generic(soup)
 
        total_pages = self._total_pages(soup)
        return products, total_pages
 
    def search(self, term: str, max_pages: Optional[int] = None, debug: bool = False) -> List[Product]:
        all_products: List[Product] = []
        page = 1
        total_pages = 1
 
        while True:
            products, total_pages = self.search_page(term, page, debug=debug)
            if not products:
                break
            all_products.extend(products)
 
            if max_pages:
                total_pages = min(total_pages, max_pages)
            if page >= total_pages:
                break
 
            page += 1
            time.sleep(self.delay)
 
        return all_products
 
    # ------------------------------------------------------------------ #
    # Optional: visit each product page for extra detail
    # ------------------------------------------------------------------ #
    def enrich_with_details(self, product: Product) -> Product:
        try:
            soup = self._get(product.url)
        except requests.RequestException:
            return product
 
        # Availability
        stock_label = soup.find(string=re.compile("Availability", re.I))
        if stock_label:
            container = stock_label.find_parent()
            if container:
                sibling_text = container.get_text(" ", strip=True)
                m = re.search(r"Availability:\s*([A-Za-z ]+)", sibling_text)
                if m:
                    product.in_stock = m.group(1).strip()
 
        # SKU / Product Code
        sku_label = soup.find(string=re.compile(r"Product Code|SKU", re.I))
        if sku_label:
            container = sku_label.find_parent()
            if container:
                text = container.get_text(" ", strip=True)
                m = re.search(r"(?:Product Code|SKU):\s*(\S+)", text)
                if m:
                    product.sku = m.group(1).strip()
 
        # Short description
        desc_tag = soup.select_one("#tab-description, .tab-content #tab-description")
        if desc_tag:
            product.description = desc_tag.get_text(" ", strip=True)[:500]
 
        return product
 
    def search_with_details(self, term: str, max_pages: Optional[int] = None) -> List[Product]:
        products = self.search(term, max_pages)
        enriched = []
        for i, p in enumerate(products, 1):
            enriched.append(self.enrich_with_details(p))
            time.sleep(self.delay)
        return enriched
 
 
# ---------------------------------------------------------------------- #
# Output helpers
# ---------------------------------------------------------------------- #
def save_csv(products: List[Product], path: str):
    if not products:
        print("No products to save.")
        return
    fieldnames = list(asdict(products[0]).keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in products:
            writer.writerow(asdict(p))
 
 
def save_json(products: List[Product], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(p) for p in products], f, indent=2, ensure_ascii=False)
 
 
# ---------------------------------------------------------------------- #
# CLI
# ---------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(description="Scrape MDComputers.in product search results.")
    parser.add_argument("term", help='Search term, e.g. "external harddrive"')
    parser.add_argument("--pages", type=int, default=None, help="Max pages to scrape (default: all)")
    parser.add_argument("--details", action="store_true", help="Visit each product page for SKU/stock/description")
    parser.add_argument("--out", default="mdcomputers_results.csv", help="Output file path")
    parser.add_argument("--format", choices=["csv", "json"], default="csv")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
    parser.add_argument("--debug", action="store_true", help="Save raw HTML of each fetched page for inspection")
    args = parser.parse_args()
 
    scraper = MDComputersScraper(delay=args.delay)
 
    print(f"Searching MDComputers for: {args.term!r} ...")
    if args.details:
        products = scraper.search_with_details(args.term, max_pages=args.pages)
    else:
        products = scraper.search(args.term, max_pages=args.pages, debug=args.debug)
 
    print(f"Found {len(products)} products.")
 
    if args.format == "csv":
        save_csv(products, args.out)
    else:
        save_json(products, args.out)
 
    print(f"Saved results to {args.out}")
 
    for p in products[:5]:
        print(f" - {p.name} | {p.special_price or 'N/A'} (was {p.regular_price or '—'}) | {p.discount_pct or ''}")
    if len(products) > 5:
        print(f"   ... and {len(products) - 5} more")
 
 
if __name__ == "__main__":
    main()