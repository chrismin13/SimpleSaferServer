(function () {
  const existingPathInput = document.getElementById('existingStoragePath');
  const saveExistingBtn = document.getElementById('saveExistingStorageBtn');
  const existingError = document.getElementById('existingStorageError');
  const repairMarkerBtn = document.getElementById('repairMarkerBtn');
  const repairMarkerError = document.getElementById('repairMarkerError');
  const modeButtons = document.querySelectorAll('[data-storage-mode]');
  const modePanels = {
    prepared_drive: document.getElementById('preparedDriveStoragePanel'),
    existing_folder: document.getElementById('existingFolderStoragePanel')
  };

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

  function setStorageMode(mode) {
    // The Storage page mirrors setup: one mode is active and only its controls are visible.
    modeButtons.forEach((button) => {
      const isActive = button.dataset.storageMode === mode;
      button.classList.toggle('active', isActive);
      button.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    Object.entries(modePanels).forEach(([panelMode, panel]) => {
      if (!panel) return;
      panel.classList.toggle('d-none', panelMode !== mode);
    });
  }

  function reloadAfterNotification() {
    window.setTimeout(() => window.location.reload(), 1800);
  }

  async function saveExistingStorage() {
    hideInlineError(existingError);
    const path = existingPathInput ? existingPathInput.value.trim() : '';
    if (!path) {
      showInlineError(existingError, 'Enter a storage folder path.');
      return;
    }
    window.AsyncButtonState.start(saveExistingBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/storage/existing-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      window.AsyncButtonState.success(saveExistingBtn);
      if (window.showAlert) window.showAlert(message || 'Storage folder saved.', 'success');
      reloadAfterNotification();
    } catch (error) {
      window.AsyncButtonState.error(saveExistingBtn);
      showInlineError(existingError, error.message || 'Could not save storage folder.');
    }
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

  if (saveExistingBtn) saveExistingBtn.addEventListener('click', saveExistingStorage);
  if (repairMarkerBtn) repairMarkerBtn.addEventListener('click', repairMarker);
  modeButtons.forEach((button) => {
    button.addEventListener('click', () => setStorageMode(button.dataset.storageMode));
  });
})();
