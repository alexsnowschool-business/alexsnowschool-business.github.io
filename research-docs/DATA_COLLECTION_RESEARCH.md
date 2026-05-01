# Data Collection Research: Fake vs. Authentic Hermès Handbag Dataset

## 1. Best Counterfeit Sources to Scrape

**DHgate** is the strongest starting point. It uses server-side rendered HTML (no JS rendering required for basic data), has well-documented scraping patterns (open GitHub scrapers exist), and product images are publicly accessible without login. The main challenges are Cloudflare protection and aggressive rate limiting — Playwright (already in this project) handles both. Search terms: `"Hermes Kelly bag"`, `"Hermes Birkin replica"`. Use keyword-based URLs rather than category URLs to get richer per-product metadata.

**AliExpress** has significantly harder bot protection (Akamai Bot Manager, TLS fingerprinting, CAPTCHA slide challenges). Playwright partially mitigates this but you'll hit blocks at volume. Image quality is generally higher than DHgate. Use it as a secondary source.

**eBay** is useful specifically for borderline/ambiguous cases — listings described as "inspired by" or "pre-owned" with unknown provenance. These are valuable for a harder test set. eBay's HTML is stable and well-documented. No login required for browsing.

**Taobao/1688**: Highest volume by far, but requires login and Chinese-language parsing. Worth considering at a later stage if the dataset needs scale.

**Avoid Wish**: Very low image quality, inconsistent product photography — not useful for visual feature learning.

---

## 2. Existing Public Datasets

No large, publicly downloadable fake-vs-real Hermès-specific dataset exists. The closest:

- **Luxury Handbag Dataset** (Springer, 2022): 74,916 images across Chanel, Gucci, LV, Prada — not Hermès-specific and **not publicly released**, but authors share on request. Paper: [Hybrid attention network for counterfeit handbag detection](https://link.springer.com/article/10.1007/s40747-021-00633-1).
- **Two-Stage Logo Detection Dataset** (639 images, Chanel only) — too small, not released publicly. [Paper](https://link.springer.com/article/10.1007/s11760-022-02352-7).
- **Kaggle**: No counterfeit-labeled handbag dataset exists. There are handbag classification datasets (brand-only, no fake/real labels).
- **Carousell dataset** (259,926 images, 785 sellers): Used in [Deep learning-based counterfeit seller detection](https://www.researchgate.net/publication/326561776) — seller-level, not image-level labels.

**Recommendation**: Email the Hybrid Attention Network authors — they have the largest known dataset and academic data-sharing is common. Otherwise, build from scratch.

---

## 3. Data Quality Strategy

**Must-have metadata per image:**
- `source_url`, `platform`, `authenticity_label` (`authentic` / `counterfeit`)
- `product_title`, `price`, `seller_id` (for deduplication — same seller often lists same item repeatedly)
- `image_index` (position in product gallery: 0 = hero shot, 1+ = detail shots)
- `scrape_date` (listing availability changes)

**Image diversity needed for a useful classifier:**
Counterfeit detection works best on fine-grained detail, not overall silhouette. You need:
- Close-up shots of hardware (lock clasp, zipper pulls)
- Stitching detail shots
- Interior lining
- Logo/brand stamp images
- Multiple lighting conditions

DHgate sellers typically upload 5–8 images per listing covering most of these. Collect all images per listing (not just the hero), and record `image_index`.

---

## 4. Dataset Size and Balance

Based on published results (98.8% accuracy achieved on ~4,000 images in the Nike counterfeit paper; the 74k Luxury Handbag dataset is the large-scale reference):

- **Minimum viable**: 2,000 images per class (4,000 total) for fine-tuned ResNet/EfficientNet
- **Recommended**: 5,000–10,000 per class (10k–20k total) for robust generalization
- **Ratio**: 1:1 authentic:counterfeit is strongly preferred. Class imbalance degrades recall on the minority class.

The existing `hermes.com` scraper is capped at `max_products=50` by default. Hermès lists ~200–400 bag SKUs total; with 5 images each, the authentic ceiling is ~1,000–2,000 images. Plan fake collection to match that ceiling, not exceed it.

---

## 5. Legal / ToS Considerations

| Platform | ToS prohibits scraping | Login required | Risk level |
|---|---|---|---|
| DHgate | Yes (standard clause) | No (public pages) | Low |
| AliExpress | Yes | No (public pages) | Low–Medium |
| eBay | Yes | No (public pages) | Low |
| Taobao | Yes | **Yes** | High |

Under current US case law, scraping publicly accessible data (no login required) is generally lawful even if ToS prohibits it — courts have found ToS violations are civil, not criminal, and don't constitute CFAA violations for public data. Academic/research use adds further fair-use argument.

**Stay safe**: rate-limit to ~1 req/2–3s, respect `robots.txt`, don't create fake accounts, don't bypass CAPTCHAs programmatically.

---

## 6. Alternative / Complementary Approaches

- **REACT** (react.org): Industry anti-counterfeiting network, 350 brand members. Data sharing is enforcement-focused and member-only — not a realistic raw image source, but worth contacting for label validation.
- **Brand protection firms** (Red Points, Corsearch, Incopro): Massive counterfeit image databases but proprietary. Some publish APIs for rights holders only.
- **Google Vision API / reverse image search**: Useful post-collection to deduplicate images that appear on both authentic and counterfeit listings (repurposed marketing photos).
- **Synthetic augmentation**: Once you have ~1,000 real counterfeit images, augmentation (color jitter, blur, JPEG compression artifacts) simulates lower-quality photography common in counterfeit listings — particularly useful for hardware/stitching close-ups.
- **Crowdsourced labels via MTurk**: For ambiguous eBay listings, use 3-annotator consensus to label them — adds an "uncertain" class useful for calibration.

---

## Recommended Sequencing

1. Extend `hermes.com` scraper to collect all ~400 SKUs × 5 images ≈ **~2,000 authentic images**
2. Build DHgate scraper (Playwright-based, same pattern as existing code) targeting `"Hermes Birkin"` / `"Hermes Kelly"` searches — collect matching **~2,000 counterfeit images**
3. Supplement with eBay for ambiguous/hard negatives
4. Email Hybrid Attention Network authors for their 74k dataset as an external validation set

---

## References

- [Hybrid attention network for counterfeit luxury handbag detection (Springer, 2022)](https://link.springer.com/article/10.1007/s40747-021-00633-1)
- [Two-stage deep learning framework for counterfeit luxury handbag detection (Springer, 2022)](https://link.springer.com/article/10.1007/s11760-022-02352-7)
- [Enhanced Platform for Counterfeit Goods Detection (arXiv)](https://arxiv.org/pdf/2002.06735)
- [The Fake vs Real Goods Problem: Microscopy and ML (KDD 2017)](https://nyunetworks.github.io/Pubs/sharma-kdd2017-fake.pdf)
- [Is Web Scraping Legal? Laws & Court Cases (2026)](https://dataresearchtools.com/is-web-scraping-legal/)
- [REACT - The Anti-Counterfeiting Network](https://www.react.org/)
