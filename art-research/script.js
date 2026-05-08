'use strict';

const progressBar = document.getElementById('progressBar');
function updateProgress() {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    progressBar.style.width = (scrollTop / docHeight * 100) + '%';
}

const scrollTopBtn = document.getElementById('scrollTop');
function toggleScrollTop() {
    scrollTopBtn.classList.toggle('visible', window.scrollY > 500);
}

const navLinks = document.querySelectorAll('.nav-links a');
const sections = document.querySelectorAll('section[id]');

function updateActiveNav() {
    let current = '';
    sections.forEach(section => {
        const top = section.offsetTop - 100;
        if (window.scrollY >= top) current = section.getAttribute('id');
    });
    navLinks.forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === '#' + current) link.classList.add('active');
    });
}

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target);
        }
    });
}, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

document.querySelectorAll('.reveal').forEach(el => observer.observe(el));

document.querySelectorAll('.thinker-grid .thinker-card, .artist-card').forEach((el, i) => {
    el.style.transitionDelay = (i % 3) * 0.07 + 's';
});

// Movement filter
const movementBtns = document.querySelectorAll('.movement-btn');
const artistCards = document.querySelectorAll('.artist-card');

movementBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        movementBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const filter = btn.dataset.movement;
        artistCards.forEach(card => {
            if (filter === 'all' || card.dataset.movement === filter) {
                card.classList.remove('hidden');
            } else {
                card.classList.add('hidden');
            }
        });
    });
});

window.addEventListener('scroll', () => {
    updateProgress();
    toggleScrollTop();
    updateActiveNav();
}, { passive: true });

document.getElementById('scrollTop').addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
});
