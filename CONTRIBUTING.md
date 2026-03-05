# 🔧 PROVENANCE — Contribution Guidelines

## 📋 Quick Collaboration Workflow

1. **Branch Naming**  
   ```bash
   git checkout -b <type>/<short-desc>
   # type: feat, fix, docs, chore, refactor, test, perf, ci
   # e.g.: feat/hero-section-animations
   ```

2. **Development Cycle**  
   - Make changes locally
   - Test in browser (open `index.html`)
   - Commit with conventional message:
     ```bash
     git commit -m "type(scope): short description"
     # e.g.: git commit -m "feat(animations): add smooth scroll on navbar"
     ```
   - Push to remote and open PR against `main`

3. **PR Checklist**  
   - [ ] Code follows existing style (4-space indent, BEM class naming)
   - [ ] No console errors in browser dev tools
   - [ ] Responsive design verified (mobile, tablet, desktop)
   - [ ] Images optimized (check file sizes)
   - [ ] Accessibility: semantic HTML, alt text for images

## 📁 Repository Structure

```
/
├── index.html          # Main page (don't modify structure unless needed)
├── styles.css          # All styling (follow existing BEM conventions)
├── script.js           # JavaScript interactions
├── README.md           # Project overview
├── CONTRIBUTING.md     # ← You are here
├── walkthrough.md      # Design decisions & build notes
├── .github/           # GitHub workflows & templates
└── assets/            # Images, fonts, etc.
    ├── logo.png
    ├── hero.png
    ├── campus.png
    └── (any future assets)
```

## 🔧 Development Commands

```bash
# Install dependencies (if any)
npm install

# Run local dev server (if package.json exists)
npm run dev

# Build for production (if needed)
npm run build

# Lint CSS/JS (if configured)
npm run lint
```

## 🔍 Code Style

- **CSS**: Use BEM class naming (`block__element--modifier`)
- **Indentation**: 4 spaces (no tabs)
- **Colors**: Use CSS custom properties from `:root` (e.g., `var(--ivory)`)
- **Fonts**: Cormorant Garamond for headings, Jost for body
- **JavaScript**: ES6+ syntax, use `const`/`let`, avoid `var`

## 🎨 Design System

### Colors
- Ivory (`--ivory`), Slate (`--slate`), Gold (`--gold`)
- Use CSS custom properties, don't hardcode values

### Typography
- Headings: Cormorant Garamond italic
- Body: Jost 300/400
- Sizes: Use rem units for scalability

### Layout
- Mobile-first responsive design
- CSS Grid for complex layouts
- Flexbox for component alignment

## 🤝 Pull Request Process

1. Open PR against `main`
2. Include: 
   - Description of changes
   - Screenshots if UI changes
   - Links to related issues
3. Request review from maintainers
4. Address feedback promptly
5. Merge when approved

## 📝 Issues & Feature Requests

- Use GitHub Issues to track work
- Label appropriately: `bug`, `enhancement`, `documentation`, `design`
- Include clear description, steps to reproduce (for bugs), and acceptance criteria

## 🚀 Getting Started

1. Fork the repository
2. Clone your fork locally
3. Create a feature branch
4. Make your changes
5. Test thoroughly
6. Submit a pull request

## 🔧 Tools & Resources

- **Browser DevTools**: For debugging CSS and JavaScript
- **Lighthouse**: For performance and accessibility audits
- **VS Code Extensions**: Prettier, ESLint, Live Server
- **Design References**: [Google Fonts](https://fonts.google.com/), [CSS Tricks](https://css-tricks.com/)

---

**Remember**: Every contribution matters. Even small fixes improve the project for everyone.

---
*Last updated: 2026-03-05*
