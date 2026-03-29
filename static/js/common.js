/* ============================================================
   COMMON.JS — Vanilla JS UI System (replaces Bootstrap JS)
   Modal, Collapse, Tooltip, and Confirmation Dialog
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
  const alertDiv = document.createElement('div');
  alertDiv.className = `alert alert-${type}`;

  const icon = document.createElement('i');
  icon.className = `fas ${
    type === 'success'
      ? 'fa-check-circle'
      : type === 'danger'
      ? 'fa-exclamation-triangle'
      : type === 'warning'
      ? 'fa-exclamation-circle'
      : 'fa-info-circle'
  }`;

  const messageSpan = document.createElement('span');
  messageSpan.textContent = message;

  alertDiv.appendChild(icon);
  alertDiv.appendChild(messageSpan);
  const target = container || document.querySelector('.page-alerts') || document.querySelector('.main-content') || document.body;
  target.prepend(alertDiv);

  setTimeout(() => {
    alertDiv.style.opacity = '0';
    alertDiv.style.transition = 'opacity 300ms';
    setTimeout(() => alertDiv.remove(), 300);
  }, 4000);
};


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
