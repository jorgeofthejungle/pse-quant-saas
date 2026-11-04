// ============================================================
// dashboard.js — Shared Vanilla JS Utilities
// PSE Quant SaaS — Dashboard
// ============================================================
// Charts are initialized per-page in their own <script> blocks.
// This file contains shared utilities used across all pages.
// ============================================================

// ── Auto-refresh activity feed (home page) ────────────────────

function startActivityRefresh(intervalMs) {
  const tbody = document.getElementById('activity-tbody');
  if (!tbody) return;

  setInterval(() => {
    fetch('/api/activity')
      .then(r => r.json())
      .then(items => {
        tbody.innerHTML = items.map(item => `
          <tr>
            <td class="text-mono">${item.timestamp}</td>
            <td><span class="badge badge-${item.category}">${item.category}</span></td>
            <td>${item.action}</td>
            <td class="text-muted">${item.detail || ''}</td>
            <td><span class="status-dot status-${item.status}"></span></td>
          </tr>
        `).join('') || '<tr><td colspan="5" class="text-muted text-center">No activity yet</td></tr>';
      })
      .catch(() => {});
  }, intervalMs || 30000);
}

// ── Flash messages auto-dismiss ────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss flash messages after 4 seconds
  document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity 0.5s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    }, 4000);
  });

  // Start activity auto-refresh on home page
  startActivityRefresh(30000);
});

// ── Copy to clipboard utility ──────────────────────────────────

function copyToClipboard(text) {
  navigator.clipboard.writeText(text)
    .then(() => showToastGlobal('Copied to clipboard', 'success'))
    .catch(() => showToastGlobal('Copy failed', 'error'));
}

function showToastGlobal(msg, type) {
  let t = document.getElementById('global-toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'global-toast';
    t.className = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = `toast toast-${type}`;
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 3000);
}

// ── Hamburger sidebar toggle (mobile) ─────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const hamburger = document.getElementById('hamburger');
  const sidebar   = document.getElementById('sidebar');
  const overlay   = document.getElementById('sidebar-overlay');
  if (!hamburger || !sidebar) return;

  function openSidebar() {
    sidebar.classList.add('open');
    overlay.classList.add('active');
    hamburger.innerHTML = '&times;';
  }
  function closeSidebar() {
    sidebar.classList.remove('open');
    overlay.classList.remove('active');
    hamburger.innerHTML = '&#9776;';
  }

  hamburger.addEventListener('click', () => {
    sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
  });
  overlay.addEventListener('click', closeSidebar);

  // Close sidebar on nav link click (mobile UX)
  sidebar.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', closeSidebar);
  });
});

// ── Confirm-before-submit utility ─────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', e => {
      if (!confirm(form.dataset.confirm)) {
        e.preventDefault();
      }
    });
  });
});
