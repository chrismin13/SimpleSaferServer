/* ============================================================
   SCRIPTS.JS — Setup Wizard Logic + Task Detail Auto-Refresh
   (Mobile nav is now handled by common.js)
   ============================================================ */

document.addEventListener("DOMContentLoaded", function () {

  // --- Auto-refresh logs on the task detail page ---
  const autoRefreshCheckbox = document.getElementById("auto-refresh");
  if (autoRefreshCheckbox) {
    const logContainer = document.querySelector(".log-viewer");
    const taskName = autoRefreshCheckbox.getAttribute("data-task-name");
    let intervalId;
    let initialLoad = true;

    function scrollToBottom() {
      if (logContainer) logContainer.scrollTop = logContainer.scrollHeight;
    }

    function fetchLogs() {
      const distanceFromBottom = logContainer
        ? logContainer.scrollHeight - logContainer.scrollTop - logContainer.clientHeight
        : 0;
      const stickToBottom = distanceFromBottom < 48;

      return fetch(`/task/${encodeURIComponent(taskName)}/logs`)
        .then((resp) => resp.text())
        .then((text) => {
          if (logContainer) logContainer.textContent = text;
          if (initialLoad) {
            scrollToBottom();
            initialLoad = false;
          } else if (logContainer && stickToBottom) {
            scrollToBottom();
          }
        })
        .catch((err) => console.error(err));
    }

    function start() {
      fetchLogs();
      intervalId = setInterval(fetchLogs, 1000);
    }

    function stop() {
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
    }

    autoRefreshCheckbox.addEventListener("change", () => {
      if (autoRefreshCheckbox.checked) {
        start();
      } else {
        stop();
      }
    });

    scrollToBottom();
    start();
  }

  // --- Setup Wizard: Backup Config Step Logic ---
  function showBackupModeFields() {
    const modeRadio = document.querySelector('input[name="backupMode"]:checked');
    if (!modeRadio) return;
    const mode = modeRadio.value;
    const megaConfigFields = document.getElementById('megaConfigFields');
    const advancedConfigFields = document.getElementById('advancedConfigFields');
    if (megaConfigFields && advancedConfigFields) {
      megaConfigFields.classList.toggle('d-none', mode !== 'mega');
      advancedConfigFields.classList.toggle('d-none', mode !== 'advanced');
    }
  }

  const backupModeRadios = document.getElementsByName('backupMode');
  if (backupModeRadios && backupModeRadios.length > 0) {
    backupModeRadios.forEach(radio => {
      radio.addEventListener('change', showBackupModeFields);
    });
  }

  // --- MEGA Connect: Pressing Enter in Password triggers Connect ---
  const megaPassword = document.getElementById('megaPassword');
  const megaConnectBtn = document.getElementById('megaConnectBtn');
  if (megaPassword && megaConnectBtn) {
    megaPassword.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        megaConnectBtn.click();
      }
    });
  }

  // --- Update MEGA Connect logic ---
  const megaFolderPathArea = document.getElementById('megaFolderPathArea');
  const megaFolderPath = document.getElementById('megaFolderPath');
  const megaBrowseBtn = document.getElementById('megaBrowseBtn');

  function updateSaveBackupConfigState() {
    const saveBtn = document.getElementById('saveBackupConfigBtn');
    const modeRadio = document.querySelector('input[name="backupMode"]:checked');
    if (!saveBtn || !modeRadio) return;
    const mode = modeRadio.value;
    if (mode === 'mega') {
      const megaFolderPathArea = document.getElementById('megaFolderPathArea');
      const megaFolderPath = document.getElementById('megaFolderPath');
      const connected = megaFolderPathArea && !megaFolderPathArea.classList.contains('d-none');
      const folder = megaFolderPath && megaFolderPath.value.trim();
      saveBtn.disabled = !(connected && folder);
    } else {
      const config = document.getElementById('rcloneConfig');
      const remoteName = document.getElementById('remoteName');
      saveBtn.disabled = !(config && config.value.trim() && remoteName && remoteName.value.trim());
    }
  }

  if (megaConnectBtn) {
    megaConnectBtn.addEventListener('click', function() {
      const email = document.getElementById('megaEmail');
      const password = document.getElementById('megaPassword');
      if (!email || !password) return;
      if (!email.value.trim() || !password.value) {
        email.classList.add('is-invalid');
        password.classList.add('is-invalid');
        return;
      }
      email.classList.remove('is-invalid');
      password.classList.remove('is-invalid');
      window.AsyncButtonState.start(megaConnectBtn);
      megaConnectBtn.disabled = true;
      fetch('/api/setup/mega/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.value.trim(), password: password.value })
      })
      .then(resp => resp.json())
      .then(data => {
        if (data.success) {
          window.AsyncButtonState.success(megaConnectBtn);
        } else {
          window.AsyncButtonState.error(megaConnectBtn);
        }
        const backupConfigError = document.getElementById('backupConfigError');
        if (data.success) {
          if (megaFolderPathArea) megaFolderPathArea.classList.remove('d-none');
          if (megaFolderPath) megaFolderPath.value = '/';
          updateSaveBackupConfigState();
        } else if (backupConfigError) {
          backupConfigError.textContent = data.error || 'Failed to connect to MEGA.';
          backupConfigError.classList.remove('d-none');
        }
      })
      .catch(err => {
        window.AsyncButtonState.error(megaConnectBtn);
        const backupConfigError = document.getElementById('backupConfigError');
        if (backupConfigError) {
          backupConfigError.textContent = 'Error connecting to MEGA.';
          backupConfigError.classList.remove('d-none');
        }
      });
    });
  }

  if (megaBrowseBtn) {
    megaBrowseBtn.addEventListener('click', function() {
      openMegaFolderPicker({
        getCredentials: () => {
          return {
            email: document.getElementById('megaEmail').value.trim(),
            password: document.getElementById('megaPassword').value
          };
        },
        onSelect: (folderPath) => {
          document.getElementById('megaFolderPath').value = folderPath;
          const warning = document.getElementById('megaFolderWarning');
          if (warning) warning.classList.remove('d-none');
        },
        modalId: 'megaFolderPickerModal',
        listUrl: '/api/setup/mega/list_folders',
        createUrl: '/api/setup/mega/create_folder'
      });
    });
  }

  // Save Backup Config
  window.saveBackupConfig = function saveBackupConfig() {
    const modeRadio = document.querySelector('input[name="backupMode"]:checked');
    if (!modeRadio) return;
    const mode = modeRadio.value;
    const backupConfigError = document.getElementById('backupConfigError');
    if (backupConfigError) {
      backupConfigError.classList.add('d-none');
      backupConfigError.textContent = '';
    }
    const saveBtn = document.getElementById('saveBackupConfigBtn');
    function setSaving(saving) {
      if (!saveBtn) return;
      if (saving) {
        window.AsyncButtonState.start(saveBtn);
      }
    }
    if (mode === 'mega') {
      const emailField = document.getElementById('megaEmail');
      const passwordField = document.getElementById('megaPassword');
      const folderField = document.getElementById('megaFolderPath');
      let valid = true;
      if (!emailField || !emailField.value.trim()) {
        if (emailField) emailField.classList.add('is-invalid');
        valid = false;
      } else if (emailField) {
        emailField.classList.remove('is-invalid');
      }
      if (!passwordField || !passwordField.value) {
        if (passwordField) passwordField.classList.add('is-invalid');
        valid = false;
      } else if (passwordField) {
        passwordField.classList.remove('is-invalid');
      }
      if (!folderField || !folderField.value) {
        if (folderField) folderField.classList.add('is-invalid');
        valid = false;
      } else if (folderField) {
        folderField.classList.remove('is-invalid');
      }
      if (!valid) return;
      setSaving(true);
      fetch('/api/setup/mega/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: emailField.value.trim(), password: passwordField.value, folder: folderField.value })
      })
      .then(resp => resp.json())
      .then(data => {
        if (data.success) {
          window.AsyncButtonState.success(saveBtn);
          if (typeof nextStep === 'function') nextStep();
        } else if (backupConfigError) {
          window.AsyncButtonState.error(saveBtn);
          backupConfigError.textContent = data.error || 'Failed to save MEGA config.';
          backupConfigError.classList.remove('d-none');
        }
      })
      .catch(err => {
        window.AsyncButtonState.error(saveBtn);
        if (backupConfigError) {
          backupConfigError.textContent = 'Error saving MEGA config.';
          backupConfigError.classList.remove('d-none');
        }
      });
      return;
    }
    const configField = document.getElementById('rcloneConfig');
    const remoteNameField = document.getElementById('remoteName');
    let valid = true;
    if (configField && !configField.value.trim()) {
      configField.classList.add('is-invalid');
      valid = false;
    } else if (configField) {
      configField.classList.remove('is-invalid');
    }
    if (remoteNameField && !remoteNameField.value.trim()) {
      remoteNameField.classList.add('is-invalid');
      valid = false;
    } else if (remoteNameField) {
      remoteNameField.classList.remove('is-invalid');
    }
    if (!valid) return;
    setSaving(true);
    fetch('/api/setup/rclone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: configField ? configField.value.trim() : '', remote_name: remoteNameField ? remoteNameField.value.trim() : '' })
    })
    .then(resp => resp.json())
    .then(data => {
      if (data.success) {
        window.AsyncButtonState.success(saveBtn);
        if (typeof nextStep === 'function') nextStep();
      } else if (backupConfigError) {
        window.AsyncButtonState.error(saveBtn);
        backupConfigError.textContent = data.error || 'Failed to save rclone config.';
        backupConfigError.classList.remove('d-none');
      }
    })
    .catch(err => {
      window.AsyncButtonState.error(saveBtn);
      if (backupConfigError) {
        backupConfigError.textContent = 'Error saving rclone config.';
        backupConfigError.classList.remove('d-none');
      }
    });
  };

  // Add defensive checks for event listeners
  const rcloneConfig = document.getElementById('rcloneConfig');
  if (rcloneConfig) rcloneConfig.addEventListener('input', updateSaveBackupConfigState);
  const remoteName = document.getElementById('remoteName');
  if (remoteName) remoteName.addEventListener('input', updateSaveBackupConfigState);
  if (megaFolderPath) megaFolderPath.addEventListener('input', updateSaveBackupConfigState);
  if (backupModeRadios && backupModeRadios.length > 0) {
    backupModeRadios.forEach(radio => {
      radio.addEventListener('change', updateSaveBackupConfigState);
    });
  }

  updateSaveBackupConfigState();
});
