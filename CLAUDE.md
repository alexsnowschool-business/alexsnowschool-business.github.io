# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running Locally

```bash
npx serve .
```

Then open `http://localhost:3000` in a browser. No build step — all files are plain HTML/CSS/JS.

## Structure

This is a multi-venture portfolio hub. Each business lives in its own subdirectory with its own `index.html`, `styles.css`, and `script.js`. The root `index.html` is a dashboard that links to each venture via cards.

Current ventures:
- `provenance/` — Heritage luxury resale platform (status: Live)
- `studentroadtogermany/` — Myanmar → Germany study consultation (status: In Development)

To add a new venture: create a new folder, add its files, then add a card in the root `index.html` `#cardGrid`.

## Code Style

- **CSS**: BEM class naming (`block__element--modifier`), CSS custom properties from `:root` — never hardcode color values
- **Indentation**: 4 spaces
- **JS**: ES6+ syntax, `const`/`let` only

## Design System (Provenance / shared aesthetic)

- **Fonts**: Cormorant Garamond italic for headings, Jost 300/400 for body
- **Colors**: `--ivory`, `--slate`, `--gold` via CSS custom properties; warm palette only — no cool grays, no neons
- **Icons/numbers**: Roman numerals (I. II. III. IV.), no emoji
- **Borders**: 1px hairlines only
- **CTA copy tone**: "Enquire" not "Buy Now" — editorial, unhurried

## Commit Convention

```
type(scope): short description
# e.g.: feat(animations): add smooth scroll on navbar
# types: feat, fix, docs, chore, refactor, test, perf, ci
```

Branch naming: `type/short-desc` (e.g. `feat/hero-section-animations`). PRs go against `main`.
