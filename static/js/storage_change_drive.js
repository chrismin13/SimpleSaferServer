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
  const defaultCopy = {
    drives: {
      unknownDrive: 'Unknown Drive',
      mountedAt: 'mounted at {mountpoint}',
      partitionCount: '{count} partition(s)',
      blankDisk: 'blank',
      selectDisk: 'Select a disk...',
      noCandidateDisks: 'No candidate disks found',
      selectPartition: 'Select an NTFS partition...',
      noNtfsPartitions: 'No NTFS partitions found'
    },
    status: {
      refreshingDrives: 'Refreshing drives...',
      driveListRefreshed: 'Drive list refreshed.',
      refreshingPartitions: 'Refreshing partitions...',
      partitionListRefreshed: 'Partition list refreshed.',
      unmountingDisk: 'Unmounting selected disk...',
      driveUnmounted: 'Drive unmounted.',
      formattingDisk: 'Formatting selected disk...',
      driveFormatted: 'Drive formatted as NTFS.',
      unmountingPartition: 'Unmounting selected partition...',
      partitionUnmounted: 'Partition unmounted.',
      applyingDrive: 'Applying managed drive...',
      managedDriveSaved: 'Managed drive saved.'
    },
    errors: {
      refreshDrivesFailed: 'Failed to refresh drives.',
      refreshPartitionsFailed: 'Failed to refresh partitions.',
      selectDiskToUnmount: 'Select a disk to unmount first.',
      selectDiskToFormat: 'Select a disk to format first.',
      unmountDiskFailed: 'Failed to unmount the selected disk.',
      formatDiskFailed: 'Failed to format the selected disk.',
      selectPartitionToUnmount: 'Select an NTFS partition to unmount first.',
      unmountPartitionFailed: 'Failed to unmount the selected partition.',
      selectPartition: 'Select an NTFS partition first.',
      mountPointRequired: 'Mount point is required.',
      useDriveFailed: 'Failed to use the selected drive.',
      noDetails: 'No additional details available.'
    },
    confirm: {
      unmountDriveTitle: 'Unmount Drive',
      unmountDriveMessage: 'This temporarily unmounts mounted partitions on the selected disk. It does not change SimpleSaferServer storage configuration.',
      unmountConfirm: 'Unmount',
      formatDriveTitle: 'Format Drive',
      formatDriveMessage: 'Formatting {disk} deletes all files and partitions on that disk.\n\nSimpleSaferServer storage will not change until you use the NTFS partition in the next section.',
      formatDriveConfirm: 'Format Drive',
      unmountPartitionTitle: 'Unmount Partition',
      unmountPartitionMessage: 'This temporarily unmounts the selected partition so it can be used as the managed drive.',
      useDriveTitle: 'Use This Drive',
      useDriveMessage: 'Use {partition} as SimpleSaferServer storage at {mount_point}?',
      useDriveConfirm: 'Use This Drive'
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
    const script = document.getElementById('storage-change-drive-copy');
    if (!script) return defaultCopy;
    try {
      return mergeCopy(JSON.parse(JSON.stringify(defaultCopy)), JSON.parse(script.textContent || '{}'));
    } catch (error) {
      console.error('Could not read Storage change-drive page copy:', error);
      return defaultCopy;
    }
  }

  const copy = readCopy();

  function copyTemplate(template, values) {
    return Object.keys(values || {}).reduce(
      (message, key) => message.replaceAll(`{${key}}`, values[key]),
      template || ''
    );
  }

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
    const bits = [drive.path, drive.model || copy.drives.unknownDrive, drive.size || '', drive.type || ''];
    return bits.filter(Boolean).join(' · ');
  }

  function partitionLabel(partition) {
    const mountedAt = partition.mountpoint
      ? copyTemplate(copy.drives.mountedAt, { mountpoint: partition.mountpoint })
      : '';
    const bits = [partition.path, partition.size || '', partition.label || '', mountedAt];
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
    resetSelect(formatDriveSelect, drives.length ? copy.drives.selectDisk : copy.drives.noCandidateDisks);
    drives.forEach((drive) => {
      const option = document.createElement('option');
      option.value = drive.path;
      const partitionCount = (drive.partitions || []).length;
      const partitionLabelText = partitionCount
        ? copyTemplate(copy.drives.partitionCount, { count: partitionCount })
        : copy.drives.blankDisk;
      option.textContent = `${driveLabel(drive)} · ${partitionLabelText}`;
      formatDriveSelect.appendChild(option);
    });
  }

  function populatePartitions(drives) {
    resetSelect(backupDriveSelect, drives.length ? copy.drives.selectPartition : copy.drives.noNtfsPartitions);
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
    setStatus(formatFeedback, copy.status.refreshingDrives, 'info');
    window.AsyncButtonState.start(refreshFormatDrivesBtn);
    try {
      const { data } = await window.ApiClient.fetchJson('/api/backup_drive/format-drives');
      populateFormatDrives(data.drives || []);
      setStatus(formatFeedback, copy.status.driveListRefreshed, 'success');
      window.AsyncButtonState.success(refreshFormatDrivesBtn);
    } catch (error) {
      showError(formatFeedback, error.message || copy.errors.refreshDrivesFailed, error.details);
      window.AsyncButtonState.error(refreshFormatDrivesBtn);
    }
  }

  async function refreshPartitions() {
    hideError(partitionFeedback);
    setStatus(partitionFeedback, copy.status.refreshingPartitions, 'info');
    window.AsyncButtonState.start(refreshPartitionsBtn);
    try {
      const { data } = await window.ApiClient.fetchJson('/api/backup_drive/drives');
      populatePartitions(data.drives || []);
      setStatus(partitionFeedback, copy.status.partitionListRefreshed, 'success');
      window.AsyncButtonState.success(refreshPartitionsBtn);
    } catch (error) {
      showError(partitionFeedback, error.message || copy.errors.refreshPartitionsFailed, error.details);
      window.AsyncButtonState.error(refreshPartitionsBtn);
    }
  }

  async function unmountFormatDrive() {
    hideError(formatFeedback);
    if (!formatDriveSelect || !formatDriveSelect.value) {
      showError(formatFeedback, copy.errors.selectDiskToUnmount);
      return;
    }
    const confirmed = await window.showConfirmationDialog({
      title: copy.confirm.unmountDriveTitle,
      message: copy.confirm.unmountDriveMessage,
      confirmLabel: copy.confirm.unmountConfirm,
      confirmClass: 'btn-warning'
    });
    if (!confirmed) return;

    setStatus(formatFeedback, copy.status.unmountingDisk, 'info');
    window.AsyncButtonState.start(unmountFormatDriveBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/backup_drive/unmount', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ disk: formatDriveSelect.value })
      });
      setStatus(formatFeedback, message || copy.status.driveUnmounted, 'success');
      window.AsyncButtonState.success(unmountFormatDriveBtn);
      await refreshFormatDrives();
    } catch (error) {
      showError(formatFeedback, error.message || copy.errors.unmountDiskFailed, error.details);
      window.AsyncButtonState.error(unmountFormatDriveBtn);
    }
  }

  async function formatDrive() {
    hideError(formatFeedback);
    if (!formatDriveSelect || !formatDriveSelect.value) {
      showError(formatFeedback, copy.errors.selectDiskToFormat);
      return;
    }
    const confirmed = await window.showConfirmationDialog({
      title: copy.confirm.formatDriveTitle,
      message: copyTemplate(copy.confirm.formatDriveMessage, { disk: formatDriveSelect.value }),
      confirmLabel: copy.confirm.formatDriveConfirm,
      confirmClass: 'btn-danger'
    });
    if (!confirmed) return;

    setStatus(formatFeedback, copy.status.formattingDisk, 'warning');
    window.AsyncButtonState.start(formatDriveBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/backup_drive/format', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ disk: formatDriveSelect.value })
      });
      setStatus(formatFeedback, message || copy.status.driveFormatted, 'success');
      if (window.showAlert) window.showAlert(message || copy.status.driveFormatted, 'success');
      window.AsyncButtonState.success(formatDriveBtn);
      await refreshFormatDrives();
      await refreshPartitions();
    } catch (error) {
      showError(formatFeedback, error.message || copy.errors.formatDiskFailed, error.details);
      window.AsyncButtonState.error(formatDriveBtn);
    }
  }

  async function unmountPartition() {
    hideError(partitionFeedback);
    if (!backupDriveSelect || !backupDriveSelect.value) {
      showError(partitionFeedback, copy.errors.selectPartitionToUnmount);
      return;
    }
    const confirmed = await window.showConfirmationDialog({
      title: copy.confirm.unmountPartitionTitle,
      message: copy.confirm.unmountPartitionMessage,
      confirmLabel: copy.confirm.unmountConfirm,
      confirmClass: 'btn-warning'
    });
    if (!confirmed) return;

    setStatus(partitionFeedback, copy.status.unmountingPartition, 'info');
    window.AsyncButtonState.start(unmountPartitionBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/backup_drive/unmount', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ partition: backupDriveSelect.value })
      });
      setStatus(partitionFeedback, message || copy.status.partitionUnmounted, 'success');
      window.AsyncButtonState.success(unmountPartitionBtn);
      await refreshPartitions();
    } catch (error) {
      showError(partitionFeedback, error.message || copy.errors.unmountPartitionFailed, error.details);
      window.AsyncButtonState.error(unmountPartitionBtn);
    }
  }

  async function useDrive() {
    hideError(partitionFeedback);
    if (!backupDriveSelect || !backupDriveSelect.value) {
      showError(partitionFeedback, copy.errors.selectPartition);
      return;
    }
    const mountPoint = mountPointInput ? mountPointInput.value.trim() : '';
    if (!mountPoint) {
      showError(partitionFeedback, copy.errors.mountPointRequired);
      return;
    }

    const confirmed = await window.showConfirmationDialog({
      title: copy.confirm.useDriveTitle,
      message: copyTemplate(copy.confirm.useDriveMessage, {
        partition: backupDriveSelect.value,
        mount_point: mountPoint
      }),
      confirmLabel: copy.confirm.useDriveConfirm,
      confirmClass: 'btn-primary'
    });
    if (!confirmed) return;

    setStatus(partitionFeedback, copy.status.applyingDrive, 'info');
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
      setStatus(partitionFeedback, result.message || copy.status.managedDriveSaved, 'success');
      if (window.showAlert) window.showAlert(result.message || copy.status.managedDriveSaved, 'success');
      window.AsyncButtonState.success(useDriveBtn);
      window.setTimeout(() => {
        window.location.assign('/storage');
      }, 900);
    } catch (error) {
      showError(partitionFeedback, error.message || copy.errors.useDriveFailed, error.details);
      window.AsyncButtonState.error(useDriveBtn);
    }
  }

  function wireDetailsButton(feedback) {
    if (!feedback.detailsBtn) return;
    feedback.detailsBtn.addEventListener('click', () => {
      if (errorDetailsTextEl) {
        errorDetailsTextEl.textContent = feedback.details || copy.errors.noDetails;
      }
      if (window.AppModal) window.AppModal.show('backupDriveSetupErrorDetailsModal');
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
