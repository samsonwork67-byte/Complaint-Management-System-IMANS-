document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('themeToggle');
    const THEME_KEY = 'admin-theme';

    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);

        localStorage.setItem(THEME_KEY, theme);

        if (!themeToggle) return;

        const darkLabel = themeToggle.querySelector('.theme-toggle-dark-label');
        const lightLabel = themeToggle.querySelector('.theme-toggle-light-label');

        if (darkLabel) darkLabel.style.display = theme === 'dark' ? 'inline' : 'none';
        if (lightLabel) lightLabel.style.display = theme === 'dark' ? 'none' : 'inline';

        themeToggle.setAttribute('aria-pressed', theme === 'dark');
    }

    // load saved theme
    const savedTheme = localStorage.getItem(THEME_KEY) || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);

    function syncToggleUI() {
        const theme = localStorage.getItem(THEME_KEY) || 'light';

        if (!themeToggle) return;

        const darkLabel = themeToggle.querySelector('.theme-toggle-dark-label');
        const lightLabel = themeToggle.querySelector('.theme-toggle-light-label');

        if (darkLabel) darkLabel.style.display = theme === 'dark' ? 'inline' : 'none';
        if (lightLabel) lightLabel.style.display = theme === 'dark' ? 'none' : 'inline';

        themeToggle.setAttribute('aria-pressed', theme === 'dark');
    }

    syncToggleUI();

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const current = localStorage.getItem(THEME_KEY) || 'light';
            const next = current === 'dark' ? 'light' : 'dark';

            applyTheme(next);
        });
    }
});

document.getElementById('logoutLink')?.addEventListener('click', () => {
    auditLogger.resetSessionId();
});