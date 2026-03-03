/* ===============================================
   PROVENANCE — Authenticated Heritage
   JavaScript: interactions, filters, tabs, forms
   =============================================== */

// ===== NAVBAR SCROLL =====
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
  navbar.classList.toggle('scrolled', window.scrollY > 60);
}, { passive: true });

// ===== HAMBURGER =====
const hamburger = document.getElementById('hamburger');
const navLinks = document.getElementById('navLinks');
hamburger.addEventListener('click', () => {
  navLinks.classList.toggle('open');
  hamburger.classList.toggle('active');
  hamburger.setAttribute('aria-label', navLinks.classList.contains('open') ? 'Close menu' : 'Open menu');
});
document.querySelectorAll('.nav-link, .nav-btn').forEach(link => {
  link.addEventListener('click', () => {
    navLinks.classList.remove('open');
    hamburger.classList.remove('active');
  });
});

// ===== COLLECTION FILTER =====
const filterBtns = document.querySelectorAll('.filter-btn');
const pieceCards = document.querySelectorAll('.piece-card');

filterBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    // Toggle active button
    filterBtns.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const filter = btn.dataset.filter;

    pieceCards.forEach(card => {
      if (filter === 'all' || card.dataset.house === filter) {
        card.classList.remove('hidden');
        // Re-trigger reveal if needed
        setTimeout(() => card.classList.add('visible'), 20);
      } else {
        card.classList.add('hidden');
      }
    });
  });
});

// ===== BUY / CONSIGN TABS =====
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

tabBtns.forEach(btn => {
  btn.addEventListener('click', () => {
    tabBtns.forEach(b => b.classList.remove('active'));
    tabContents.forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

// ===== SCROLL REVEAL =====
const revealEls = document.querySelectorAll(
  '.piece-card, .house-card, .why-point, .step, .manifesto-inner, .why-image-col, .why-content'
);
revealEls.forEach(el => el.classList.add('reveal'));

const revealObs = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        setTimeout(() => entry.target.classList.add('visible'), i * 70);
        revealObs.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.08, rootMargin: '0px 0px -40px 0px' }
);
revealEls.forEach(el => revealObs.observe(el));

// ===== SELECT COLOUR ON VALUE =====
document.querySelectorAll('select').forEach(sel => {
  sel.addEventListener('change', () => sel.classList.add('has-value'));
});

// ===== CONTACT FORM =====
const contactForm = document.getElementById('contactForm');
const formSuccess = document.getElementById('formSuccess');

if (contactForm) {
  contactForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const name = document.getElementById('nameInput').value.trim();
    const email = document.getElementById('emailInput').value.trim();
    if (!name) { shakeEl(document.getElementById('nameInput')); }
    if (!email) { shakeEl(document.getElementById('emailInput')); }
    if (!name || !email) return;

    const btn = document.getElementById('submitBtn');
    const span = btn.querySelector('span');
    span.textContent = 'Sending\u2026';
    btn.disabled = true;

    setTimeout(() => {
      formSuccess.style.display = 'block';
      contactForm.reset();
      document.querySelectorAll('select').forEach(s => s.classList.remove('has-value'));
      span.textContent = 'Submit Enquiry';
      btn.disabled = false;
      setTimeout(() => { formSuccess.style.display = 'none'; }, 6000);
    }, 1200);
  });
}

function shakeEl(el) {
  el.style.borderBottomColor = '#8B3347';
  el.style.animation = 'shake 0.4s ease';
  setTimeout(() => { el.style.borderBottomColor = ''; el.style.animation = ''; }, 420);
}

const shakeStyle = document.createElement('style');
shakeStyle.textContent = `
  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    20% { transform: translateX(-6px); }
    40% { transform: translateX(6px); }
    60% { transform: translateX(-4px); }
    80% { transform: translateX(4px); }
  }
`;
document.head.appendChild(shakeStyle);

// ===== SCROLL TO TOP =====
const scrollTopBtn = document.getElementById('scrollTop');
window.addEventListener('scroll', () => {
  scrollTopBtn.classList.toggle('visible', window.scrollY > 400);
}, { passive: true });
scrollTopBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

// ===== ACTIVE NAV HIGHLIGHT =====
const sections = document.querySelectorAll('section[id]');
const navItems = document.querySelectorAll('.nav-link');

function updateActiveNav() {
  const pos = window.scrollY + 120;
  sections.forEach(section => {
    if (pos >= section.offsetTop && pos < section.offsetTop + section.offsetHeight) {
      navItems.forEach(link => {
        link.classList.remove('active-nav');
        if (link.getAttribute('href') === '#' + section.id) link.classList.add('active-nav');
      });
    }
  });
}

const navActiveStyle = document.createElement('style');
navActiveStyle.textContent = `.active-nav { color: var(--slate) !important; }
.navbar.scrolled .active-nav { color: var(--gold-muted) !important; }`;
document.head.appendChild(navActiveStyle);
window.addEventListener('scroll', updateActiveNav, { passive: true });

// ===== PIECE CARD — AUTO-FILL FORM HOUSE ====
document.querySelectorAll('.piece-btn:not(.piece-btn-reserved)').forEach(btn => {
  btn.addEventListener('click', (e) => {
    const card = btn.closest('.piece-card');
    const house = card?.dataset.house;
    const houseSelect = document.getElementById('houseSelect');
    const intSelect = document.getElementById('packageSelect');
    if (houseSelect && house) houseSelect.value = house, houseSelect.classList.add('has-value');
    if (intSelect) intSelect.value = 'buy', intSelect.classList.add('has-value');
  });
});
