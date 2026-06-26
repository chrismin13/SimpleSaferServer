(function () {
  const runSafetyCheckBtn = document.getElementById('runSafetyCheckBtn');
  const runSafetyCheckError = document.getElementById('runSafetyCheckError');
  const storageSafetyChecks = document.getElementById('storageSafetyChecks');
  const storageCurrentStatusLine = document.getElementById('storageCurrentStatusLine');
  const storageCurrentStatusNote = document.getElementById('storageCurrentStatusNote');
  const storageLastVerified = document.getElementById('storageLastVerified');
  const repairMarkerBtn = document.getElementById('repairMarkerBtn');
  const repairMarkerError = document.getElementById('repairMarkerError');
  const defaultCopy = {
    checks: {
      fallbackLabel: 'Check',
      passedLine: 'Safety check passed',
      passedNote: 'Storage location is ready for cloud backups.',
      justNow: 'Just now',
      failedLine: 'Check failed',
      failedNote: 'Storage safety check failed.',
      failedJustNow: 'Check failed just now'
    },
    safety: {
      success: 'Storage safety check passed.',
      failure: 'Storage safety check failed.',
      requestFailure: 'Could not run storage safety check.'
    },
    repair: {
      title: 'Repair Storage Marker',
      message: 'This recreates the small SimpleSaferServer marker file inside your storage location.\n\nCloud backup uses this marker to avoid syncing the wrong or empty folder.',
      confirm: 'Repair Marker',
      success: 'Storage marker repaired.',
      failure: 'Could not repair storage marker.'
    }
  };

  function mergeCopy(base, overrides) {
    if (!overrides || typeof overrides !== 'object') return base;
    Object.keys(overrides).forEach((key) => {
      if (
        overrides[key]
        && typeof overrides[key] === 'object'
        && !Array.isArray(overrides[key])
        && base[key]
        && typeof base[key] === 'object'
      ) {
        mergeCopy(base[key], overrides[key]);
      } else {
        base[key] = overrides[key];
      }
    });
    return base;
  }

  function readCopy() {
    const script = document.getElementById('storage-copy');
    if (!script) return defaultCopy;
    try {
      return mergeCopy(JSON.parse(JSON.stringify(defaultCopy)), JSON.parse(script.textContent || '{}'));
    } catch (error) {
      console.error('Could not read Storage page copy:', error);
      return defaultCopy;
    }
  }

  const copy = readCopy();

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
      label.append(` ${check.label || copy.checks.fallbackLabel}`);

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
      storageCurrentStatusLine.append(icon, ` ${copy.checks.passedLine}`);
      storageCurrentStatusNote.textContent = copy.checks.passedNote;
      if (storageLastVerified) storageLastVerified.textContent = copy.checks.justNow;
      return;
    }
    storageCurrentStatusLine.className = 'storage-error-line';
    icon.className = 'fas fa-circle-xmark';
    storageCurrentStatusLine.append(icon, ` ${copy.checks.failedLine}`);
    storageCurrentStatusNote.textContent = error || copy.checks.failedNote;
    if (storageLastVerified) storageLastVerified.textContent = copy.checks.failedJustNow;
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
        if (window.showAlert) window.showAlert(message || copy.safety.success, 'success');
      } else {
        window.AsyncButtonState.error(runSafetyCheckBtn);
        showInlineError(runSafetyCheckError, (data && data.error) || message || copy.safety.failure);
      }
    } catch (error) {
      window.AsyncButtonState.error(runSafetyCheckBtn);
      showInlineError(runSafetyCheckError, error.message || copy.safety.requestFailure);
    }
  }

  async function repairMarker() {
    hideInlineError(repairMarkerError);
    const confirmed = await window.showConfirmationDialog({
      title: copy.repair.title,
      message: copy.repair.message,
      confirmLabel: copy.repair.confirm,
      confirmClass: 'btn-primary'
    });
    if (!confirmed) return;
    window.AsyncButtonState.start(repairMarkerBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/storage/repair-marker', {
        method: 'POST'
      });
      window.AsyncButtonState.success(repairMarkerBtn);
      if (window.showAlert) window.showAlert(message || copy.repair.success, 'success');
      reloadAfterNotification();
    } catch (error) {
      window.AsyncButtonState.error(repairMarkerBtn);
      showInlineError(repairMarkerError, error.message || copy.repair.failure);
    }
  }

  if (runSafetyCheckBtn) runSafetyCheckBtn.addEventListener('click', runSafetyCheck);
  if (repairMarkerBtn) repairMarkerBtn.addEventListener('click', repairMarker);
})();
