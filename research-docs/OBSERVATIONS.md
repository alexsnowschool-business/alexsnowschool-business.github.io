# Dataset Observations — Wealth, Culture & Distribution Analysis

Analytical framework for interpreting the Hermès authenticity dataset through the lens of
wealth-class behaviour and market structure. Numbers are derived from live data on the
`/analysis` page; this document captures the *why* behind each metric.

---

## 1. Status Symbol Concentration

**What we measure**: What percentage of each class's listings target each bag type.

**Observation**: Counterfeit production does not distribute evenly across the Hermès catalogue.
It concentrates on the most *culturally legible* pieces — Birkin and Kelly dominate because
they are recognisable to people who cannot afford them. A buyer spending €150 on a fake
Birkin is not confused; they are purchasing the *signal*, not the object. This means the
concentration gap between authentic and counterfeit listings by type is a direct measure of
aspirational pressure. Types with a large fake-pct / auth-pct ratio are cultural desire objects;
types with roughly equal ratios are more utilitarian purchases.

**Expected pattern**: Birkin + Kelly likely account for 60–80% of counterfeit listings while
making up 40–50% of authentic listings. The remainder of the Hermès catalogue (Constance,
Evelyne, Picotin, Lindy) is more evenly spread in the authentic market but barely counterfeited
because it carries less immediate status recognition.

---

## 2. Aspirational Distance (Compression Ratio)

**What we measure**: `authentic_avg / counterfeit_avg` by bag type — how many times more
expensive the real item is than its fake equivalent.

**Observation**: The compression ratio is not just a price gap; it is a proxy for
*inaccessibility to aspiring buyers*. A ratio of 200× (Birkin) means the authentic item is
so far out of reach that the counterfeit market is structurally guaranteed — no amount of
saving or stretching closes the gap. A ratio of 8× (e.g. Evelyne) means many aspirational
buyers could actually afford the real thing eventually; demand for fakes is weaker.

**Cultural implication**: Old-money culture deliberately uses extreme price inaccessibility
(waiting lists, in-store-only availability, no online sales) as a filtering mechanism. The
Birkin's 200× ratio is partly by design — Hermès keeps supply constrained to maintain the
signal quality of ownership. Counterfeit demand is the shadow of that constraint.

---

## 3. Price Distribution Shape — The Bimodal Wealth Signal

**What we measure**: Fine-grained (€2k bins) histogram of authentic resale prices.

**Observation**: Authentic Hermès resale should reveal a bimodal distribution:
- **First hump (€2k–€6k)**: Entry-level and functional pieces accessible to upper-middle
  class buyers (Evelyne, Picotin, smaller Kellys). This tier is reachable with a stretch purchase.
- **Second hump (€15k–€30k)**: Trophy assets — large Birkins and Kellys, exotic leathers,
  limited editions. This tier is accessible only to genuinely wealthy buyers.
- **Valley (€6k–€12k)**: Relatively sparse — this is the awkward "expensive but not iconic"
  zone that neither aspirational nor trophy buyers target as strongly.

The counterfeit distribution will be unimodal and left-skewed, compressed below €500. The two
distributions barely overlap, which is why price alone is a strong classifier feature.

---

## 4. Psychological Price Points in Counterfeit Listings

**What we measure**: €25-bin histogram of counterfeit prices from €0–€500.

**Observation**: Sellers on peer-to-peer platforms like Vinted exhibit anchored pricing
behaviour. Two distinct seller types emerge:

- **Informed fakers**: Price at psychological anchors — €99, €149, €199, €249, €299.
  These round numbers signal "this is a good deal on something branded" without triggering
  suspicion. Spikes at these points are intentional framing.
- **Naive sellers**: Price at what they believe the item is worth — often €50–€150 for
  a bag they know is not authentic but don't think is worthless. These create a more
  uniform baseline between the anchored spikes.
- **High-end fakes (€300–€500)**: Sellers attempting to pass off counterfeits as genuine
  secondary-market items, pricing to mimic entry-level Vestiaire listings.

The shape of this distribution (spike pattern vs. smooth baseline) tells us how sophisticated
the average counterfeit seller on this platform is.

---

## 5. Image Quality as a Class Proxy

**What we measure**: Average image file size (KB) by authenticity label as a proxy for
photo quality and listing effort.

**Observation**: Listing photo quality encodes the seller's class position and intent.
- **Vestiaire (authentic)**: Semi-professional photos on neutral or lifestyle backgrounds.
  Sellers know buyers are evaluating authentication markers; every photo is deliberate.
  File sizes are larger — high-res JPEGs or WebP.
- **Vinted (counterfeit)**: Phone photos in domestic settings — living rooms, beds, bathroom
  mirrors. Lower resolution, smaller file sizes, cluttered backgrounds.

**Classifier hygiene note**: If authentic images are systematically larger/higher-resolution
than counterfeit images, a model trained on this data will partially learn "high-res photo =
authentic" rather than bag features. This is a confounder to quantify before training. A
large gap (e.g. 3× file size ratio) warrants either resolution normalisation or ensuring the
model's augmentation pipeline randomly degrades image quality.

---

## 6. Market Spread — Platform as Wealth Tier Signal

**What we measure**: Median price by source platform (hermes.com, vestiairecollective.com,
vinted.de).

**Observation**: Each platform represents a distinct wealth tier and purchase intent:
- **hermes.com**: Retail price — aspirational reference point. Buyers here are purchasing
  access, not just the object. Many listings require in-store purchase or waiting list.
- **Vestiaire Collective**: Authenticated resale — upper-middle class and wealthy buyers
  seeking authentic pieces at secondary-market prices. Trust is the product; Vestiaire
  charges ~15% for authentication and curation.
- **Vinted.de**: Peer-to-peer, no authentication, price-sensitive buyers. The Hermès
  listings here range from outright fakes to potentially mislabelled genuine pieces
  sold by uninformed owners (inherited bags, charity shop finds).

The platform spread (Vestiaire median >> Vinted median) quantifies the "trust premium" —
how much buyers pay for authenticated sourcing. This is the core value proposition of any
authentication service entering this market.

---

## Implications for Classifier Training

1. **Don't train on price** — price is a perfect predictor but a useless one for real-world
   authentication (a fake can be priced at €5,000 on a deceptive listing).
2. **Watch image quality confounder** (Observation 5) — normalise resolution before training.
3. **Class imbalance follows cultural logic** — the Birkin/Kelly concentration means the
   model will have more training examples for culturally prominent types and fewer for rarer
   styles (Constance, Herbag). Stratified sampling by bag type before the train/val split.
4. **Aspirational distance predicts feature complexity** — bags with very high compression
   ratios (Birkin 200×) are harder to fake convincingly at the material level, which means
   the model should learn real discriminative features. Bags with low ratios may be
   harder for the model because authentic and fake versions are visually closer.
