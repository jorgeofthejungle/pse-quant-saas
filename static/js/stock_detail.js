/**
 * Stock Detail Page – Interaction Controller
 * Provides expand/collapse sections, MoS tooltips, and chart toggle (placeholders).
 * @module stockDetail
 */

(function () {
  'use strict';

  /** @constant {string} CSS class for expanded state */
  const EXPANDED_CLASS = 'section--expanded';

  /** @constant {string} CSS class for hidden chart */
  const CHART_HIDDEN_CLASS = 'chart--hidden';

  /** @constant {string} Selector for collapsible section headers */
  const SECTION_HEADER_SELECTOR = '[data-toggle="section"]';

  /** @constant {string} Selector for MoS elements */
  const MOS_ELEMENT_SELECTOR = '[data-tooltip="mos"]';

  /** @constant {string} Selector for chart toggle buttons */
  const CHART_TOGGLE_SELECTOR = '[data-toggle="chart"]';

  /** @constant {string} Selector for chart containers */
  const CHART_CONTAINER_SELECTOR = '[data-chart-container]';

  /** @constant {string} Tooltip content attribute */
  const TOOLTIP_CONTENT_ATTR = 'data-tooltip-content';

  /** @type {HTMLElement|null} Reference to the tooltip element */
  let tooltipEl = null;

  /**
   * Initialise all stock detail interactions.
   * @throws {Error} If required DOM elements are missing.
   */
  function init() {
    try {
      setupExpandCollapse();
      setupTooltips();
      setupChartToggle();
      console.log('[StockDetail] Initialised successfully.');
    } catch (err) {
      console.error('[StockDetail] Init failed:', err.message || err);
    }
  }

  /**
   * Attaches delegated click handler for section expand/collapse.
   */
  function setupExpandCollapse() {
    const headerEl = document.querySelector(SECTION_HEADER_SELECTOR);
    if (!headerEl) {
      console.warn('[StockDetail] No section toggle elements found. Skipping expand/collapse.');
      return;
    }

    document.addEventListener('click', function (e) {
      const header = e.target.closest(SECTION_HEADER_SELECTOR);
      if (!header) return;

      const sectionId = header.getAttribute('data-section');
      if (!sectionId) {
        console.warn('[StockDetail] Section header missing data-section attribute.');
        return;
      }

      const section = document.getElementById(sectionId);
      if (!section) {
        console.warn('[StockDetail] Section element not found for id:', sectionId);
        return;
      }

      const isExpanded = section.classList.contains(EXPANDED_CLASS);
      section.classList.toggle(EXPANDED_CLASS, !isExpanded);
      header.setAttribute('aria-expanded', (!isExpanded).toString());
      console.log('[StockDetail] Section toggled:', sectionId, !isExpanded ? 'expanded' : 'collapsed');
    });
  }

  /**
   * Creates the tooltip element on first usage and attaches hover listeners for MoS.
   */
  function setupTooltips() {
    // Create tooltip element once
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.id = 'stock-detail-tooltip';
      tooltipEl.style.position = 'fixed';
      tooltipEl.style.zIndex = '9999';
      tooltipEl.style.display = 'none';
      tooltipEl.style.pointerEvents = 'none';
      tooltipEl.style.background = '#1a2744';
      tooltipEl.style.color = '#fff';
      tooltipEl.style.padding = '4px 12px';
      tooltipEl.style.borderRadius = '4px';
      tooltipEl.style.fontSize = '14px';
      tooltipEl.style.fontFamily = 'Inter, sans-serif';
      tooltipEl.style.boxShadow = '0 2px 8px rgba(0,0,0,0.15)';
      tooltipEl.style.whiteSpace = 'nowrap';
      document.body.appendChild(tooltipEl);
    }

    const mosElements = document.querySelectorAll(MOS_ELEMENT_SELECTOR);
    if (mosElements.length === 0) {
      console.warn('[StockDetail] No MoS elements found. Skipping tooltip setup.');
      return;
    }

    const showTooltip = function (e) {
      const el = e.currentTarget;
      const content = el.getAttribute(TOOLTIP_CONTENT_ATTR) || 'Margin of Safety';
      tooltipEl.textContent = content;
      tooltipEl.style.display = 'block';
      const rect = el.getBoundingClientRect();
      tooltipEl.style.left = rect.left + (rect.width / 2) - (tooltipEl.offsetWidth / 2) + 'px';
      tooltipEl.style.top = rect.bottom + 8 + 'px';
    };

    const hideTooltip = function () {
      tooltipEl.style.display = 'none';
    };

    mosElements.forEach(function (el) {
      el.addEventListener('mouseenter', showTooltip);
      el.addEventListener('mouseleave', hideTooltip);
      el.setAttribute('aria-label', 'MoS tooltip');
    });
  }

  /**
   * Toggles visibility of a chart container when the toggle button is clicked.
   */
  function setupChartToggle() {
    const toggleBtn = document.querySelector(CHART_TOGGLE_SELECTOR);
    if (!toggleBtn) {
      console.warn('[StockDetail] No chart toggle button found. Skipping chart toggle.');
      return;
    }

    const chartContainer = document.querySelector(CHART_CONTAINER_SELECTOR);
    if (!chartContainer) {
      console.warn('[StockDetail] No chart container found. Skipping chart toggle.');
      return;
    }

    toggleBtn.addEventListener('click', function () {
      const isHidden = chartContainer.classList.toggle(CHART_HIDDEN_CLASS);
      console.log('[StockDetail] Chart toggled:', isHidden ? 'hidden' : 'visible');
      toggleBtn.textContent = isHidden ? 'Show Chart' : 'Hide Chart';
    });
  }

  // Boot on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();