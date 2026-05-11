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

const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            revealObserver.unobserve(entry.target);
        }
    });
}, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

document.querySelectorAll('.thinker-grid .thinker-card').forEach((el, i) => {
    el.style.transitionDelay = (i % 3) * 0.07 + 's';
});

window.addEventListener('scroll', () => {
    updateProgress();
    toggleScrollTop();
    updateActiveNav();
}, { passive: true });

document.getElementById('scrollTop').addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
});

// ── RESEARCH DATA ────────────────────────────────────────────────────────────

function fmtUSD(v) {
    if (!v) return '—';
    if (v >= 1e6) return '$' + (v / 1e6).toFixed(2).replace(/\.?0+$/, '') + 'M';
    if (v >= 1e3) return '$' + Math.round(v / 1e3) + 'k';
    return '$' + Math.round(v);
}

function buildWorksHtml(works, label) {
    if (!works || works.length === 0) return '';
    const items = works.map(w => `
        <li class="works-list__item">
            <span class="works-list__title">${w.title}</span
            ><span class="works-list__year">${w.year}</span>
            <span class="works-list__notes">${w.notes}</span>
        </li>`).join('');
    return `
        <div class="artist-works__section">
            <div class="artist-works__label">${label}</div>
            <ul class="works-list">${items}</ul>
        </div>`;
}

function buildArtistCard(artist, index) {
    const { display_name, dates, nationality, movement, movement_id,
            bio, famous_works, lesser_known_works, dataset } = artist;

    const datesNat = [dates, nationality].filter(Boolean).join(' · ');
    const lotLabel = `${dataset.lot_count} lot${dataset.lot_count !== 1 ? 's' : ''}`;
    const perfLabel = dataset.total_usd
        ? `${dataset.total_label} total · ${dataset.avg_label} avg`
        : 'In dataset';

    const worksHtml = bio ? `
        <div class="artist-works">
            ${buildWorksHtml(famous_works, 'Famous Works')}
            ${buildWorksHtml(lesser_known_works, 'Lesser-Known Works')}
        </div>` : '';

    const delay = (index % 3) * 0.07;

    return `<div class="artist-card reveal${bio ? '' : ' artist-card--stub'}"
                 data-movement="${movement_id}"
                 data-name="${display_name.toLowerCase()}"
                 style="transition-delay:${delay}s">
        <div class="artist-movement">${movement || 'Contemporary'}</div>
        <div class="artist-name">${display_name}</div>
        ${datesNat ? `<div class="artist-dates">${datesNat}</div>` : ''}
        ${bio ? `<p class="artist-bio">${bio}</p>` : ''}
        ${worksHtml}
        <div class="artist-auction">
            <div class="artist-auction-label">Dataset — ${lotLabel}</div>
            <div class="artist-auction-value">${perfLabel}</div>
        </div>
    </div>`;
}

function wireFilters() {
    const btns        = document.querySelectorAll('.movement-btn');
    const searchInput = document.getElementById('artistSearch');
    const grid        = document.getElementById('artistsGrid');

    function applyFilters() {
        const movement = document.querySelector('.movement-btn.active')?.dataset.movement || 'all';
        const query    = (searchInput?.value || '').trim().toLowerCase();

        grid.querySelectorAll('.artist-card').forEach(card => {
            const matchMovement = movement === 'all' || card.dataset.movement === movement;
            const matchName     = !query || card.dataset.name.includes(query);
            card.classList.toggle('hidden', !(matchMovement && matchName));
        });
    }

    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            btns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            applyFilters();
        });
    });

    searchInput?.addEventListener('input', applyFilters);
}

async function loadResearch() {
    let data;
    try {
        const res = await fetch('research.json');
        data = await res.json();
    } catch (e) {
        console.error('research.json not found — run build_research_json.py', e);
        return;
    }

    const { stats, artists } = data;

    // Hero stats
    const statMap = {
        total_lots:    stats.total_lots.toLocaleString(),
        total_artists: stats.total_artists.toLocaleString(),
        median_hammer: fmtUSD(stats.median_hammer_usd),
        pct_above:     stats.pct_above_estimate + '%',
        max_ratio:     stats.max_ratio + '×',
        sources:       (stats.sources || []).join(', '),
    };
    document.querySelectorAll('[data-stat]').forEach(el => {
        const key = el.dataset.stat;
        if (statMap[key] !== undefined) el.textContent = statMap[key];
    });

    // Update description
    const desc = document.getElementById('artistsDesc');
    if (desc && stats.generated_at) {
        desc.textContent = `Profiles drawn from ${stats.total_lots.toLocaleString()} auction lots across ${(stats.sources || []).join(', ')} — biography, key works, and market performance. Synced ${stats.generated_at}. All prices are hammer in USD.`;
    }

    // Render artist grid
    const grid = document.getElementById('artistsGrid');
    const profiled  = artists.filter(a => a.bio);
    const stubs     = artists.filter(a => !a.bio);

    grid.innerHTML = profiled.map((a, i) => buildArtistCard(a, i)).join('') +
                     stubs.map((a, i) => buildArtistCard(a, profiled.length + i)).join('');

    // Observe new cards
    grid.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

    wireFilters();
}

loadResearch();
