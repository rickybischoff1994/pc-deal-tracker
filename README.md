# PC Deal Tracker 🖥️

A small Python project that checks Australian prices for the parts in my next
gaming PC **every day**, using GitHub Actions. It searches
[StaticICE](https://www.staticice.com.au) (an Aussie price-comparison site),
finds the cheapest matching listing for each part, and updates the table below.

## Today's best prices

<!-- PRICES:START -->
_No results yet - the first daily check hasn't run._
<!-- PRICES:END -->

✅ means the price is at or below my target.

## How it works

1. **`parts.json`** lists each part: what to search, words that must (or must
   not) appear in the product name, and my target price.
2. **`price_watch.py`** downloads the search results, filters out the wrong
   products (water blocks, laptop RAM, prebuilt PCs...), and keeps the cheapest.
3. It rewrites the table above and adds a line to **`price_history.csv`**.
4. **`.github/workflows/price-watch.yml`** tells GitHub to run the script every
   morning and save the changes back to this repo.

## Run it yourself

You only need Python 3 (no extra packages):

```bash
python price_watch.py
```

## Change what it watches

Edit `parts.json` - add a part, change a target price, or add words to
`exclude` if the wrong product keeps showing up.

## What I learned building this

- Downloading web pages with `urllib`
- Pulling data out of HTML with regular expressions
- Reading/writing JSON and CSV files
- Scheduling code with GitHub Actions (cron)

_Prices are for my own tracking only and may be out of date - always check the
store's site before buying._
