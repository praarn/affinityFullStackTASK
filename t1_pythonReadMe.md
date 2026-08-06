# MDComputers.in Product Search Scraper

Two versions of a Python script that scrape product listings from
[mdcomputers.in](https://mdcomputers.in) search results (e.g.
`?route=product/search&search=external harddrive`) and export them to
CSV or JSON.

Both versions share the same CLI and output shape — they differ only in
**how they locate product cards** inside the page HTML.

```bash
pip install requests beautifulsoup4 lxml
python <script>.py "external harddrive"
```

- `t1.py` — version 1 (OpenCart-default selectors)
- `t1modified.py` — version 2 (theme-agnostic, with fallback parser) — **this is the working version**

---

## File 1 — `t1.py` (v1, OpenCart-default selectors)

### How it works
MDComputers runs on the OpenCart platform, so this version assumes the
site uses OpenCart's **default** theme markup:

- Product card: `div.product-thumb` or `div.product-layout`
- Product name/link: `.caption h4 a`
- Price block: `.price`, with `.price-old` / `.price-new` (or `<del>` /
  `<ins>`) for old vs. discounted price
- Discount badge: `.sale`, `.special-tag`, or `.discount`
- Pagination total: parsed from the `"Showing X to Y of Z (N Pages)"`
  footer text, with a fallback that counts `page=` links in
  `ul.pagination`

### What actually happened when run
MDComputers uses a **customized** theme, not OpenCart's stock class
names, so none of the CSS selectors above (`div.product-thumb`,
`.caption h4 a`, etc.) matched anything on the real page.

```
Searching MDComputers for: 'external harddrive' ...
Found 0 products.
No products to save.
Saved results to mdcomputers_results.csv
```

The request itself succeeded (no network/HTTP errors) — the script
just couldn't find any elements matching its selector guesses, so it
returned an empty list and wrote a CSV with headers only, no rows.

### Verdict
❌ Non-functional against the live site as-is. Kept here only as a
reference for what a "default OpenCart theme" scraper looks like.

---

## File 2 — `t1modified.py` (v2, theme-agnostic with fallback parser)

### How it works
This version keeps the v1 selectors as a fast first attempt, but adds a
**structure-agnostic fallback parser**, `_parse_generic()`, used
whenever the CSS-based pass finds nothing:

1. Find every `<a href="...">` tag whose URL matches `/product/<slug>`
   — this pattern is a stable feature of MDComputers' product URLs
   regardless of theme.
2. Group all anchors that point at the same product URL (a card
   typically has 2–3: image link, title link, "Quick view" link).
3. Walk up the DOM tree from that anchor (up to 8 levels) until it
   finds a container whose text contains a `₹` price — that container
   is treated as "the card."
4. Extract fields from that card:
   - **Name** — prefers anchor text inside a heading tag (`h1`–`h5`);
     falls back to the longest non-button anchor text (skipping
     "Add to Cart", "Quick view", "Compare", "Add to wishlist"); falls
     back further to the image's `alt` text.
   - **Image** — first `<img>` inside the card (`data-src` or `src`).
   - **Prices** — all `₹`-prefixed numbers found in the card's text;
     if two are found, the first is `regular_price` and the second is
     `special_price` (discounted); if only one, it's `special_price`.
   - **Discount %** — a `-NN%` pattern found in the card's text.
5. Pagination total-pages logic is unchanged from v1.

It also adds a `--debug` flag that dumps the raw HTML of each fetched
page to `debug_page_<N>.html`, so mismatches can be diagnosed directly
from what the site actually returned, instead of guessing again.

### Confirmed output
Run against the live site with `python t1modified.py "external harddrive"`:

```
Searching MDComputers for: 'external harddrive' ...
Found 45 products.
Saved results to mdcomputers_results.csv
 - EK-Loop Connect - External USB Cable (1M) | ₹550 (was ₹1,299) | -58%
 - Pioneer 240GB Type-C External SSD | ₹4,999 (was ₹9,900) | -50%
 - Pioneer XS03 External SSD 480GB | ₹5,999 (was ₹10,500) | -43%
 - Seagate Expansion 1TB External Hard Drive | ₹9,140 (was ₹10,000) | -9%
 - Western Digital Elements 1TB External Hard Drive | ₹9,299 (was ₹14,000) | -34%
   ... and 40 more
```

The fallback parser (`_parse_generic`) matched the live theme and
correctly extracted name, both prices, and the discount badge for all
45 products across the paginated result set. `mdcomputers_results.csv`
now has one row per product, e.g.:

| name | url | image | regular_price | special_price | discount_pct | in_stock | sku | description |
|---|---|---|---|---|---|---|---|---|
| Seagate Expansion 1TB External Hard Drive | https://mdcomputers.in/product/seagate-expansion-1tb-external-hard-drive-stkm1000400 | https://mdcomputers.in/image/... | ₹10,000 | ₹9,140 | -9% | | | |

`in_stock`, `sku`, and `description` are only populated when the script
is run with `--details` (which visits each product's own page — slower,
one extra HTTP request per product).

### Status
✅ Working against the live site — 45/45 products found for
`"external harddrive"` (matches the site's own "44"-ish result count,
since search also picks up loosely related accessories like USB hubs
and capture cards). If a different search term ever returns 0
products (e.g. the theme changes again), diagnose with:

```bash
python t1modified.py "<term>" --debug
```

then inspect `debug_page_1.html` for the actual markup around one
product to further refine the selectors/parser.

---

## CLI reference (both versions)

| Flag | Description | Default |
|---|---|---|
| `term` (positional) | Search term, e.g. `"external harddrive"` | required |
| `--pages N` | Max result pages to scrape | all pages |
| `--details` | Visit each product page for SKU/stock/description | off |
| `--out PATH` | Output file path | `mdcomputers_results.csv` |
| `--format {csv,json}` | Output format | `csv` |
| `--delay SECONDS` | Delay between requests | `1.0` |
| `--debug` | Save raw HTML of each fetched page (`t1modified.py` only) | off |

## Output fields

| Field | Meaning |
|---|---|
| `name` | Product title |
| `url` | Product detail page URL |
| `image` | Thumbnail image URL |
| `regular_price` | Original (strikethrough) price, if discounted |
| `special_price` | Current selling price |
| `discount_pct` | Discount badge text, e.g. `-41%` |
| `in_stock` | Availability text (only with `--details`) |
| `sku` | Product code (only with `--details`) |
| `description` | First ~500 chars of product description (only with `--details`) |
