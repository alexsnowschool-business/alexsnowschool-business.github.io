/* ============================================================
   Who Owns What — Application Script
   Handles: search autocomplete, profile rendering, fact cards
   ============================================================ */

(function () {
    'use strict';

    /* ── UTILS ──────────────────────────────────────────────── */

    function qs(selector, root) {
        return (root || document).querySelector(selector);
    }

    function qsa(selector, root) {
        return Array.from((root || document).querySelectorAll(selector));
    }

    function getParam(name) {
        return new URLSearchParams(window.location.search).get(name);
    }

    function profileUrl(id, type) {
        const page = type === 'company' ? 'company.html' : 'person.html';
        return `${page}?id=${encodeURIComponent(id)}`;
    }

    function entityTypeLabel(type) {
        return type === 'company' ? 'Company' : 'Person';
    }

    /* ── SEARCH ─────────────────────────────────────────────── */

    function buildSearchIndex() {
        return Object.entries(WOW_DATA.entities).map(([id, entity]) => ({
            id,
            type: entity.type,
            name: entity.name,
            sub: entity.type === 'company'
                ? (entity.ticker ? `${entity.ticker} · ${entity.sector}` : entity.sector)
                : entity.title
        }));
    }

    const searchIndex = buildSearchIndex();

    function matchEntities(query) {
        const q = query.trim().toLowerCase();
        if (!q) return [];
        return searchIndex.filter(e =>
            e.name.toLowerCase().includes(q) || e.id.includes(q)
        ).slice(0, 6);
    }

    function renderDropdown(matches, dropdown) {
        if (!matches.length) {
            dropdown.hidden = true;
            return;
        }
        dropdown.innerHTML = matches.map(m => `
            <a class="dropdown__item" href="${profileUrl(m.id, m.type)}">
                <span class="dropdown__tag">${entityTypeLabel(m.type)}</span>
                <span class="dropdown__name">${m.name}</span>
                <span class="dropdown__sub">${m.sub}</span>
            </a>
        `).join('');
        dropdown.hidden = false;
    }

    function attachSearch(inputEl, dropdownEl) {
        if (!inputEl || !dropdownEl) return;

        inputEl.addEventListener('input', () => {
            const matches = matchEntities(inputEl.value);
            renderDropdown(matches, dropdownEl);
        });

        inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const matches = matchEntities(inputEl.value);
                if (matches.length) {
                    window.location.href = profileUrl(matches[0].id, matches[0].type);
                }
            }
            if (e.key === 'Escape') {
                dropdownEl.hidden = true;
            }
        });

        document.addEventListener('click', (e) => {
            if (!inputEl.contains(e.target) && !dropdownEl.contains(e.target)) {
                dropdownEl.hidden = true;
            }
        });
    }

    /* ── LANDING PAGE ───────────────────────────────────────── */

    function initLanding() {
        // Hero search
        const heroWrap = qs('.search__wrap');
        if (heroWrap) {
            const input = qs('.search__input', heroWrap);
            const btn = qs('.search__btn', heroWrap);
            const dropdown = qs('.search__dropdown', heroWrap);

            attachSearch(input, dropdown);

            if (btn) {
                btn.addEventListener('click', () => {
                    const matches = matchEntities(input.value);
                    if (matches.length) {
                        window.location.href = profileUrl(matches[0].id, matches[0].type);
                    }
                });
            }
        }

        // Nav search
        const navWrap = qs('.nav__search-wrap');
        if (navWrap) {
            const navInput = qs('.nav__search', navWrap);
            const navDropdown = qs('.nav__dropdown', navWrap);
            attachSearch(navInput, navDropdown);
        }

        // Fact cards
        const track = qs('.facts__track');
        if (track && WOW_DATA.factCards) {
            track.innerHTML = WOW_DATA.factCards.map(card => `
                <div class="fact-card">
                    <div class="fact-card__category">${card.category}</div>
                    <div class="fact-card__headline">${card.headline}</div>
                    <div class="fact-card__detail">${card.detail}</div>
                    <div class="fact-card__source">
                        Source: <a href="${card.url}" target="_blank" rel="noopener">${card.source}</a>
                    </div>
                </div>
            `).join('');
        }

        // Featured people
        const peopleGrid = qs('#featured-people');
        if (peopleGrid) {
            const people = Object.entries(WOW_DATA.entities)
                .filter(([, e]) => e.type === 'person');
            peopleGrid.innerHTML = people.map(([id, e]) => {
                const rankLabel = e.netWorthRank ? ` · ${e.netWorthRank}` : '';
                return `
                <a class="entity-card" href="${profileUrl(id, 'person')}">
                    <div class="entity-card__tag">Individual</div>
                    <div class="entity-card__name">${e.name}</div>
                    <div class="entity-card__sub">${e.title}</div>
                    <div class="entity-card__stat">
                        <strong>${e.netWorth}</strong>
                        <span>Net Worth${rankLabel}</span>
                    </div>
                </a>
            `}).join('');
        }

        // Featured companies — only show entities with lobbying data, sorted by spend
        const companyGrid = qs('#featured-companies');
        if (companyGrid) {
            const parseLobbyingAmount = (lobbying) => {
                if (!lobbying || !lobbying.length) return -1;
                const latest = lobbying.reduce((a, b) => a.year >= b.year ? a : b);
                const m = latest.amount.replace(/[€,]/g, '').match(/([\d.]+)/);
                return m ? parseFloat(m[1]) : 0;
            };

            const companies = Object.entries(WOW_DATA.entities)
                .filter(([, e]) => e.type === 'company' && e.lobbying && e.lobbying.length > 0)
                .sort((a, b) => parseLobbyingAmount(b[1].lobbying) - parseLobbyingAmount(a[1].lobbying))
                .slice(0, 12);

            companyGrid.innerHTML = companies.map(([id, e]) => {
                const latest = e.lobbying.reduce((a, b) => a.year >= b.year ? a : b);
                const sub = [e.sector, e.headquarters].filter(Boolean).join(' · ');
                return `
                <a class="entity-card" href="${profileUrl(id, 'company')}">
                    <div class="entity-card__tag">Company · ${e.ticker || e.sector}</div>
                    <div class="entity-card__name">${e.name}</div>
                    <div class="entity-card__sub">${sub}</div>
                    <div class="entity-card__stat">
                        <strong>${latest.amount}</strong>
                        <span>Lobbying Budget · ${latest.year}</span>
                    </div>
                </a>
            `}).join('');
        }

        // Country card — update entity count from live data
        const germanyCount = qs('.entity-card--germany-count');
        if (germanyCount) {
            const total = Object.values(WOW_DATA.entities)
                .filter(e => e.country === 'germany').length;
            germanyCount.textContent = `${total} Entities`;
        }
    }

    /* ── SECTION VISIBILITY ─────────────────────────────────── */

    function hideSection(id) {
        const el = qs('#' + id);
        if (el) el.hidden = true;
    }

    function hasData(value) {
        if (value === null || value === undefined) return false;
        if (Array.isArray(value)) return value.length > 0;
        if (typeof value === 'object') return Object.keys(value).length > 0;
        return Boolean(value);
    }

    /* ── COMPANY PROFILE ────────────────────────────────────── */

    function initCompanyProfile() {
        const id = getParam('id');
        const entity = id && WOW_DATA.entities[id];

        if (!entity || entity.type !== 'company') {
            renderNotFound('company');
            return;
        }

        document.title = `${entity.name} — Who Owns What`;

        qs('#company-ticker').textContent = entity.ticker || '';
        qs('#company-sector').textContent = entity.sector;
        qs('#company-name').textContent = entity.name;
        qs('#company-summary').textContent = entity.summary;
        qs('#stat-market-cap').textContent = entity.marketCap;
        qs('#stat-employees').textContent = entity.employees;
        qs('#stat-hq').textContent = entity.headquarters;
        qs('#stat-founded').textContent = entity.founded;

        // I. Shareholders
        if (hasData(entity.shareholders)) {
            const shareholdersTable = qs('#shareholders-body');
            if (shareholdersTable) {
                shareholdersTable.innerHTML = entity.shareholders.map(s => `
                    <tr>
                        <td>${s.name}</td>
                        <td class="wow-table__stake">${s.stake}</td>
                        <td>${s.type}</td>
                        <td><a class="wow-table__source-link" href="${s.url}" target="_blank" rel="noopener">${s.source}</a></td>
                    </tr>
                `).join('');
            }
        } else {
            hideSection('section-shareholders');
        }

        // II. Compensation
        const comp = entity.compensation;
        const compHasData = comp && (comp.ceeName || comp.ceoTotal || comp.medianWorker);
        if (compHasData) {
            qs('#comp-ceo-name').textContent = comp.ceeName || '';
            qs('#comp-ceo-title').textContent = comp.ceoTitle || '';
            qs('#comp-ceo-total').textContent = comp.ceoTotal || '';
            qs('#comp-ceo-salary').textContent = comp.ceoSalary || '';
            qs('#comp-ceo-equity').textContent = comp.ceoEquity || '';
            qs('#comp-worker').textContent = comp.medianWorker || '';
            qs('#comp-ratio').textContent = comp.ceoWorkerRatio || '';
            const compSourceEl = qs('#comp-source');
            if (compSourceEl && comp.url) {
                compSourceEl.innerHTML = `Source: <a href="${comp.url}" target="_blank" rel="noopener">${comp.source}</a>`;
            }
        } else {
            hideSection('section-compensation');
        }

        // III. Lobbying
        if (hasData(entity.lobbying)) {
            const lobbyingWrap = qs('#lobbying-rows');
            if (lobbyingWrap) {
                const maxAmt = Math.max(...entity.lobbying.map(l => parseFloat(l.amount.replace(/[$M]/g, ''))));
                lobbyingWrap.innerHTML = entity.lobbying.map(l => {
                    const pct = (parseFloat(l.amount.replace(/[$M]/g, '')) / maxAmt * 100).toFixed(0);
                    return `
                        <div class="lobbying-row">
                            <div class="lobbying-row__year">${l.year}</div>
                            <div class="lobbying-row__bar-wrap">
                                <div class="lobbying-row__bar" style="width:${pct}%"></div>
                            </div>
                            <div class="lobbying-row__amount">${l.amount}</div>
                            <a class="lobbying-row__source" href="${l.url}" target="_blank" rel="noopener">${l.source}</a>
                        </div>
                    `;
                }).join('');
            }
        } else {
            hideSection('section-lobbying');
        }

        // IV. Political Spending
        const pol = entity.politicalSpending;
        const polHasData = pol && (pol.pac || pol.total2022 || pol.note);
        if (polHasData) {
            const polBlock = qs('#political-spending');
            if (polBlock) {
                polBlock.innerHTML = `
                    <div class="pol-block">
                        <div class="pol-block__pac">PAC: <strong>${pol.pac}</strong></div>
                        ${pol.total2022 ? `<div class="pol-block__pac">2022 Cycle Total: <strong>${pol.total2022}</strong></div>` : ''}
                        <div class="pol-block__note">${pol.note}</div>
                        <a class="pol-block__source" href="${pol.url}" target="_blank" rel="noopener">Source: ${pol.source} →</a>
                    </div>
                `;
            }
        } else {
            hideSection('section-political');
        }

        // V. Fines & Settlements
        if (hasData(entity.fines)) {
            const finesList = qs('#fines-list');
            if (finesList) {
                finesList.innerHTML = entity.fines.map(f => `
                    <li class="item-list__entry">
                        <span class="item-list__year">${f.year}</span>
                        <span class="item-list__body">
                            ${f.description}
                            <a class="item-list__source" href="${f.url}" target="_blank" rel="noopener">${f.source} →</a>
                        </span>
                    </li>
                `).join('');
            }
        } else {
            hideSection('section-fines');
        }

        // VI. Labour
        if (hasData(entity.labor)) {
            const laborList = qs('#labor-list');
            if (laborList) {
                laborList.innerHTML = entity.labor.map(l => `
                    <li class="plain-list__entry">
                        ${l.description}
                        <a class="item-list__source" href="${l.url}" target="_blank" rel="noopener">${l.source} →</a>
                    </li>
                `).join('');
            }
        } else {
            hideSection('section-labor');
        }

        // VII. Competitors
        if (hasData(entity.competitors)) {
            const competitorWrap = qs('#competitors-wrap');
            if (competitorWrap) {
                competitorWrap.innerHTML = `
                    <div class="competitor-pills">
                        ${entity.competitors.map(c => `<span class="competitor-pill">${c}</span>`).join('')}
                    </div>
                `;
            }
        } else {
            hideSection('section-competitors');
        }

        // Sources
        const sourcesList = qs('#sources-list');
        if (sourcesList && entity.sources) {
            sourcesList.innerHTML = entity.sources.map(s => `
                <li><a href="${s.url}" target="_blank" rel="noopener">${s.title}</a></li>
            `).join('');
        }
    }

    /* ── PERSON PROFILE ─────────────────────────────────────── */

    function initPersonProfile() {
        const id = getParam('id');
        const entity = id && WOW_DATA.entities[id];

        if (!entity || entity.type !== 'person') {
            renderNotFound('person');
            return;
        }

        document.title = `${entity.name} — Who Owns What`;

        qs('#person-name').textContent = entity.name;
        qs('#person-title').textContent = entity.title;
        qs('#person-net-worth').textContent = entity.netWorth;
        qs('#person-nw-source').innerHTML = `${entity.netWorthRank} · <a href="${entity.netWorthUrl}" target="_blank" rel="noopener">${entity.netWorthSource}</a>`;
        qs('#person-nationality').textContent = entity.nationality;
        qs('#person-born').textContent = entity.born;

        // I. Summary
        if (entity.summary) {
            const summaryEl = qs('#person-summary');
            if (summaryEl) summaryEl.textContent = entity.summary;
        } else {
            hideSection('section-summary');
        }

        // II. Major Assets
        if (hasData(entity.assets)) {
            const assetList = qs('#assets-list');
            if (assetList) {
                assetList.innerHTML = entity.assets.map(a => `
                    <div class="asset-card">
                        <div class="asset-card__name">${a.name}</div>
                        <div class="asset-card__desc">${a.description}</div>
                        <a class="asset-card__source" href="${a.url}" target="_blank" rel="noopener">${a.source} →</a>
                    </div>
                `).join('');
            }
        } else {
            hideSection('section-assets');
        }

        // III. Board Memberships
        if (hasData(entity.boardMemberships)) {
            const boardList = qs('#board-list');
            if (boardList) {
                boardList.innerHTML = entity.boardMemberships.map(b => `
                    <li class="plain-list__entry">
                        <strong>${b.org}</strong> — ${b.role}
                    </li>
                `).join('');
            }
        } else {
            hideSection('section-board');
        }

        // IV. Foundations
        if (hasData(entity.foundations)) {
            const foundationList = qs('#foundations-list');
            if (foundationList) {
                foundationList.innerHTML = entity.foundations.map(f => `
                    <li class="plain-list__entry">
                        <strong>${f.name}</strong> — ${f.description}
                        ${f.url ? `<a class="item-list__source" href="${f.url}" target="_blank" rel="noopener">→</a>` : ''}
                    </li>
                `).join('');
            }
        } else {
            hideSection('section-foundations');
        }

        // V. Political Spending
        const polPerson = entity.politicalSpending;
        const polPersonHasData = polPerson && (polPerson.total2024 || polPerson.total2022 || polPerson.total2020 ||
            (polPerson.pac && polPerson.pac !== 'None' && polPerson.pac !== 'None disclosed'));
        if (polPersonHasData) {
            const polBlock = qs('#political-spending');
            if (polBlock) {
                polBlock.innerHTML = `
                    <div class="pol-block">
                        ${polPerson.pac && polPerson.pac !== 'None' && polPerson.pac !== 'None disclosed' ? `<div class="pol-block__pac">PAC: <strong>${polPerson.pac}</strong></div>` : ''}
                        ${polPerson.total2024 ? `<div class="pol-block__pac">2024 Total: <strong>${polPerson.total2024}</strong></div>` : ''}
                        ${polPerson.total2022 ? `<div class="pol-block__pac">2022 Total: <strong>${polPerson.total2022}</strong></div>` : ''}
                        ${polPerson.total2020 ? `<div class="pol-block__pac">2020 Total: <strong>${polPerson.total2020}</strong></div>` : ''}
                        <div class="pol-block__note">${polPerson.summary}</div>
                        <a class="pol-block__source" href="${polPerson.url}" target="_blank" rel="noopener">Source: ${polPerson.source} →</a>
                    </div>
                `;
            }
        } else {
            hideSection('section-political');
        }

        // VI. Timeline
        if (hasData(entity.timeline)) {
            const timeline = qs('#timeline');
            if (timeline) {
                timeline.innerHTML = entity.timeline.map(t => `
                    <div class="timeline__entry">
                        <div class="timeline__year">${t.year}</div>
                        <div class="timeline__event">${t.event}</div>
                    </div>
                `).join('');
            }
        } else {
            hideSection('section-timeline');
        }

        // Sources
        const sourcesList = qs('#sources-list');
        if (sourcesList && entity.sources) {
            sourcesList.innerHTML = entity.sources.map(s => `
                <li><a href="${s.url}" target="_blank" rel="noopener">${s.title}</a></li>
            `).join('');
        }
    }

    /* ── NAV SEARCH (all pages) ─────────────────────────────── */

    function initNavSearch() {
        const navInput = qs('.nav__search');
        const navDropdown = qs('.nav__dropdown');
        if (navInput && navDropdown) {
            attachSearch(navInput, navDropdown);
        }
    }

    /* ── NOT FOUND ──────────────────────────────────────────── */

    function renderNotFound(type) {
        const profile = qs('.profile');
        if (profile) {
            profile.innerHTML = `
                <div class="not-found">
                    <h1>Not Found</h1>
                    <p>We don't have a profile for that ${type} yet. Our database is expanding — check back soon.</p>
                    <a href="./index.html">← Back to Search</a>
                </div>
            `;
        }
    }

    /* ── INIT ───────────────────────────────────────────────── */

    document.addEventListener('DOMContentLoaded', () => {
        const page = document.body.dataset.page;

        initNavSearch();

        if (page === 'landing') initLanding();
        else if (page === 'company') initCompanyProfile();
        else if (page === 'person') initPersonProfile();
    });

}());
