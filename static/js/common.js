/* ============================================================
   COMMON.JS — Vanilla JS UI System (replaces Bootstrap JS)
   Modal, Collapse, and Confirmation Dialog
   ============================================================ */

/* ── Modal System ───────────────────────────────────────────── */
window.BunkerModal = {
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

  // Get or create an instance-like object for compatibility
  getInstance(modalId) {
    return {
      show: () => BunkerModal.show(modalId),
      hide: () => BunkerModal.hide(modalId)
    };
  }
};

// Close modal on overlay click or close button
document.addEventListener('click', (e) => {
  // Close button
  const closeBtn = e.target.closest('.modal-close, [data-modal-close]');
  if (closeBtn) {
    const overlay = closeBtn.closest('.modal-overlay');
    if (overlay) BunkerModal.hide(overlay.id);
    return;
  }

  // Overlay click (outside modal container)
  if (e.target.classList.contains('modal-overlay') && e.target.classList.contains('visible')) {
    BunkerModal.hide(e.target.id);
  }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const openModal = document.querySelector('.modal-overlay.visible');
    if (openModal) BunkerModal.hide(openModal.id);
  }
});

// Modal trigger buttons
document.addEventListener('click', (e) => {
  const trigger = e.target.closest('[data-modal-target]');
  if (trigger) {
    const targetId = trigger.getAttribute('data-modal-target');
    BunkerModal.show(targetId);
  }
});


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
  bodyEl.textContent = message;
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
      BunkerModal.hide('confirmationModal');
    };

    const handleCancel = () => {
      finish(false);
      BunkerModal.hide('confirmationModal');
    };

    const handleHidden = () => {
      finish(false);
    };

    confirmBtn.addEventListener('click', handleConfirm);
    cancelBtn.addEventListener('click', handleCancel);
    modalEl.addEventListener('modal:hidden', handleHidden);

    BunkerModal.show('confirmationModal');
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

window.formatRelativeTimestamp = function formatRelativeTimestamp(value, options = {}) {
  const { fallback = '—', futurePrefix = true } = options;
  const parsed = window.parseServerDateTime(value);
  if (!parsed) return value || fallback;

  const diffMs = parsed.getTime() - Date.now();
  const isFuture = diffMs > 0;
  const totalMinutes = Math.max(0, Math.floor(Math.abs(diffMs) / 60000));

  if (Math.abs(diffMs) < 60000) {
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
