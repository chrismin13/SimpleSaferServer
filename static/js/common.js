/* ============================================================
   COMMON.JS — Vanilla JS UI System (replaces Bootstrap JS)
   Modal, Collapse, and Confirmation Dialog
   ============================================================ */

/* ── Modal System ───────────────────────────────────────────── */
window.AppModal = {
  show(modalId) {
    const overlay = document.getElementById(modalId);
    if (!overlay) return;
    overlay.classList.add('visible');
    document.body.style.overflow = 'hidden';
    // Focus trap: focus first focusable element
    requestAnimationFrame(() => {
      const focusable = overlay.querySelector('input:not([type="hidden"]):not([disabled]), button:not([disabled]), textarea:not([disabled]), select:not([disabled])');
      if (focusable) focusable.focus();
    });
  },

  hide(modalId) {
    const overlay = document.getElementById(modalId);
    if (!overlay) return;
    overlay.classList.remove('visible');
    // Only restore scroll if no other modals are open
    if (!document.querySelector('.modal-overlay.visible')) {
      document.body.style.overflow = '';
    }
    // Fire custom event
    overlay.dispatchEvent(new CustomEvent('modal:hidden'));
  },

  hideAll() {
    document.querySelectorAll('.modal-overlay.visible').forEach(m => {
      m.classList.remove('visible');
    });
    document.body.style.overflow = '';
  },

  // Some page scripts prefer a tiny object they can pass around.
  getInstance(modalId) {
    return {
      show: () => AppModal.show(modalId),
      hide: () => AppModal.hide(modalId)
    };
  }
};

// Close modal on overlay click or close button
document.addEventListener('click', (e) => {
  // Close button
  const closeBtn = e.target.closest('.modal-close, [data-modal-close]');
  if (closeBtn) {
    const overlay = closeBtn.closest('.modal-overlay');
    if (overlay) AppModal.hide(overlay.id);
    return;
  }

  // Overlay click (outside modal container)
  if (e.target.classList.contains('modal-overlay') && e.target.classList.contains('visible')) {
    AppModal.hide(e.target.id);
  }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const openModal = document.querySelector('.modal-overlay.visible');
    if (openModal) AppModal.hide(openModal.id);
  }
});

// Modal trigger buttons
document.addEventListener('click', (e) => {
  const trigger = e.target.closest('[data-modal-target]');
  if (trigger) {
    const targetId = trigger.getAttribute('data-modal-target');
    AppModal.show(targetId);
  }
});

/* ── Numeric Inputs ─────────────────────────────────────────── */
document.addEventListener('input', (e) => {
  const input = e.target.closest('input[inputmode="numeric"][pattern="[0-9]*"]');
  if (!input) return;

  const numericValue = input.value.replace(/\D/g, '');
  if (input.value === numericValue) return;

  // Numeric text inputs give us consistent integer-only display behavior across
  // browsers; native number inputs can keep invalid text visible in Firefox.
  input.value = numericValue;
});

/* ── API Client ─────────────────────────────────────────────── */
class ApiProblemError extends Error {
  constructor(problem, fallbackMessage) {
    const message = problem && problem.detail ? problem.detail : fallbackMessage;
    super(message || 'Request failed.');
    this.name = 'ApiProblemError';
    this.problem = problem || null;
    this.status = problem && problem.status ? problem.status : 0;
    this.title = problem && problem.title ? problem.title : 'Request failed';
    this.type = problem && problem.type ? problem.type : 'about:blank';
    if (problem && typeof problem === 'object') {
      Object.keys(problem).forEach((key) => {
        if (!Object.prototype.hasOwnProperty.call(this, key)) {
          this[key] = problem[key];
        }
      });
    }
  }
}

window.ApiProblemError = ApiProblemError;

window.ApiClient = {
  async fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const text = await response.text();
    let payload = {};

    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (error) {
        throw new ApiProblemError(null, `Unexpected response from server (${response.status})`);
      }
    }

    if (!response.ok) {
      throw new ApiProblemError(payload, payload.detail || payload.error || payload.message);
    }

    if (payload && Object.prototype.hasOwnProperty.call(payload, 'data')) {
      return {
        data: payload.data,
        message: payload.message || ''
      };
    }

    return {
      data: payload,
      message: payload && payload.message ? payload.message : ''
    };
  }
};

/* ── Backup readiness checklist ─────────────────────────────── */
window.AppBackupReadiness = {
  escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },

  statusMeta(item) {
    if (item && item.complete) {
      return {
        itemClass: 'is-complete',
        badgeClass: 'badge-success',
        iconClass: 'fa-circle-check',
        label: item.status_label || 'Complete'
      };
    }
    if (item && item.status === 'skipped') {
      return {
        itemClass: 'is-skipped',
        badgeClass: 'badge-warning',
        iconClass: 'fa-forward',
        label: item.status_label || 'Skipped'
      };
    }
    return {
      itemClass: 'is-incomplete',
      badgeClass: 'badge-warning',
      iconClass: 'fa-circle-exclamation',
      label: (item && item.status_label) || 'Incomplete'
    };
  },

  renderItem(item) {
    const meta = this.statusMeta(item);
    return `
      <div class="backup-readiness-item ${meta.itemClass}" data-readiness-item="${this.escapeHtml(item.key)}">
        <div class="backup-readiness-icon" aria-hidden="true">
          <i class="fas ${meta.iconClass}"></i>
        </div>
        <div class="backup-readiness-copy">
          <div class="backup-readiness-item-title">${this.escapeHtml(item.title)}</div>
          <div class="backup-readiness-item-detail">${this.escapeHtml(item.detail)}</div>
        </div>
        <div class="backup-readiness-item-actions">
          <span class="badge ${meta.badgeClass}">${meta.label}</span>
          <a class="btn btn-secondary btn-sm" href="${this.escapeHtml(item.action_url)}">${this.escapeHtml(item.action_label)}</a>
        </div>
      </div>
    `;
  },

  render(container, readiness) {
    if (!container || !readiness) return;
    const badge = container.querySelector('[data-readiness-badge]');
    const count = container.querySelector('[data-readiness-count]');
    const detail = container.querySelector('[data-readiness-detail]');
    const items = container.querySelector('[data-readiness-items]');
    const complete = Boolean(readiness.complete);
    const countLabel = readiness.count_label ||
      `${readiness.completed_required_count} of ${readiness.required_count} complete`;

    if (badge) {
      badge.className = `badge ${complete ? 'badge-success' : 'badge-warning'}`;
      badge.innerHTML = `<i class="fas ${complete ? 'fa-circle-check' : 'fa-triangle-exclamation'}"></i> <span data-readiness-count>${this.escapeHtml(countLabel)}</span>`;
    }
    if (count) {
      count.textContent = countLabel;
    }
    if (detail) {
      detail.textContent = readiness.detail || '';
    }
    if (items) {
      items.innerHTML = (readiness.items || []).map((item) => this.renderItem(item)).join('');
    }
  },

  async refresh(container) {
    const target = container || document.querySelector('[data-backup-readiness-url]');
    if (!target) return;
    const url = target.getAttribute('data-backup-readiness-url');
    if (!url) return;
    const { data } = await window.ApiClient.fetchJson(url, {
      headers: { 'Accept': 'application/json' }
    });
    this.render(target, data);
  },

  refreshAll() {
    if (window.htmx && document.querySelector('[hx-get][hx-trigger*="backup-readiness-refresh"]')) {
      window.htmx.trigger(document.body, 'backup-readiness-refresh');
    }
    return Promise.all(
      Array.from(document.querySelectorAll('[data-backup-readiness-url]')).map((container) =>
        this.refresh(container).catch((error) => console.error(error))
      )
    );
  }
};

document.addEventListener('DOMContentLoaded', () => {
  if (document.querySelector('[data-backup-readiness-url]')) {
    window.AppBackupReadiness.refreshAll();
  }
});

window.refreshBackupReadiness = function refreshBackupReadiness() {
  if (!window.AppBackupReadiness) return Promise.resolve();
  return window.AppBackupReadiness.refreshAll();
};


/* ── Collapse System ────────────────────────────────────────── */
document.addEventListener('click', (e) => {
  const trigger = e.target.closest('[data-collapse-target]');
  if (!trigger) return;

  const targetId = trigger.getAttribute('data-collapse-target');
  const content = document.getElementById(targetId);
  if (!content) return;

  const isExpanded = content.classList.contains('expanded');

  if (isExpanded) {
    content.classList.remove('expanded');
    trigger.classList.remove('expanded');
  } else {
    content.classList.add('expanded');
    trigger.classList.add('expanded');
  }
});


/* ── Confirmation Dialog ────────────────────────────────────── */
window.showConfirmationDialog = function showConfirmationDialog(options) {
  const {
    title = 'Confirm Action',
    message = 'Are you sure you want to continue?',
    body = null,
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    confirmClass = 'btn-primary'
  } = options || {};

  const modalEl = document.getElementById('confirmationModal');
  if (!modalEl) {
    return Promise.resolve(window.confirm(message));
  }

  const titleEl = document.getElementById('confirmationModalTitle');
  const bodyEl = document.getElementById('confirmationModalBody');
  const confirmBtn = document.getElementById('confirmationModalConfirmBtn');
  const cancelBtn = document.getElementById('confirmationModalCancelBtn');

  titleEl.textContent = title;
  bodyEl.textContent = '';
  if (typeof Node !== 'undefined' && body instanceof Node) {
    bodyEl.classList.remove('modal-body-pre');
    bodyEl.appendChild(body);
  } else {
    bodyEl.classList.add('modal-body-pre');
    bodyEl.textContent = message;
  }
  confirmBtn.textContent = confirmLabel;
  cancelBtn.textContent = cancelLabel;
  confirmBtn.className = `btn ${confirmClass}`;

  return new Promise((resolve) => {
    let settled = false;

    const cleanup = () => {
      confirmBtn.removeEventListener('click', handleConfirm);
      cancelBtn.removeEventListener('click', handleCancel);
      modalEl.removeEventListener('modal:hidden', handleHidden);
    };

    const finish = (result) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(result);
    };

    const handleConfirm = () => {
      finish(true);
      AppModal.hide('confirmationModal');
    };

    const handleCancel = () => {
      finish(false);
      AppModal.hide('confirmationModal');
    };

    const handleHidden = () => {
      finish(false);
    };

    confirmBtn.addEventListener('click', handleConfirm);
    cancelBtn.addEventListener('click', handleCancel);
    modalEl.addEventListener('modal:hidden', handleHidden);

    AppModal.show('confirmationModal');
  });
};

// Data-confirm attribute handler (same pattern as before)
document.addEventListener('click', function(event) {
  const trigger = event.target.closest('[data-confirm]');
  if (!trigger) return;
  if (trigger.disabled) return;

  if (trigger.dataset.confirmApproved === 'true') {
    delete trigger.dataset.confirmApproved;
    return;
  }

  event.preventDefault();
  event.stopPropagation();

  window.showConfirmationDialog({
    title: trigger.getAttribute('data-confirm-title') || 'Confirm Action',
    message: trigger.getAttribute('data-confirm') || 'Are you sure you want to continue?',
    confirmLabel: trigger.getAttribute('data-confirm-button') || 'Confirm',
    cancelLabel: trigger.getAttribute('data-confirm-cancel') || 'Cancel',
    confirmClass: trigger.getAttribute('data-confirm-class') || 'btn-primary'
  }).then((confirmed) => {
    if (!confirmed) return;
    trigger.dataset.confirmApproved = 'true';
    trigger.click();
  });
}, true);


/* ── Mobile Sidebar Toggle ──────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('mobileNavToggle');
  const sidebar = document.querySelector('.sidebar');
  const backdrop = document.getElementById('sidebarBackdrop');
  const body = document.body;

  if (toggle && sidebar) {
    const closeSidebar = () => {
      sidebar.classList.remove('open');
      if (body) body.classList.remove('sidebar-open');
      if (backdrop) backdrop.classList.remove('visible');
    };

    toggle.addEventListener('click', () => {
      const isOpen = sidebar.classList.contains('open');
      if (isOpen) {
        closeSidebar();
      } else {
        sidebar.classList.add('open');
        if (body) body.classList.add('sidebar-open');
        if (backdrop) backdrop.classList.add('visible');
      }
    });

    if (backdrop) {
      backdrop.addEventListener('click', closeSidebar);
    }
  }
});


/* ── Alert / Toast Utility ──────────────────────────────────── */
window.showAlert = function showAlert(message, type = 'success', container = null) {
  const normalizedType = type === 'error' ? 'danger' : type;
  const alertDiv = document.createElement('div');
  alertDiv.className = `alert alert-${normalizedType}`;
  let isDismissed = false;

  const content = document.createElement('div');
  content.className = 'alert-content';

  const icon = document.createElement('i');
  icon.className = `fas ${
    normalizedType === 'success'
      ? 'fa-check-circle'
      : normalizedType === 'danger'
      ? 'fa-exclamation-triangle'
      : normalizedType === 'warning'
      ? 'fa-exclamation-circle'
      : 'fa-info-circle'
  }`;

  const messageSpan = document.createElement('span');
  messageSpan.className = 'alert-message';
  messageSpan.textContent = message;

  content.appendChild(icon);
  content.appendChild(messageSpan);
  alertDiv.appendChild(content);

  const dismiss = () => {
    if (isDismissed) return;
    isDismissed = true;
    alertDiv.classList.add('is-hiding');
    setTimeout(() => alertDiv.remove(), 200);
  };

  if (container) {
    container.prepend(alertDiv);
    setTimeout(dismiss, 4000);
    return alertDiv;
  }

  alertDiv.classList.add('toast-notification');
  alertDiv.setAttribute('role', normalizedType === 'danger' || normalizedType === 'warning' ? 'alert' : 'status');

  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'toast-close';
  closeButton.setAttribute('aria-label', 'Dismiss notification');
  closeButton.innerHTML = '<i class="fas fa-xmark"></i>';
  closeButton.addEventListener('click', dismiss);
  alertDiv.appendChild(closeButton);

  const target = document.getElementById('toastStack') || document.body;
  target.appendChild(alertDiv);

  requestAnimationFrame(() => {
    alertDiv.classList.add('visible');
  });

  let timeoutId = setTimeout(dismiss, 4000);
  alertDiv.addEventListener('mouseenter', () => {
    clearTimeout(timeoutId);
  });
  alertDiv.addEventListener('mouseleave', () => {
    timeoutId = setTimeout(dismiss, 2500);
  });

  return alertDiv;
};


/* ── Async Button State ─────────────────────────────────────── */
window.AsyncButtonState = (() => {
  const stateMap = new WeakMap();

  function clearTimers(state) {
    if (!state) return;
    window.clearTimeout(state.settleTimer);
  }

  function restoreButton(button, state, restoreDisabled) {
    button.classList.remove('is-async-pending');
    button.removeAttribute('aria-busy');

    if (restoreDisabled !== false && state) {
      button.disabled = state.wasDisabled;
    }

    stateMap.delete(button);
  }

  function start(button, options = {}) {
    if (!button) return;

    const existing = stateMap.get(button);
    if (existing) {
      clearTimers(existing);
      restoreButton(button, existing, false);
    }

    const state = {
      minPendingVisible: options.minPendingVisible ?? 180,
      wasDisabled: button.disabled,
      startedAt: performance.now(),
      settleTimer: null
    };

    button.disabled = true;
    button.classList.add('is-async-pending');
    button.setAttribute('aria-busy', 'true');

    stateMap.set(button, state);
  }

  function settle(button, options = {}) {
    const state = stateMap.get(button);
    if (!button || !state) return;

    clearTimers(state);
    const elapsed = performance.now() - state.startedAt;
    const waitTime = Math.max(0, state.minPendingVisible - elapsed);

    state.settleTimer = window.setTimeout(() => {
      restoreButton(button, state, options.restoreDisabled);
    }, waitTime);
  }

  function success(button, options = {}) {
    settle(button, options);
  }

  function error(button, options = {}) {
    settle(button, options);
  }

  function reset(button, options = {}) {
    const state = stateMap.get(button);
    if (!button || !state) return;
    clearTimers(state);
    restoreButton(button, state, options.restoreDisabled);
  }

  return {
    start,
    success,
    error,
    reset
  };
})();


/* ── Action Context Menu ─────────────────────────────────────── */
window.ActionContextMenu = (() => {
  let menuEl = null;
  let activeItems = [];

  // Rule: if a list/table row exposes row-level actions in an Actions column,
  // expose the same actions on right-click via this helper as well.
  function ensureMenu() {
    if (menuEl) return menuEl;

    menuEl = document.createElement('div');
    menuEl.id = 'globalActionContextMenu';
    menuEl.className = 'action-context-menu';
    menuEl.setAttribute('role', 'menu');
    menuEl.setAttribute('aria-hidden', 'true');
    document.body.appendChild(menuEl);

    menuEl.addEventListener('click', (event) => {
      const button = event.target.closest('[data-context-menu-index]');
      if (!button || button.disabled) return;

      const item = activeItems[Number(button.dataset.contextMenuIndex)];
      hide();
      if (item && typeof item.onSelect === 'function') {
        item.onSelect();
      }
    });

    document.addEventListener('click', (event) => {
      if (!event.target.closest('#globalActionContextMenu')) {
        hide();
      }
    });
    document.addEventListener('scroll', hide, true);
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') hide();
    });
    window.addEventListener('resize', hide);

    return menuEl;
  }

  function renderItems(items) {
    const el = ensureMenu();
    el.innerHTML = '';
    activeItems = items;

    items.forEach((item, index) => {
      if (!item || item.hidden) return;

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'action-context-menu-item';
      if (item.destructive) button.classList.add('danger');
      button.dataset.contextMenuIndex = String(index);
      button.setAttribute('role', 'menuitem');
      button.disabled = Boolean(item.disabled);

      if (item.iconClass) {
        const icon = document.createElement('i');
        icon.className = item.iconClass;
        button.appendChild(icon);
      }

      button.appendChild(document.createTextNode(item.label || 'Action'));
      el.appendChild(button);
    });
  }

  function show(items, clientX, clientY) {
    const visibleItems = (items || []).filter((item) => item && !item.hidden);
    if (!visibleItems.length) return;

    const el = ensureMenu();
    renderItems(visibleItems);
    el.classList.add('visible');
    el.setAttribute('aria-hidden', 'false');

    const { innerWidth, innerHeight } = window;
    const menuWidth = el.offsetWidth;
    const menuHeight = el.offsetHeight;
    const left = Math.min(clientX, innerWidth - menuWidth - 8);
    const top = Math.min(clientY, innerHeight - menuHeight - 8);

    el.style.left = `${Math.max(8, left)}px`;
    el.style.top = `${Math.max(8, top)}px`;
  }

  function hide() {
    if (!menuEl) return;
    menuEl.classList.remove('visible');
    menuEl.setAttribute('aria-hidden', 'true');
    activeItems = [];
  }

  function bind(triggerEl, getItems) {
    if (!triggerEl || typeof getItems !== 'function') return;

    triggerEl.addEventListener('contextmenu', (event) => {
      const items = getItems(event) || [];
      const visibleItems = items.filter((item) => item && !item.hidden);
      if (!visibleItems.length) return;

      event.preventDefault();
      show(visibleItems, event.clientX, event.clientY);
    });
  }

  return {
    bind,
    hide,
    show
  };
})();


/* ── Time Formatting ─────────────────────────────────────────── */
window.parseServerDateTime = function parseServerDateTime(value) {
  if (!value || typeof value !== 'string') return null;

  const trimmed = value.trim();
  if (!trimmed || /^(never|unknown|not run yet|not scheduled|retrieval error|-)$/i.test(trimmed)) {
    return null;
  }

  const direct = new Date(trimmed);
  if (!Number.isNaN(direct.getTime())) return direct;

  let normalized = trimmed.replace(/^[A-Za-z]{3}\s+/, '');
  normalized = normalized.replace(/\s+[A-Z]{2,5}$/, '');

  const isoLike = new Date(normalized.replace(' ', 'T'));
  if (!Number.isNaN(isoLike.getTime())) return isoLike;

  const match = normalized.match(/^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/);
  if (!match) return null;

  const [, year, month, day, hour, minute, second] = match;
  return new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second)
  );
};

window.AppFormat = (() => {
  const locale = document.documentElement.lang || undefined;

  function number(value, options = {}) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return options.fallback || '—';
    try {
      return new Intl.NumberFormat(locale, options.format || {}).format(parsed);
    } catch (error) {
      return String(parsed);
    }
  }

  function percent(value, options = {}) {
    return number(value, {
      fallback: options.fallback || '0%',
      format: {
        maximumFractionDigits: 0,
        style: 'percent'
      }
    });
  }

  function dateTime(value, options = {}) {
    const parsed = window.parseServerDateTime(value);
    if (!parsed) return value || options.fallback || '—';
    try {
      return new Intl.DateTimeFormat(locale, {
        dateStyle: options.dateStyle || 'medium',
        timeStyle: options.timeStyle || 'short'
      }).format(parsed);
    } catch (error) {
      return parsed.toLocaleString();
    }
  }

  function date(value, options = {}) {
    const parsed = window.parseServerDateTime(value);
    if (!parsed) return value || options.fallback || '—';
    try {
      return new Intl.DateTimeFormat(locale, {
        dateStyle: options.dateStyle || 'medium'
      }).format(parsed);
    } catch (error) {
      return parsed.toLocaleDateString();
    }
  }

  function relativeTimestamp(value, options = {}) {
    const parsed = window.parseServerDateTime(value);
    if (!parsed) return value || options.fallback || '—';

    const diffSeconds = Math.round((parsed.getTime() - Date.now()) / 1000);
    const absSeconds = Math.abs(diffSeconds);
    const divisions = [
      { unit: 'year', seconds: 31536000 },
      { unit: 'month', seconds: 2592000 },
      { unit: 'week', seconds: 604800 },
      { unit: 'day', seconds: 86400 },
      { unit: 'hour', seconds: 3600 },
      { unit: 'minute', seconds: 60 },
      { unit: 'second', seconds: 1 }
    ];
    const division = divisions.find((item) => absSeconds >= item.seconds) || divisions[divisions.length - 1];
    const valueForUnit = Math.round(diffSeconds / division.seconds);

    try {
      if (diffSeconds > 0 && options.futurePrefix === false) {
        return new Intl.NumberFormat(locale, {
          maximumFractionDigits: 0,
          style: 'unit',
          unit: division.unit,
          unitDisplay: options.compact ? 'narrow' : 'long'
        }).format(Math.abs(valueForUnit));
      }
      return new Intl.RelativeTimeFormat(locale, {
        numeric: options.numeric || 'auto',
        style: options.compact ? 'short' : 'long'
      }).format(valueForUnit, division.unit);
    } catch (error) {
      return window.formatRelativeTimestamp(value, options);
    }
  }

  return {
    date,
    dateTime,
    number,
    percent,
    relativeTimestamp
  };
})();

window.formatRelativeTimestamp = function formatRelativeTimestamp(value, options = {}) {
  const { fallback = '—', futurePrefix = true, compact = false } = options;
  const parsed = window.parseServerDateTime(value);
  if (!parsed) return value || fallback;

  const diffMs = parsed.getTime() - Date.now();
  const isFuture = diffMs > 0;
  const totalMinutes = Math.max(0, Math.floor(Math.abs(diffMs) / 60000));

  if (Math.abs(diffMs) < 60000) {
    if (compact) {
      return isFuture && futurePrefix ? 'in <1m' : (isFuture ? '<1m' : 'Just now');
    }
    if (isFuture) {
      return futurePrefix ? 'in a few seconds' : 'a few seconds';
    }
    return 'a few seconds ago';
  }

  const units = [
    ['w', 10080],
    ['d', 1440],
    ['h', 60],
    ['m', 1]
  ];

  let remaining = totalMinutes;
  const parts = [];
  units.forEach(([suffix, size]) => {
    if (parts.length >= 3) return;
    const amount = Math.floor(remaining / size);
    if (amount > 0) {
      parts.push(`${amount}${suffix}`);
      remaining -= amount * size;
    }
  });

  if (parts.length === 0) {
    parts.push('0m');
  }

  if (compact) {
    const compactPart = parts[0] || '0m';
    return isFuture ? (futurePrefix ? `in ${compactPart}` : compactPart) : `${compactPart} ago`;
  }

  return isFuture
    ? (futurePrefix ? `in ${parts.join(' ')}` : parts.join(' '))
    : `${parts.join(' ')} ago`;
};


/* ── Path Breadcrumbs ────────────────────────────────────────── */
window.renderPathBreadcrumbs = function renderPathBreadcrumbs(container, value, onNavigate) {
  if (!container) return;

  const path = value && value.trim() ? value.trim() : '/';
  const segments = path === '/' ? [] : path.split('/').filter(Boolean);
  container.dataset.path = path;
  container.innerHTML = '';

  function appendSeparator() {
    const separator = document.createElement('span');
    separator.className = 'path-breadcrumb-separator';
    separator.textContent = '/';
    container.appendChild(separator);
  }

  function appendPart(label, partPath, isCurrent) {
    if (isCurrent || typeof onNavigate !== 'function') {
      const current = document.createElement('span');
      current.className = 'path-breadcrumb-current';
      current.textContent = label;
      container.appendChild(current);
      return;
    }

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'path-breadcrumb-btn';
    button.textContent = label;
    button.addEventListener('click', () => onNavigate(partPath));
    container.appendChild(button);
  }

  appendPart('/', '/', segments.length === 0);

  let currentPath = '';
  segments.forEach((segment, index) => {
    appendSeparator();
    currentPath += `/${segment}`;
    appendPart(segment, currentPath, index === segments.length - 1);
  });
};


/* ── Feedback-slot .is-empty sync ───────────────────────────── */
// Marks .feedback-slot elements as .is-empty when all their children are
// hidden (.d-none), so CSS can collapse the slot even in browsers that
// don't support :has(). Runs on DOMContentLoaded and re-evaluates whenever
// a child's class changes (via MutationObserver).
(function initFeedbackSlotSync() {
  function hasVisibleChild(slot) {
    for (const child of slot.children) {
      if (!child.classList.contains('d-none')) return true;
    }
    return false;
  }

  function syncSlot(slot) {
    const empty = slot.children.length === 0 || !hasVisibleChild(slot);
    slot.classList.toggle('is-empty', empty);
  }

  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      const slot = mutation.target.closest('.feedback-slot');
      if (slot) syncSlot(slot);
    });
  });

  function init() {
    document.querySelectorAll('.feedback-slot').forEach((slot) => {
      syncSlot(slot);
      observer.observe(slot, {
        childList: true,
        subtree: true,
        attributeFilter: ['class'],
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}());
