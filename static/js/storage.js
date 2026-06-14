(function () {
  const repairMarkerBtn = document.getElementById('repairMarkerBtn');
  const repairMarkerError = document.getElementById('repairMarkerError');

  function showInlineError(element, message) {
    if (!element) return;
    element.textContent = message;
    element.classList.remove('d-none');
  }

  function hideInlineError(element) {
    if (!element) return;
    element.textContent = '';
    element.classList.add('d-none');
  }

  function reloadAfterNotification() {
    window.setTimeout(() => window.location.reload(), 1800);
  }

  async function repairMarker() {
    hideInlineError(repairMarkerError);
    const confirmed = await window.showConfirmationDialog({
      title: 'Repair Storage Marker',
      message: `This recreates the small SimpleSaferServer marker file inside your storage location.

Cloud backup uses this marker to avoid syncing the wrong or empty folder.`,
      confirmLabel: 'Repair Marker',
      confirmClass: 'btn-primary'
    });
    if (!confirmed) return;
    window.AsyncButtonState.start(repairMarkerBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/storage/repair-marker', {
        method: 'POST'
      });
      window.AsyncButtonState.success(repairMarkerBtn);
      if (window.showAlert) window.showAlert(message || 'Storage marker repaired.', 'success');
      reloadAfterNotification();
    } catch (error) {
      window.AsyncButtonState.error(repairMarkerBtn);
      showInlineError(repairMarkerError, error.message || 'Could not repair storage marker.');
    }
  }

  if (repairMarkerBtn) repairMarkerBtn.addEventListener('click', repairMarker);
})();
