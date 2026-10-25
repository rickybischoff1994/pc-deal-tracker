# PC Deal Tracker 🖥️

A Python project that checks Australian prices for the parts in my next gaming
PC **every morning**, using GitHub Actions. It looks at:

- **[StaticICE](https://www.staticice.com.au)** - a price-comparison site covering ~15 stores
  (PC Case Gear, Scorptec, Umart, MSY, JB Hi-Fi, Computer & Parts Land, JW Computers,
  CCPU, Computer Alliance, PLE, I-Tech, MegaBuy...)
- **[Mwave](https://www.mwave.com.au)** - checked directly, since it isn't on StaticICE
- **[OzBargain](https://www.ozbargain.com.au)** - community-posted deals from the last 30 days

✅ = at or below my target price · 🟢 in stock · 🟡 pre-order · 🔴 out of stock · ⚪ store doesn't say

## Today's prices

<!-- PRICES:START -->
_First check pending._
<!-- PRICES:END -->

## How it works

1. **`parts.json`** lists each part: what to search, words that must (or must
   not) appear in the product name, and my target price.
2. **`sources.py`** has one function per website. Each one returns listings in
   the same shape (price, title, store, link, stock, picture).
3. **`price_watch.py`** collects listings from every website, filters out the
   wrong products (water blocks, laptops, prebuilt PCs...), sorts them cheapest
   first, finds pictures, and rewrites this page. It also adds the cheapest
   price for each part to **`price_history.csv`**.
4. **`.github/workflows/price-watch.yml`** tells GitHub to run it every morning.

## Run it yourself

You only need Python 3 (no extra packages):

```bash
python price_watch.py
```

## Change what it watches

Edit `parts.json` - add a part, change a target price, or add words to
`exclude` if the wrong product keeps showing up.

## What I learned building this

- Downloading web pages and JSON with `urllib`
- Pulling data out of HTML and RSS feeds with regular expressions
- Splitting a program into modules (`sources.py`)
- Reading/writing JSON and CSV files
- Scheduling code with GitHub Actions (cron)

_Prices are for my own tracking only and may be out of date - always check the
store's site before buying._
