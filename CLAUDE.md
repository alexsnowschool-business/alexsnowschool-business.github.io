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

## Rules

- @.claude/rules/code-style.md
- @.claude/rules/design-system.md
- @.claude/rules/git-workflow.md
- @.claude/rules/new-venture.md
