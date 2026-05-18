/**
 * StockPilot PH Portfolio Table Controller
 * Version: 2.0.0
 * 
 * Handles table search, column sorting (by Score / MoS), color bar rendering,
 * and tag display for the operator dashboard portfolio table.
 * 
 * @module static/js/portfolio
 * @description Provides search, sort, visual elements for StockPilot portfolio tables.
 * @requires Tailwind CSS (CDN) for styling
 */

(function () {
  'use strict';

  /**
   * PortfolioTableController manages interactive features for portfolio tables.
   */
  class PortfolioTableController {
    /**
     * Creates a new table controller instance.
     * @param {string} tableId - HTML id attribute of the portfolio table element.
     * @param {Object} [options] - Configuration overrides.
     * @param {string} [options.searchInputId='portfolio-search'] - ID of the search input field.
     * @param {string[]} [options.sortableColumns=['score','mos']] - Data attributes for sortable columns.
     * @param {string} [options.colorBarContainer='.color-bar'] - CSS selector for color bar cells.
     * @param {string} [options.tagContainer='.tags'] - CSS selector for tag container cells.
     * @throws {Error} If required DOM elements are missing.
     */
    constructor(tableId, options = {}) {
      this.tableId = tableId;
      this.options = Object.assign(
        {
          searchInputId: 'portfolio-search',
          sortableColumns: ['score', 'mos'],
          colorBarContainer: '.color-bar',
          tagContainer: '.tags',
        },
        options
      );

      /** @type {HTMLTableElement|null} */
      this.table = document.getElementById(tableId);
      if (!this.table) {
        console.error(`PortfolioTableController: Table with id "${tableId}" not found.`);
        return;
      }

      /** @type {HTMLInputElement|null} */
      this.searchInput = document.getElementById(this.options.searchInputId);
      if (!this.searchInput) {
        console.warn(`PortfolioTableController: Search input "#${this.options.searchInputId}" not found — search disabled.`);
      }

      this.init();
    }

    /**
     * Binds event listeners and initializes visual elements.
     */
    init() {
      console.log(`PortfolioTableController: Initializing table "${this.tableId}".`);
      try {
        this._renderColorBars();
        this._renderTags();
        this._attachSortHandlers();
        this._attachSearchHandler();
      } catch (err) {
        console.error('PortfolioTableController: Initialization failed:', err);
      }
    }

    /**
     * Renders color bars inside cells matching colorBarContainer selector.
     * Each cell is expected to have a numeric value (e.g., 85) that determines width and color.
     * Uses StockPilot brand colors: navy (#1a2744) for low, gold (#d4a843) for medium-high.
     * @private
     */
    _renderColorBars() {
      const cells = this.table.querySelectorAll(this.options.colorBarContainer);
      cells.forEach((cell) => {
        const value = parseFloat(cell.textContent.trim());
        if (isNaN(value)) return;

        const clamped = Math.min(100, Math.max(0, value));
        const hue = clamped > 50 ? 40 : 220; // goldish above 50, navy below
        const lightness = 30 + (clamped / 100) * 30;

        const bar = document.createElement('div');
        bar.className = 'color-bar-fill h-2 rounded-full transition-all duration-300';
        bar.style.width = `${clamped}%`;
        bar.style.backgroundColor = `hsl(${hue}, 50%, ${lightness}%)`;

        // Keep numeric text accessible but style it as overlay
        const textSpan = document.createElement('span');
        textSpan.className = 'text-xs text-gray-600 ml-2';
        textSpan.textContent = `${Math.round(clamped)}%`;

        cell.innerHTML = '';
        cell.appendChild(bar);
        cell.appendChild(textSpan);
      });
    }

    /**
     * Renders tags inside cells matching tagContainer selector.
     * Expects tag data as comma-separated or array-like strings.
     * @private
     */
    _renderTags() {
      const cells = this.table.querySelectorAll(this.options.tagContainer);
      cells.forEach((cell) => {
        const rawTags = cell.getAttribute('data-tags');
        if (!rawTags) return;

        const tags = rawTags.split(',').map((t) => t.trim()).filter(Boolean);
        if (tags.length === 0) return;

        cell.innerHTML = '';
        tags.forEach((tag) => {
          const badge = document.createElement('span');
          badge.className = 'inline-block bg-accent text-white text-xs font-semibold px-2 py-0.5 rounded-full mr-1 mb-1';
          badge.textContent = tag;
          cell.appendChild(badge);
        });
      });
    }

    /**
     * Attaches click event listeners to sortable column headers.
     * Sorts table rows ascending/descending by data attribute value (numeric).
     * @private
     */
    _attachSortHandlers() {
      const thead = this.table.querySelector('thead');
      if (!thead) return;

      const headers = thead.querySelectorAll('th');
      headers.forEach((th) => {
        const sortKey = th.getAttribute('data-sort');
        if (this.options.sortableColumns.includes(sortKey)) {
          th.classList.add('cursor-pointer', 'select-none', 'hover:bg-navy-light', 'transition-colors');
          th.addEventListener('click', (event) => this._handleSort(event, sortKey));
        }
      });
    }

    /**
     * Sorts the table body rows based on sort key.
     * @param {Event} event - Click event.
     * @param {string} sortKey - Data attribute value to sort by.
     * @private
     */
    _handleSort(event, sortKey) {
      const th = event.currentTarget;
      const tbody = this.table.querySelector('tbody');
      if (!tbody) return;

      const rows = Array.from(tbody.querySelectorAll('tr'));
      if (rows.length === 0) return;

      // Toggle sort direction
      const currentDir = th.getAttribute('data-dir') || 'asc';
      const newDir = currentDir === 'asc' ? 'desc' : 'asc';
      th.setAttribute('data-dir', newDir);

      // Remove sorted indicator from other headers
      this.table.querySelectorAll('th[data-sort]').forEach((h) => {
        if (h !== th) h.removeAttribute('data-dir');
      });

      // Visual arrow indicator
      const arrow = newDir === 'asc' ? ' ▲' : ' ▼';
      th.textContent = th.textContent.replace(/[▲▼]/g, '').trim() + arrow;

      const sorted = rows.sort((a, b) => {
        const aVal = parseFloat(a.querySelector(`[data-sort-value="${sortKey}"]`)?.textContent || a.dataset[sortKey]);
        const bVal = parseFloat(b.querySelector(`[data-sort-value="${sortKey}"]`)?.textContent || b.dataset[sortKey]);

        if (isNaN(aVal) || isNaN(bVal)) return 0;
        return newDir === 'asc' ? aVal - bVal : bVal - aVal;
      });

      sorted.forEach((row) => tbody.appendChild(row));
    }

    /**
     * Attaches input event listener to search input for filtering table rows.
     * Filters by text content in any cell, case-insensitive.
     * @private
     */
    _attachSearchHandler() {
      if (!this.searchInput) return;

      this.searchInput.addEventListener('input', (event) => {
        const query = event.target.value.toLowerCase().trim();
        const tbody = this.table.querySelector('tbody');
        if (!tbody) return;

        const rows = tbody.querySelectorAll('tr');
        rows.forEach((row) => {
          const text = row.textContent.toLowerCase();
          row.style.display = text.includes(query) ? '' : 'none';
        });
      });
    }
  }

  // Instantiate controller after DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    try {
      const tableId = 'portfolio-table';
      new PortfolioTableController(tableId, {
        searchInputId: 'portfolio-search',
      });
    } catch (e) {
      console.error('PortfolioTableController: Fatal error during instantiation:', e);
    }
  });

  // Export for potential module usage (optional)
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = PortfolioTableController;
  }
})();