// Cloud Backup Page JS

function renderStatusBadge(status) {
  if (status === 'Success') return '<span class="badge bg-success"><i class="fas fa-circle-check"></i> Success</span>';
  if (status === 'Failure') return '<span class="badge bg-danger"><i class="fas fa-circle-xmark"></i> Failure</span>';
  if (status === 'Running') return '<span class="badge bg-info text-dark"><i class="fas fa-spinner fa-spin"></i> Running</span>';
  if (status === 'Missing') return '<span class="badge bg-warning text-dark"><i class="fas fa-circle-exclamation"></i> Missing</span>';
  if (status === 'Not Run Yet') return '<span class="badge bg-secondary"><i class="fas fa-clock"></i> Not Run Yet</span>';
  if (status === 'Error') return '<span class="badge bg-danger"><i class="fas fa-triangle-exclamation"></i> Error</span>';
  return `<span class="badge bg-warning text-dark">${status}</span>`;
}

function loadStatus() {
  const statusBadge = document.getElementById('cloud-backup-status-badge');
  const lastRun = document.getElementById('cloud-backup-last-run');
  const nextRun = document.getElementById('cloud-backup-next-run');
  const lastDuration = document.getElementById('cloud-backup-last-duration');
  const statusError = document.getElementById('cloud-backup-status-error');

  statusBadge.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
  lastRun.textContent = '-';
  nextRun.textContent = '-';
  lastDuration.textContent = '-';
  statusError.classList.add('d-none');
  fetch('/api/cloud_backup/status')
    .then(r => r.json())
    .then(data => {
      if (!data.success) throw new Error(data.error || 'Failed to load status');
      const s = data.status;
      statusBadge.innerHTML = renderStatusBadge(s.status);
      lastRun.textContent = s.last_run || '-';
      nextRun.textContent = s.next_run || '-';
      lastDuration.textContent = s.last_run_duration || '-';
    })
    .catch(e => {
      statusBadge.innerHTML = renderStatusBadge('Error');
      statusError.textContent = e.message || 'Could not load backup status.';
      statusError.classList.remove('d-none');
    });
}

document.addEventListener('DOMContentLoaded', function () {
  // Elements
  const statusBadge = document.getElementById('cloud-backup-status-badge');
  const lastRun = document.getElementById('cloud-backup-last-run');
  const nextRun = document.getElementById('cloud-backup-next-run');
  const lastDuration = document.getElementById('cloud-backup-last-duration');
  const runBtn = document.getElementById('cloud-backup-run-btn');
  const runSpinner = document.getElementById('cloud-backup-run-spinner');
  const statusError = document.getElementById('cloud-backup-status-error');
  const logLink = document.getElementById('cloud-backup-log-link');

  const configForm = document.getElementById('cloud-backup-config-form');
  const saveBtn = document.getElementById('cloud-backup-save-btn');
  const saveSpinner = document.getElementById('cloud-backup-save-spinner');
  const configError = document.getElementById('cloud-backup-config-error');
  const configSuccess = document.getElementById('cloud-backup-config-success');
  const configSuccessMessage = document.getElementById('config-success-message');

  // Config fields
  const modeMega = document.getElementById('cloudModeMega');
  const modeAdvanced = document.getElementById('cloudModeAdvanced');
  const megaFields = document.getElementById('megaConfigFields');
  const advancedFields = document.getElementById('advancedConfigFields');
  const megaEmail = document.getElementById('megaEmail');
  const megaPassword = document.getElementById('megaPassword');
  const megaFolderPath = document.getElementById('megaFolderPath');
  const megaBrowseBtn = document.getElementById('megaBrowseBtn');
  const megaFolderWarning = document.getElementById('megaFolderWarning');
  const rcloneConfig = document.getElementById('rcloneConfig');
  const remoteName = document.getElementById('remoteName');
  const backupTime = document.getElementById('backupTime');
  const bandwidthLimit = document.getElementById('bandwidthLimit');

  // Modal elements
  const megaFolderPickerModal = new bootstrap.Modal(document.getElementById('megaFolderPickerModal'));
  const megaPickerCurrentPath = document.getElementById('megaPickerCurrentPath');
  const megaPickerDirsList = document.getElementById('megaPickerDirsList');
  const megaPickerUpBtn = document.getElementById('megaPickerUpBtn');
  const megaPickerCreateFolderBtn = document.getElementById('megaPickerCreateFolderBtn');
  const megaPickerNewFolderName = document.getElementById('megaPickerNewFolderName');
  const megaPickerSaveNewFolderBtn = document.getElementById('megaPickerSaveNewFolderBtn');
  const megaPickerError = document.getElementById('megaPickerError');
  const megaPickerSelectCurrentBtn = document.getElementById('megaPickerSelectCurrentBtn');

  // --- Schedule (Backup Time & Bandwidth) ---
  const scheduleForm = document.getElementById('cloud-backup-schedule-form');
  const scheduleSaveBtn = document.getElementById('cloud-backup-schedule-save-btn');
  const scheduleSaveSpinner = document.getElementById('cloud-backup-schedule-save-spinner');
  const scheduleError = document.getElementById('cloud-backup-schedule-error');
  const scheduleSuccess = document.getElementById('cloud-backup-schedule-success');
  const scheduleSuccessMessage = document.getElementById('schedule-success-message');

  let lastSavedSchedule = { backup_cloud_time: '', bandwidth_limit: '' };

  // Function to show temporary success message
  function showTemporarySuccess(element, message, duration = 3000) {
    element.textContent = message;
    element.classList.remove('d-none');
    setTimeout(() => {
      element.classList.add('d-none');
    }, duration);
  }

  // Add showPicker logic for backupTime field (like setup wizard)
  if (backupTime) {
    const showTimePicker = () => {
      if (typeof backupTime.showPicker === 'function') {
        backupTime.showPicker();
      }
    };
    backupTime.addEventListener('focus', showTimePicker);
    backupTime.addEventListener('click', showTimePicker);
  }

  // Add Enter key handler for MEGA password field
  if (megaPassword) {
    megaPassword.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !megaSaveCredsBtn.classList.contains('d-none')) {
        e.preventDefault();
        megaSaveCredsBtn.click();
      }
    });
  }

  function fillScheduleForm(cfg) {
    backupTime.value = (cfg.backup_cloud_time || '').padStart(5, '0');
    bandwidthLimit.value = cfg.bandwidth_limit || '';
    lastSavedSchedule = {
      backup_cloud_time: backupTime.value,
      bandwidth_limit: bandwidthLimit.value
    };
  }

  function loadSchedule() {
    scheduleError.classList.add('d-none');
    scheduleSuccess.classList.add('d-none');
    fetch('/api/cloud_backup/config')
      .then(r => r.json())
      .then(data => {
        if (!data.success) throw new Error(data.error || 'Failed to load schedule');
        fillScheduleForm(data.config);
      })
      .catch(e => {
        scheduleError.textContent = e.message || 'Could not load schedule.';
        scheduleError.classList.remove('d-none');
      });
  }

  scheduleForm.addEventListener('submit', function (e) {
    e.preventDefault();
    scheduleError.classList.add('d-none');
    scheduleSuccess.classList.add('d-none');
    scheduleSaveBtn.disabled = true;
    scheduleSaveSpinner.classList.remove('d-none');
    // Validate
    let valid = true;
    if (!backupTime.value) {
      backupTime.classList.add('is-invalid'); valid = false;
    } else { backupTime.classList.remove('is-invalid'); }
    // Bandwidth is optional, but if present, must be a string (no strict validation here)
    if (!valid) {
      scheduleSaveBtn.disabled = false;
      scheduleSaveSpinner.classList.add('d-none');
      return;
    }
    fetch('/api/cloud_backup/schedule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        backup_cloud_time: backupTime.value,
        bandwidth_limit: bandwidthLimit.value.trim()
      })
    })
      .then(r => r.json())
      .then(data => {
        if (!data.success) throw new Error(data.error || 'Failed to save schedule');
        showTemporarySuccess(scheduleSuccessMessage, 'Schedule saved successfully!');
        loadSchedule();
        loadStatus(); // update next run time
      })
      .catch(e => {
        scheduleError.textContent = e.message || 'Could not save schedule.';
        scheduleError.classList.remove('d-none');
      })
      .finally(() => {
        scheduleSaveBtn.disabled = false;
        scheduleSaveSpinner.classList.add('d-none');
      });
  });

  // --- Main Config (MEGA/rclone) ---
  // Mode switching
  function showModeFields(mode) {
    if (mode === 'mega') {
      megaFields.classList.remove('d-none');
      advancedFields.classList.add('d-none');
    } else {
      megaFields.classList.add('d-none');
      advancedFields.classList.remove('d-none');
      // If switching to advanced and current config is MEGA, auto-populate remote name
      if (modeMega.checked === false && megaEmail.value && megaFolderPath.value) {
        remoteName.value = `mega:${megaFolderPath.value}`;
      }
    }
  }
  modeMega.addEventListener('change', () => showModeFields('mega'));
  modeAdvanced.addEventListener('change', () => showModeFields('advanced'));

  // --- MEGA Credential Locking & Status ---
  const megaChangeCredsBtn = document.getElementById('megaChangeCredsBtn');
  const megaCredStatus = document.getElementById('megaCredStatus');
  const megaSaveCredsBtn = document.getElementById('megaSaveCredsBtn');
  let megaCredsLocked = false;
  let megaPickerAuth = { email: '', password: '' };

  function setMegaCredsLocked(locked, email, showStatus) {
    megaCredsLocked = locked;
    megaEmail.readOnly = locked;
    megaEmail.disabled = locked;
    megaPassword.disabled = locked;
    megaChangeCredsBtn.classList.toggle('d-none', !locked);
    megaSaveCredsBtn.classList.toggle('d-none', locked);
    megaBrowseBtn.disabled = !locked;
    if (locked) {
      megaPassword.value = '********';
      if (showStatus) {
        megaCredStatus.textContent = 'Connection successful. You are signed in.';
        megaCredStatus.classList.remove('d-none');
        megaCredStatus.classList.remove('alert-danger');
        megaCredStatus.classList.add('alert-success');
      }
    } else {
      megaPassword.value = '';
      megaCredStatus.classList.add('d-none');
    }
  }

  megaChangeCredsBtn.addEventListener('click', function () {
    setMegaCredsLocked(false);
    megaEmail.readOnly = false;
    megaEmail.disabled = false;
    megaPassword.disabled = false;
    megaPassword.value = '';
    megaFolderPath.value = '';
    megaChangeCredsBtn.classList.add('d-none');
    megaSaveCredsBtn.classList.remove('d-none');
    megaBrowseBtn.disabled = true;
    megaCredStatus.classList.add('d-none');
  });

  megaSaveCredsBtn.addEventListener('click', function () {
    // Validate and save credentials
    const email = megaEmail.value.trim();
    const password = megaPassword.value;
    if (!email.match(/^[^@\s]+@[^@\s]+\.[^@\s]+$/)) {
      megaEmail.classList.add('is-invalid');
      return;
    } else {
      megaEmail.classList.remove('is-invalid');
    }
    if (!password) {
      megaPassword.classList.add('is-invalid');
      return;
    } else {
      megaPassword.classList.remove('is-invalid');
    }
    megaSaveCredsBtn.disabled = true;
    megaSaveCredsBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Saving...';
    fetch('/api/cloud_backup/mega/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    })
      .then(r => r.json())
      .then(data => {
        megaSaveCredsBtn.disabled = false;
        megaSaveCredsBtn.innerHTML = 'Save Credentials';
        if (data.success) {
          setMegaCredsLocked(true, email, true);
        } else {
          megaCredStatus.textContent = data.error || 'Could not validate credentials.';
          megaCredStatus.classList.remove('d-none');
          megaCredStatus.classList.replace('alert-success', 'alert-danger');
        }
      })
      .catch(e => {
        megaSaveCredsBtn.disabled = false;
        megaSaveCredsBtn.innerHTML = 'Save Credentials';
        megaCredStatus.textContent = e.message || 'Could not validate credentials.';
        megaCredStatus.classList.remove('d-none');
        megaCredStatus.classList.replace('alert-success', 'alert-danger');
      });
  });

  // Update fillConfigForm to lock creds if present/valid
  function fillConfigForm(cfg) {
    if (!cfg) return;
    
    // Always populate rclone config field with current config (for switching between modes)
    rcloneConfig.value = cfg.rclone_config || '';
    
    if (cfg.cloud_mode === 'mega') {
      modeMega.checked = true;
      showModeFields('mega');
      megaEmail.value = cfg.mega_email || '';
      megaPassword.value = '';
      megaFolderPath.value = cfg.mega_folder || '';
      megaFolderWarning.classList.toggle('d-none', !cfg.mega_folder);
      // Lock creds if present and valid (simulate valid for now)
      if (cfg.mega_email && cfg.mega_folder) {
        setMegaCredsLocked(true, cfg.mega_email, true);
      } else {
        setMegaCredsLocked(false);
      }
    } else {
      modeAdvanced.checked = true;
      showModeFields('advanced');
      remoteName.value = cfg.rclone_dir || '';
      setMegaCredsLocked(false);
    }
  }

  function getConfigFormData() {
    const mode = modeMega.checked ? 'mega' : 'advanced';
    const data = { cloud_mode: mode };
    if (mode === 'mega') {
      data.mega_email = megaEmail.value.trim();
      // Only send password if credentials are not locked (i.e., password field is not empty)
      if (megaPassword.value && megaPassword.value !== '********') {
        data.mega_password = megaPassword.value;
      }
      data.mega_folder = megaFolderPath.value.trim();
    } else {
      data.rclone_config = rcloneConfig.value.trim();
      data.remote_name = remoteName.value.trim();
    }
    return data;
  }

  function loadConfig() {
    configError.classList.add('d-none');
    configSuccess.classList.add('d-none');
    fetch('/api/cloud_backup/config')
      .then(r => r.json())
      .then(data => {
        if (!data.success) throw new Error(data.error || 'Failed to load settings');
        fillConfigForm(data.config);
      })
      .catch(e => {
        configError.textContent = e.message || 'Could not load backup settings.';
        configError.classList.remove('d-none');
      });
  }

  function validateRemoteName() {
    const value = remoteName.value.trim();
    const regex = /^[a-zA-Z0-9_-]+:(?:\/[^\s]*)?$/; // e.g., myremote: or myremote:/backups
    if (!regex.test(value)) {
      remoteName.classList.add('is-invalid');
      return false;
    } else {
      remoteName.classList.remove('is-invalid');
      return true;
    }
  }

  // --- Undo ---
  // The undo functionality is removed as per the edit hint.

  // --- Save ---
  // On save, if MEGA, validate and lock creds on success
  configForm.addEventListener('submit', function (e) {
    e.preventDefault();
    configError.classList.add('d-none');
    configSuccess.classList.add('d-none');
    saveBtn.disabled = true;
    // Validate
    const data = getConfigFormData();
    let valid = true;
    if (data.cloud_mode === 'mega') {
      if (!data.mega_email.match(/^[^@\s]+@[^@\s]+\.[^@\s]+$/)) {
        megaEmail.classList.add('is-invalid'); valid = false;
      } else { megaEmail.classList.remove('is-invalid'); }
      // Only validate password if credentials are not locked (password field is not empty)
      if (megaPassword.value && megaPassword.value !== '********' && !data.mega_password) {
        megaPassword.classList.add('is-invalid'); valid = false;
      } else { megaPassword.classList.remove('is-invalid'); }
      if (!data.mega_folder) {
        megaFolderPath.classList.add('is-invalid'); valid = false;
      } else { megaFolderPath.classList.remove('is-invalid'); }
    } else {
      if (!data.rclone_config) {
        rcloneConfig.classList.add('is-invalid'); valid = false;
      } else { rcloneConfig.classList.remove('is-invalid'); }
      if (!validateRemoteName()) {
        valid = false;
      }
    }
    if (!valid) {
      saveBtn.disabled = false;
      return;
    }
    fetch('/api/cloud_backup/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
      .then(r => r.json())
      .then(data => {
        if (!data.success) throw new Error(data.error || 'Failed to save settings');
        showTemporarySuccess(configSuccessMessage, 'Cloud backup settings saved successfully!');
        // Lock creds if MEGA
        if (data.config && data.config.cloud_mode === 'mega') {
          setMegaCredsLocked(true, data.config.mega_email, true);
        }
      })
      .catch(e => {
        configError.textContent = e.message || 'Could not save backup settings.';
        configError.classList.remove('d-none');
      })
      .finally(() => {
        saveBtn.disabled = false;
      });
  });

  // --- MEGA Folder Picker ---
  megaBrowseBtn.addEventListener('click', function () {
    openMegaFolderPicker({
      getCredentials: () => {
        if (megaPassword.value === '********') {
          return { email: null, password: null };
        }
        return {
          email: megaEmail.value.trim(),
          password: megaPassword.value
        };
      },
      onSelect: (folderPath) => {
        megaFolderPath.value = folderPath;
        megaFolderWarning.classList.remove('d-none');
      },
      modalSelector: '#megaFolderPickerModal'
    });
  });

  // Add validation event listeners
  if (remoteName) {
    remoteName.addEventListener('blur', validateRemoteName);
    remoteName.addEventListener('input', validateRemoteName);
  }

  // Add mode switching event listeners
  if (modeMega) {
    modeMega.addEventListener('change', function() {
      if (this.checked) showModeFields('mega');
    });
  }
  if (modeAdvanced) {
    modeAdvanced.addEventListener('change', function() {
      if (this.checked) showModeFields('advanced');
    });
  }

  // --- Init ---
  loadStatus();
  loadConfig();
  loadSchedule();
}); 