"""
history.py - keeps a price HISTORY and draws a price graph for every part.

Two jobs:
  1. update_deal_history() saves real, dated OzBargain deals into
     deal_history.csv (so we remember them even after OzBargain forgets).
  2. draw_charts() reads price_history.csv (our own checks) and
     deal_history.csv and draws one SVG graph per part into charts/.

GOLDEN RULE: every dot on a graph is a REAL price with a REAL date.
We never guess, estimate or "fill in" the gaps - if there are only two real
prices, the graph shows only two dots.

An SVG is just a text file full of drawing instructions (lines, circles,
text), so we can write one with plain Python - no graph library needed.

Run it on its own to (re)build the history and charts:
    python history.py
"""

import csv                          # reads/writes CSV (spreadsheet-style) files
import re                           # "regular expressions" - pattern matching in text
from datetime import datetime, timedelta, timezone
from html import escape             # makes text safe to put inside SVG/HTML
from pathlib import Path            # a tidy way to work with file paths

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent                    # the folder this script lives in
TRACKER_FILE = HERE / "price_history.csv"       # our own price checks
DEAL_FILE = HERE / "deal_history.csv"           # OzBargain deals we've saved
CHARTS_DIR = HERE / "charts"                    # where the SVG graphs go
BRISBANE = timezone(timedelta(hours=10))        # Queensland: UTC+10, no daylight saving

DEAL_COLUMNS = ["posted_date", "part", "price", "store", "title", "link", "expired", "votes"]
CHART_DAYS = 30                                 # how many days a graph shows

# Colours (dark enough to read on a white background).
COLOUR_TEXT = "#1f2328"
COLOUR_GRID = "#d0d7de"
COLOUR_TRACKER = "#0969da"                      # blue  = our own checks
COLOUR_DEAL = "#c2410c"                         # orange = OzBargain deals
COLOUR_TARGET = "#cf222e"                       # red   = target price


# ---------------------------------------------------------------------------
# SMALL HELPERS
# ---------------------------------------------------------------------------
def slugify(name):
    """Turn a part name into a file-friendly name: "RX 9070 XT" -> "rx-9070-xt"."""
    # Replace every run of characters that aren't letters/numbers with one "-".
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def money(amount):
    """1200.0 -> "$1,200"   and   226.7 -> "$226.70"."""
    return f"${amount:,.0f}" if amount == int(amount) else f"${amount:,.2f}"


def read_csv(path):
    """Read a CSV file into a list of dictionaries (empty list if the file is missing)."""
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# 1) deal_history.csv - remembering OzBargain deals
# ---------------------------------------------------------------------------
def update_deal_history(parts, skip_everywhere, deals, is_good_match, days=45):
    """
    Add new OzBargain deals to deal_history.csv.

    parts, skip_everywhere - from parts.json
    deals                  - a list of deal dictionaries (from sources.ozbargain_history)
    is_good_match          - price_watch's function that decides if a deal is a given part
    days                   - ignore deals older than this many days

    Safe to run every time: a deal that is already saved (same part + same
    link) is NOT added again. For deals we already have we only refresh the
    "expired" and "votes" columns, since those change over time.
    Returns how many new rows were added.
    """
    oldest = (datetime.now(BRISBANE) - timedelta(days=days)).strftime("%Y-%m-%d")

    # Load what we already saved, keyed by (part, link) so we can spot repeats.
    saved = {(row["part"], row["link"]): row for row in read_csv(DEAL_FILE)}
    added = 0

    for deal in deals:
        # A deal with no $ price in its title can't be put on a graph.
        if deal["price"] is None or deal["posted_date"] < oldest:
            continue
        for part in parts:
            if not is_good_match(deal, part, skip_everywhere):
                continue
            key = (part["name"], deal["link"])
            expired = "yes" if deal["expired"] else "no"
            if key in saved:
                # Already saved: just update the things that change over time.
                saved[key]["expired"] = expired
                saved[key]["votes"] = str(deal["votes"])
            else:
                saved[key] = {
                    "posted_date": deal["posted_date"], "part": part["name"],
                    "price": deal["price"], "store": deal["store"],
                    "title": deal["title"], "link": deal["link"],
                    "expired": expired, "votes": deal["votes"],
                }
                added += 1

    # Write the whole file again, oldest deal first (the file is small).
    rows = sorted(saved.values(), key=lambda r: (r["posted_date"], r["part"], r["link"]))
    with open(DEAL_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DEAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return added


def recent_deals(part_name, days=CHART_DAYS):
    """Saved OzBargain deals for one part from the last `days` days, newest first."""
    oldest = (datetime.now(BRISBANE) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = [r for r in read_csv(DEAL_FILE)
            if r["part"] == part_name and r["posted_date"] >= oldest]
    return sorted(rows, key=lambda r: r["posted_date"], reverse=True)


# ---------------------------------------------------------------------------
# 2) charts - one SVG graph per part
# ---------------------------------------------------------------------------
def nice_ticks(low, high, wanted=5):
    """
    Pick tidy gridline values between low and high, e.g. 1000, 1100, 1200...
    Returns a list of numbers. The step is 1, 2, 2.5 or 5 times a power of 10.
    """
    span = max(high - low, 1)
    rough = span / wanted                           # the step if we wanted exactly `wanted` lines
    size = 10 ** (len(str(int(rough))) - 1) if rough >= 1 else 1
    # Choose the smallest tidy step that is at least as big as `rough`.
    step = next((m * size for m in (1, 2, 2.5, 5, 10) if m * size >= rough), 10 * size)
    first = int(low // step) * step                 # round the start down to a tidy number
    ticks = []
    value = first
    while value <= high + step:
        ticks.append(value)
        value += step
        if len(ticks) > 12:                         # safety stop - never loop forever
            break
    return ticks


def read_points(part_name, start, end):
    """
    Gather the real data points for one part between two datetimes.
    Returns (tracker_points, deal_points); each point is (datetime, price, label).
    """
    tracker = []
    for row in read_csv(TRACKER_FILE):
        if row["part"] != part_name:
            continue
        when = datetime.strptime(row["checked_at"], "%Y-%m-%d %H:%M").replace(tzinfo=BRISBANE)
        if start <= when <= end:
            tracker.append((when, float(row["price"]),
                            f"Our check {row['checked_at']}: {money(float(row['price']))} at {row['store']}"))

    deals = []
    for row in read_csv(DEAL_FILE):
        if row["part"] != part_name:
            continue
        # A deal only has a date, so we draw it in the middle of that day.
        when = datetime.strptime(row["posted_date"], "%Y-%m-%d").replace(hour=12, tzinfo=BRISBANE)
        if start <= when <= end:
            note = " (expired)" if row["expired"] == "yes" else ""
            deals.append((when, float(row["price"]),
                          f"OzBargain {row['posted_date']}: {money(float(row['price']))} - {row['title']}{note}"))
    return sorted(tracker), sorted(deals)


def draw_chart(part, now=None):
    """
    Build the SVG text for one part's graph. `part` is an entry from parts.json.
    Shows the last CHART_DAYS days, ending today.
    """
    now = now or datetime.now(BRISBANE)
    # The graph runs from midnight 29 days ago to midnight tonight = 30 whole days.
    end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start = end - timedelta(days=CHART_DAYS)
    tracker, deals = read_points(part["name"], start, end)
    target = float(part["target_price"])

    # ---- the size of the picture and the plotting area inside it ----
    width, height = 720, 260
    left, right, top, bottom = 66, 24, 62, 36       # empty margins around the plot
    plot_w = width - left - right
    plot_h = height - top - bottom

    # ---- work out the y-axis range from the REAL data plus the target line ----
    prices = [p for _, p, _ in tracker + deals] + [target]
    low, high = min(prices), max(prices)
    pad = max((high - low) * 0.12, high * 0.03)     # breathing room above and below
    ticks = nice_ticks(max(low - pad, 0), high + pad)
    y_min, y_max = ticks[0], ticks[-1]
    if len(ticks) > 1 and ticks[-2] >= high + pad:  # don't keep a pointless extra top line
        ticks.pop()
        y_max = ticks[-1]

    def x_of(when):
        """Convert a datetime to a left-right pixel position."""
        return left + plot_w * (when - start).total_seconds() / (end - start).total_seconds()

    def y_of(price):
        """Convert a price to an up-down pixel position (bigger price = higher up)."""
        return top + plot_h * (1 - (price - y_min) / (y_max - y_min))

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Segoe UI, Helvetica, Arial, sans-serif">',
        # A solid white background so the graph also reads on GitHub's dark theme.
        f'<rect width="{width}" height="{height}" rx="6" fill="#ffffff" stroke="{COLOUR_GRID}"/>',
        f'<text x="{left}" y="26" font-size="16" font-weight="700" fill="{COLOUR_TEXT}">'
        f'{escape(part["name"])} - price history (last {CHART_DAYS} days)</text>',
    ]

    # ---- legend (a small key explaining the symbols) ----
    lx, ly = left, 46
    svg += [
        f'<line x1="{lx}" y1="{ly}" x2="{lx + 22}" y2="{ly}" stroke="{COLOUR_TRACKER}" stroke-width="2"/>',
        f'<circle cx="{lx + 11}" cy="{ly}" r="3.5" fill="{COLOUR_TRACKER}"/>',
        f'<text x="{lx + 28}" y="{ly + 4}" font-size="12" fill="{COLOUR_TEXT}">Our price checks (cheapest found)</text>',
        f'<path d="M{lx + 262} {ly - 5} l5 5 l-5 5 l-5 -5 z" fill="{COLOUR_DEAL}"/>',
        f'<text x="{lx + 273}" y="{ly + 4}" font-size="12" fill="{COLOUR_TEXT}">OzBargain deals</text>',
        f'<line x1="{lx + 385}" y1="{ly}" x2="{lx + 407}" y2="{ly}" stroke="{COLOUR_TARGET}" '
        f'stroke-width="1.5" stroke-dasharray="5 4"/>',
        f'<text x="{lx + 413}" y="{ly + 4}" font-size="12" fill="{COLOUR_TEXT}">Target price</text>',
    ]

    # ---- horizontal gridlines with $ labels on the left ----
    for tick in ticks:
        y = y_of(tick)
        svg.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="{COLOUR_GRID}"/>')
        svg.append(f'<text x="{left - 8}" y="{y + 4:.1f}" font-size="11" text-anchor="end" '
                   f'fill="{COLOUR_TEXT}">{money(tick)}</text>')

    # ---- date labels along the bottom (every 5 days, counting back from today) ----
    for days_back in range(0, CHART_DAYS, 5):
        day_start = end - timedelta(days=days_back + 1)      # midnight at the start of that day
        x = x_of(day_start + timedelta(hours=12))            # label sits in the middle of its day
        svg.append(f'<line x1="{x:.1f}" y1="{top + plot_h}" x2="{x:.1f}" y2="{top + plot_h + 4}" stroke="{COLOUR_TEXT}"/>')
        svg.append(f'<text x="{x:.1f}" y="{top + plot_h + 18}" font-size="11" text-anchor="middle" '
                   f'fill="{COLOUR_TEXT}">{day_start.day} {day_start.strftime("%b")}</text>')
    svg.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" stroke="{COLOUR_TEXT}"/>')
    svg.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="{COLOUR_TEXT}"/>')

    # ---- the dashed target line and its label ----
    ty = y_of(target)
    svg.append(f'<line x1="{left}" y1="{ty:.1f}" x2="{width - right}" y2="{ty:.1f}" stroke="{COLOUR_TARGET}" '
               f'stroke-width="1.5" stroke-dasharray="6 4"/>')
    # The label sits at the left, where recent data (on the right) won't cover it.
    # The white outline (stroke) around it keeps it readable over other lines.
    svg.append(f'<text x="{left + 6}" y="{ty - 5:.1f}" font-size="11" font-weight="700" '
               f'text-anchor="start" fill="{COLOUR_TARGET}" stroke="#ffffff" stroke-width="3" '
               f'paint-order="stroke">Target {money(target)}</text>')

    # ---- our tracker: a solid line joining the dots (needs 2+ points for a line) ----
    if len(tracker) > 1:
        path = " ".join(f"{x_of(w):.1f},{y_of(p):.1f}" for w, p, _ in tracker)
        svg.append(f'<polyline points="{path}" fill="none" stroke="{COLOUR_TRACKER}" stroke-width="2"/>')
    for when, price, label in tracker:
        svg.append(f'<circle cx="{x_of(when):.1f}" cy="{y_of(price):.1f}" r="4" fill="{COLOUR_TRACKER}" '
                   f'stroke="#ffffff" stroke-width="1"><title>{escape(label)}</title></circle>')

    # ---- OzBargain deals: orange diamonds (no joining line - they're separate deals) ----
    for when, price, label in deals:
        x, y = x_of(when), y_of(price)
        svg.append(f'<path d="M{x:.1f} {y - 6:.1f} l6 6 l-6 6 l-6 -6 z" fill="{COLOUR_DEAL}" '
                   f'stroke="#ffffff" stroke-width="1"><title>{escape(label)}</title></path>')

    # ---- a friendly note when there's nothing real to show yet ----
    if not tracker and not deals:
        svg.append(f'<text x="{left + plot_w / 2}" y="{top + plot_h / 2 + 24}" font-size="14" '
                   f'text-anchor="middle" fill="{COLOUR_TEXT}">Not enough data yet</text>')

    svg.append("</svg>")
    return "\n".join(svg)


def draw_charts(parts):
    """Write charts/<slug>.svg for every part. Returns how many were drawn."""
    CHARTS_DIR.mkdir(exist_ok=True)                 # make the folder if it isn't there
    for part in parts:
        (CHARTS_DIR / f"{slugify(part['name'])}.svg").write_text(draw_chart(part), encoding="utf-8")
    return len(parts)


# ---------------------------------------------------------------------------
# Run this file directly to collect OzBargain history and redraw the graphs.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import price_watch                  # imported here (not at the top) to avoid a loop
    import sources

    settings = json.loads((HERE / "parts.json").read_text(encoding="utf-8"))
    print("Reading OzBargain history (this takes a minute)...")
    found = sources.ozbargain_history(settings.get("ozbargain_history_pages", []),
                                      settings.get("ozbargain_feeds", []))
    new = update_deal_history(settings["parts"], settings.get("skip_everywhere", []),
                              found, price_watch.is_good_match)
    print(f"{len(found)} deals read, {new} new rows saved to deal_history.csv")
    print(f"{draw_charts(settings['parts'])} charts drawn in charts/")
