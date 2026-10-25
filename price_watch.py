"""
price_watch.py - finds the cheapest Australian price for each PC part we want.

HOW IT WORKS (the big picture):
  1. Read the list of parts from parts.json
  2. For each part, search StaticICE (an Aussie price-comparison website)
  3. Pull every price + product name out of the web page
  4. Throw away results that don't match (wrong product, accessories, etc.)
  5. Keep the cheapest one that's left
  6. Write a table of results into README.md, and save a line per part
     into price_history.csv so we can see prices change over time

This file only uses Python's built-in "standard library", so there is
nothing extra to install. You can run it yourself with:
    python price_watch.py
"""

# ---------------------------------------------------------------------------
# IMPORTS - pulling in ready-made tools that come with Python
# ---------------------------------------------------------------------------
import csv                      # reads/writes CSV (spreadsheet-style) files
import html                     # turns things like "&amp;" back into "&"
import json                     # reads our parts.json file
import re                       # "regular expressions" - pattern matching in text
import time                     # lets us pause between web requests
import urllib.parse             # builds and picks apart web addresses (URLs)
import urllib.request           # downloads web pages
from datetime import datetime, timezone, timedelta
from pathlib import Path        # a tidy way to work with file paths

# ---------------------------------------------------------------------------
# SETTINGS - values used throughout the program. Written in CAPITALS by
# convention, which tells other programmers "this never changes while running".
# ---------------------------------------------------------------------------
SEARCH_URL = "https://www.staticice.com.au/cgi-bin/search.cgi"

# Path(__file__).parent means "the folder this script lives in", so the
# program finds its files no matter where you run it from.
HERE = Path(__file__).parent
PARTS_FILE = HERE / "parts.json"
README_FILE = HERE / "README.md"
HISTORY_FILE = HERE / "price_history.csv"

# The README has two invisible marker comments. We replace everything
# between them with the new table, and leave the rest of the README alone.
START_MARKER = "<!-- PRICES:START -->"
END_MARKER = "<!-- PRICES:END -->"

# Brisbane time is UTC+10 all year (Queensland has no daylight saving).
BRISBANE = timezone(timedelta(hours=10))

# Websites like to know who is visiting. We say honestly what we are.
HEADERS = {"User-Agent": "Mozilla/5.0 (pc-deal-tracker hobby project; daily check)"}

# This pattern finds each search result on the StaticICE page. In the page's
# HTML a result looks roughly like:
#   <a ... href="...newurl=STORE_LINK&..." target="_blank">$599.00</a><br></td>
#   <td valign="bottom">PRODUCT NAME<br> ... <b><font ...>STORE NAME</font></b>
# The bits in ( ) brackets are "capture groups" - the parts we want to keep.
#   (?P<name> ... )  gives a capture group a name so we can ask for it later
#   .*?              means "any characters, as few as possible"
#   re.DOTALL        lets . also match new lines
RESULT_PATTERN = re.compile(
    r'href="(?P<link>[^"]*?)"\s+target="_blank">\$(?P<price>[\d,]+\.\d\d)</a><br></td>'
    r'\s*<td valign="bottom">(?P<title>.*?)<br>'
    r'.*?<b><font color="#0080CC">(?P<store>.*?)</font></b>',
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# FUNCTIONS - each one does one small job. "def" starts a function.
# ---------------------------------------------------------------------------
def load_parts():
    """Open parts.json and return the list of parts inside it."""
    # "with" opens the file and closes it again automatically when done.
    with open(PARTS_FILE, encoding="utf-8") as f:
        data = json.load(f)      # turns the JSON text into Python lists/dicts
    return data["parts"]


def download_search_page(search_text, min_price=0):
    """Search StaticICE for search_text and return the page's HTML as text."""
    # urlencode turns {"q": "RX 9070 XT"} into "q=RX+9070+XT" (safe for a URL).
    # "price-min" asks StaticICE to skip anything cheaper than min_price, so
    # cheap accessories don't fill up the first page of results.
    query = urllib.parse.urlencode({"q": search_text, "price-min": min_price})
    url = f"{SEARCH_URL}?{query}"   # an f-string drops variables into text

    request = urllib.request.Request(url, headers=HEADERS)
    # timeout=30 means give up if the site takes longer than 30 seconds.
    with urllib.request.urlopen(request, timeout=30) as response:
        # The site's text is encoded as "latin-1"; decode turns bytes into text.
        return response.read().decode("latin-1")


def get_store_link(redirect_link):
    """
    StaticICE links go through its own redirect page, with the real shop
    address tucked inside as "newurl=...". This digs out the real address
    so the README links straight to the shop.
    """
    query_part = urllib.parse.urlparse(html.unescape(redirect_link)).query
    params = urllib.parse.parse_qs(query_part)   # {"newurl": ["https://..."], ...}
    # .get() returns the default ([redirect_link]) if "newurl" isn't there.
    return params.get("newurl", [redirect_link])[0]


def clean_text(raw_html):
    """Remove leftover HTML tags and turn codes like &amp; into normal text."""
    no_tags = re.sub(r"<[^>]+>", "", raw_html)   # delete anything like <b>
    return html.unescape(no_tags).strip()        # .strip() trims spaces


def find_results(page_html):
    """Pull every (price, title, store, link) out of a search page."""
    results = []                                  # start with an empty list
    for match in RESULT_PATTERN.finditer(page_html):
        results.append({
            # "1,199.00" -> 1199.0 (remove the comma, then turn text into a number)
            "price": float(match.group("price").replace(",", "")),
            "title": clean_text(match.group("title")),
            "store": clean_text(match.group("store")),
            "link": get_store_link(match.group("link")),
        })
    return results


def is_good_match(result, part):
    """Return True if this search result really is the part we want."""
    title = result["title"].lower()               # lower-case so "XT" == "xt"

    # all(...) is True only if EVERY required word is in the title.
    if not all(word.lower() in title for word in part["must_include"]):
        return False
    # any(...) is True if AT LEAST ONE banned word is in the title.
    if any(word.lower() in title for word in part.get("exclude", [])):
        return False
    # Too cheap usually means it's an accessory, not the real thing.
    if result["price"] < part.get("min_price", 0):
        return False
    return True


def find_cheapest(part):
    """Search for one part and return its cheapest good result (or None)."""
    page = download_search_page(part["search"], part.get("min_price", 0))
    results = find_results(page)

    # A "list comprehension": keep only results that pass is_good_match.
    good = [r for r in results if is_good_match(r, part)]
    if not good:                                  # an empty list counts as False
        return None
    # min() with key= picks the result with the smallest price.
    return min(good, key=lambda r: r["price"])


def build_table(rows, checked_at):
    """Turn our results into a Markdown table (GitHub shows it as a nice table)."""
    lines = [
        f"_Last checked: {checked_at} (Brisbane time)_",
        "",
        "| Part | Best price | Target | Deal? | Store | Product |",
        "|---|---:|---:|:---:|---|---|",
    ]
    for row in rows:
        part, best = row["part"], row["best"]
        target = f"${part['target_price']:,.0f}"      # 1099 -> "$1,099"
        if best is None:
            lines.append(f"| {part['name']} | not found | {target} | - | - | - |")
            continue                                  # skip to the next row
        deal = "✅ YES" if best["price"] <= part["target_price"] else "—"
        # The | character would break a table cell, so swap it for a dash.
        product = best["title"].replace("|", "-")[:80]
        lines.append(
            f"| {part['name']} | **${best['price']:,.2f}** | {target} | {deal} "
            f"| {best['store']} | [{product}]({best['link']}) |"
        )
    return "\n".join(lines)                           # join lines with new lines


def update_readme(table):
    """Swap the old table in README.md for the new one."""
    text = README_FILE.read_text(encoding="utf-8")
    start = text.index(START_MARKER) + len(START_MARKER)   # just after START
    end = text.index(END_MARKER)                            # just before END
    # Keep the text before and after, and put the new table in the middle.
    new_text = text[:start] + "\n" + table + "\n" + text[end:]
    README_FILE.write_text(new_text, encoding="utf-8")


def save_history(rows, checked_at):
    """Add today's prices to the bottom of price_history.csv."""
    file_is_new = not HISTORY_FILE.exists()
    # "a" means append: add to the end instead of overwriting the file.
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if file_is_new:                                # header row, first time only
            writer.writerow(["checked_at", "part", "price", "store", "product"])
        for row in rows:
            best = row["best"]
            if best:
                writer.writerow([checked_at, row["part"]["name"], best["price"],
                                 best["store"], best["title"]])


def main():
    """The starting point: runs all the steps in order."""
    checked_at = datetime.now(BRISBANE).strftime("%Y-%m-%d %H:%M")
    rows = []

    for part in load_parts():
        print(f"Checking {part['name']}...")
        # try/except: if one part fails (site hiccup), report it and keep going
        # instead of crashing the whole program.
        try:
            best = find_cheapest(part)
        except Exception as error:
            print(f"  Problem checking this part: {error}")
            best = None

        if best:
            print(f"  ${best['price']:,.2f} at {best['store']} - {best['title'][:60]}")
        else:
            print("  No matching result found")

        rows.append({"part": part, "best": best})
        time.sleep(3)    # be polite: wait 3 seconds so we don't hammer the site

    update_readme(build_table(rows, checked_at))
    save_history(rows, checked_at)
    print("Done! README.md and price_history.csv updated.")


# This line means "only run main() when this file is run directly",
# not when another Python file imports it. It's a common Python habit.
if __name__ == "__main__":
    main()
