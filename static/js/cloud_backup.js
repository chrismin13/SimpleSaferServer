// Cloud Backup Page JS

function renderStatusBadge(status) {
  if (status === 'Success') return '<span class="badge badge-success"><i class="fas fa-circle-check"></i> Success</span>';
  if (status === 'Failure') return '<span class="badge badge-danger"><i class="fas fa-circle-xmark"></i> Failure</span>';
  if (status === 'Running') return '<span class="badge badge-info"><i class="fas fa-spinner fa-spin"></i> Running</span>';
  if (status === 'Missing') return '<span class="badge badge-warning"><i class="fas fa-circle-exclamation"></i> Missing</span>';
  if (status === 'Not Run Yet') return '<span class="badge badge-neutral"><i class="fas fa-clock"></i> Not Run Yet</span>';
  if (status === 'Error') return '<span class="badge badge-danger"><i class="fas fa-triangle-exclamation"></i> Error</span>';
  return `<span class="badge badge-warning">${status}</span>`;
}

function loadStatus() {
  const statusBadge = document.getElementById('cloud-backup-status-badge');
  const lastRun = document.getElementById('cloud-backup-last-run');
  const nextRun = document.getElementById('cloud-backup-next-run');
  const lastDuration = document.getElementById('cloud-backup-last-duration');

  statusBadge.innerHTML = '<span class="spinner"></span>';
  lastRun.textContent = '-';
  nextRun.textContent = '-';
  lastDuration.textContent = '-';
  fetch('/api/cloud_backup/status')
    .then(r => r.json())
    .then(data => {
      if (!data.success) throw new Error(data.error || 'Failed to load status');
      const s = data.status;
      statusBadge.innerHTML = renderStatusBadge(s.status);
      lastRun.textContent = window.formatRelativeTimestamp(s.last_run, { fallback: '-' });
      lastRun.title = s.last_run || '';
      nextRun.textContent = window.formatRelativeTimestamp(s.next_run, { fallback: '-', futurePrefix: false });
      nextRun.title = s.next_run || '';
      lastDuration.textContent = s.last_run_duration || '-';
    })
    .catch(e => {
      statusBadge.innerHTML = renderStatusBadge('Error');
      showAlert(e.message || 'Could not load backup status.', 'danger');
    });
}

function runBackupNow() {
  const runBtn = document.getElementById('cloud-backup-run-btn');
  window.AsyncButtonState.start(runBtn);

  fetch('/api/cloud_backup/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
    .then(r => r.json())
    .then(data => {
      if (!data.success) throw new Error(data.error || 'Failed to start backup');
      window.AsyncButtonState.success(runBtn);
      showAlert(data.message || 'Cloud backup started.', 'success');
      loadStatus();
    })
    .catch(e => {
      window.AsyncButtonState.error(runBtn);
      showAlert(e.message || 'Could not start backup.', 'danger');
    });
}

document.addEventListener('DOMContentLoaded', function () {
  const runBtn = document.getElementById('cloud-backup-run-btn');

  const configForm = document.getElementById('cloud-backup-config-form');
  const saveBtn = document.getElementById('cloud-backup-save-btn');

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

  const scheduleForm = document.getElementById('cloud-backup-schedule-form');
  const scheduleSaveBtn = document.getElementById('cloud-backup-schedule-save-btn');

  if (backupTime) {
    const showTimePicker = () => {
      if (typeof backupTime.showPicker === 'function') {
        backupTime.showPicker();
      }
    };
    backupTime.addEventListener('focus', showTimePicker);
    backupTime.addEventListener('click', showTimePicker);
  }

  if (runBtn) {
    runBtn.addEventListener('click', function () {
      runBackupNow();
    });
  }

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
  }

  function loadSchedule() {
    fetch('/api/cloud_backup/config')
      .then(r => r.json())
      .then(data => {
        if (!data.success) throw new Error(data.error || 'Failed to load schedule');
        fillScheduleForm(data.config);
      })
      .catch(e => {
        showAlert(e.message || 'Could not load schedule.', 'danger');
      });
  }

  scheduleForm.addEventListener('submit', function (e) {
    e.preventDefault();
    let valid = true;
    if (!backupTime.value) {
      backupTime.classList.add('is-invalid'); valid = false;
    } else { backupTime.classList.remove('is-invalid'); }
    if (!valid) {
      return;
    }
    window.AsyncButtonState.start(scheduleSaveBtn);
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
        window.AsyncButtonState.success(scheduleSaveBtn);
        showAlert('Schedule saved successfully!', 'success');
        loadSchedule();
        loadStatus();
      })
      .catch(e => {
        window.AsyncButtonState.error(scheduleSaveBtn);
        showAlert(e.message || 'Could not save schedule.', 'danger');
      });
  });

  function showModeFields(mode) {
    if (mode === 'mega') {
      megaFields.classList.add('active');
      advancedFields.classList.remove('active');
    } else {
      megaFields.classList.remove('active');
      advancedFields.classList.add('active');
      if (megaEmail.value && megaFolderPath.value && !remoteName.value.trim()) {
        remoteName.value = `mega:${megaFolderPath.value}`;
      }
    }

    // Update Tab Buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === mode);
    });

    // Sync Hidden Radio Inputs (to keep save/submit logic happy)
    if (mode === 'mega' && modeMega) {
      modeMega.checked = true;
    } else if (modeAdvanced) {
      modeAdvanced.checked = true;
    }
  }

  // Bind Custom Tabs
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const mode = this.getAttribute('data-tab');
      if (mode) showModeFields(mode);
    });
  });

  const megaChangeCredsBtn = document.getElementById('megaChangeCredsBtn');
  const megaCredStatus = document.getElementById('megaCredStatus');
  const megaSaveCredsBtn = document.getElementById('megaSaveCredsBtn');
  let megaCredsLocked = false;

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
        megaCredStatus.className = 'alert alert-success mt-2';
        megaCredStatus.style.fontSize = 'var(--text-sm)';
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
    window.AsyncButtonState.start(megaSaveCredsBtn);
    fetch('/api/cloud_backup/mega/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    })
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          window.AsyncButtonState.success(megaSaveCredsBtn);
          setMegaCredsLocked(true, email, true);
        } else {
          window.AsyncButtonState.error(megaSaveCredsBtn);
          megaCredStatus.textContent = data.error || 'Could not validate credentials.';
          megaCredStatus.classList.remove('d-none');
          megaCredStatus.className = 'alert alert-danger mt-2';
          megaCredStatus.style.fontSize = 'var(--text-sm)';
        }
      })
      .catch(e => {
        window.AsyncButtonState.error(megaSaveCredsBtn);
        megaCredStatus.textContent = e.message || 'Could not validate credentials.';
        megaCredStatus.classList.remove('d-none');
        megaCredStatus.className = 'alert alert-danger mt-2';
        megaCredStatus.style.fontSize = 'var(--text-sm)';
      });
  });

  function fillConfigForm(cfg) {
    if (!cfg) return;
    rcloneConfig.value = cfg.rclone_config || '';
    if (cfg.cloud_mode === 'mega') {
      modeMega.checked = true;
      showModeFields('mega');
      megaEmail.value = cfg.mega_email || '';
      megaPassword.value = '';
      megaFolderPath.value = cfg.mega_folder || '';
      megaFolderWarning.classList.toggle('d-none', !cfg.mega_folder);
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
    fetch('/api/cloud_backup/config')
      .then(r => r.json())
      .then(data => {
        if (!data.success) throw new Error(data.error || 'Failed to load settings');
        fillConfigForm(data.config);
      })
      .catch(e => {
        showAlert(e.message || 'Could not load backup settings.', 'danger');
      });
  }

  function validateRemoteName() {
    const value = remoteName.value.trim();
    const regex = /^[a-zA-Z0-9_-]+:(?:\/[^\s]*)?$/;
    if (!regex.test(value)) {
      remoteName.classList.add('is-invalid');
      return false;
    } else {
      remoteName.classList.remove('is-invalid');
      return true;
    }
  }

  configForm.addEventListener('submit', function (e) {
    e.preventDefault();
    const data = getConfigFormData();
    let valid = true;
    if (data.cloud_mode === 'mega') {
      if (!data.mega_email.match(/^[^@\s]+@[^@\s]+\.[^@\s]+$/)) {
        megaEmail.classList.add('is-invalid'); valid = false;
      } else { megaEmail.classList.remove('is-invalid'); }
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
      return;
    }
    window.AsyncButtonState.start(saveBtn);
    fetch('/api/cloud_backup/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
      .then(r => r.json())
      .then(data => {
        if (!data.success) throw new Error(data.error || 'Failed to save settings');
        window.AsyncButtonState.success(saveBtn);
        showAlert('Cloud backup settings saved successfully!', 'success');
        if (data.config && data.config.cloud_mode === 'mega') {
          setMegaCredsLocked(true, data.config.mega_email, true);
        }
      })
      .catch(e => {
        window.AsyncButtonState.error(saveBtn);
        showAlert(e.message || 'Could not save backup settings.', 'danger');
      });
  });

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
      modalId: 'megaFolderPickerModal',
      listUrl: '/api/cloud_backup/mega/list_folders',
      createUrl: '/api/cloud_backup/mega/create_folder'
    });
  });

  if (remoteName) {
    remoteName.addEventListener('blur', validateRemoteName);
    remoteName.addEventListener('input', validateRemoteName);
  }

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

  loadStatus();
  loadConfig();
  loadSchedule();
});
