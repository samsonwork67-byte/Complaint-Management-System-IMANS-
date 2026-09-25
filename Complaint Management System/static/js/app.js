/**
 * app.js — General Interactive Script for the IGD Portal
 * Handles: Header scroll effects, mobile menu, smooth scrolling,
 * IntersectionObserver for reveal & counter animations, toast notifications,
 * contact form submission, and modals.
 */
(function () {
  'use strict';

  // ==========================================
  // HEADER SCROLL EFFECT
  // ==========================================
  const header = document.getElementById('header');
  if (header) {
    window.addEventListener('scroll', function () {
      header.classList.toggle('scrolled', window.scrollY > 60);
    });
  }

  // ==========================================
  // MOBILE HAMBURGER MENU
  // ==========================================
  const menuToggle = document.getElementById('menuToggle');
  const navMenu = document.getElementById('navMenu');

  if (menuToggle && navMenu) {
    menuToggle.addEventListener('click', function () {
      menuToggle.classList.toggle('active');
      navMenu.classList.toggle('active');
    });

    // Close menu on nav-link click (mobile)
    navMenu.querySelectorAll('.nav-link').forEach(function (link) {
      link.addEventListener('click', function () {
        menuToggle.classList.remove('active');
        navMenu.classList.remove('active');
      });
    });
  }

  // ==========================================
  // ACTIVE NAV HIGHLIGHT (Index Page Only)
  // ==========================================
  const sections = document.querySelectorAll('section[id]');
  const navLinks = document.querySelectorAll('.nav-link');

  if (sections.length > 0 && navLinks.length > 0) {
    function updateActiveNav() {
      let current = '';
      sections.forEach(function (section) {
        const sectionTop = section.offsetTop - 120;
        if (window.scrollY >= sectionTop) {
          current = section.getAttribute('id');
        }
      });
      navLinks.forEach(function (link) {
        link.classList.remove('active');
        const href = link.getAttribute('href');
        if (href && href.includes('#' + current)) {
          link.classList.add('active');
        }
      });
    }
    window.addEventListener('scroll', updateActiveNav);
  }

  // ==========================================
  // INTERSECTION OBSERVER: REVEAL ANIMATIONS
  // ==========================================
  const revealElements = document.querySelectorAll('.reveal');

  if (revealElements.length > 0) {
    const revealObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('active');
          revealObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -50px 0px' });

    revealElements.forEach(function (el) {
      revealObserver.observe(el);
    });
  }

  // ==========================================
  // ANIMATED STAT COUNTERS
  // ==========================================
  const statNumbers = document.querySelectorAll('.stat-number[data-target]');
  let countersAnimated = false;

  function animateCounters() {
    if (countersAnimated) return;
    countersAnimated = true;

    statNumbers.forEach(function (el) {
      const target = parseInt(el.getAttribute('data-target'), 10);
      const duration = 2000; // ms
      const steps = 60;
      const increment = target / steps;
      let count = 0;
      let step = 0;

      const timer = setInterval(function () {
        step++;
        count = Math.min(Math.round(increment * step), target);
        el.textContent = count;
        if (step >= steps) {
          clearInterval(timer);
          el.textContent = target;
        }
      }, duration / steps);
    });
  }

  fetch('/api/complaint-stats')
    .then(res => res.json())
    .then(data => {

      const statNumbers = document.querySelectorAll('.stat-number');

      const values = [
        data.received,
        data.resolved,
        data.ongoing,
        data.no_further_action
      ];

      statNumbers.forEach((el, index) => {
        el.setAttribute('data-target', values[index]);
        el.textContent = 0; // reset before animation
      });

      // now trigger your existing animation manually
      animateCounters();
    })
    .catch(err => {
      console.error('Failed to load stats:', err);
    });

  // Listen for cross-tab stats updates (e.g., admin changed a complaint status)
  window.addEventListener('storage', (e) => {
    if (e.key === 'statsUpdated') {
      // refetch stats and update counters without full reload
      fetch('/api/complaint-stats')
        .then(res => res.json())
        .then(data => {
          const statNumbers = document.querySelectorAll('.stat-number');
          const values = [data.received, data.resolved, data.ongoing, data.no_further_action];
          statNumbers.forEach((el, index) => {
            el.setAttribute('data-target', values[index]);
            el.textContent = values[index];
          });
        })
        .catch(err => console.error('Failed to refresh stats after update:', err));
    }
  });

  // ==========================================
  // TOAST NOTIFICATIONS
  // ==========================================
  window.showToast = function (message, type) {
    type = type || 'info';
    const container = document.getElementById('toastContainer');
    if (!container) return;

    var iconSvg = '';
    if (type === 'success') {
      iconSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
    } else if (type === 'info') {
      iconSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="#0d9488" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>';
    } else if (type === 'error') {
      iconSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>';
    }

    var toast = document.createElement('div');
    toast.className = 'toast' + (type === 'success' ? ' toast-success' : '');
    toast.innerHTML =
      '<span class="toast-icon">' + iconSvg + '</span>' +
      '<span class="toast-message">' + message + '</span>';

    container.appendChild(toast);

    // Trigger show animation
    setTimeout(function () {
      toast.classList.add('show');
    }, 10);

    // Auto-remove after 3.5s
    setTimeout(function () {
      toast.classList.remove('show');
      setTimeout(function () {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 3500);
  };

  // ==========================================
  // MODAL OPEN / CLOSE
  // ==========================================
  window.openModal = function (id) {
    var modal = document.getElementById(id);
    if (modal) {
      modal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }
  };

  window.closeModal = function (id) {
    var modal = document.getElementById(id);
    if (modal) {
      modal.classList.remove('active');
      document.body.style.overflow = '';
    }
  };

  // Close modal when clicking on overlay background
  document.querySelectorAll('.modal-overlay').forEach(function (overlay) {
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) {
        overlay.classList.remove('active');
        document.body.style.overflow = '';
      }
    });
  });

})();

document.addEventListener('DOMContentLoaded', () => {

  // ===== Stagger row animations =====
  const rows = document.querySelectorAll('.complaint-row');
  rows.forEach((row, i) => {
    row.style.animationDelay = `${0.25 + i * 0.04}s`;
  });

  // ===== Search =====
  const searchInput = document.getElementById('searchInput');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      filterTable();
      updateCount();
    });
  }

  // ===== Filter Tabs =====
  const filterTabs = document.querySelectorAll('.filter-tab');
  filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      filterTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      filterTable();
      updateCount();
    });
  });

  function getActiveFilter() {
    const active = document.querySelector('.filter-tab.active');
    return active ? active.dataset.filter : 'all';
  }

  function filterTable() {
    const query = searchInput ? searchInput.value.toLowerCase().trim() : '';
    const filter = getActiveFilter();

    rows.forEach(row => {
      const status = row.dataset.status;
      const text = row.textContent.toLowerCase();

      const matchesSearch = !query || text.includes(query);
      const matchesFilter = filter === 'all' || status === filter;

      row.classList.toggle('hidden', !(matchesSearch && matchesFilter));
    });
  }

  function updateCount() {
    const visible = document.querySelectorAll('.complaint-row:not(.hidden)');
    const countEl = document.getElementById('resultsCount');
    if (countEl) {
      const n = visible.length;
      countEl.textContent = `${n} complaint${n !== 1 ? 's' : ''}`;
    }
  }

  // ===== Sync Sheets Button =====
  const syncBtn = document.getElementById('syncBtn');
  if (syncBtn) {
    syncBtn.addEventListener('click', () => {
      syncBtn.classList.add('spinning');
      syncBtn.disabled = true;
      syncBtn.querySelector('span').textContent = 'Syncing...';

      function getCsrfToken() {
          var inp = document.querySelector('input[name="csrf_token"]');
          return inp ? inp.value : '';
      }

      fetch('/api/refresh', { method: 'POST', headers: { 'X-CSRF-Token': getCsrfToken() } })
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            setTimeout(() => {
              window.location.reload();
            }, 1000);
          } else {
            alert('Sync failed: ' + data.message);
            syncBtn.classList.remove('spinning');
            syncBtn.disabled = false;
            syncBtn.querySelector('span').textContent = 'Sync Sheets';
          }
        })
        .catch(err => {
          console.error('Error syncing:', err);
          alert('An error occurred while syncing.');
          syncBtn.classList.remove('spinning');
          syncBtn.disabled = false;
          syncBtn.querySelector('span').textContent = 'Sync Sheets';
        });
    });
  }

  // ===== Retry Action Buttons =====
  const retryButtons = document.querySelectorAll('.retry-action-btn');
  retryButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();

      const complaintId = btn.dataset.id;
      const originalText = btn.innerHTML;
      btn.disabled = true;
      btn.textContent = 'Queuing...';

      fetch(`/api/retry/${complaintId}`, { method: 'POST', headers: { 'X-CSRF-Token': getCsrfToken() } })
        .then(response => response.json())
        .then(data => {
          if (data.success) {
            btn.textContent = 'Queued!';
            setTimeout(() => {
              window.location.href = '/';
            }, 1000);
          } else {
            alert('Retry failed: ' + data.message);
            btn.innerHTML = originalText;
            btn.disabled = false;
          }
        })
        .catch(err => {
          console.error('Error retrying:', err);
          alert('An error occurred during retry.');
          btn.innerHTML = originalText;
          btn.disabled = false;
        });
    });
  });

  // ===== Sidebar Toggle (Mobile) =====
  const menuToggle = document.getElementById('menuToggle');
  const sidebar = document.getElementById('sidebar');
  if (menuToggle && sidebar) {
    menuToggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });

    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', (e) => {
      if (window.innerWidth <= 768 &&
        sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) &&
        !menuToggle.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    });
  }
});

