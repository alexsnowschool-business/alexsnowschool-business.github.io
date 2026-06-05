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
            <a class="works-list__thumb-link" href="https://en.wikipedia.org/wiki/${encodeURIComponent(w.title)}" target="_blank" rel="noopener">
                <img class="works-list__thumb" data-wiki-title="${w.title}" alt="${w.title}" />
            </a>
            <div class="works-list__item-text">
                <div class="works-list__title-row">
                    <span class="works-list__title">${w.title}</span>
                    <span class="works-list__year">${w.year}</span>
                </div>
                <span class="works-list__notes">${w.notes}</span>
            </div>
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
        ? `${dataset.total_label} · ${lotLabel}`
        : `${lotLabel}`;

    const bodyContent = bio
        ? `<p class="artist-bio">${bio}</p>
           ${buildWorksHtml(famous_works, 'Famous Works')}
           ${buildWorksHtml(lesser_known_works, 'Lesser-Known Works')}
           <div class="artist-dataset-row">
               <span class="artist-dataset-label">Dataset</span>
               <span class="artist-dataset-value">${dataset.total_label} total · ${dataset.avg_label} avg · ${lotLabel}</span>
               ${dataset.top_lot ? `<span class="artist-dataset-top">Top lot: <em>${dataset.top_lot.title}</em> — ${fmtUSD(dataset.top_lot.hammer_usd)}</span>` : ''}
               <a class="artist-archive-link" href="../art-archive/?artist=${encodeURIComponent(display_name)}" target="_blank" rel="noopener">View lots in catalogue →</a>
           </div>`
        : `<p class="artist-stub-note">Auction data only — no biographical profile for this artist yet.</p>`;

    const toggleIcon = `<svg viewBox="0 0 10 10" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M5 1v8M1 5h8" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
    </svg>`;

    const delay = (index % 4) * 0.05;

    return `<div class="artist-card reveal${bio ? '' : ' artist-card--stub'}"
                 data-movement="${movement_id}"
                 data-name="${display_name.toLowerCase()}"
                 style="transition-delay:${delay}s">
        <button class="artist-card__header" aria-expanded="false">
            <div class="artist-card__header-left">
                <span class="artist-movement">${movement || 'Contemporary'}</span>
                <span class="artist-name">${display_name}</span>
            </div>
            <div class="artist-card__header-right">
                ${datesNat ? `<span class="artist-dates">${datesNat}</span>` : ''}
                <span class="artist-auction-value">${perfLabel}</span>
                <span class="artist-card__toggle">${toggleIcon}</span>
            </div>
        </button>
        <div class="artist-card__body">
            <div class="artist-card__body-inner">
                <div class="artist-card__body-content">
                    ${bodyContent}
                </div>
            </div>
        </div>
    </div>`;
}

async function fetchWikiThumb(title, artistName) {
    const tryQuery = async (query) => {
        try {
            const res = await fetch(
                `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(query)}`
            );
            if (!res.ok) return null;
            const data = await res.json();
            return data.thumbnail?.source || null;
        } catch { return null; }
    };
    return await tryQuery(title) || await tryQuery(`${title} (${artistName})`);
}

async function loadArtworkImages(card) {
    const artistName = card.querySelector('.artist-name')?.textContent?.trim() || '';
    const thumbEls = [...card.querySelectorAll('.works-list__thumb[data-wiki-title]')]
        .filter(img => !img.dataset.loaded);

    await Promise.all(thumbEls.map(async img => {
        img.dataset.loaded = '1';
        const src = await fetchWikiThumb(img.dataset.wikiTitle, artistName);
        if (src) {
            img.src = src;
            img.classList.add('works-list__thumb--visible');
        } else {
            img.closest('.works-list__item').classList.add('works-list__item--no-thumb');
        }
    }));
}

const MOVEMENTS = [
    { id: 'impressionism',          label: 'Impressionism',          period: 'c. 1870–1900' },
    { id: 'post-impressionism',     label: 'Post-Impressionism',     period: 'c. 1886–1910' },
    { id: 'expressionism',          label: 'Expressionism',          period: 'c. 1905–1930' },
    { id: 'cubism',                 label: 'Cubism',                 period: 'c. 1907–1930' },
    { id: 'dada',                   label: 'Dada',                   period: 'c. 1916–1924' },
    { id: 'surrealism',             label: 'Surrealism',             period: 'c. 1924–1945' },
    { id: 'modernism',              label: 'Modernism',              period: 'c. 1910–1950' },
    { id: 'abstract-expressionism', label: 'Abstract Expressionism', period: 'c. 1943–1965' },
    { id: 'colour-field',           label: 'Colour Field',           period: 'c. 1950–1970' },
    { id: 'pop-art',                label: 'Pop Art',                period: 'c. 1955–1975' },
    { id: 'minimalism',             label: 'Minimalism',             period: 'c. 1960–1975' },
    { id: 'conceptual',             label: 'Conceptual Art',         period: 'c. 1966–present' },
    { id: 'neo-expressionism',      label: 'Neo-Expressionism',      period: 'c. 1980–1990' },
    { id: 'photography',            label: 'Photography',            period: 'medium' },
    { id: 'sculpture',              label: 'Sculpture',              period: 'medium' },
    { id: 'installation',           label: 'Installation',           period: 'c. 1960–present' },
    { id: 'street-art',             label: 'Street Art',             period: 'c. 1970–present' },
    { id: 'new-media',              label: 'New Media',              period: 'c. 1990–present' },
    { id: 'contemporary',           label: 'Contemporary',           period: 'c. 1970–present' },
];

const CLUSTER_PREVIEW = 8;

function buildTimeline(artists) {
    const byMovement = {};
    artists.forEach(a => {
        const id = a.movement_id || 'contemporary';
        if (!byMovement[id]) byMovement[id] = [];
        byMovement[id].push(a);
    });

    return MOVEMENTS
        .filter(m => byMovement[m.id] && byMovement[m.id].length > 0)
        .map(m => {
            const group = byMovement[m.id];
            const visible = group.slice(0, CLUSTER_PREVIEW);
            const hidden  = group.slice(CLUSTER_PREVIEW);

            const visibleHtml = visible.map((a, i) => buildArtistCard(a, i)).join('');
            const overflowHtml = hidden.length
                ? `<div class="cluster-overflow" hidden>${hidden.map((a, i) => buildArtistCard(a, visible.length + i)).join('')}</div>
                   <button class="cluster-show-more" data-hidden="${hidden.length}">Show ${hidden.length} more →</button>`
                : '';

            return `<div class="movement-cluster" data-movement="${m.id}">
                <div class="movement-node">
                    <div class="movement-node__label">${m.label}</div>
                    <div class="movement-node__period">${m.period}</div>
                    <div class="movement-node__count">${group.length} artist${group.length !== 1 ? 's' : ''}</div>
                </div>
                <div class="cluster-cards">${visibleHtml}${overflowHtml}</div>
            </div>`;
        })
        .join('');
}

function wireTimeline() {
    const searchInput = document.getElementById('artistSearch');
    const timeline    = document.getElementById('movementTimeline');

    function resetClusters() {
        timeline.querySelectorAll('.movement-cluster').forEach(cluster => {
            cluster.hidden = false;
            cluster.querySelectorAll('.artist-card').forEach(c => c.classList.remove('hidden'));
            cluster.querySelectorAll('.cluster-overflow').forEach(ov => { ov.hidden = true; });
            cluster.querySelectorAll('.cluster-show-more').forEach(btn => { btn.hidden = false; });
        });
    }

    searchInput?.addEventListener('input', () => {
        const query = searchInput.value.trim().toLowerCase();
        if (!query) { resetClusters(); return; }

        timeline.querySelectorAll('.movement-cluster').forEach(cluster => {
            cluster.querySelectorAll('.cluster-overflow').forEach(ov => { ov.hidden = false; });
            cluster.querySelectorAll('.cluster-show-more').forEach(btn => { btn.hidden = true; });

            let anyVisible = false;
            cluster.querySelectorAll('.artist-card').forEach(card => {
                const match = card.dataset.name.includes(query);
                card.classList.toggle('hidden', !match);
                if (match) anyVisible = true;
            });
            cluster.hidden = !anyVisible;
        });
    });

    timeline.addEventListener('click', e => {
        const showMoreBtn = e.target.closest('.cluster-show-more');
        if (showMoreBtn) {
            const cluster = showMoreBtn.closest('.movement-cluster');
            const overflow = cluster.querySelector('.cluster-overflow');
            if (overflow) {
                overflow.hidden = false;
                overflow.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));
            }
            showMoreBtn.remove();
            return;
        }

        const header = e.target.closest('.artist-card__header');
        if (!header) return;
        const card = header.closest('.artist-card');
        const isOpen = card.classList.toggle('artist-card--open');
        header.setAttribute('aria-expanded', isOpen);
        if (isOpen) loadArtworkImages(card);
    });
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

    // Render movement timeline
    const timeline = document.getElementById('movementTimeline');
    timeline.innerHTML = buildTimeline(artists);

    // Observe visible cards (overflow cards are hidden until "Show more")
    timeline.querySelectorAll('.cluster-cards > .artist-card.reveal').forEach(el => revealObserver.observe(el));

    wireTimeline();
}

loadResearch();
