# PC Deal Tracker 🖥️

A small Python project that checks Australian prices for the parts in my next
gaming PC **every day**, using GitHub Actions. It searches
[StaticICE](https://www.staticice.com.au) (an Aussie price-comparison site),
finds the cheapest matching listing for each part, and updates the table below.

## Today's best prices

<!-- PRICES:START -->
_Last checked: 2026-10-25 20:00 (Brisbane time)_

| Part | Best price | Target | Deal? | Store | Product |
|---|---:|---:|:---:|---|---|
| GPU - Radeon RX 9070 XT 16GB | **$1,199.00** | $1,099 | — | PC Case Gear | [PowerColor Radeon RX 9070 XT Reaper 16GB [RX9070XT-16G-A]](https://www.pccasegear.com/products/68061/powercolor-radeon-rx-9070-xt-reaper-16gb) |
| CPU - Ryzen 7 9800X3D | **$595.00** | $549 | — | CCPU Computers | [AMD RYZEN 7 9800X3D CPU 100-100001084WOF](https://www.ccpu.com.au/product/amd-ryzen-7-9800x3d-cpu-100-100001084wof/) |
| RAM - DDR5 32GB (2x16GB) 6000MHz CL30 | **$199.00** | $299 | ✅ YES | Computer & Parts Land | [G.Skill F5-6000J3040F16GX2-RS5W Ripjaws S5 32GB (2x 16GB) DDR5 6000MHz CL30...](https://cplonline.com.au/g-skill-f5-6000j3040f16gx2-rs5w-ripjaws-s5-32gb-2x-16gb-ddr5-6000mhz-cl30-desktop-memory-white.html) |
| RAM - DDR5 64GB (2x32GB) 6000MHz CL30 | **$959.00** | $699 | — | Computer & Parts Land | [G.Skill F5-6000J3040G32GX2-RS5K Ripjaws S5 64GB (2x 32GB) DDR5 6000MHz CL30...](https://cplonline.com.au/g-skill-f5-6000j3040g32gx2-rs5k-ripjaws-s5-64gb-2x-32gb-ddr5-6000mhz-cl30-desktop-memory-black.html) |
| SSD - 2TB NVMe Gen4 | **$226.70** | $219 | — | Computer & Parts Land | [MSI SPATIUM M470 PRO 2TB PCIe 4.0 NVMe M.2 2280 SSD](https://cplonline.com.au/msi-spatium-m470-pro-2tb-pcie-4-0-nvme-m-2-2280-ssd.html) |
| SSD - 4TB NVMe Gen4 | **$449.00** | $429 | — | Computer & Parts Land | [HP 8U2N7AA# FX700 4TB PCIe Gen 4x4 NVMe M.2 2280 SSD](https://cplonline.com.au/hp-8u2n7aa-fx700-4tb-pcie-gen-4x4-nvme-m-2-2280-ssd.html) |
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
