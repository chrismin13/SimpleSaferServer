window.showConfirmationDialog = function showConfirmationDialog(options) {
  const {
    title = 'Confirm Action',
    message = 'Are you sure you want to continue?',
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    confirmClass = 'btn-primary'
  } = options || {};

  const modalEl = document.getElementById('confirmationModal');
  if (!modalEl || typeof bootstrap === 'undefined') {
    return Promise.resolve(window.confirm(message));
  }

  const titleEl = document.getElementById('confirmationModalTitle');
  const bodyEl = document.getElementById('confirmationModalBody');
  const confirmBtn = document.getElementById('confirmationModalConfirmBtn');
  const cancelBtn = document.getElementById('confirmationModalCancelBtn');
  const closeBtn = modalEl.querySelector('.btn-close');
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

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
      closeBtn.removeEventListener('click', handleCancel);
      modalEl.removeEventListener('hidden.bs.modal', handleHidden);
    };

    const finish = (result) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(result);
    };

    const handleConfirm = () => {
      finish(true);
      modal.hide();
    };

    const handleCancel = () => {
      finish(false);
    };

    const handleHidden = () => {
      finish(false);
    };

    confirmBtn.addEventListener('click', handleConfirm);
    cancelBtn.addEventListener('click', handleCancel);
    closeBtn.addEventListener('click', handleCancel);
    modalEl.addEventListener('hidden.bs.modal', handleHidden);
    modal.show();
  });
};

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
