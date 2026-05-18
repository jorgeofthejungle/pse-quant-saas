/**
 * StockPilot PH Operator Dashboard
 * Client-side interactivity: real-time status polling, AJAX actions, table sorting/filtering.
 * @module dashboard
 */

(function () {
  'use strict';

  /**
   * Application configuration.
   * @type {Object}
   * @property {number} pollingInterval - Milliseconds between status polls.
   * @property {string} statusEndpoint - URL for pipeline status.
   * @property {string} logPrefix - Prefix for console logs.
   */
  const CONFIG = Object.freeze({
    pollingInterval: 5000,
    statusEndpoint: '/api/pipeline/status',
    logPrefix: '[Dashboard]'
  });

  /**
   * Logs a message with prefix.
   * @param {string} message - The log message.
   * @param {'info'|'warn'|'error'} [level='info'] - Log level.
   */
  function log(message, level = 'info') {
    const prefix = CONFIG.logPrefix;
    if (level === 'warn') {
      console.warn(`${prefix} ${message}`);
    } else if (level === 'error') {
      console.error(`${prefix} ${message}`);
    } else {
      console.log(`${prefix} ${message}`);
    }
  }

  /**
   * Initialises real-time status polling.
   * Fetches pipeline status at intervals and updates the UI.
   */
  function initStatusPolling() {
    log('Starting status polling every ' + CONFIG.pollingInterval + 'ms');

    /**
     * Fetches pipeline status and updates indicators.
     */
    async function poll() {
      try {
        const response = await fetch(CONFIG.statusEndpoint);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const data = await response.json();
        updateStatusIndicators(data);
      } catch (err) {
        log('Status poll failed: ' + err.message, 'warn');
      }
    }

    // Immediate first call, then interval
    poll();
    setInterval(poll, CONFIG.pollingInterval);
  }

  /**
   * Updates status badges/indicators based on pipeline data.
   * @param {Object} data - Pipeline status object from server.
   */
  function updateStatusIndicators(data) {
    const statusElement = document.getElementById('pipeline-status');
    const statusText = document.getElementById('pipeline-status-text');
    if (!statusElement || !statusText) return;

    const status = data.status || 'unknown';
    const isRunning = data.running || false;

    let badgeClass = 'bg-gray-200 text-gray-800';
    let label = 'Unknown';

    if (isRunning) {
      badgeClass = 'bg-yellow-200 text-yellow-800';
      label = 'Running';
    } else if (status === 'idle') {
      badgeClass = 'bg-green-200 text-green-800';
      label = 'Idle';
    } else if (status === 'error') {
      badgeClass = 'bg-red-200 text-red-800';
      label = 'Error';
    } else if (status === 'completed') {
      badgeClass = 'bg-blue-200 text-blue-800';
      label = 'Completed';
    }

    statusElement.className = `inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badgeClass}`;
    statusElement.textContent = label;
    if (data.message) {
      statusText.textContent = data.message;
    }
    log('Status updated: ' + label + (data.message ? ' - ' + data.message : ''));
  }

  /**
   * Binds one-click AJAX actions to buttons with data attributes.
   * Expects buttons with `data-action-url` and optional `data-action-method`.
   */
  function initActionButtons() {
    log('Binding action buttons...');

    document.querySelectorAll('[data-action-url]').forEach((button) => {
      button.addEventListener('click', async function (e) {
        e.preventDefault();
        const url = this.dataset.actionUrl;
        const method = (this.dataset.actionMethod || 'POST').toUpperCase();
        const confirmText = this.dataset.confirm;

        if (confirmText && !window.confirm(confirmText)) {
          log('Action cancelled by user');
          return;
        }

        log(`Executing ${method} ${url}`);

        // Disable button and show loading
        const originalText = this.textContent;
        this.disabled = true;
        this.textContent = 'Processing...';
        this.classList.add('opacity-50', 'cursor-not-allowed');

        try {
          const response = await fetch(url, {
            method: method,
            headers: {
              'Content-Type': 'application/json',
              'X-Requested-With': 'XMLHttpRequest'
            }
          });

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }

          const result = await response.json();
          log(`Action ${url} succeeded: ` + JSON.stringify(result));
          showToast('Action completed successfully', 'success');

          // Optionally trigger a status refresh
          if (typeof refreshStatus === 'function') {
            refreshStatus();
          }
        } catch (err) {
          log(`Action ${url} failed: ${err.message}`, 'error');
          showToast('Action failed: ' + err.message, 'error');
        } finally {
          // Restore button
          this.disabled = false;
          this.textContent = originalText;
          this.classList.remove('opacity-50', 'cursor-not-allowed');
        }
      });
    });
  }

  /**
   * Shows a temporary toast notification.
   * @param {string} message - Notification text.
   * @param {'success'|'error'|'info'} [type='info'] - Notification type.
   */
  function showToast(message, type = 'info') {
    const existing = document.querySelector('.dashboard-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `dashboard-toast fixed top-4 right-4 px-6 py-3 rounded shadow-lg text-white text-sm z-50 transition-opacity duration-300`;
    if (type === 'success') toast.classList.add('bg-green-600');
    else if (type === 'error') toast.classList.add('bg-red-600');
    else toast.classList.add('bg-blue-600');
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  /**
   * Initialises table sorting.
   * Makes <th> elements with `data-sortable` trigger sorting on click.
   */
  function initTableSorting() {
    log('Initialising table sorting...');

    document.querySelectorAll('table[data-sortable] thead th[data-sortable]').forEach((th) => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', function () {
        const table = this.closest('table');
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const index = Array.from(this.parentNode.children).indexOf(this);
        const isAsc = this.dataset.order !== 'asc';

        // Reset other headers
        table.querySelectorAll('thead th').forEach((other) => {
          other.dataset.order = '';
          other.classList.remove('sort-asc', 'sort-desc');
        });

        this.dataset.order = isAsc ? 'asc' : 'desc';
        this.classList.add(isAsc ? 'sort-asc' : 'sort-desc');

        rows.sort((a, b) => {
          const aVal = a.cells[index]?.textContent.trim() || '';
          const bVal = b.cells[index]?.textContent.trim() || '';

          // Try numeric sort
          const aNum = parseFloat(aVal.replace(/[^0-9.-]/g, ''));
          const bNum = parseFloat(bVal.replace(/[^0-9.-]/g, ''));
          if (!isNaN(aNum) && !isNaN(bNum)) {
            return isAsc ? aNum - bNum : bNum - aNum;
          }
          return isAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
        });

        rows.forEach((row) => tbody.appendChild(row));
        log(`Table sorted by column index ${index} ${isAsc ? 'asc' : 'desc'}`);
      });
    });
  }

  /**
   * Initialises table filtering.
   * Filters rows based on input value, matching any cell text.
   */
  function initTableFilter() {
    const filterInput = document.getElementById('filter-input');
    if (!filterInput) return;

    log('Initialising table filter...');

    filterInput.addEventListener('input', function () {
      const query = this.value.toLowerCase().trim();
      const table = document.querySelector('table[data-sortable]');
      if (!table) return;

      const rows = table.querySelectorAll('tbody tr');
      rows.forEach((row) => {
        const match = Array.from(row.cells).some((cell) =>
          cell.textContent.toLowerCase().includes(query)
        );
        row.style.display = match ? '' : 'none';
      });
      log(`Filter applied: "${query}" - ${rows.length} rows visible`);
    });
  }

  /**
   * Refreshes pipeline status manually (exposed globally for button use).
   * @function
   */
  window.refreshStatus = function () {
    log('Manual status refresh triggered');
    // Trigger a single poll by executing the poll function again
    (async function () {
      try {
        const response = await fetch(CONFIG.statusEndpoint);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();
        updateStatusIndicators(data);
      } catch (err) {
        log('Manual refresh failed: ' + err.message, 'warn');
        showToast('Status refresh failed', 'error');
      }
    })();
  };

  /**
   * Main initialisation. Called on DOMContentLoaded.
   */
  function init() {
    log('Dashboard initialising...');
    initStatusPolling();
    initActionButtons();
    initTableSorting();
    initTableFilter();
    log('Dashboard initialised.');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();