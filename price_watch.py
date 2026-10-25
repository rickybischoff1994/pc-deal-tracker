"""
price_watch.py - finds the cheapest Australian prices for the PC parts we want.

HOW IT WORKS (the big picture):
  1. Read the list of parts from parts.json
  2. For each part, collect listings from several websites (see sources.py):
       StaticICE (~15 stores), Mwave, and OzBargain deals
  3. Throw away listings that don't match (wrong product, accessories...)
  4. Sort what's left from cheapest to dearest and keep the top few
  5. Find a product picture for each one
  6. Save the cheapest price for each part into price_history.csv, remember
     real OzBargain deals in deal_history.csv, and draw a price graph for
     every part into charts/ (see history.py)
  7. Write everything into README.md (the repo's front page)

This program only uses Python's built-in "standard library", so there is
nothing extra to install. Run it yourself with:
    python price_watch.py
"""

# ---------------------------------------------------------------------------
# IMPORTS - ready-made tools. The last line imports OUR OWN file, sources.py.
# ---------------------------------------------------------------------------
import csv                      # reads/writes CSV (spreadsheet-style) files
import json                     # reads/writes JSON files
import re                       # "regular expressions" - pattern matching in text
import time                     # lets us pause between web requests
from datetime import datetime, timezone, timedelta
from pathlib import Path        # a tidy way to work with file paths

import history                  # price history + graphs (our own file)
import sources                  # our file with one function per website

# ---------------------------------------------------------------------------
# SETTINGS - CAPITAL names are a convention for "this never changes".
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent    # the folder this script lives in
PARTS_FILE = HERE / "parts.json"
README_FILE = HERE / "README.md"
HISTORY_FILE = HERE / "price_history.csv"
IMAGE_CACHE_FILE = HERE / "images.json"   # remembers pictures we've found

# The README has two invisible marker comments. We replace everything
# between them, and leave the rest of the README alone.
START_MARKER = "<!-- PRICES:START -->"
END_MARKER = "<!-- PRICES:END -->"

BRISBANE = timezone(timedelta(hours=10))   # Queensland: UTC+10, no daylight saving
PAUSE_SECONDS = 2                          # wait between requests to be polite

# Shown instead of a photo when we couldn't find a picture of that exact product.
CATEGORY_ICONS = {
    "Graphics cards": "🎮",
    "Processors": "🧠",
    "Memory (RAM)": "💾",
    "Storage (SSD)": "🗄️",
}

# Little coloured dots to show stock status in the README.
STOCK_ICONS = {
    "in stock": "🟢 in stock",
    "pre-order": "🟡 pre-order",
    "out of stock": "🔴 out of stock",
    "?": "⚪ check site",
}


# ---------------------------------------------------------------------------
# MATCHING - deciding whether a listing really is the part we want
# ---------------------------------------------------------------------------
def squash(text):
    """
    Lower-case the text and remove spaces, dashes and underscores, so that
    "RX 9070 XT", "RX9070XT" and "rx-9070-xt" all become "rx9070xt".
    That way one rule in parts.json matches however a shop writes the name.
    """
    return re.sub(r"[\s\-_]", "", text.lower())


def is_good_match(listing, part, skip_everywhere):
    """Return True if this listing really is the part we want."""
    title = squash(listing["title"])

    # all(...) is True only if EVERY required word is in the title.
    if not all(squash(word) in title for word in part["must_include"]):
        return False
    # any(...) is True if AT LEAST ONE banned word is in the title.
    # The + joins the part's own exclude list and the global skip list.
    banned = part.get("exclude", []) + skip_everywhere
    if any(squash(word) in title for word in banned):
        return False
    # Too cheap usually means it's an accessory, not the real thing.
    # (OzBargain deals sometimes have no price, so check it exists first.)
    if listing["price"] is not None and listing["price"] < part.get("min_price", 0):
        return False
    return True


def remove_duplicates(listings):
    """
    The same product from the same store can turn up twice (e.g. listed
    twice on StaticICE). Keep only the first of each store + product pair.
    """
    seen = set()               # a "set" is like a list that ignores repeats
    unique = []
    for listing in listings:
        key = (listing["store"], squash(listing["title"]))   # a "tuple" pair
        if key not in seen:
            seen.add(key)
            unique.append(listing)
    return unique


# ---------------------------------------------------------------------------
# COLLECTING - asking each website about one part
# ---------------------------------------------------------------------------
def collect_listings(part):
    """Ask every website about one part and return all listings together."""
    listings = []
    # Each entry: (website name, a function to call). "lambda" makes a tiny
    # nameless function, so we can store "how to search" in a list.
    websites = [
        ("StaticICE", lambda: sources.staticice_search(
            part["search"], part.get("min_price", 0), part.get("pages", 1))),
        ("Mwave", lambda: sources.mwave_search(part["search"])),
    ]
    for website_name, search in websites:
        # try/except: if one website fails (hiccup, blocked), print a note
        # and carry on with the others instead of crashing.
        try:
            found = search()
            listings.extend(found)       # extend = add every item from found
        except Exception as error:
            print(f"  {website_name} failed: {error}")
        time.sleep(PAUSE_SECONDS)
    return listings


def model_codes(title):
    """
    Pull out the model codes in a product name, e.g. "RX9070XT-16G-A" or
    "100-100001084WOF". The same code at two different shops means it's the
    same product, so they can share a picture.
    A code here = a word of 6+ characters that mixes letters AND numbers.
    """
    words = re.findall(r"[A-Za-z0-9\-]{6,}", title)
    return {w.upper() for w in words                       # a "set comprehension"
            if re.search(r"\d", w) and re.search(r"[A-Za-z]", w)
            and not re.fullmatch(r"\d+(GB|TB|MHZ)", w.upper())}   # not "6000MHz"


def get_image(listing, image_cache):
    """Return a listing's picture, fetching it from the shop page only once ever."""
    if listing["image"]:
        return listing["image"]
    link = listing["link"]
    if link not in image_cache:                 # never tried this link before
        image_cache[link] = sources.find_image(link)
        if image_cache[link] is not None:
            time.sleep(1)                       # be polite to the shop
    return image_cache[link]


def add_pictures(rows, image_cache):
    """
    Give each listing we show a picture of THAT product:
      1. Use the picture the website gave us, or fetch one from the shop page.
      2. If that shop doesn't share pictures, look for the same model code at
         a shop that does (Umart, MSY, JB Hi-Fi, Mwave) and use that picture.
    """
    for row in rows:
        for listing in row["top"]:
            listing["image"] = get_image(listing, image_cache)
            if listing["image"]:
                continue                        # got one - next listing
            codes = model_codes(listing["title"])
            for other in row["all"]:            # every matching listing for this part
                # "&" between two sets = the codes they have in common.
                if other is not listing and codes & model_codes(other["title"]):
                    image = get_image(other, image_cache)
                    if image:
                        listing["image"] = image
                        break                   # found one - stop looking
        # The part's picture for the summary table = first one we have.
        # If none of the top listings has one, try every matching listing.
        row["picture"] = next((l["image"] for l in row["top"] if l["image"]), "")
        if not row["picture"]:
            for other in row["all"]:
                row["picture"] = get_image(other, image_cache)
                if row["picture"]:
                    break


# ---------------------------------------------------------------------------
# WRITING THE README
# ---------------------------------------------------------------------------
def picture(url, size=60):
    """HTML for a small picture (GitHub's README allows simple HTML)."""
    return f'<img src="{url}" width="{size}">' if url else ""


def safe(text, length=70):
    """Shorten text and remove | characters, which would break a table."""
    text = text.replace("|", "-")
    return text if len(text) <= length else text[:length - 1] + "…"


def money(amount):
    """1199.0 -> "$1,199"   and   226.7 -> "$226.70"."""
    if amount is None:
        return "?"
    return f"${amount:,.0f}" if amount == int(amount) else f"${amount:,.2f}"


def build_report(rows, checked_at, sources_used):
    """Build the whole price report as Markdown text."""
    lines = [
        f"_Last checked: {checked_at} (Brisbane time) · Sources: {sources_used}_",
        "",
        "### Summary",
        "",
        "| | Part | Best price | Target | Deal? | Store |",
        "|---|---|---:|---:|:---:|---|",
    ]
    # ---- summary table: one line per part ----
    for row in rows:
        part = row["part"]
        best = row["top"][0] if row["top"] else None
        if best is None:
            lines.append(f"| {picture(row['picture'], 40)} | {part['name']} | not found "
                         f"| {money(part['target_price'])} | - | - |")
            continue
        deal = "✅" if best["price"] <= part["target_price"] else "—"
        lines.append(f"| {picture(row['picture'], 40)} | [{part['name']}](#{anchor(part['name'])}) "
                     f"| **{money(best['price'])}** | {money(part['target_price'])} | {deal} "
                     f"| {best['store']} |")

    # ---- a detailed section for each category, then each part ----
    current_category = None
    for row in rows:
        part = row["part"]
        if part["category"] != current_category:     # a new category starts
            current_category = part["category"]
            lines += ["", f"## {current_category}"]

        lines += ["", f"### {part['name']}",
                  f"Target: **{money(part['target_price'])}**", ""]

        # The price graph made by history.py. Only embed it if the file exists,
        # so a failed chart never leaves a broken-image icon in the README.
        slug = history.slugify(part["name"])
        if (HERE / "charts" / f"{slug}.svg").exists():
            lines += [f"![Price history for {part['name']}](charts/{slug}.svg)", ""]

        if not row["top"]:
            lines.append("_Nothing matching found today._")
        else:
            lines += ["| | Price | Store | Product | Stock |",
                      "|---|---:|---|---|---|"]
            # enumerate() counts for us: 1, 2, 3... alongside each listing.
            for number, listing in enumerate(row["top"], start=1):
                tick = " ✅" if listing["price"] <= part["target_price"] else ""
                lines.append(
                    f"| {picture(listing['image']) or CATEGORY_ICONS.get(part['category'], '')} "
                    f"| **{money(listing['price'])}**{tick} "
                    f"| {listing['store']} | {number}. [{safe(listing['title'])}]({listing['link']}) "
                    f"| {STOCK_ICONS.get(listing['stock'], listing['stock'])} |"
                )

        if row["deals"]:
            lines += ["", "**🔥 OzBargain deals (last 30 days):**", ""]
            for deal in row["deals"]:
                lines.append(f"- {deal['posted']} · 👍 {deal['votes']} · "
                             f"[{safe(deal['title'], 120)}]({deal['link']})")

        lines += history_details(part["name"])
    return "\n".join(lines)


def history_details(part_name):
    """
    A collapsible list (<details>) of the OzBargain deals saved for this part
    in the last 30 days, including expired ones. Returns a list of lines,
    or an empty list if there are no deals (so nothing is added).
    """
    try:
        deals = history.recent_deals(part_name)
    except Exception as error:         # never let the history break the report
        print(f"  Could not read deal history: {error}")
        return []
    if not deals:
        return []
    lines = ["", "<details>", f"<summary>OzBargain deal history ({len(deals)})</summary>", ""]
    for deal in deals:
        # "2026-09-18" -> "18 Sep"
        day = datetime.strptime(deal["posted_date"], "%Y-%m-%d").strftime("%d %b")
        expired = " (expired)" if deal["expired"] == "yes" else ""
        lines.append(f"- {day} · {money(float(deal['price']))} · {safe(deal['store'], 40)} · "
                     f"[{safe(deal['title'], 100)}]({deal['link']}){expired}")
    lines += ["", "</details>"]
    return lines


def anchor(heading):
    """GitHub turns a heading into a link target: "RTX 5070 Ti" -> "rtx-5070-ti"."""
    return re.sub(r"[^a-z0-9 \-]", "", heading.lower()).replace(" ", "-")


def update_readme(report):
    """Swap the old report in README.md for the new one."""
    text = README_FILE.read_text(encoding="utf-8")
    start = text.index(START_MARKER) + len(START_MARKER)
    end = text.index(END_MARKER)
    README_FILE.write_text(text[:start] + "\n" + report + "\n" + text[end:], encoding="utf-8")


def save_history(rows, checked_at):
    """Add today's cheapest price for each part to price_history.csv."""
    file_is_new = not HISTORY_FILE.exists()
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:   # "a" = append
        writer = csv.writer(f)
        if file_is_new:
            writer.writerow(["checked_at", "part", "price", "store", "product"])
        for row in rows:
            if row["top"]:
                best = row["top"][0]
                writer.writerow([checked_at, row["part"]["name"], best["price"],
                                 best["store"], best["title"]])


# ---------------------------------------------------------------------------
# MAIN - runs all the steps in order
# ---------------------------------------------------------------------------
def main():
    checked_at = datetime.now(BRISBANE).strftime("%Y-%m-%d %H:%M")
    settings = json.loads(PARTS_FILE.read_text(encoding="utf-8"))
    skip_everywhere = settings.get("skip_everywhere", [])
    how_many = settings.get("show_per_part", 5)

    # Load pictures found on earlier runs (or start with an empty dictionary).
    image_cache = {}
    if IMAGE_CACHE_FILE.exists():
        image_cache = json.loads(IMAGE_CACHE_FILE.read_text(encoding="utf-8"))

    # OzBargain deals are read once, then matched to every part below.
    print("Reading OzBargain deals...")
    all_deals = sources.ozbargain_deals(settings.get("ozbargain_feeds", []))
    print(f"  {len(all_deals)} current deals found")

    rows = []
    for part in settings["parts"]:
        print(f"Checking {part['name']}...")
        listings = collect_listings(part)

        # Keep only real matches, sort cheapest first, drop repeats, keep the top few.
        good = [l for l in listings if is_good_match(l, part, skip_everywhere)]
        good = remove_duplicates(sorted(good, key=lambda l: l["price"]))
        top = good[:how_many]          # a "slice": the first how_many items

        deals = [d for d in all_deals if is_good_match(d, part, skip_everywhere)]

        if top:
            print(f"  {len(good)} matches, cheapest {money(top[0]['price'])} at {top[0]['store']}")
        else:
            print("  No matching listings")
        rows.append({"part": part, "top": top, "all": good, "deals": deals, "picture": ""})

    print("Finding pictures...")
    add_pictures(rows, image_cache)
    IMAGE_CACHE_FILE.write_text(json.dumps(image_cache, indent=1), encoding="utf-8")

    # Save our own prices first, so today's check is on the graphs too.
    save_history(rows, checked_at)

    # Price history + graphs. Each step has its own try/except: if one goes wrong
    # (OzBargain down, a bug...) we print a note, carry on, and still write the report.
    try:
        print("Reading OzBargain deal history...")
        found = sources.ozbargain_history(settings.get("ozbargain_history_pages", []),
                                          settings.get("ozbargain_feeds", []))
        new = history.update_deal_history(settings["parts"], skip_everywhere, found, is_good_match)
        print(f"  {len(found)} deals read, {new} new saved to deal_history.csv")
    except Exception as error:
        print(f"  Deal history failed (the price report still gets written): {error}")
    try:
        print(f"  {history.draw_charts(settings['parts'])} charts drawn in charts/")
    except Exception as error:
        print(f"  Charts failed (the price report still gets written): {error}")

    update_readme(build_report(rows, checked_at, "StaticICE (~15 stores), Mwave, OzBargain"))
    print("Done! README.md, price_history.csv, deal_history.csv and charts/ updated.")


# Only run main() when this file is run directly (not when imported).
if __name__ == "__main__":
    main()
