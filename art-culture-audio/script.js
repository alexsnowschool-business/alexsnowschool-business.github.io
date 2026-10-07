const HISTORY_KEY = 'audioArchiveHistory';
const STATUS_LABEL = {
    not_started: 'Unheard',
    in_progress: 'In Progress',
    completed: 'Completed',
};

function loadHistory() {
    try {
        return JSON.parse(localStorage.getItem(HISTORY_KEY)) || {};
    } catch {
        return {};
    }
}

function saveHistory(history) {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
}

function getStatus(history, id) {
    return history[id]?.status || 'not_started';
}

function markAccessed(id) {
    const history = loadHistory();
    const now = new Date().toISOString();
    const existing = history[id];
    history[id] = {
        status: existing?.status === 'completed' ? 'completed' : 'in_progress',
        firstAccessed: existing?.firstAccessed || now,
        lastAccessed: now,
        accessCount: (existing?.accessCount || 0) + 1,
    };
    saveHistory(history);
}

function markCompleted(id) {
    const history = loadHistory();
    const now = new Date().toISOString();
    const existing = history[id];
    history[id] = {
        status: 'completed',
        firstAccessed: existing?.firstAccessed || now,
        lastAccessed: now,
        completedAt: now,
        accessCount: existing?.accessCount || 1,
    };
    saveHistory(history);
}

const PAGE_SIZE = 20;

let episodes = [];
let history = loadHistory();
let activeStatusFilter = 'all';
let activeTopicFilter = 'all';
let activeQuery = '';
let currentPage = 1;

const libraryView = document.getElementById('view-library');
const episodeView = document.getElementById('view-episode');
const episodeListEl = document.getElementById('episodeList');
const emptyStateEl = document.getElementById('emptyState');
const statsEl = document.getElementById('stats');
const searchEl = document.getElementById('search');
const statusFiltersEl = document.getElementById('statusFilters');
const topicFiltersEl = document.getElementById('topicFilters');
const paginationEl = document.getElementById('pagination');
const backLink = document.getElementById('backToLibrary');
const markCompletedBtn = document.getElementById('markCompleted');
const audioPlayer = document.getElementById('audioPlayer');

function renderTopicFilters() {
    const counts = {};
    episodes.forEach((e) => {
        if (!e.topic) return;
        counts[e.topic] = (counts[e.topic] || 0) + 1;
    });
    const topics = Object.keys(counts).sort((a, b) => counts[b] - counts[a] || a.localeCompare(b));

    topicFiltersEl.innerHTML = '';

    const allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.className = `pill ${activeTopicFilter === 'all' ? 'pill--active' : ''}`;
    allBtn.dataset.topic = 'all';
    allBtn.textContent = `All Topics (${episodes.length})`;
    topicFiltersEl.appendChild(allBtn);

    topics.forEach((topic) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `pill ${activeTopicFilter === topic ? 'pill--active' : ''}`;
        btn.dataset.topic = topic;
        btn.textContent = `${topic} (${counts[topic]})`;
        topicFiltersEl.appendChild(btn);
    });
}

function renderStats() {
    const total = episodes.length;
    const transcribed = episodes.filter(e => e.has_transcript).length;
    const completed = Object.values(history).filter(h => h.status === 'completed').length;

    statsEl.innerHTML = `
        <div class="stat"><span class="stat__value">${total}</span><span class="stat__label">Episodes</span></div>
        <div class="stat"><span class="stat__value">${transcribed}</span><span class="stat__label">Transcribed</span></div>
        <div class="stat"><span class="stat__value">${completed}</span><span class="stat__label">Completed</span></div>
    `;
}

function filteredEpisodes() {
    return episodes.filter(e => {
        const status = getStatus(history, e.id);
        const matchesStatus = activeStatusFilter === 'all' || status === activeStatusFilter;
        const matchesTopic = activeTopicFilter === 'all' || e.topic === activeTopicFilter;
        const matchesQuery = e.title.toLowerCase().includes(activeQuery.toLowerCase());
        return matchesStatus && matchesTopic && matchesQuery;
    });
}

function renderList() {
    const list = filteredEpisodes();
    const pageCount = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
    currentPage = Math.min(Math.max(1, currentPage), pageCount);
    const start = (currentPage - 1) * PAGE_SIZE;
    const pageItems = list.slice(start, start + PAGE_SIZE);

    episodeListEl.innerHTML = '';
    emptyStateEl.hidden = list.length > 0;

    pageItems.forEach((episode) => {
        const status = getStatus(history, episode.id);
        const card = document.createElement('button');
        card.type = 'button';
        card.className = 'episode-card';
        card.innerHTML = `
            <span>
                <span class="episode-card__title">${episode.title}</span>
            </span>
            <span class="episode-card__meta">
                <span class="status-badge status-badge--${status}">${STATUS_LABEL[status]}</span>
                ${episode.published ? `<span class="episode-card__published">${episode.published}</span>` : ''}
            </span>
        `;
        card.addEventListener('click', () => {
            location.hash = `#/episode/${episode.id}`;
        });
        episodeListEl.appendChild(card);
    });

    renderPagination(pageCount);
}

function renderPagination(pageCount) {
    paginationEl.innerHTML = '';
    if (pageCount <= 1) return;

    const makeBtn = (label, page, disabled = false) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'pill';
        btn.textContent = label;
        if (disabled) btn.disabled = true;
        else btn.addEventListener('click', () => {
            currentPage = page;
            renderList();
        });
        return btn;
    };

    paginationEl.appendChild(makeBtn('Prev', currentPage - 1, currentPage === 1));

    const pageLabel = document.createElement('span');
    pageLabel.className = 'pill pill--active pagination__page';
    pageLabel.textContent = `${currentPage} / ${pageCount}`;
    paginationEl.appendChild(pageLabel);

    paginationEl.appendChild(makeBtn('Next', currentPage + 1, currentPage === pageCount));
}

function renderEpisode(id) {
    const episode = episodes.find(e => e.id === id);
    if (!episode) {
        location.hash = '#/';
        return;
    }

    document.getElementById('episodeEyebrow').textContent =
        `II. ${episode.has_transcript ? 'Lecture with Transcript' : 'Audio Recording'}`;
    document.getElementById('episodeTitle').textContent = episode.title;
    document.getElementById('episodePublished').textContent = episode.published || '';

    audioPlayer.src = episode.mp3;

    const transcriptBody = document.getElementById('transcriptBody');
    if (episode.transcript) {
        transcriptBody.textContent = episode.transcript;
        transcriptBody.classList.remove('transcript--empty');
    } else {
        transcriptBody.textContent = 'No transcript has been generated for this episode yet.';
        transcriptBody.classList.add('transcript--empty');
    }

    updateStatusBadge(episode.id);

    markCompletedBtn.onclick = () => {
        markCompleted(episode.id);
        history = loadHistory();
        updateStatusBadge(episode.id);
    };

    audioPlayer.onplay = () => {
        markAccessed(episode.id);
        history = loadHistory();
        updateStatusBadge(episode.id);
    };
}

function updateStatusBadge(id) {
    const status = getStatus(history, id);
    const badge = document.getElementById('episodeStatus');
    badge.className = `status-badge status-badge--${status}`;
    badge.textContent = STATUS_LABEL[status];
}

function router() {
    const hash = location.hash;
    const match = hash.match(/^#\/episode\/(.+)$/);

    if (match) {
        libraryView.hidden = true;
        episodeView.hidden = false;
        renderEpisode(match[1]);
    } else {
        libraryView.hidden = false;
        episodeView.hidden = true;
        audioPlayer.pause();
        renderStats();
        renderTopicFilters();
        renderList();
    }
}

searchEl.addEventListener('input', (e) => {
    activeQuery = e.target.value;
    currentPage = 1;
    renderList();
});

statusFiltersEl.addEventListener('click', (e) => {
    const btn = e.target.closest('.pill');
    if (!btn) return;
    activeStatusFilter = btn.dataset.status;
    [...statusFiltersEl.children].forEach(c => c.classList.remove('pill--active'));
    btn.classList.add('pill--active');
    currentPage = 1;
    renderList();
});

topicFiltersEl.addEventListener('click', (e) => {
    const btn = e.target.closest('.pill');
    if (!btn) return;
    activeTopicFilter = btn.dataset.topic;
    [...topicFiltersEl.children].forEach(c => c.classList.remove('pill--active'));
    btn.classList.add('pill--active');
    currentPage = 1;
    renderList();
});

backLink.addEventListener('click', () => {
    location.hash = '#/';
});

window.addEventListener('hashchange', router);

function parsePublished(dateStr) {
    const time = dateStr ? new Date(dateStr).getTime() : NaN;
    return Number.isNaN(time) ? -Infinity : time;
}

fetch('data/episodes.json')
    .then(res => res.json())
    .then(data => {
        episodes = (data.episodes || []).sort(
            (a, b) => parsePublished(b.published) - parsePublished(a.published)
        );
        router();
    })
    .catch(() => {
        episodeListEl.innerHTML = '<p class="empty-state">Could not load episodes. Run scripts/build_episodes_json.py first.</p>';
    });
