(function () {
  const formatDriveSelect = document.getElementById('formatDriveSelect');
  const backupDriveSelect = document.getElementById('backupDriveSelect');
  const mountPointInput = document.getElementById('backupDriveMountPoint');
  const ntfsDriverSelect = document.getElementById('backupDriveNtfsDriver');

  const refreshFormatDrivesBtn = document.getElementById('refreshFormatDrivesBtn');
  const unmountFormatDriveBtn = document.getElementById('unmountFormatDriveBtn');
  const formatDriveBtn = document.getElementById('formatDriveBtn');
  const refreshPartitionsBtn = document.getElementById('refreshPartitionsBtn');
  const unmountPartitionBtn = document.getElementById('unmountPartitionBtn');
  const useDriveBtn = document.getElementById('useDriveBtn');

  const errorDetailsTextEl = document.getElementById('backupDriveSetupErrorDetailsText');

  const formatFeedback = {
    status: document.getElementById('formatDriveStatus'),
    error: document.getElementById('formatDriveError'),
    errorText: document.getElementById('formatDriveErrorText'),
    detailsBtn: document.getElementById('formatDriveErrorDetailsBtn'),
    details: ''
  };
  const partitionFeedback = {
    status: document.getElementById('partitionDriveStatus'),
    error: document.getElementById('partitionDriveError'),
    errorText: document.getElementById('partitionDriveErrorText'),
    detailsBtn: document.getElementById('partitionDriveErrorDetailsBtn'),
    details: ''
  };

  function setStatus(feedback, message, type) {
    if (!feedback.status) return;
    feedback.status.textContent = message || '';
    feedback.status.className = 'drive-setup-status';
    const classMap = {
      info: 'text-info',
      success: 'text-success',
      error: 'text-danger',
      warning: 'text-warning'
    };
    feedback.status.classList.add(classMap[type || 'info'] || 'text-muted');
  }

  function hideError(feedback) {
    if (!feedback.error || !feedback.errorText) return;
    feedback.error.classList.add('d-none');
    feedback.errorText.textContent = '';
    feedback.details = '';
    if (feedback.detailsBtn) feedback.detailsBtn.classList.add('d-none');
  }

  function showError(feedback, message, details) {
    if (!feedback.error || !feedback.errorText) return;
    feedback.errorText.textContent = message;
    feedback.error.classList.remove('d-none');
    feedback.details = details || '';
    if (feedback.detailsBtn) feedback.detailsBtn.classList.toggle('d-none', !feedback.details);
    setStatus(feedback, '', 'info');
  }

  function driveLabel(drive) {
    const bits = [drive.path, drive.model || 'Unknown Drive', drive.size || '', drive.type || ''];
    return bits.filter(Boolean).join(' · ');
  }

  function partitionLabel(partition) {
    const bits = [partition.path, partition.size || '', partition.label || '', partition.mountpoint ? `mounted at ${partition.mountpoint}` : ''];
    return bits.filter(Boolean).join(' · ');
  }

  function resetSelect(select, label) {
    if (!select) return;
    select.innerHTML = '';
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = label;
    select.appendChild(placeholder);
  }

  function populateFormatDrives(drives) {
    resetSelect(formatDriveSelect, drives.length ? 'Select a disk...' : 'No candidate disks found');
    drives.forEach((drive) => {
      const option = document.createElement('option');
      option.value = drive.path;
      const partitionCount = (drive.partitions || []).length;
      option.textContent = `${driveLabel(drive)}${partitionCount ? ` · ${partitionCount} partition(s)` : ' · blank'}`;
      formatDriveSelect.appendChild(option);
    });
  }

  function populatePartitions(drives) {
    resetSelect(backupDriveSelect, drives.length ? 'Select an NTFS partition...' : 'No NTFS partitions found');
    drives.forEach((drive) => {
      const group = document.createElement('optgroup');
      group.label = driveLabel(drive);
      (drive.partitions || []).forEach((partition) => {
        const option = document.createElement('option');
        option.value = partition.path;
        option.textContent = partitionLabel(partition);
        group.appendChild(option);
      });
      if (group.children.length > 0) backupDriveSelect.appendChild(group);
    });
  }

  async function refreshFormatDrives() {
    hideError(formatFeedback);
    setStatus(formatFeedback, 'Refreshing drives...', 'info');
    window.AsyncButtonState.start(refreshFormatDrivesBtn);
    try {
      const { data } = await window.ApiClient.fetchJson('/api/backup_drive/format-drives');
      populateFormatDrives(data.drives || []);
      setStatus(formatFeedback, 'Drive list refreshed.', 'success');
      window.AsyncButtonState.success(refreshFormatDrivesBtn);
    } catch (error) {
      showError(formatFeedback, error.message || 'Failed to refresh drives.', error.details);
      window.AsyncButtonState.error(refreshFormatDrivesBtn);
    }
  }

  async function refreshPartitions() {
    hideError(partitionFeedback);
    setStatus(partitionFeedback, 'Refreshing partitions...', 'info');
    window.AsyncButtonState.start(refreshPartitionsBtn);
    try {
      const { data } = await window.ApiClient.fetchJson('/api/backup_drive/drives');
      populatePartitions(data.drives || []);
      setStatus(partitionFeedback, 'Partition list refreshed.', 'success');
      window.AsyncButtonState.success(refreshPartitionsBtn);
    } catch (error) {
      showError(partitionFeedback, error.message || 'Failed to refresh partitions.', error.details);
      window.AsyncButtonState.error(refreshPartitionsBtn);
    }
  }

  async function unmountFormatDrive() {
    hideError(formatFeedback);
    if (!formatDriveSelect || !formatDriveSelect.value) {
      showError(formatFeedback, 'Select a disk to unmount first.');
      return;
    }
    const confirmed = await window.showConfirmationDialog({
      title: 'Unmount Drive',
      message: 'This temporarily unmounts mounted partitions on the selected disk. It does not change SimpleSaferServer storage configuration.',
      confirmLabel: 'Unmount',
      confirmClass: 'btn-warning'
    });
    if (!confirmed) return;

    setStatus(formatFeedback, 'Unmounting selected disk...', 'info');
    window.AsyncButtonState.start(unmountFormatDriveBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/backup_drive/unmount', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ disk: formatDriveSelect.value })
      });
      setStatus(formatFeedback, message || 'Drive unmounted.', 'success');
      window.AsyncButtonState.success(unmountFormatDriveBtn);
      await refreshFormatDrives();
    } catch (error) {
      showError(formatFeedback, error.message || 'Failed to unmount the selected disk.', error.details);
      window.AsyncButtonState.error(unmountFormatDriveBtn);
    }
  }

  async function formatDrive() {
    hideError(formatFeedback);
    if (!formatDriveSelect || !formatDriveSelect.value) {
      showError(formatFeedback, 'Select a disk to format first.');
      return;
    }
    const confirmed = await window.showConfirmationDialog({
      title: 'Format Drive',
      message: `Formatting ${formatDriveSelect.value} deletes all files and partitions on that disk.

SimpleSaferServer storage will not change until you use the NTFS partition in the next section.`,
      confirmLabel: 'Format Drive',
      confirmClass: 'btn-danger'
    });
    if (!confirmed) return;

    setStatus(formatFeedback, 'Formatting selected disk...', 'warning');
    window.AsyncButtonState.start(formatDriveBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/backup_drive/format', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ disk: formatDriveSelect.value })
      });
      setStatus(formatFeedback, message || 'Drive formatted as NTFS.', 'success');
      if (window.showAlert) window.showAlert(message || 'Drive formatted as NTFS.', 'success');
      window.AsyncButtonState.success(formatDriveBtn);
      await refreshFormatDrives();
      await refreshPartitions();
    } catch (error) {
      showError(formatFeedback, error.message || 'Failed to format the selected disk.', error.details);
      window.AsyncButtonState.error(formatDriveBtn);
    }
  }

  async function unmountPartition() {
    hideError(partitionFeedback);
    if (!backupDriveSelect || !backupDriveSelect.value) {
      showError(partitionFeedback, 'Select an NTFS partition to unmount first.');
      return;
    }
    const confirmed = await window.showConfirmationDialog({
      title: 'Unmount Partition',
      message: 'This temporarily unmounts the selected partition so it can be used as the managed drive.',
      confirmLabel: 'Unmount',
      confirmClass: 'btn-warning'
    });
    if (!confirmed) return;

    setStatus(partitionFeedback, 'Unmounting selected partition...', 'info');
    window.AsyncButtonState.start(unmountPartitionBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/backup_drive/unmount', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ partition: backupDriveSelect.value })
      });
      setStatus(partitionFeedback, message || 'Partition unmounted.', 'success');
      window.AsyncButtonState.success(unmountPartitionBtn);
      await refreshPartitions();
    } catch (error) {
      showError(partitionFeedback, error.message || 'Failed to unmount the selected partition.', error.details);
      window.AsyncButtonState.error(unmountPartitionBtn);
    }
  }

  async function useDrive() {
    hideError(partitionFeedback);
    if (!backupDriveSelect || !backupDriveSelect.value) {
      showError(partitionFeedback, 'Select an NTFS partition first.');
      return;
    }
    const mountPoint = mountPointInput ? mountPointInput.value.trim() : '';
    if (!mountPoint) {
      showError(partitionFeedback, 'Mount point is required.');
      return;
    }

    const confirmed = await window.showConfirmationDialog({
      title: 'Use This Drive',
      message: `Use ${backupDriveSelect.value} as SimpleSaferServer storage at ${mountPoint}?`,
      confirmLabel: 'Use This Drive',
      confirmClass: 'btn-primary'
    });
    if (!confirmed) return;

    setStatus(partitionFeedback, 'Applying managed drive...', 'info');
    window.AsyncButtonState.start(useDriveBtn);
    try {
      const { data } = await window.ApiClient.fetchJson('/api/backup_drive/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          partition: backupDriveSelect.value,
          mount_point: mountPoint,
          ntfs_driver: ntfsDriverSelect ? ntfsDriverSelect.value : 'ntfs-3g'
        })
      });
      const result = data.result || {};
      setStatus(partitionFeedback, result.message || 'Managed drive saved.', 'success');
      if (window.showAlert) window.showAlert(result.message || 'Managed drive saved.', 'success');
      window.AsyncButtonState.success(useDriveBtn);
      window.setTimeout(() => {
        window.location.assign('/storage');
      }, 900);
    } catch (error) {
      showError(partitionFeedback, error.message || 'Failed to use the selected drive.', error.details);
      window.AsyncButtonState.error(useDriveBtn);
    }
  }

  function wireDetailsButton(feedback) {
    if (!feedback.detailsBtn) return;
    feedback.detailsBtn.addEventListener('click', () => {
      if (errorDetailsTextEl) {
        errorDetailsTextEl.textContent = feedback.details || 'No additional details available.';
      }
      if (window.BunkerModal) window.BunkerModal.show('backupDriveSetupErrorDetailsModal');
    });
  }

  if (refreshFormatDrivesBtn) refreshFormatDrivesBtn.addEventListener('click', refreshFormatDrives);
  if (unmountFormatDriveBtn) unmountFormatDriveBtn.addEventListener('click', unmountFormatDrive);
  if (formatDriveBtn) formatDriveBtn.addEventListener('click', formatDrive);
  if (refreshPartitionsBtn) refreshPartitionsBtn.addEventListener('click', refreshPartitions);
  if (unmountPartitionBtn) unmountPartitionBtn.addEventListener('click', unmountPartition);
  if (useDriveBtn) useDriveBtn.addEventListener('click', useDrive);
  wireDetailsButton(formatFeedback);
  wireDetailsButton(partitionFeedback);

  refreshFormatDrives();
  refreshPartitions();
})();
