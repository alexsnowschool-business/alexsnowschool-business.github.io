# Study Plan — AI-Powered Luxury Authentication & Resale

A structured learning path covering everything needed to build, validate, and operate an AI-driven Hermès authentication and resale business.

---

## Overview

| Track | Focus | Time estimate |
|---|---|---|
| **Track 1** | Domain knowledge — Hermès & luxury resale | 2–3 weeks |
| **Track 2** | Data collection & dataset engineering | 1–2 weeks |
| **Track 3** | Business & market operations | 1–2 weeks |
| **Track 4** | Legal & compliance (EU/DE) | 3–5 days |

Work tracks in parallel — domain knowledge and business tracks can run alongside the technical ones.

---

## Track 1 — Domain Knowledge: Hermès & Luxury Authentication

### 1.1 Hermès product knowledge
- **Bag families**: Kelly, Birkin, Constance, Lindy, Picotin — shapes, sizes, hardware
- **Leather types**: Togo, Clemence, Epsom, Box Calf, Ostrich, Crocodile — texture, grain, patina
- **Hardware finishes**: Gold (GHW), Palladium (PHW), Brushed Gold (BGHW), Ruthenium — weight, colour
- **Stitching**: Saddle stitch count per inch, thread colour by leather, stitch angle
- **Date stamps**: Craftsman blind stamp system (letter + symbol enclosing shape = year + atelier)
- **Dust bags, boxes, clochettes**: Authentic packaging characteristics
- **Serial number / craftsman stamp locations** by model

**Resources**
- Baghunter authentication guides
- Yoogi's Closet authentication blog
- PurseForum (tPF) Hermès subforum — years of community authentication threads
- YouTube: "authenticate Hermès Kelly" — hands-on visual walkthroughs

---

### 1.2 Common counterfeit tells
- Hardware weight and shine (counterfeits use hollow, lightweight hardware)
- Stitching irregularities — uneven spacing, wrong thread colour, fraying
- Leather texture — too uniform (machine-pressed), wrong grain pattern
- Logo font — "Hermès Paris" text spacing, font weight, depth of embossing
- Lining fabric — wrong colour, wrong texture, visible glue at edges
- Lock and key — authentic Hermès locks have a specific weight and engraving depth
- Smell — genuine leather vs synthetic odour

---

### 1.3 Grading and condition
- Vestiaire condition grades: Never worn / Very good / Good / Fair
- How condition affects resale price (10–50% difference between grades)
- Patina on box calf: expected vs damage
- Cleaning and restoration impact on resale value

---

## Track 2 — Data Collection & Dataset Engineering

### 2.1 What makes a good training dataset
- **Minimum viable**: 500 images/class for transfer learning fine-tuning
- **Good**: 2,000 images/class (current target — correct)
- **Ideal**: 5,000+ images/class with diversity across bag models, angles, lighting
- Balance across: bag models, colours, leather types, lighting conditions, image quality

### 2.2 Dataset labelling strategy
- Source-level labelling (current approach): Vestiaire/hermes.com → authentic, Vinted under €500 → counterfeit
- Risks: some Vinted items are genuinely authentic and mislabelled; some Vestiaire items may have slipped through
- Validation: randomly sample 50 per class and manually verify before training

### 2.3 Image quality requirements for training
- Minimum resolution: 224×224 (ResNet input), but collect at higher resolution and resize at training time
- Avoid: heavily watermarked images, collage thumbnails, screenshots with text overlays
- Ideal: clean product shots, multiple angles per item

### 2.4 Dataset versioning and management
- Track dataset versions alongside model versions
- Tools to explore: DVC (Data Version Control), or simple JSON manifest files
- Never delete raw data — keep original downloads even if not used in current training run

---

## Track 3 — Business & Market Operations

### 3.1 Vestiaire Collective seller mechanics
- **Commission**: 12–15% for individual sellers; negotiable for pro sellers above volume threshold
- **Authentication fee**: included in commission for items over €150; Vestiaire physically inspects
- **Payout timeline**: 72 hours after buyer confirms receipt
- **Listing best practices**: multiple angles, detail shots of hardware/stitching/stamps, honest condition grading

### 3.2 Sourcing and deal evaluation
- Target price rules of thumb:
  - Buy below 15% of Vestiaire ask → healthy margin after fees
  - Kelly 25: buy under €800, list at €4,000–6,000 (if authentic)
  - Birkin 30: buy under €1,200, list at €6,000–10,000 (if authentic)
- Speed matters: set up alerts (Vinted app notifications, scraper running daily at 7am)
- Red flags that a listing is already spotted: multiple watchers, price already raised

### 3.3 Inventory and capital management
- Capital at risk = purchase price of items in inventory
- Target turnover: Vestiaire median days-to-sell for Hermès ≈ 14–30 days
- Start small: 1–2 items, validate the full cycle before scaling
- Insurance: check whether home contents insurance covers luxury goods in transit

### 3.4 Alternative business models
- **Authentication-as-a-service**: charge Vinted sellers €20–50 to pre-authenticate before listing at higher price. Low capital requirement, recurring revenue
- **Consignment brokerage**: take items from Vinted sellers on consignment, list on Vestiaire, take 20–30% of sale. No capital required
- **Price intelligence newsletter**: daily Vinted Hermès market report, sold as subscription to resellers. Pure data product, no inventory risk

---

## Track 4 — Legal & Compliance (EU / Germany)

### 4.1 Second-hand goods trading in Germany
- **Gewerbeanmeldung** (business registration): required if reselling regularly for profit — €20–50 to register
- **Kleinunternehmerregelung**: if under €22,000/year revenue, simplified VAT rules apply
- Above that threshold: must charge and remit VAT (19% in DE); factor into margins
- **Umsatzsteuerliche Differenzbesteuerung** (margin scheme): for second-hand goods, VAT is only charged on the profit margin, not the full sale price — significantly better than standard VAT

### 4.2 Consumer protection obligations
- EU Consumer Rights Directive: if selling to consumers (not B2B), 14-day return right applies
- Must provide accurate item description — if you sell something as authentic and it isn't, liability is yours
- Keep purchase receipts and transaction records for 10 years (German tax law)

### 4.3 Stolen goods risk
- Buying stolen luxury goods unknowingly carries legal risk in DE (§ 259 StGB — Hehlerei)
- Mitigation: keep purchase records, buy from traceable accounts, avoid cash deals
- Entrupy and similar services also check against stolen goods databases

### 4.4 Anti-counterfeiting law
- Do NOT knowingly buy or resell counterfeits — even for research/dataset purposes, cross-border movement of fakes can trigger customs seizure
- The dataset you're building (labelled "counterfeit") is for AI training, not physical resale — this is fine

---

## Suggested learning order

```
Week 1–2   Track 1 (1.1, 1.2) + Track 3 (3.1, 3.2)  — domain + market basics
Week 2–3   Track 2 (all) + collect dataset to 500/class
Week 3–4   Train first baseline model, validate label quality
Week 4–5   Track 4 (all)                              — legal & compliance
Week 5+    Track 3 (3.3, 3.4)                         — decide on business model, run pilot
```

---

## Milestone checklist

- [ ] Can identify the 5 most common counterfeit tells on a Hermès Kelly by eye
- [ ] Understand blind stamp date code system
- [ ] Dataset at 1,000+ images per class
- [ ] Baseline classifier trained, AUC > 0.85
- [ ] Grad-CAM visualisations confirm model looks at correct features
- [ ] First Vinted → Vestiaire cycle completed (1 item, end to end)
- [ ] Business registration decision made (Gewerbe or not)
