(function () {
  const existingPathInput = document.getElementById('existingStoragePath');
  const saveExistingBtn = document.getElementById('saveExistingStorageBtn');
  const existingError = document.getElementById('existingStorageError');
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
      window.location.reload();
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
      window.location.reload();
    } catch (error) {
      window.AsyncButtonState.error(repairMarkerBtn);
      showInlineError(repairMarkerError, error.message || 'Could not repair storage marker.');
    }
  }

  if (saveExistingBtn) saveExistingBtn.addEventListener('click', saveExistingStorage);
  if (repairMarkerBtn) repairMarkerBtn.addEventListener('click', repairMarker);

  const statusEl = document.getElementById('driveSetupStatus');
  const errorEl = document.getElementById('driveSetupError');
  const errorTextEl = document.getElementById('driveSetupErrorText');
  const errorDetailsBtn = document.getElementById('driveSetupErrorDetailsBtn');
  const errorDetailsTextEl = document.getElementById('backupDriveSetupErrorDetailsText');
  const scanBtn = document.getElementById('scanBackupDrivesBtn');
  const unmountBtn = document.getElementById('unmountBackupDriveBtn');
  const applyBtn = document.getElementById('applyBackupDriveBtn');
  const driveSelect = document.getElementById('backupDriveSelect');
  const mountPointInput = document.getElementById('backupDriveMountPoint');
  const ntfsDriverSelect = document.getElementById('backupDriveNtfsDriver');
  const configuredMountPointValue = document.getElementById('configuredMountPointValue');
  const configuredUuidValue = document.getElementById('configuredUuidValue');
  const configuredUsbIdValue = document.getElementById('configuredUsbIdValue');
  let currentDriveSetupErrorDetails = '';

  function setDriveSetupStatus(message, type) {
    if (!statusEl) return;
    statusEl.textContent = message || '';
    statusEl.className = 'drive-setup-status';
    const classMap = {
      info: 'text-info',
      success: 'text-success',
      error: 'text-danger',
      warning: 'text-warning'
    };
    statusEl.classList.add(classMap[type || 'info'] || 'text-muted');
  }

  function showDriveSetupError(message, details) {
    if (!errorEl || !errorTextEl) return;
    errorTextEl.textContent = message;
    errorEl.classList.remove('d-none');
    currentDriveSetupErrorDetails = details || '';
    if (errorDetailsBtn) errorDetailsBtn.classList.toggle('d-none', !currentDriveSetupErrorDetails);
    setDriveSetupStatus('', 'info');
  }

  function hideDriveSetupError() {
    if (!errorEl || !errorTextEl) return;
    errorEl.classList.add('d-none');
    errorTextEl.textContent = '';
    if (errorDetailsBtn) errorDetailsBtn.classList.add('d-none');
    currentDriveSetupErrorDetails = '';
  }

  function populateDriveSelect(drives) {
    if (!driveSelect) return;
    driveSelect.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = drives.length ? 'Select an NTFS partition' : 'No NTFS partitions found';
    driveSelect.appendChild(placeholder);

    drives.forEach((drive) => {
      const group = document.createElement('optgroup');
      group.label = `${drive.model} (${drive.size || 'unknown size'})`;
      (drive.partitions || []).forEach((partition) => {
        const option = document.createElement('option');
        option.value = partition.path;
        option.textContent = `${partition.path}${partition.size ? ` (${partition.size})` : ''}`;
        group.appendChild(option);
      });
      if (group.children.length > 0) driveSelect.appendChild(group);
    });
  }

  async function scanDrives() {
    hideDriveSetupError();
    setDriveSetupStatus('Scanning connected drives...', 'info');
    if (window.AsyncButtonState && scanBtn) window.AsyncButtonState.start(scanBtn);
    try {
      const { data } = await window.ApiClient.fetchJson('/api/backup_drive/drives');
      populateDriveSelect(data.drives || []);
      setDriveSetupStatus('Drive scan complete.', 'success');
      if (window.AsyncButtonState && scanBtn) window.AsyncButtonState.success(scanBtn);
    } catch (error) {
      showDriveSetupError(error.message || 'Failed to scan connected drives.', error.details);
      if (window.AsyncButtonState && scanBtn) window.AsyncButtonState.error(scanBtn);
    }
  }

  async function unmountSelectedDrive() {
    hideDriveSetupError();
    if (!driveSelect || !driveSelect.value) {
      showDriveSetupError('Select a drive partition to unmount first.');
      return;
    }
    const confirmed = await window.showConfirmationDialog({
      title: 'Unmount Selected Drive',
      message: 'This temporarily unmounts the selected partition so drive setup can continue.',
      confirmLabel: 'Unmount',
      confirmClass: 'btn-warning'
    });
    if (!confirmed) return;

    setDriveSetupStatus('Unmounting selected drive...', 'info');
    if (window.AsyncButtonState && unmountBtn) window.AsyncButtonState.start(unmountBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/backup_drive/unmount', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ partition: driveSelect.value })
      });
      setDriveSetupStatus(message || 'Drive unmounted successfully.', 'success');
      if (window.AsyncButtonState && unmountBtn) window.AsyncButtonState.success(unmountBtn);
    } catch (error) {
      showDriveSetupError(error.message || 'Failed to unmount the selected drive.', error.details);
      if (window.AsyncButtonState && unmountBtn) window.AsyncButtonState.error(unmountBtn);
    }
  }

  async function applyDriveSetup() {
    hideDriveSetupError();
    if (!driveSelect || !driveSelect.value) {
      showDriveSetupError('Select a drive partition first.');
      return;
    }
    if (!mountPointInput || !mountPointInput.value.trim()) {
      showDriveSetupError('Storage path is required.');
      return;
    }

    setDriveSetupStatus('Applying drive setup...', 'info');
    if (window.AsyncButtonState && applyBtn) window.AsyncButtonState.start(applyBtn);
    try {
      const { data } = await window.ApiClient.fetchJson('/api/backup_drive/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          partition: driveSelect.value,
          mount_point: mountPointInput.value.trim(),
          ntfs_driver: ntfsDriverSelect ? ntfsDriverSelect.value : 'ntfs-3g'
        })
      });
      const result = data.result || {};
      setDriveSetupStatus(result.message || 'Drive setup updated successfully.', 'success');
      if (configuredMountPointValue) configuredMountPointValue.textContent = result.mount_point || mountPointInput.value.trim();
      if (configuredUuidValue) configuredUuidValue.textContent = result.uuid || '—';
      if (configuredUsbIdValue) configuredUsbIdValue.textContent = result.usb_id || '—';
      if (window.showAlert) window.showAlert(result.message || 'Drive setup updated successfully.', 'success');
      if (window.AsyncButtonState && applyBtn) window.AsyncButtonState.success(applyBtn);
      window.location.reload();
    } catch (error) {
      showDriveSetupError(error.message || 'Failed to apply drive setup.', error.details);
      if (window.AsyncButtonState && applyBtn) window.AsyncButtonState.error(applyBtn);
    }
  }

  if (errorDetailsBtn) {
    errorDetailsBtn.addEventListener('click', () => {
      if (errorDetailsTextEl) {
        errorDetailsTextEl.textContent = currentDriveSetupErrorDetails || 'No additional details available.';
      }
      if (window.BunkerModal) window.BunkerModal.show('backupDriveSetupErrorDetailsModal');
    });
  }
  if (scanBtn) scanBtn.addEventListener('click', scanDrives);
  if (unmountBtn) unmountBtn.addEventListener('click', unmountSelectedDrive);
  if (applyBtn) applyBtn.addEventListener('click', applyDriveSetup);
})();
