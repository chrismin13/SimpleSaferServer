/* ============================================================
   SCRIPTS.JS — Setup Wizard Logic + Task Detail Auto-Refresh
   (Mobile nav is now handled by common.js)
   ============================================================ */

document.addEventListener("DOMContentLoaded", function () {

  // --- Auto-refresh logs on the task detail page ---
  const autoRefreshCheckbox = document.getElementById("auto-refresh");
  if (autoRefreshCheckbox) {
    const logContainer = document.querySelector(".log-viewer");
    const refreshState = document.getElementById("task-log-refresh-state");
    const statusBadge = document.getElementById("task-status-badge");
    const taskName = autoRefreshCheckbox.getAttribute("data-task-name");
    const logLines = autoRefreshCheckbox.getAttribute("data-log-lines") || "500";
    let intervalId;
    let initialLoad = true;
    let failedFetchCount = 0;

    function scrollToBottom() {
      if (logContainer) logContainer.scrollTop = logContainer.scrollHeight;
    }

    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function ansiCodesToClass(codes) {
      const parts = codes.split(";").filter(Boolean);
      const classes = [];
      let isBright = false;
      parts.forEach((part) => {
        if (part === "1") isBright = true;
        if (part === "31") classes.push("ansi-red");
        if (part === "32") classes.push("ansi-green");
        if (part === "33") classes.push("ansi-yellow");
        if (part === "34") classes.push("ansi-blue");
        if (part === "35") classes.push("ansi-magenta");
        if (part === "36") classes.push("ansi-cyan");
        if (part === "37") classes.push("ansi-white");
      });
      if (isBright && classes.length) classes.push("ansi-bright");
      return classes.join(" ");
    }

    function renderAnsiLog(text) {
      let html = "";
      let open = false;
      let lastIndex = 0;
      const ansiPattern = /\x1b\[([0-9;]*)m/g;
      let match;

      // Only SGR color/reset sequences become markup. Log text is escaped so
      // command output cannot inject HTML while still allowing installer colors.
      while ((match = ansiPattern.exec(text)) !== null) {
        html += escapeHtml(text.slice(lastIndex, match.index));
        if (open) {
          html += "</span>";
          open = false;
        }

        const className = ansiCodesToClass(match[1] || "0");
        if (className) {
          html += `<span class="${className}">`;
          open = true;
        }
        lastIndex = ansiPattern.lastIndex;
      }

      html += escapeHtml(text.slice(lastIndex));
      if (open) html += "</span>";
      return html;
    }

    function renderTaskStatusBadge(status) {
      if (status === "Success") return '<span class="badge badge-success"><i class="fas fa-circle-check"></i> Success</span>';
      if (status === "Failure") return '<span class="badge badge-danger"><i class="fas fa-circle-xmark"></i> Failure</span>';
      if (status === "Running") return '<span class="badge badge-info"><i class="fas fa-spinner fa-spin"></i> Running</span>';
      if (status === "Missing") return '<span class="badge badge-warning"><i class="fas fa-circle-exclamation"></i> Missing</span>';
      if (status === "Not Run Yet") return '<span class="badge badge-neutral"><i class="fas fa-clock"></i> Not Run Yet</span>';
      if (status === "Stopped") return '<span class="badge badge-neutral"><i class="fas fa-stop"></i> Stopped</span>';
      return `<span class="badge badge-warning"><i class="fas fa-question-circle"></i> ${escapeHtml(status || "Unknown")}</span>`;
    }

    function fetchTaskStatus() {
      if (!statusBadge) return Promise.resolve();
      return fetch(`/api/tasks/${encodeURIComponent(taskName)}/status`, {
        headers: { "Accept": "application/json" }
      })
        .then((resp) => {
          if (!resp.ok) throw new Error(`Task status refresh failed with HTTP ${resp.status}`);
          return resp.json();
        })
        .then((payload) => {
          const task = payload && payload.data ? payload.data.task : null;
          statusBadge.innerHTML = renderTaskStatusBadge(task && task.status);
        });
    }

    function fetchLogs() {
      const distanceFromBottom = logContainer
        ? logContainer.scrollHeight - logContainer.scrollTop - logContainer.clientHeight
        : 0;
      const stickToBottom = distanceFromBottom < 48;

      return fetch(`/task/${encodeURIComponent(taskName)}/logs?lines=${encodeURIComponent(logLines)}`)
        .then((resp) => {
          if (!resp.ok) throw new Error(`Log refresh failed with HTTP ${resp.status}`);
          return resp.text();
        })
        .then((text) => {
          failedFetchCount = 0;
          if (refreshState) refreshState.textContent = "";
          if (logContainer) logContainer.innerHTML = renderAnsiLog(text);
          if (initialLoad) {
            scrollToBottom();
            initialLoad = false;
          } else if (logContainer && stickToBottom) {
            scrollToBottom();
          }
        })
        .catch((err) => {
          failedFetchCount += 1;
          if (refreshState) {
            refreshState.textContent = failedFetchCount > 1
              ? "Reconnecting to log..."
              : "Log refresh paused; retrying...";
          }
          console.error(err);
        });
    }

    function refreshTaskDetail() {
      fetchTaskStatus().catch((err) => console.error(err));
      fetchLogs();
    }

    function start() {
      refreshTaskDetail();
      intervalId = setInterval(refreshTaskDetail, 1000);
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
      megaConfigFields.classList.toggle('active', mode === 'mega');
      advancedConfigFields.classList.toggle('active', mode === 'advanced');
    }

    document.querySelectorAll('#step4 .tab-btn').forEach(btn => {
      const isActive = btn.getAttribute('data-tab') === mode;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', isActive);
    });
  }

  const backupModeRadios = document.getElementsByName('backupMode');
  if (backupModeRadios && backupModeRadios.length > 0) {
    backupModeRadios.forEach(radio => {
      radio.addEventListener('change', () => {
        showBackupModeFields();
        updateSaveBackupConfigState();
      });
    });
  }

  // Bind Custom Tabs for Setup
  document.querySelectorAll('#step4 .tab-btn').forEach(btn => {
    btn.addEventListener('click', function() {
      const mode = this.getAttribute('data-tab');
      const radio = document.querySelector(`input[name="backupMode"][value="${mode}"]`);
      if (radio) {
        radio.checked = true;
        showBackupModeFields();
        updateSaveBackupConfigState();
      }
    });
  });

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
      window.ApiClient.fetchJson('/api/setup/mega/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.value.trim(), password: password.value })
      })
      .then(() => {
        window.AsyncButtonState.success(megaConnectBtn);
        const backupConfigError = document.getElementById('backupConfigError');
        if (backupConfigError) backupConfigError.classList.add('d-none');
        if (megaFolderPathArea) megaFolderPathArea.classList.remove('d-none');
        if (megaFolderPath) megaFolderPath.value = '/';
        updateSaveBackupConfigState();
      })
      .catch(err => {
        window.AsyncButtonState.error(megaConnectBtn);
        const backupConfigError = document.getElementById('backupConfigError');
        if (backupConfigError) {
          backupConfigError.textContent = err.message || 'Error connecting to MEGA.';
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
      window.ApiClient.fetchJson('/api/setup/mega/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: emailField.value.trim(), password: passwordField.value, folder: folderField.value })
      })
      .then(() => {
        window.AsyncButtonState.success(saveBtn);
        if (typeof nextStep === 'function') nextStep();
      })
      .catch(err => {
        window.AsyncButtonState.error(saveBtn);
        if (backupConfigError) {
          backupConfigError.textContent = err.message || 'Error saving MEGA config.';
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
    window.ApiClient.fetchJson('/api/setup/rclone', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: configField ? configField.value.trim() : '', remote_name: remoteNameField ? remoteNameField.value.trim() : '' })
    })
    .then(() => {
      window.AsyncButtonState.success(saveBtn);
      if (typeof nextStep === 'function') nextStep();
    })
    .catch(err => {
      window.AsyncButtonState.error(saveBtn);
      if (backupConfigError) {
        backupConfigError.textContent = err.message || 'Error saving rclone config.';
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
