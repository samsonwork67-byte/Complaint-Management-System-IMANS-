document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('themeToggle');
    const THEME_KEY = 'admin-theme';
    if (window.auditLogger) {
        window.auditLogger.trackPageView(document.title || window.location.pathname);
        window.auditLogger.startHeartbeat();
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);

        if (!themeToggle) return;

        const darkLabel = themeToggle.querySelector('.theme-toggle-dark-label');
        const lightLabel = themeToggle.querySelector('.theme-toggle-light-label');

        if (darkLabel) darkLabel.style.display = theme === 'dark' ? 'inline' : 'none';
        if (lightLabel) lightLabel.style.display = theme === 'dark' ? 'none' : 'inline';

        themeToggle.setAttribute('aria-pressed', theme === 'dark');
    }

    function initThemeUI() {
        const storedTheme = localStorage.getItem(THEME_KEY) || 'light';

        const isPublicPage =
            window.location.pathname === '/' ||
            window.location.pathname === '/complaint';

        const theme = isPublicPage ? 'light' : storedTheme;

        document.documentElement.setAttribute('data-theme', theme);

        // keep storage in sync so admin pages don’t drift
        localStorage.setItem(THEME_KEY, theme);
    }

    initThemeUI();

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const current = localStorage.getItem(THEME_KEY) || 'light';
            const next = current === 'dark' ? 'light' : 'dark';

            localStorage.setItem(THEME_KEY, next);
            applyTheme(next);
        });
    }
});

(function () {
    fetch('/api/log-view', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page: window.location.pathname })
    }).catch(() => { }); // fire-and-forget, never blocks page load
})();

document.addEventListener('DOMContentLoaded', () => {
    const openBtn = document.getElementById('openManualComplaintBtn');
    const closeBtn = document.getElementById('closeManualComplaintBtn');
    const overlay = document.getElementById('manualComplaintOverlay');
    const form = document.getElementById('manualComplaintForm');
    const submitBtn = document.getElementById('manualSubmitBtn');

    if (!openBtn || !overlay || !form) return;

    openBtn.addEventListener('click', () => {
        overlay.style.display = 'flex';
    });

    closeBtn.addEventListener('click', () => {
        overlay.style.display = 'none';
        form.reset();
    });

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.style.display = 'none';
            form.reset();
        }
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving...';

        const formData = new FormData(form);

        try {
            const res = await fetch('/api/manual-complaint', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            if (data.success) {
                if (typeof showToast === 'function') {
                    showToast(`Complaint saved — Reference ID: ${data.complaint_ref_id}`, 'success');
                } else {
                    alert(`Complaint saved successfully!\nReference ID: ${data.complaint_ref_id}\nTracking ID: ${data.tracking_id}`);
                }
                form.reset();
                overlay.style.display = 'none';
                setTimeout(() => window.location.reload(), 1000);
            } else {
                if (typeof showToast === 'function') {
                    showToast(data.message || 'Failed to save complaint', 'error');
                } else {
                    alert(data.message || 'Failed to save complaint');
                }
            }
        } catch (err) {
            console.error('Manual complaint submission error:', err);
            if (typeof showToast === 'function') {
                showToast('An error occurred while saving.', 'error');
            } else {
                alert('An error occurred while saving.');
            }
        }

        submitBtn.disabled = false;
        submitBtn.textContent = 'Save Complaint';
    });
});
