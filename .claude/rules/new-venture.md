---
name: New Venture Checklist
description: Steps and conventions for scaffolding a new venture subdirectory
type: always
---

# Adding a New Venture

When asked to create or scaffold a new venture, follow these steps in order:

## I. Directory Structure

Create the following files under `venture-name/`:

```
venture-name/
├── index.html
├── styles.css
├── script.js
└── CLAUDE.md
```

## II. HTML Boilerplate

- Link Google Fonts: Cormorant Garamond (italic, 400/600) + Jost (300/400)
- Use semantic HTML5 elements (`<main>`, `<section>`, `<nav>`, `<footer>`)
- No inline styles — all styling via `styles.css`

## III. CSS Setup

Define these tokens in `:root` before any other rules:

```css
:root {
    --ivory: #f5f0e8;
    --slate: #3a3a3a;
    --gold: #c9a84c;
    --font-heading: 'Cormorant Garamond', serif;
    --font-body: 'Jost', sans-serif;
}
```

- Use BEM naming throughout: `block__element--modifier`
- 1px hairline borders only — never thicker
- No hardcoded color values — always reference a CSS custom property

## IV. Root Dashboard

Add a card to the root `index.html` `#cardGrid`:

```html
<a href="./venture-name/" class="card">
    <h2 class="card__title">Venture Name</h2>
    <p class="card__status">In Development</p>
    <p class="card__description">One-line description of the venture.</p>
</a>
```

## V. Venture CLAUDE.md

Create `venture-name/CLAUDE.md` with:

```markdown
# Venture Name

Status: In Development
Audience: [who this is for]
Brand tone: [editorial direction — e.g. "aspirational but approachable"]
Key sections: [list main page sections]
Notes: [anything Claude should know before editing this venture]
```

## VI. Checklist Before Handing Off

- [ ] Fonts loaded from Google Fonts
- [ ] CSS tokens defined in `:root`
- [ ] No hardcoded colors or emoji
- [ ] Card added to root `#cardGrid`
- [ ] `CLAUDE.md` created in venture folder
- [ ] Branch named `feat/venture-name`
