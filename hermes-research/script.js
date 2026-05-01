'use strict';

// Reading progress bar
const progressBar = document.getElementById('progressBar');
function updateProgress() {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    progressBar.style.width = (scrollTop / docHeight * 100) + '%';
}

// Scroll to top button
const scrollTopBtn = document.getElementById('scrollTop');
function toggleScrollTop() {
    scrollTopBtn.classList.toggle('visible', window.scrollY > 500);
}

// Active nav link on scroll
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

// Intersection observer for reveal animations
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            observer.unobserve(entry.target);
        }
    });
}, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

document.querySelectorAll('.reveal').forEach(el => observer.observe(el));

// Stagger reveal for grids
document.querySelectorAll('.thinker-grid .thinker-card, .ideology-grid .ideology-card, .library-grid .library-card').forEach((el, i) => {
    el.style.transitionDelay = (i % 2) * 0.1 + 's';
});

window.addEventListener('scroll', () => {
    updateProgress();
    toggleScrollTop();
    updateActiveNav();
}, { passive: true });
