(function () {
  const runSafetyCheckBtn = document.getElementById('runSafetyCheckBtn');
  const runSafetyCheckError = document.getElementById('runSafetyCheckError');
  const storageSafetyChecks = document.getElementById('storageSafetyChecks');
  const storageCurrentStatusLine = document.getElementById('storageCurrentStatusLine');
  const storageCurrentStatusNote = document.getElementById('storageCurrentStatusNote');
  const storageLastVerified = document.getElementById('storageLastVerified');
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

  function safetyIconClass(state) {
    if (state === 'pass') return 'fa-circle-check';
    if (state === 'fail') return 'fa-circle-xmark';
    return 'fa-circle-minus';
  }

  function renderSafetyChecks(checks) {
    if (!storageSafetyChecks || !Array.isArray(checks)) return;
    storageSafetyChecks.textContent = '';
    checks.forEach((check) => {
      const row = document.createElement('div');
      row.className = `storage-table-row storage-check-${check.state || 'pending'}`;

      const label = document.createElement('div');
      const icon = document.createElement('i');
      icon.className = `fas ${safetyIconClass(check.state)}`;
      label.appendChild(icon);
      label.append(` ${check.label || 'Check'}`);

      const detail = document.createElement('span');
      detail.textContent = check.detail || '';

      row.append(label, detail);
      storageSafetyChecks.appendChild(row);
    });
  }

  function renderCurrentStatus(ok, error) {
    if (!storageCurrentStatusLine || !storageCurrentStatusNote) return;
    storageCurrentStatusLine.textContent = '';
    const icon = document.createElement('i');
    if (ok) {
      storageCurrentStatusLine.className = 'storage-ready-line';
      icon.className = 'fas fa-circle-check';
      storageCurrentStatusLine.append(icon, ' Safety check passed');
      storageCurrentStatusNote.textContent = 'Storage location is ready for cloud backups.';
      if (storageLastVerified) storageLastVerified.textContent = 'Just now';
      return;
    }
    storageCurrentStatusLine.className = 'storage-error-line';
    icon.className = 'fas fa-circle-xmark';
    storageCurrentStatusLine.append(icon, ' Check failed');
    storageCurrentStatusNote.textContent = error || 'Storage safety check failed.';
    if (storageLastVerified) storageLastVerified.textContent = 'Check failed just now';
  }

  async function runSafetyCheck() {
    hideInlineError(runSafetyCheckError);
    window.AsyncButtonState.start(runSafetyCheckBtn);
    try {
      const { data, message } = await window.ApiClient.fetchJson('/api/storage/safety-check', {
        method: 'POST'
      });
      renderSafetyChecks(data && data.safety_checks);
      renderCurrentStatus(Boolean(data && data.ok), data && data.error);
      if (data && data.ok) {
        window.AsyncButtonState.success(runSafetyCheckBtn);
        if (window.showAlert) window.showAlert(message || 'Storage safety check passed.', 'success');
      } else {
        window.AsyncButtonState.error(runSafetyCheckBtn);
        showInlineError(runSafetyCheckError, (data && data.error) || message || 'Storage safety check failed.');
      }
    } catch (error) {
      window.AsyncButtonState.error(runSafetyCheckBtn);
      showInlineError(runSafetyCheckError, error.message || 'Could not run storage safety check.');
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

  if (runSafetyCheckBtn) runSafetyCheckBtn.addEventListener('click', runSafetyCheck);
  if (repairMarkerBtn) repairMarkerBtn.addEventListener('click', repairMarker);
})();
