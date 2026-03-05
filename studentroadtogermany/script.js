/* ===============================================
   Student Road to Germany - JavaScript
   =============================================== */

// ===== NAVBAR SCROLL EFFECT =====
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
  if (window.scrollY > 60) {
    navbar.classList.add('scrolled');
  } else {
    navbar.classList.remove('scrolled');
  }
});

// ===== HAMBURGER MENU =====
const hamburger = document.getElementById('hamburger');
const navLinks = document.getElementById('navLinks');

hamburger.addEventListener('click', () => {
  navLinks.classList.toggle('open');
  hamburger.classList.toggle('active');
  const isOpen = navLinks.classList.contains('open');
  hamburger.setAttribute('aria-label', isOpen ? 'Close menu' : 'Open menu');
});

// Close mobile menu when a link is clicked
document.querySelectorAll('.nav-link, .nav-btn').forEach(link => {
  link.addEventListener('click', () => {
    navLinks.classList.remove('open');
    hamburger.classList.remove('active');
  });
});

// ===== SCROLL REVEAL ANIMATION =====
const revealElements = document.querySelectorAll(
  '.package-card, .step, .why-point, .testi-card, .faq-item, .channel, .why-image-col, .why-content'
);

revealElements.forEach(el => el.classList.add('reveal'));

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        setTimeout(() => {
          entry.target.classList.add('visible');
        }, i * 80);
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.1, rootMargin: '0px 0px -50px 0px' }
);

revealElements.forEach(el => revealObserver.observe(el));

// ===== ANIMATED COUNTER =====
function animateCounter(el, target, duration = 1500) {
  let start = 0;
  const step = target / (duration / 16);
  const timer = setInterval(() => {
    start += step;
    if (start >= target) {
      start = target;
      clearInterval(timer);
    }
    el.textContent = Math.floor(start);
  }, 16);
}

const statsObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        document.querySelectorAll('.stat-num').forEach(el => {
          const target = parseInt(el.getAttribute('data-target'));
          animateCounter(el, target);
        });
        statsObserver.disconnect();
      }
    });
  },
  { threshold: 0.5 }
);

const heroStats = document.querySelector('.hero-stats');
if (heroStats) statsObserver.observe(heroStats);

// ===== FAQ ACCORDION =====
document.querySelectorAll('.faq-question').forEach(button => {
  button.addEventListener('click', () => {
    const item = button.parentElement;
    const answer = item.querySelector('.faq-answer');
    const isOpen = item.classList.contains('open');

    // Close all
    document.querySelectorAll('.faq-item').forEach(faqItem => {
      faqItem.classList.remove('open');
      const ans = faqItem.querySelector('.faq-answer');
      ans.style.maxHeight = '0';
    });

    // Open clicked if it was closed
    if (!isOpen) {
      item.classList.add('open');
      answer.style.maxHeight = answer.scrollHeight + 'px';
    }
  });
});

// ===== CONTACT FORM =====
const contactForm = document.getElementById('contactForm');
const formSuccess = document.getElementById('formSuccess');

if (contactForm) {
  contactForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const name = document.getElementById('nameInput').value.trim();
    const email = document.getElementById('emailInput').value.trim();

    if (!name || !email) {
      // Simple validation shake
      if (!name) shakeElement(document.getElementById('nameInput'));
      if (!email) shakeElement(document.getElementById('emailInput'));
      return;
    }

    // Simulate form submission
    const submitBtn = document.getElementById('submitBtn');
    submitBtn.textContent = 'Sending...';
    submitBtn.disabled = true;

    setTimeout(() => {
      formSuccess.style.display = 'block';
      contactForm.reset();
      submitBtn.textContent = 'Send Message 🚀';
      submitBtn.disabled = false;

      // Hide success message after 5s
      setTimeout(() => {
        formSuccess.style.display = 'none';
      }, 5000);
    }, 1200);
  });
}

function shakeElement(el) {
  el.style.borderColor = '#ef4444';
  el.style.animation = 'shake 0.4s ease';
  setTimeout(() => {
    el.style.borderColor = '';
    el.style.animation = '';
  }, 400);
}

// Add shake keyframes dynamically
const shakeStyle = document.createElement('style');
shakeStyle.textContent = `
  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    20% { transform: translateX(-8px); }
    40% { transform: translateX(8px); }
    60% { transform: translateX(-6px); }
    80% { transform: translateX(6px); }
  }
`;
document.head.appendChild(shakeStyle);

// ===== SCROLL TO TOP BUTTON =====
const scrollTopBtn = document.getElementById('scrollTop');

window.addEventListener('scroll', () => {
  if (window.scrollY > 400) {
    scrollTopBtn.classList.add('visible');
  } else {
    scrollTopBtn.classList.remove('visible');
  }
});

scrollTopBtn.addEventListener('click', () => {
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// ===== SMOOTH ACTIVE NAV HIGHLIGHT =====
const sections = document.querySelectorAll('section[id]');
const navItems = document.querySelectorAll('.nav-link');

function updateActiveNav() {
  const scrollPos = window.scrollY + 120;
  sections.forEach(section => {
    if (
      scrollPos >= section.offsetTop &&
      scrollPos < section.offsetTop + section.offsetHeight
    ) {
      navItems.forEach(link => {
        link.classList.remove('active-nav');
        if (link.getAttribute('href') === '#' + section.id) {
          link.classList.add('active-nav');
        }
      });
    }
  });
}

// Add active nav style
const navActiveStyle = document.createElement('style');
navActiveStyle.textContent = `.active-nav { color: var(--secondary-light) !important; background: rgba(206,148,47,0.12) !important; }`;
document.head.appendChild(navActiveStyle);

window.addEventListener('scroll', updateActiveNav, { passive: true });

// ===== PACKAGE CARD TILT EFFECT =====
document.querySelectorAll('.package-card').forEach(card => {
  card.addEventListener('mousemove', (e) => {
    const rect = card.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width - 0.5) * 8;
    const y = ((e.clientY - rect.top) / rect.height - 0.5) * -8;
    card.style.transform = `perspective(1000px) rotateX(${y}deg) rotateY(${x}deg) translateY(-6px)`;
  });

  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
  });
});

// ===== HERO PARALLAX =====
const heroImg = document.querySelector('.hero-img');
if (heroImg) {
  window.addEventListener('scroll', () => {
    const scrolled = window.scrollY;
    heroImg.style.transform = `translateY(${scrolled * 0.3}px)`;
  }, { passive: true });
}

// ===== PACKAGE BUTTON - AUTO SET FORM SELECT =====
document.querySelectorAll('.pkg-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    const card = btn.closest('.package-card');
    const select = document.getElementById('packageSelect');
    if (!select) return;

    if (card.id === 'pkg-university') select.value = 'university';
    else if (card.id === 'pkg-blocked') select.value = 'blocked';
    else if (card.id === 'pkg-full') select.value = 'full';
  });
});

// ===== INITIAL LOAD ANIMATION =====
document.addEventListener('DOMContentLoaded', () => {
  setTimeout(() => {
    document.body.style.opacity = '1';
  }, 100);
});
