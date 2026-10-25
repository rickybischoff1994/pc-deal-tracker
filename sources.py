"""
sources.py - one function for each website we collect prices from.

Every "search" function hands back a LIST of listings, and every listing is
a dictionary (a set of labelled values) that looks the same no matter which
website it came from:

    {
        "price": 599.0,                 # in Australian dollars
        "title": "AMD Ryzen 7 9800X3D",  # the product name the shop uses
        "store": "Scorptec",            # which shop sells it
        "link":  "https://...",         # where to buy it
        "stock": "in stock",            # "in stock", "out of stock" or "?" (unknown)
        "image": "https://..." or "",   # a product photo, if the site gives one
        "source": "StaticICE",          # which website we found it on
    }

Keeping every listing the same shape means price_watch.py doesn't need to
care where a listing came from - it can sort and compare them all together.

WEBSITES USED:
  * StaticICE  - an Aussie price-comparison site covering ~15 stores
                 (PC Case Gear, Scorptec, Umart, MSY, JB Hi-Fi, Computer &
                 Parts Land, JW Computers, CCPU, Computer Alliance, PLE ...)
  * Mwave      - not on StaticICE, so we ask Mwave directly
  * OzBargain  - the community deals site; we read its public deal "feeds"
"""

import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime   # reads dates like "Fri, 18 Sep 2026"

# Pretend to be a normal web browser - a few sites refuse anything else.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
}


def download(url):
    """Download any web address and return its contents as text."""
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    # Most sites use "utf-8" text encoding. If that fails, fall back to
    # "latin-1", which can read any bytes (StaticICE uses it).
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def clean_text(raw_html):
    """Remove HTML tags and turn codes like &amp; into normal text."""
    no_tags = re.sub(r"<[^>]+>", " ", raw_html)       # delete things like <b>
    one_line = re.sub(r"\s+", " ", html.unescape(no_tags))  # squash spaces
    return one_line.strip()


def guess_stock(title):
    """
    Some shops add stock info to the product name, like "(In Stock)" or
    "[Avail: In Stock]". Look for those words and return a stock label.
    """
    lower = title.lower()
    if "out of stock" in lower or "sold out" in lower:
        return "out of stock"
    if "pre-order" in lower or "preorder" in lower:
        return "pre-order"
    if "in stock" in lower:
        return "in stock"
    return "?"                     # the listing doesn't say


# ===========================================================================
# 1) STATICICE - lots of stores in one search
# ===========================================================================
STATICICE_URL = "https://www.staticice.com.au/cgi-bin/search.cgi"


def staticice_search(search_text, min_price=0, pages=1):
    """
    Search StaticICE and return every listing on the first `pages` pages
    of results (20 listings per page, cheapest first).
    """
    rows = []
    # range(pages) counts 0, 1, 2... so page 0 starts at result 1,
    # page 1 starts at result 21, and so on.
    for page_number in range(pages):
        # urlencode safely turns {"q": "RX 9070 XT"} into "q=RX+9070+XT".
        # "price-min" asks StaticICE to hide anything cheaper than min_price,
        # so cheap accessories (cables, water blocks) don't fill the page.
        query = urllib.parse.urlencode({
            "q": search_text,
            "price-min": min_price,
            "start": page_number * 20 + 1,
            "links": 20,
        })
        page = download(f"{STATICICE_URL}?{query}")
        # Each search result sits in its own table row that starts with
        # <tr valign="top">. re.findall grabs every one of those rows.
        rows += re.findall(r'<tr valign="top">.*?</tr>', page, re.DOTALL)

    listings = []

    for row in rows:
        # re.search looks for a pattern; the ( ) part is what we keep.
        price = re.search(r'>\$([\d,]+\.\d\d)</a>', row)
        title = re.search(r'<td valign="bottom">(.*?)<br>', row, re.DOTALL)
        store = re.search(r'title="Click to visit the (.*?) web site"', row)
        link = re.search(r'href="([^"]*?)"[^>]*>\$', row)

        # If any piece is missing, this row isn't a normal listing - skip it.
        if not (price and title and store and link):
            continue

        title_text = clean_text(title.group(1))
        listings.append({
            "price": float(price.group(1).replace(",", "")),   # "1,199.00" -> 1199.0
            "title": title_text,
            "store": html.unescape(store.group(1)),
            "link": staticice_real_link(link.group(1)),
            "stock": guess_stock(title_text),
            "image": "",              # StaticICE doesn't show product photos
            "source": "StaticICE",
        })
    return listings


def staticice_real_link(redirect_link):
    """
    StaticICE links go through its own redirect page, with the real shop
    address tucked inside as "newurl=...". Dig out the real address so our
    links go straight to the shop.
    """
    query_part = urllib.parse.urlparse(html.unescape(redirect_link)).query
    params = urllib.parse.parse_qs(query_part)        # {"newurl": ["https://..."]}
    real = params.get("newurl", [redirect_link])[0]

    # Some shops (like JW Computers) wrap their link in an advertising
    # tracker that holds the shop address in "Url=". Unwrap that too.
    inner = urllib.parse.parse_qs(urllib.parse.urlparse(real).query)
    return inner.get("Url", [real])[0]


# ===========================================================================
# 2) MWAVE - a big Aussie store that isn't on StaticICE
# ===========================================================================
def mwave_search(search_text):
    """
    Mwave runs on Shopify, and every Shopify shop has a public search
    address that answers in JSON (neat, computer-readable data) instead of
    a web page. That's much easier and more reliable than reading HTML.
    """
    query = urllib.parse.urlencode({
        "q": search_text,
        "resources[type]": "product",
        "resources[limit]": 10,          # Shopify's maximum
    })
    data = json.loads(download(f"https://www.mwave.com.au/search/suggest.json?{query}"))

    listings = []
    for product in data["resources"]["results"]["products"]:
        listings.append({
            "price": float(product["price"]),
            "title": product["title"],
            "store": "Mwave",
            "link": "https://www.mwave.com.au" + product["url"].split("?")[0],
            # Shopify tells us True/False for "available". The "if/else" on
            # one line is called a conditional expression.
            "stock": "in stock" if product.get("available") else "out of stock",
            "image": fix_image_link(product.get("image") or ""),
            "source": "Mwave",
        })
    return listings


# ===========================================================================
# 3) OZBARGAIN - deals posted by the community
# ===========================================================================
def ozbargain_deals(feed_paths, days=30):
    """
    Read OzBargain "feeds" (RSS - a simple list of the newest posts that
    websites publish for news readers). Return deals from the last `days`
    days that haven't expired.
    """
    now = datetime.now(timezone.utc)
    oldest_allowed = now - timedelta(days=days)
    deals = {}        # a dictionary keyed by link, so the same deal isn't added twice

    for path in feed_paths:
        try:
            feed = download(f"https://www.ozbargain.com.au/{path}/feed")
        except Exception as error:
            print(f"  OzBargain feed {path} failed: {error}")
            continue                      # move on to the next feed

        for item in re.findall(r"<item>(.*?)</item>", feed, re.DOTALL):
            # OzBargain marks finished deals with title-msg type="expired".
            if 'type="expired"' in item:
                continue

            title = clean_text(re.search(r"<title>(.*?)</title>", item, re.DOTALL).group(1))
            link = re.search(r"<link>(.*?)</link>", item).group(1)
            posted = parsedate_to_datetime(re.search(r"<pubDate>(.*?)</pubDate>", item).group(1))
            if posted < oldest_allowed:
                continue                  # too old

            # Some deals list an expiry date - skip them if it has passed.
            expiry = re.search(r'expiry="([^"]+)"', item)
            if expiry and datetime.fromisoformat(expiry.group(1)) < now:
                continue

            image = re.search(r'image="([^"]+)"', item)
            # Find the first "$123" or "$1,234.56" in the title = the deal price.
            price = re.search(r"\$([\d,]+(?:\.\d\d)?)", title)
            # Shops are named after an "@" at the end, e.g. "... @ Amazon AU".
            store = title.rsplit("@", 1)[1].strip() if "@" in title else "OzBargain"
            votes = re.search(r'votes-pos="(\d+)"', item)

            deals[link] = {
                "price": float(price.group(1).replace(",", "")) if price else None,
                "title": title,
                "store": store,
                "link": link,
                "stock": "?",
                "image": html.unescape(image.group(1)) if image else "",
                "source": "OzBargain",
                "posted": posted.strftime("%d %b"),
                "votes": int(votes.group(1)) if votes else 0,
            }
    # .values() gives just the deals, without the link keys.
    return list(deals.values())


# ===========================================================================
# PICTURES - find a product photo for listings that don't have one
# ===========================================================================
# Shops whose product pages we're allowed to read and that include a photo.
IMAGE_FRIENDLY_SHOPS = ("jbhifi.com.au", "umart.com.au", "msy.com.au", "mwave.com.au")


def fix_image_link(url):
    """Make image links complete: "//cdn..." -> "https://cdn..." and http -> https."""
    if url.startswith("//"):
        url = "https:" + url
    return url.replace("http://", "https://", 1)


def find_image(product_link):
    """
    Most shop pages include an "og:image" tag - the picture that shows up
    when you share the link on Facebook or Messenger. We borrow that.
    Returns "" (empty text) if there's no picture or the shop blocks us.
    """
    # any() is True if the link contains at least one of the friendly shops.
    if not any(shop in product_link for shop in IMAGE_FRIENDLY_SHOPS):
        return ""
    try:
        page = download(product_link)
    except Exception:
        return ""
    match = re.search(r'<meta[^>]*property="og:image"[^>]*content="([^"]+)"', page)
    if not match or "logo" in match.group(1).lower():   # skip shop logos
        return ""
    return fix_image_link(html.unescape(match.group(1)))
