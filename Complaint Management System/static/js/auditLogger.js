/**
 * auditLogger.js — Lightweight admin activity tracker
 * Batches logs client-side, flushes periodically, never breaks the UI.
 */
(function (window) {
    'use strict';

    const ENDPOINT = '/api/audit-log';
    const SESSION_KEY = 'imans_session_id';
    const FLUSH_INTERVAL_MS = 8000;       // batch flush every 8s
    const HEARTBEAT_INTERVAL_MS = 180000; // 3 min heartbeat
    const MAX_QUEUE = 20;                 // safety cap
    const DEBOUNCE_MS = 400;

    let queue = [];
    let flushTimer = null;
    let debounceMap = new Map();

    function getSessionId() {
        let sid = localStorage.getItem(SESSION_KEY);
        if (!sid) {
            sid = (crypto.randomUUID ? crypto.randomUUID() : 'sid-' + Date.now() + '-' + Math.random().toString(36).slice(2));
            localStorage.setItem(SESSION_KEY, sid);
        }
        return sid;
    }

    function resetSessionId() {
        // call on logout so a fresh session_id is used next login
        localStorage.removeItem(SESSION_KEY);
    }

    function enqueue(action_type, target, details) {
        if (queue.length >= MAX_QUEUE) queue.shift(); // drop oldest if flooded
        queue.push({
            action_type,
            target: target || null,
            details: details || {},
            session_id: getSessionId(),
            client_time: new Date().toISOString()
        });
        scheduleFlush();
    }

    function scheduleFlush() {
        if (flushTimer) return;
        flushTimer = setTimeout(flush, FLUSH_INTERVAL_MS);
    }

    function flush(useBeacon) {
        flushTimer = null;
        if (!queue.length) return;
        const batch = queue.splice(0, queue.length);

        try {
            const body = JSON.stringify({ logs: batch });
            if (useBeacon && navigator.sendBeacon) {
                navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'application/json' }));
                return;
            }
            fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body,
                keepalive: true
            }).catch(() => { /* swallow — logging must never break UI */ });
        } catch (e) {
            // swallow silently
        }
    }

    function log(action_type, target, details) {
        try {
            enqueue(action_type, target, details);
        } catch (e) {
            // never throw from logger
        }
    }

    function logDebounced(key, action_type, target, details, wait) {
        clearTimeout(debounceMap.get(key));
        const t = setTimeout(() => log(action_type, target, details), wait || DEBOUNCE_MS);
        debounceMap.set(key, t);
    }

    function trackPageView(pageName, details) {
        log('VIEW', pageName || window.location.pathname, details);
    }

    function trackClick(action_type, target, details) {
        // clicks are debounced per target to avoid double-fire spam
        logDebounced('click:' + target, action_type, target, details, 250);
    }

    function startHeartbeat() {
        setInterval(() => log('HEARTBEAT', window.location.pathname, {}), HEARTBEAT_INTERVAL_MS);
    }

    // Flush on tab close/hide so nothing is lost
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') flush(true);
    });
    window.addEventListener('pagehide', () => flush(true));

    window.auditLogger = {
        log,
        trackPageView,
        trackClick,
        startHeartbeat,
        resetSessionId,
        getSessionId,
        flush
    };
})(window); 

//AUDIT DASHBOARD JS
(function () {
    'use strict';

    let currentPage = 1;
    const pageSize = 25;
    let totalRows = 0;

    const ACTION_COLORS = {
        LOGIN: '#22c55e',
        LOGOUT: '#94a3b8',
        UPDATE: '#f59e0b',
        DELETE: '#ef4444',
        VIEW: '#0d9488',
        CREATE: '#0ea5e9',
        HEARTBEAT: '#cbd5e1'
    };

    function relativeTime(iso) {
        const diff = (Date.now() - new Date(iso).getTime()) / 1000;
        if (diff < 60) return Math.floor(diff) + 's ago';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        return Math.floor(diff / 86400) + 'd ago';
    }

    function actionBadge(action) {
        const color = ACTION_COLORS[action] || '#94a3b8';
        return `<span style="display:inline-flex;align-items:center;gap:6px;font-weight:600;font-size:0.78rem;color:${color};">
            <span style="width:8px;height:8px;border-radius:50%;background:${color};"></span>${action}
        </span>`;
    }

    function getElementValue(id) {
        return document.getElementById(id)?.value || '';
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function renderDetailValue(value) {
        if (value === undefined || value === null || value === '') {
            return '<span class="details-empty">—</span>';
        }

        if (Array.isArray(value)) {
            if (!value.length) {
                return '<span class="details-empty">No items.</span>';
            }
            return `
                <ul class="details-list details-list-nested">
                    ${value.map(item => `<li>${renderDetailValue(item)}</li>`).join('')}
                </ul>
            `;
        }

        if (typeof value === 'object') {
            const entries = Object.entries(value).filter(([, entryValue]) => entryValue !== undefined && entryValue !== null && entryValue !== '');
            if (!entries.length) {
                return '<span class="details-empty">Empty object</span>';
            }
            return `
                <ul class="details-list details-list-nested">
                    ${entries.map(([entryKey, entryValue]) => `
                        <li>
                            <span class="details-key">${escapeHtml(entryKey)}</span>
                            <div class="details-value">${renderDetailValue(entryValue)}</div>
                        </li>
                    `).join('')}
                </ul>
            `;
        }

        if (value === true || value === false) {
            return escapeHtml(value ? 'Yes' : 'No');
        }

        return escapeHtml(String(value));
    }

    function formatDetails(details) {
        const data = details && typeof details === 'object' ? details : { value: details };
        const entries = Object.entries(data).filter(([, value]) => value !== undefined && value !== null && value !== '');

        if (!entries.length) {
            return '<div class="details-empty">No additional details.</div>';
        }

        return `
            <ul class="details-list">
                ${entries.map(([key, value]) => `
                    <li>
                        <span class="details-key">${escapeHtml(key)}</span>
                        <div class="details-value">${renderDetailValue(value)}</div>
                    </li>
                `).join('')}
            </ul>
        `;
    }

    async function loadSummary() {
        try {
            const res = await fetch('/api/audit-log/summary');
            const data = await res.json();
            if (!data.success) return;
            const kpiActiveAdmins = document.getElementById('kpiActiveAdmins');
            const kpiTotalActions = document.getElementById('kpiTotalActions');
            const kpiAvgSession = document.getElementById('kpiAvgSession');
            const kpiMostActive = document.getElementById('kpiMostActive');
            if (kpiActiveAdmins) kpiActiveAdmins.textContent = data.active_admins;
            if (kpiTotalActions) kpiTotalActions.textContent = data.total_actions_today;
            if (kpiAvgSession) kpiAvgSession.textContent = data.avg_session_minutes;
            if (kpiMostActive) kpiMostActive.textContent = data.most_active_admin || '—';
        } catch (e) { console.error(e); }
    }

    async function loadFeed() {
        try {
            const feed = document.getElementById('activityFeed');
            if (!feed) return;
            const res = await fetch('/api/audit-log/feed?limit=30');
            const data = await res.json();
            if (!data.success) return;
            feed.innerHTML = data.logs.map(log => `
                <div class="feed-item">
                    <div class="feed-item-top">
                        ${actionBadge(log.action_type)}
                        <span class="feed-time">${relativeTime(log.timestamp)}</span>
                    </div>
                    <div class="feed-item-body">
                        <strong>${log.admin_name}</strong>
                        ${log.target ? ' — ' + log.target : ''}
                    </div>
                </div>
            `).join('') || '<p class="empty-evidence">No activity yet.</p>';
        } catch (e) { console.error(e); }
    }

    async function loadSessions() {
        try {
            const list = document.getElementById('sessionsList');
            if (!list) return;
            const res = await fetch('/api/audit-log/sessions');
            const data = await res.json();
            if (!data.success) return;
            list.innerHTML = data.sessions.map(s => `
                <div class="session-item">
                    <div>
                        <strong>${s.admin_name}</strong>
                        <div class="session-meta">Login: ${new Date(s.login_at).toLocaleTimeString()}</div>
                    </div>
                    <div style="text-align:right;">
                        <span class="status-badge ${s.status === 'online' ? 'status-sent' : 'status-pending'}">${s.status}</span>
                        <div class="session-meta">${s.duration_minutes}m</div>
                    </div>
                </div>
            `).join('') || '<p class="empty-evidence">No sessions today.</p>';
        } catch (e) { console.error(e); }
    }

    async function loadAdminFilterOptions() {
        try {
            const sel = document.getElementById('filterAdmin');
            if (!sel) return;
            const res = await fetch('/api/audit-log/admins');
            const data = await res.json();
            if (!data.success) return;

            // Prevent duplicates
            sel.innerHTML = `<option value="">All Admins</option>`;

            data.admins.forEach(a => {
                const opt = document.createElement('option');
                opt.value = a.id;
                opt.textContent = a.username;
                sel.appendChild(opt);
            });

        } catch (e) {
            console.error(e);
        }
    }

    function buildQuery() {
        const params = new URLSearchParams();
        params.set('page', currentPage);
        params.set('page_size', pageSize);
        const action = getElementValue('filterAction');
        const admin = getElementValue('filterAdmin');
        const search = getElementValue('filterSearch').trim();
        const from = getElementValue('filterDateFrom');
        const to = getElementValue('filterDateTo');
        if (action) params.set('action_type', action);
        if (admin) params.set('admin_id', admin);
        if (search) params.set('search', search);
        if (from) params.set('date_from', from);
        if (to) params.set('date_to', to);
        return params.toString();
    }

    async function loadTable() {
        try {
            const tbody = document.getElementById('auditTableBody');
            if (!tbody) return;
            const res = await fetch('/api/audit-log/table?' + buildQuery());
            const data = await res.json();
            if (!data.success) return;
            totalRows = data.total;

            tbody.innerHTML = data.logs.map(log => `
                <tr>
                    <td>${new Date(log.timestamp).toLocaleString()}</td>
                    <td>${log.admin_name}</td>
                    <td>${actionBadge(log.action_type)}</td>
                    <td>${log.target || '—'}</td>
                    <td style="font-size:0.75rem; color:var(--text-muted);">${(log.session_id || '').slice(0, 8)}...</td>
                    <td>
                        <button class="btn-details-toggle" onclick="this.nextElementSibling.classList.toggle('open')" style="background:none;border:none;color:var(--accent);cursor:pointer;font-size:0.78rem;">View</button>
                        <div class="details-json">${formatDetails(log.details)}</div>
                    </td>
                </tr>
            `).join('') || '<tr><td colspan="6" style="text-align:center;padding:20px;">No logs found.</td></tr>';

            const pageInfo = document.getElementById('pageInfo');
            if (pageInfo) {
                pageInfo.textContent = `Page ${currentPage} of ${Math.max(1, Math.ceil(totalRows / pageSize))}`;
            }
        } catch (e) { console.error(e); }
    }

    function isAuditDashboard() {
        return !!(
            document.getElementById('auditTableBody') ||
            document.getElementById('activityFeed') ||
            document.getElementById('sessionsList') ||
            document.querySelector('.audit-filters')
        );
    }

    function refreshAll() {
        if (!isAuditDashboard()) return;
        loadSummary();
        loadFeed();
        loadSessions();
        loadTable();
    }

    document.addEventListener('DOMContentLoaded', () => {
        if (!isAuditDashboard()) return;

        loadAdminFilterOptions();
        setupAutoFilters();
        refreshAll();

        function setupAutoFilters() {
            const debounceMap = new Map();

            function debounce(key, fn, delay = 400) {
                clearTimeout(debounceMap.get(key));
                debounceMap.set(key, setTimeout(fn, delay));
            }

            function triggerReload() {
                currentPage = 1;
                loadTable();
            }

            // Select filters (instant)
            document.getElementById('filterAction')?.addEventListener('change', triggerReload);
            document.getElementById('filterAdmin')?.addEventListener('change', triggerReload);

            // Text search (debounced)
            document.getElementById('filterSearch')?.addEventListener('input', () => {
                debounce('search', triggerReload, 500);
            });

            // Date filters (instant but safe)
            document.getElementById('filterDateFrom')?.addEventListener('change', triggerReload);
            document.getElementById('filterDateTo')?.addEventListener('change', triggerReload);
        }

        document.getElementById('prevPageBtn')?.addEventListener('click', () => {
            if (currentPage > 1) { currentPage--; loadTable(); }
        });
        document.getElementById('nextPageBtn')?.addEventListener('click', () => {
            if (currentPage * pageSize < totalRows) { currentPage++; loadTable(); }
        });

        // Auto-refresh feed/sessions/KPIs every 12s (not the filtered table, to avoid disrupting user's filter view)
        setInterval(() => {
            loadSummary();
            loadFeed();
            loadSessions();
        }, 12000);
    });
})();

function initAuditFiltersUX() {
    const filters = document.querySelector('.audit-filters');
    if (!filters) return;

    const applyBtn = document.getElementById('applyFiltersBtn');
    const searchInput = document.getElementById('filterSearch');

    // Enter key triggers search
    filters.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            applyBtn?.click();
        }
    });

    // Auto apply on dropdown change (feels more “live”)
    const autoFields = filters.querySelectorAll('select');
    autoFields.forEach(el => {
        el.addEventListener('change', () => {
            applyBtn?.click();
        });
    });

    // Debounced search input
    let searchTimer;
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => {
                applyBtn?.click();
            }, 600);
        });
    }

    // Optional reset button support
    const resetBtn = document.getElementById('resetFiltersBtn');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            filters.querySelectorAll('input, select').forEach(el => {
                el.value = '';
            });
            applyBtn?.click();
        });
    }
}

function refreshAuditThemeUI() {
    const filters = document.querySelector('.audit-filters');
    if (!filters) return;

    // force repaint for smooth theme switch feel
    filters.style.transition = 'none';
    filters.offsetHeight; // trigger reflow
    filters.style.transition = '';
}

document.getElementById('themeToggle')?.addEventListener('click', () => {
    setTimeout(refreshAuditThemeUI, 50);
});