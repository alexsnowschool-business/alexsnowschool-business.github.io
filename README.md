# AlexSnow School — Business Portfolio

A multi-venture project hub. Each business idea lives in its own directory.

## Structure

```
alexsnowschool-business/
├── index.html                  ← Root dashboard (open this to navigate all ventures)
├── provenance/                 ← Heritage luxury resale platform
│   ├── index.html
│   ├── styles.css
│   ├── script.js
│   └── (images)
└── studentroadtogermany/       ← Myanmar → Germany study consultation
    └── index.html
```

## Adding a New Business Idea

1. Create a new folder: `mkdir my-new-idea/`
2. Add your `index.html`, `styles.css`, `script.js` inside it
3. Add a card in the root `index.html` pointing to `./my-new-idea/index.html`

## Running Locally

Open `index.html` in a browser, or serve with:

```bash
npx serve .
```
