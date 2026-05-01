# Competitor Analysis: Luxury Resale Data, Scraping & Authentication Platforms

*Research date: April 2026. All pricing in USD unless otherwise noted.*

---

## Quick-Reference Competitor Matrix

| Platform | Category | Pricing (entry) | Target Customer | Hermès Coverage | Vinted Coverage | Auth? | Data API? |
|---|---|---|---|---|---|---|---|
| **Oly Platform** | Crosslisting + price intel | ~€39/mo | Boutique reseller | Yes (pricing data) | Yes | No | No |
| **Apify** | Scraper marketplace | Free / $39/mo | Developer, SMB | Via actors | 10+ actors | No | Yes |
| **BrightData** | Enterprise data platform | $499/mo or PAYG | Enterprise | Via Vinted scraper | Yes (dedicated) | No | Yes |
| **Lobstr.io** | No-code e-commerce scraper | Free / €50/mo | SMB, non-technical | Via Vinted | Vinted scraper | No | Yes |
| **Entrupy** | AI authentication hardware | $499 device + sub | Boutique, pawnbroker | Yes ($139/item) | No | Yes | No |
| **LegitCheck / LegitApp** | Photo authentication app | From $10/check | Consumer, reseller | Yes | No | Yes | No |
| **Real Authentication** | Human expert auth | ~$60–$90/check | Consumer, reseller | Yes | No | Yes | No |
| **Vestiaire Collective** | Marketplace (internal tools) | Commission (15%) | Seller/buyer | Yes | No | Partial | No |
| **The RealReal** | Consignment marketplace | Commission-based | Consignor/buyer | Yes | No | Yes | No |
| **Rebag / Clair AI** | Resale + pricing index | Free (public Clair) | Consumer, dealer | Yes (leading) | No | Yes | No |
| **Fashionphile Certified** | In-person auth service | $75–$125/item | Consumer, dealer | Yes ($125) | No | Yes | No |
| **Baghunter** | Niche resale (Hermès/Chanel) | Marketplace | Collector | Yes | No | In-house | No |
| **Bagaholic** | Auth + price list (LV focus) | From $20/check | Consumer | Limited | No | Yes | No |
| **PLOTT DATA** | Multi-marketplace analytics | Custom enterprise | Brand, investor | Indirectly | Yes | No | Yes |

---

## Primary Competitors — Deep Dives

### 1. Oly Platform

**What they do:** SaaS crosslisting and inventory management tool for professional luxury resellers. Syncs listings across Vestiaire Collective, Vinted, eBay, Grailed, Joli Closet with a single upload. Auto-generates product descriptions, handles marketplace-specific data mapping, and provides pricing recommendations from comparable sold listings.

**Pricing:** ~€39/month for sellers adding fewer than 20 new items/month. Scales with listing volume and number of connected marketplaces. One-time setup fee based on catalog size.

**Target customer:** Independent professional resellers and small consignment boutiques in Europe managing 20–500 SKUs across multiple platforms.

**Data coverage:** Vestiaire, Vinted, eBay, Grailed, and several European niche platforms. Pricing intelligence derived from active listings — not confirmed sale prices.

**Key features:**
- One-click crosslisting across 6+ European luxury resale platforms
- AI-generated descriptions and automatic category mapping
- Pricing suggestions based on comparable current listings
- Human customer support (stated differentiator — no chatbot)

**Weaknesses / gaps:**
- No authentication capability
- Pricing based on asking prices, not confirmed sales — significant accuracy gap
- No public API for integrators
- No US platform coverage
- No structured data export or intelligence product

---

### 2. Apify

**What they do:** Cloud scraping and automation marketplace with 26,000+ community "Actors" (pre-built scrapers). At least 10 distinct Vinted scrapers available, ranging from simple listing extractors to price comparison tools.

**Pricing:**
- Free: $5/month in platform credits
- Starter: $39/month
- Scale: $199/month
- Business: $999/month
- Individual Vinted Actors: $0.005–$1.00 per 1,000 results on top of subscription

**Target customer:** Developers, data engineers, SMBs needing flexible scraping without managing infrastructure.

**Key features:** 26,000+ Actors; cloud scheduling + webhooks; proxy network integration; no-code UI.

**Weaknesses / gaps:**
- Generic infrastructure — no luxury or fashion domain expertise
- Community Actors vary in quality and bot-detection resilience; can break silently
- No authentication or price normalisation for luxury goods
- Raw data requires significant downstream structuring for fashion use cases (condition, hardware, colorway)

---

### 3. BrightData (formerly Luminati)

**What they do:** Enterprise data platform offering proxy networks, Web Scraper APIs, bot bypass (Web Unlocker), pre-built datasets, and AI-driven price trackers. Explicit Vinted scraper and Vinted price tracker products. Pre-collected Vinted datasets available for purchase.

**Pricing:**
- Web Scraper API: from $4/CPM; Growth $499/month; Business $999/month
- Vinted dataset/price tracker: from $0.001 per record
- Enterprise: custom

**Key features:** Massive residential proxy network; 30+ Vinted attributes extracted; pre-collected datasets; enterprise SLAs; AI-driven price insights.

**Weaknesses / gaps:**
- Minimum meaningful spend ~$499+/month — not accessible for boutique operators
- No luxury domain expertise — a Hermès Birkin treated identically to a generic handbag
- No authentication capability
- No Hermès-specific indexing (colorway, hardware, year, condition grade)
- Enterprise-only contracts; overly complex for SMBs

---

### 4. Lobstr.io

**What they do:** No-code scraping platform with 30+ ready-made extractors. Dedicated Vinted Products Scraper. Explicitly positioned for non-technical users. Discord integration for Vinted listing alerts.

**Pricing:**
- Free forever: up to 67,500 results/month
- Premium: €50/month — 810,000 results/month
- Business: €250/month — 6,480,000 results/month

**Key features:** 30+ sources; Vinted scraper extracts 30+ attributes; Google Sheets export; Discord alerts for new listings.

**Weaknesses / gaps:**
- No luxury vertical specialisation
- Raw data only — no price normalisation for luxury condition grading, hardware, colorway
- No authentication
- No historical sold-price data (active listings only)
- Only the 30+ supported scrapers — no custom sources

---

## Authentication Competitors

### 5. Entrupy

**What they do:** Physical AI authentication device (microscope-based) capturing micro-surface images of leather and materials, compared against millions of verified samples. Results in under 5 minutes. Official authentication partner for TikTok Shop and Whatnot.

**Pricing:**
- Device: $499 one-time (first 50 sellers get it free)
- Per-item fees vary by tier
- **Hermès: $139 per authentication**
- Pay-as-you-go from $10

**Accuracy:** 99.86% (self-reported, with financial guarantee on errors).

**Key features:** 22 luxury brands; in-hand result in under 5 minutes; financial guarantee; microscopic analysis harder to spoof than photo-based systems.

**Weaknesses / gaps:**
- Requires **physical possession of the item** — cannot authenticate from listing photos
- $139/Hermès item makes volume authentication expensive for small operators
- No pricing intelligence
- No Vinted or marketplace integration

---

### 6. LegitCheck / LegitApp

*Two separate services with similar names.*

**What they do:** Photo-based remote authentication — users submit photos and receive verdicts from human experts supported by AI. LegitApp: 3M+ authentications. LegitCheck By Ch: 200K+ since 2017.

**Pricing:**
- LegitApp: from $10; faster turnarounds cost more (10 min to 12 hrs)
- LegitCheck: $9.99/check; Club membership with 3 free checks/month

**Weaknesses / gaps:**
- Photo quality-dependent — bad Vinted photos produce unreliable results
- Human labour bottleneck — not scalable for bulk screening
- No bulk API or reseller integration
- No pricing intelligence

---

### 7. Real Authentication

**What they do:** Human expert service with 2M+ completions. Photo upload with AI pre-screening, then two expert authenticators. Covers 100+ luxury brands. Certificate + optional written statement.

**Pricing:** ~$60 for 12-hour; ~$90 for Chanel; express 1-hour available.

**Weaknesses / gaps:** Same as LegitApp — human bottleneck, no API, no pricing data, no platform integration.

---

## Platform / Marketplace Data Competitors

### 8. Vestiaire Collective (internal tools)

Launched a Price Estimate Tool in 2022 trained on their own transaction history — available only to sellers listing on the platform. No public API, no external data licensing. Their pricing data stays locked within the Vestiaire ecosystem.

### 9. The RealReal

Operates AI tools internally (Shield, Vision, Athena AI) for authentication and pricing. All data is proprietary. Published annual resale trend reports but no data product or API for external use.

### 10. Rebag / Clair AI

**What they do:** US luxury resale platform with the most publicly accessible pricing intelligence. The **Clair Report** (6th edition, 2025) tracks confirmed-transaction resale value retention by brand, model, and category — the only public benchmark using real sales data. Clair AI identifies a bag from a photo and returns a Rebag offer price.

**Pricing:** Clair AI and Clair Report are **free and publicly accessible**.

**Key features:** 15,000+ bag references; 91% photo-identification accuracy; 50 brands; Hermès at 138% value retention in 2025 (Kelly Mini II at 282%).

**Weaknesses / gaps:**
- US-centric — no European or Vinted market data
- Clair AI returns Rebag's own offer price, not broader market price
- No API for external developers
- No authentication certificate

### 11. Fashionphile Certified

In-person authentication launched 2025. $75 most items, **$125 for Hermès**. In-person only at flagship locations. Lifetime guarantee certificate. No data product, US-only.

### 12. PLOTT DATA

**What they do:** Multi-marketplace analytics across 60+ platforms including Vinted. REST API, CSV exports, scheduled data delivery (daily/weekly/monthly). Tracks price, stock, seller data, city-level pricing.

**Pricing:** Custom enterprise only.

**Weaknesses / gaps:** No luxury specialisation; no authentication; Vinted coverage is generic (no condition grading, hardware, colorway normalisation for luxury). Enterprise-only — inaccessible for boutique resellers.

---

## Gap Analysis — Market Opportunity

### Three things no one does well

**1. Confirmed sold-price data for Hermès on European platforms, accessible to boutique operators.**
Rebag's Clair is the only confirmed-transaction benchmark — but it's US-centric, proprietary to Rebag trades, and not API-accessible. All European scrapers (Apify, BrightData, Lobstr) deliver asking-price data only. A product tracking confirmed completed sales normalised by model, leather, hardware, condition, and date **does not exist** as a standalone data service at any price point.

**2. Photo-based Hermès authentication at scale without physical possession.**
Entrupy requires the physical item. Photo services (LegitCheck, Real Authentication) are human-labour bottlenecks at $60–$139/item with no API or bulk access. **No computer vision API exists** that authenticates Hermès from resale listing photos — the exact use case every Vinted or Vestiaire operator needs.

**3. A combined authenticate + price intelligence workflow for European boutique resellers.**
Oly covers crosslisting and pricing suggestions but does no authentication. Entrupy does authentication but no pricing. Apify/BrightData produce raw data requiring significant downstream work. No product combines: *"Is this listing authentic?" + "What is this worth today on Vinted vs Vestiaire?"* in a single API or dashboard aimed at boutique or power-seller level.

### Where a new entrant could differentiate

A product combining:
- A trained image classifier (authentic vs. counterfeit) for Hermès specifically
- Real-time confirmed sold-price tracking on Vinted and Vestiaire, normalised by sub-model, leather, hardware, and condition
- A boutique-accessible API (not a $499/month enterprise contract)
- Optional crosslisting workflow (Oly-style) as a distribution moat

...occupies white space that none of the current players fill.

### Realistic revenue potential

| Customer segment | Size estimate | Price point | ARR potential |
|---|---|---|---|
| Independent European luxury resellers | 3,000–15,000 | €69/mo | €830K at 1,000 users |
| Vinted power sellers (20–200 items/mo) | 5,000+ across Europe | €19–29/mo | €480K at 2,000 users |
| Small consignment boutiques / vintage dealers | 500–2,000 | $15–25/auth via API | Volume-dependent |

**Conservative 3-year ARR target:** €1.5M–€3M at 2,000–4,000 paying users across tiers — before any B2B platform partnerships. With one Entrupy-style platform deal (as they did with TikTok Shop / Whatnot), multiples of that become achievable.

### The core moat

The dataset itself. Each authentication and each confirmed price record makes the model more accurate and the pricing index more defensible. This is a **data flywheel business** — the first entrant to build 50,000+ labelled Hermès images from resale platforms will have a durable competitive advantage that cannot be cheaply replicated. The scraping infrastructure and dataset you're building right now is exactly that foundation.

---

## Sources
- Oly Platform pricing and blog
- Apify — Vinted scraper actors and pricing pages
- BrightData — Vinted scraper, dataset, and price tracker product pages
- Lobstr.io — Vinted scraper and pricing
- Entrupy — pricing, FAQ, TikTok Shop partnership
- LegitApp and LegitCheck By Ch — pricing pages
- Real Authentication
- Rebag 2025 Clair Report and Clair AI launch announcement
- Fashionphile Certified launch (2025)
- PLOTT DATA — Vinted analytics page
- The RealReal — AI tools and authentication
- Hermès resale value retention 2025 (WWD / Rebag Clair Report)
- Luxury Resale Market Research Report 2025–2030 (BusinessWire)
- Firecrawl — BrightData pricing analysis
