(function () {
  const POLL_MS = 2000;
  const STABLE_BRANCH = 'main';
  let pollTimer = null;
  let currentApplication = null;
  let branchChoicesLoaded = false;
  let branchChoicesLoading = false;

  const els = {};

  function $(id) {
    return document.getElementById(id);
  }

  function cacheElements() {
    [
      'support-status-badge',
      'distro-name',
      'distro-version',
      'max-eol',
      'apt-lock-badge',
      'apt-operation-title',
      'apt-progress-bar',
      'apt-phase',
      'apt-progress-text',
      'apt-log',
      'apt-update-btn',
      'apt-upgrade-btn',
      'apt-stop-btn',
      'auto-updates-badge',
      'auto-updates-summary',
      'auto-updates-form',
      'auto-update-lists',
      'auto-unattended-upgrade',
      'auto-autoclean',
      'auto-updates-hint',
      'auto-updates-save-btn',
      'livepatch-badge',
      'livepatch-title',
      'livepatch-detail',
      'livepatch-form',
      'livepatch-token',
      'livepatch-setup-btn',
      'livepatch-source-link',
      'app-update-title',
      'app-update-detail',
      'app-update-badge',
      'app-update-source',
      'app-update-commit',
      'app-update-checked',
      'app-update-refresh-btn',
      'app-update-now-btn',
      'app-update-force-btn',
      'app-update-switch-main-tooltip',
      'app-update-switch-main-btn',
      'app-branch-advanced-trigger',
      'app-branch-advanced-summary',
      'app-branch-advanced-hint',
      'app-branch-switch-form',
      'app-branch-select',
      'app-branch-switch-btn',
      'remove-locks-btn'
    ].forEach((id) => {
      els[id] = $(id);
    });
  }

  function setBadge(el, text, type) {
    if (!el) return;
    el.className = `badge badge-${type || 'neutral'}`;
    el.textContent = text;
  }

  function operationLabel(operation) {
    if (operation === 'update') return 'apt update';
    if (operation === 'upgrade') return 'apt upgrade';
    return 'Idle';
  }

  function renderDistribution(distribution) {
    if (!distribution) return;
    const support = distribution.support || {};
    els['distro-name'].textContent = distribution.pretty_name || 'Unknown Linux';
    els['distro-version'].textContent = [
      distribution.version_id,
      distribution.version_codename ? `(${distribution.version_codename})` : ''
    ].filter(Boolean).join(' ') || 'Unknown';
    els['max-eol'].textContent = support.max_eol_display || 'Unknown';

    if (support.is_supported === true && support.approaching_eol) {
      setBadge(els['support-status-badge'], 'EOL Soon', 'warning');
    } else if (support.is_supported === true) {
      setBadge(els['support-status-badge'], 'Supported', 'success');
    } else if (support.is_supported === false) {
      setBadge(els['support-status-badge'], 'Past support', 'danger');
    } else if (support.known) {
      setBadge(els['support-status-badge'], 'Dates pending', 'warning');
    } else {
      setBadge(els['support-status-badge'], 'Unknown', 'neutral');
    }
  }

  function renderOperation(operation) {
    const status = operation && operation.status ? operation.status : 'idle';
    const progress = Math.max(0, Math.min(100, Number(operation && operation.progress ? operation.progress : 0)));
    const lock = operation && operation.lock ? operation.lock : {};
    const running = status === 'running';
    const locked = Boolean(lock.locked);

    els['apt-operation-title'].textContent = running ? operationLabel(operation.operation) : operationLabel(null);
    els['apt-progress-bar'].style.width = `${progress}%`;
    els['apt-progress-bar'].setAttribute('aria-valuenow', String(progress));
    els['apt-progress-bar'].className = `progress-bar-fill ${
      status === 'failure' ? 'danger' : status === 'stopped' ? 'warning' : status === 'success' ? 'success' : ''
    }`;
    const phase = operation && operation.phase ? operation.phase : 'Idle';
    const logText = operation && operation.log ? operation.log : 'No apt output yet.';
    els['apt-phase'].textContent = phase;
    els['apt-progress-text'].textContent = `${progress}%`;
    els['apt-log'].textContent = logText;
    els['apt-log'].scrollTop = els['apt-log'].scrollHeight;

    if (running) {
      setBadge(els['apt-lock-badge'], 'Locked', 'info');
    } else if (locked) {
      setBadge(els['apt-lock-badge'], 'External apt lock', 'warning');
    } else {
      setBadge(els['apt-lock-badge'], 'Free', 'success');
    }

    els['apt-update-btn'].disabled = running || locked;
    els['apt-upgrade-btn'].disabled = running || locked;
    els['apt-stop-btn'].disabled = !running;
    els['remove-locks-btn'].disabled = running;
  }

  function renderSettings(settings) {
    if (!settings) return;
    els['auto-update-lists'].checked = Boolean(settings.update_package_lists);
    els['auto-unattended-upgrade'].checked = Boolean(settings.unattended_upgrade);
    els['auto-autoclean'].checked = Boolean(settings.autoclean);
    if (settings.update_package_lists || settings.unattended_upgrade || settings.autoclean) {
      setBadge(els['auto-updates-badge'], 'Enabled', 'success');
      els['auto-updates-summary'].textContent = settings.unattended_upgrade
        ? 'Upgrades'
        : (settings.update_package_lists ? 'Lists only' : 'Autoclean');
    } else {
      setBadge(els['auto-updates-badge'], 'Manual', 'neutral');
      els['auto-updates-summary'].textContent = 'Manual';
    }
    els['auto-updates-badge'].classList.remove('d-none');
    if (!settings.unattended_upgrades_installed) {
      els['auto-updates-hint'].textContent = 'unattended-upgrades is not installed; automatic upgrades will need that package.';
    } else if (settings.apt_updates_managed) {
      els['auto-updates-hint'].textContent = 'SimpleSaferServer manages these apt periodic settings.';
    } else {
      els['auto-updates-hint'].textContent = 'Showing the current system apt periodic settings. Save to manage them here.';
    }
  }

  function renderLivepatch(livepatch) {
    if (!livepatch) return;
    els['livepatch-detail'].textContent = livepatch.status_text || 'Livepatch status unavailable.';
    els['livepatch-source-link'].href = livepatch.source_url || 'https://ubuntu.com/security/livepatch/docs/livepatch/how-to/status';

    if (!livepatch.supported_distro) {
      setBadge(els['livepatch-badge'], 'Ubuntu only', 'neutral');
      els['livepatch-title'].textContent = 'Not available';
      els['livepatch-badge'].classList.add('d-none');
      els['livepatch-form'].classList.add('d-none');
      els['livepatch-token'].disabled = true;
      els['livepatch-setup-btn'].disabled = true;
      return;
    }

    els['livepatch-token'].disabled = false;
    els['livepatch-setup-btn'].disabled = false;
    if (livepatch.enabled) {
      setBadge(els['livepatch-badge'], 'Enabled', 'success');
      els['livepatch-title'].textContent = 'Protected';
      els['livepatch-badge'].classList.add('d-none');
      els['livepatch-form'].classList.add('d-none');
    } else if (livepatch.installed) {
      setBadge(els['livepatch-badge'], 'Needs setup', 'warning');
      els['livepatch-title'].textContent = 'Installed';
      els['livepatch-badge'].classList.remove('d-none');
      els['livepatch-form'].classList.remove('d-none');
    } else {
      setBadge(els['livepatch-badge'], 'Not installed', 'neutral');
      els['livepatch-title'].textContent = 'Ready to install';
      els['livepatch-badge'].classList.remove('d-none');
      els['livepatch-form'].classList.remove('d-none');
    }
  }

  function appUpdateBadgeType(status) {
    if (status === 'up_to_date') return 'success';
    if (status === 'behind') return 'warning';
    if (status === 'dirty' || status === 'diverged') return 'danger';
    if (status === 'ahead' || status === 'pinned') return 'neutral';
    return 'neutral';
  }

  function appUpdateBadgeText(status) {
    if (status === 'up_to_date') return 'Up to date';
    if (status === 'behind') return 'Update available';
    if (status === 'dirty') return 'Local edits';
    if (status === 'diverged') return 'Diverged';
    if (status === 'ahead') return 'Ahead';
    if (status === 'pinned') return 'Pinned';
    if (status === 'unchecked') return 'Not checked';
    return 'Unavailable';
  }

  function sourceLabel(application) {
    const sourceType = application && application.source_type ? application.source_type : 'unknown';
    const sourceName = application && application.source_name ? application.source_name : '';
    if (sourceType === 'branch') return sourceName ? `Branch ${sourceName}` : 'Branch';
    if (sourceType === 'tag') return sourceName ? `Tag ${sourceName}` : 'Tag';
    if (sourceType === 'detached') return 'Locked commit';
    return 'Unknown';
  }

  function renderSourceLabel(el, application) {
    const sourceType = application && application.source_type ? application.source_type : 'unknown';
    const sourceName = application && application.source_name ? application.source_name : '';
    el.textContent = '';

    if ((sourceType === 'branch' || sourceType === 'tag') && sourceName) {
      const label = document.createElement('span');
      label.textContent = `${sourceType === 'branch' ? 'Branch' : 'Tag'} `;
      const value = document.createElement('code');
      value.className = 'app-source-code';
      value.textContent = sourceName;
      el.appendChild(label);
      el.appendChild(value);
      return;
    }

    el.textContent = sourceLabel(application);
  }

  function canOfferBranchSwitch(application) {
    if (!application || application.dirty) return false;
    const sourceType = application.source_type || 'unknown';
    return sourceType === 'branch' || sourceType === 'tag' || sourceType === 'detached';
  }

  function canShowBranchSwitch(application) {
    if (!application) return false;
    const sourceType = application.source_type || 'unknown';
    return sourceType === 'branch' || sourceType === 'tag' || sourceType === 'detached';
  }

  function shouldShowSwitchToMain(application) {
    if (!canShowBranchSwitch(application)) return false;
    if (application.source_type === 'branch') return application.source_name !== STABLE_BRANCH;
    return application.source_type === 'tag' || application.source_type === 'detached';
  }

  function updateBranchAdvancedSummary(application) {
    if (!els['app-branch-advanced-summary']) return;
    if (!canOfferBranchSwitch(application)) {
      els['app-branch-advanced-summary'].textContent = 'Unavailable';
    } else if (application.source_type === 'branch' && application.source_name === STABLE_BRANCH) {
      els['app-branch-advanced-summary'].textContent = 'On main';
    } else {
      els['app-branch-advanced-summary'].textContent = 'Recovery';
    }
  }

  function renderBranchChoices(branches) {
    const select = els['app-branch-select'];
    select.textContent = '';
    if (!branches.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'No branches found';
      select.appendChild(option);
      els['app-branch-switch-btn'].disabled = true;
      return;
    }

    branches.forEach((branch) => {
      const option = document.createElement('option');
      option.value = branch;
      option.textContent = branch;
      select.appendChild(option);
    });
    if (branches.includes(STABLE_BRANCH)) select.value = STABLE_BRANCH;
    select.disabled = !canOfferBranchSwitch(currentApplication);
    els['app-branch-switch-btn'].disabled = !canOfferBranchSwitch(currentApplication);
  }

  function renderBranchSwitchAvailability(application) {
    const cleanupMessage = 'Clean up app folder before switching branches.';
    const blockedByDirtyCheckout = Boolean(application && application.dirty);
    const canSwitchNow = canOfferBranchSwitch(application);

    els['app-branch-select'].disabled = !canSwitchNow;
    els['app-branch-switch-btn'].disabled = !branchChoicesLoaded || !canSwitchNow;
    els['app-branch-advanced-hint'].textContent = blockedByDirtyCheckout
      ? cleanupMessage
      : 'Switch branches only for testing or recovery.';

    const switchMainTooltip = els['app-update-switch-main-tooltip'];
    if (!switchMainTooltip) return;
    if (blockedByDirtyCheckout && shouldShowSwitchToMain(application)) {
      // Native disabled buttons do not emit hover/focus reliably, so the wrapper owns the tooltip.
      switchMainTooltip.className = 'tooltip-trigger';
      switchMainTooltip.setAttribute('data-tooltip', cleanupMessage);
      switchMainTooltip.setAttribute('tabindex', '0');
    } else {
      switchMainTooltip.className = '';
      switchMainTooltip.setAttribute('data-tooltip', '');
      switchMainTooltip.setAttribute('tabindex', '-1');
    }
  }

  function renderApplicationUpdate(application) {
    if (!application) return;
    currentApplication = application;
    const status = application.status || 'unavailable';
    const lastRemoteCheck = application.last_remote_check_at || '';
    els['app-update-title'].textContent = 'Application';
    els['app-update-detail'].textContent = application.message || 'Application update status unavailable.';
    renderSourceLabel(els['app-update-source'], application);
    els['app-update-commit'].textContent = application.current_commit || '—';
    els['app-update-checked'].textContent = window.formatRelativeTimestamp(lastRemoteCheck, {
      fallback: 'Not checked',
      compact: true
    });
    // Keep the exact cached fetch time available without making the status strip harder to scan.
    els['app-update-checked'].title = lastRemoteCheck;
    setBadge(els['app-update-badge'], appUpdateBadgeText(status), appUpdateBadgeType(status));
    els['app-update-now-btn'].disabled = !application.can_update;
    if (application.can_force_update) {
      els['app-update-force-btn'].classList.remove('d-none');
      els['app-update-force-btn'].disabled = false;
    } else {
      els['app-update-force-btn'].classList.add('d-none');
      els['app-update-force-btn'].disabled = true;
    }
    if (shouldShowSwitchToMain(application)) {
      els['app-update-switch-main-btn'].classList.remove('d-none');
      els['app-update-switch-main-btn'].disabled = !canOfferBranchSwitch(application);
      if (application.source_type === 'tag' || application.source_type === 'detached') {
        els['app-update-detail'].textContent = 'This install is locked to a tag or commit. Switch to main to resume updates.';
      }
    } else {
      els['app-update-switch-main-btn'].classList.add('d-none');
      els['app-update-switch-main-btn'].disabled = true;
    }
    updateBranchAdvancedSummary(application);
    renderBranchSwitchAvailability(application);
  }

  async function loadSummary() {
    try {
      const { data } = await window.ApiClient.fetchJson('/api/system_updates/summary');
      renderDistribution(data.distribution);
      renderOperation(data.operation);
      renderSettings(data.settings);
      renderLivepatch(data.livepatch);
      renderApplicationUpdate(data.application);
    } catch (error) {
      showAlert(error.message || 'Could not load system updates.', 'danger');
    }
  }

  async function pollStatus() {
    try {
      const { data } = await window.ApiClient.fetchJson('/api/system_updates/status');
      renderOperation(data.operation);
    } catch (error) {
      console.error(error);
    }
  }

  async function startOperation(operation, button) {
    window.AsyncButtonState.start(button);
    let latestOperation = null;
    try {
      const { data } = await window.ApiClient.fetchJson(`/api/system_updates/${operation}/start`, {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      });
      latestOperation = data.operation;
      showAlert(`${operationLabel(operation)} started.`, 'success');
    } catch (error) {
      showAlert(error.message || `Could not start ${operationLabel(operation)}.`, 'danger');
    } finally {
      window.AsyncButtonState.reset(button);
      if (latestOperation) renderOperation(latestOperation);
      else pollStatus();
    }
  }

  async function stopOperation(button) {
    window.AsyncButtonState.start(button);
    let latestOperation = null;
    try {
      const { data } = await window.ApiClient.fetchJson('/api/system_updates/stop', {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      });
      latestOperation = data.operation;
      showAlert('Apt operation stop requested.', 'success');
    } catch (error) {
      showAlert(error.message || 'Could not stop apt operation.', 'danger');
    } finally {
      window.AsyncButtonState.reset(button);
      if (latestOperation) renderOperation(latestOperation);
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    const button = els['auto-updates-save-btn'];
    window.AsyncButtonState.start(button);
    try {
      const { data } = await window.ApiClient.fetchJson('/api/system_updates/settings', {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          update_package_lists: els['auto-update-lists'].checked,
          unattended_upgrade: els['auto-unattended-upgrade'].checked,
          autoclean: els['auto-autoclean'].checked
        })
      });
      renderSettings(data.settings);
      showAlert('Automatic apt settings saved.', 'success');
    } catch (error) {
      showAlert(error.message || 'Could not save automatic apt settings.', 'danger');
    } finally {
      window.AsyncButtonState.reset(button);
    }
  }

  async function setupLivepatch(event) {
    event.preventDefault();
    const button = els['livepatch-setup-btn'];
    window.AsyncButtonState.start(button);
    try {
      const { data } = await window.ApiClient.fetchJson('/api/system_updates/livepatch/setup', {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ token: els['livepatch-token'].value })
      });
      els['livepatch-token'].value = '';
      renderLivepatch(data.livepatch);
      showAlert('Livepatch setup completed.', 'success');
    } catch (error) {
      showAlert(error.message || 'Could not set up Livepatch.', 'danger');
    } finally {
      window.AsyncButtonState.reset(button);
    }
  }

  async function removeStaleLocks(button) {
    window.AsyncButtonState.start(button);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/system_updates/remove_stale_locks', {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      });
      showAlert(message || 'Stale apt locks removed.', 'success');
      pollStatus();
    } catch (error) {
      showAlert(error.message || 'Could not remove apt locks.', 'danger');
    } finally {
      window.AsyncButtonState.reset(button);
    }
  }

  async function refreshApplicationUpdate(button) {
    window.AsyncButtonState.start(button);
    let latestApplication = null;
    try {
      const { data } = await window.ApiClient.fetchJson('/api/system_updates/application/refresh', {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      });
      latestApplication = data.application;
      await loadBranchChoices({ force: true, quiet: true });
      showAlert('Application update status refreshed.', 'success');
    } catch (error) {
      showAlert(error.message || 'Could not refresh application update status.', 'danger');
    } finally {
      window.AsyncButtonState.reset(button);
      if (latestApplication) renderApplicationUpdate(latestApplication);
    }
  }

  async function loadBranchChoices(options) {
    const opts = options || {};
    if (branchChoicesLoading || (branchChoicesLoaded && !opts.force)) return;
    branchChoicesLoading = true;
    els['app-branch-select'].disabled = true;
    els['app-branch-switch-btn'].disabled = true;
    els['app-branch-advanced-hint'].textContent = 'Loading branches...';
    try {
      const { data } = await window.ApiClient.fetchJson('/api/system_updates/application/branches', {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      });
      renderBranchChoices(Array.isArray(data.branches) ? data.branches : []);
      branchChoicesLoaded = true;
      els['app-branch-advanced-hint'].textContent = 'Switch branches only for testing or recovery.';
    } catch (error) {
      els['app-branch-advanced-hint'].textContent = error.message || 'Could not load branches.';
      if (!opts.quiet) showAlert(error.message || 'Could not load branches.', 'danger');
    } finally {
      branchChoicesLoading = false;
      els['app-branch-select'].disabled = !canOfferBranchSwitch(currentApplication);
      els['app-branch-switch-btn'].disabled = !branchChoicesLoaded || !canOfferBranchSwitch(currentApplication);
    }
  }

  function branchSwitchBody(branch) {
    const body = document.createElement('div');
    const message = document.createElement('p');
    message.textContent = `Switch to ${branch} and apply it now?`;
    body.appendChild(message);
    if (branch !== STABLE_BRANCH) {
      const caution = document.createElement('p');
      caution.textContent = 'Non-main branches may be temporary or outdated.';
      body.appendChild(caution);
    }
    return body;
  }

  async function confirmBranchSwitch(branch) {
    return window.showConfirmationDialog({
      title: branch === STABLE_BRANCH ? 'Switch to main?' : 'Switch application source?',
      body: branchSwitchBody(branch),
      confirmLabel: branch === STABLE_BRANCH ? 'Switch to main' : 'Switch Branch',
      confirmClass: branch === STABLE_BRANCH ? 'btn-primary' : 'btn-warning'
    });
  }

  async function switchApplicationBranch(branch, button) {
    if (!branch) {
      showAlert('Select a branch first.', 'warning');
      return;
    }
    const confirmed = await confirmBranchSwitch(branch);
    if (!confirmed) return;

    window.AsyncButtonState.start(button);
    try {
      const { message, data } = await window.ApiClient.fetchJson('/api/system_updates/application/switch_branch', {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ branch })
      });
      showAlert(message || 'Application source switch started.', 'success');
      window.location.href = data.task_url || '/task/App%20Update';
    } catch (error) {
      showAlert(error.message || 'Could not switch application source.', 'danger');
      window.AsyncButtonState.reset(button);
    }
  }

  async function startApplicationUpdate(button) {
    window.AsyncButtonState.start(button);
    try {
      const { message, data } = await window.ApiClient.fetchJson('/api/system_updates/application/update', {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      });
      showAlert(message || 'Application update started.', 'success');
      window.location.href = data.task_url || '/task/App%20Update';
    } catch (error) {
      showAlert(error.message || 'Could not start application update.', 'danger');
      window.AsyncButtonState.reset(button);
    }
  }

  async function startApplicationForceUpdate(button) {
    const confirmed = await confirmApplicationForceUpdate(currentApplication);
    if (!confirmed) return;

    window.AsyncButtonState.start(button);
    try {
      const { message, data } = await window.ApiClient.fetchJson('/api/system_updates/application/force_update', {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      });
      showAlert(message || 'Application cleanup update started.', 'success');
      window.location.href = data.task_url || '/task/App%20Update';
    } catch (error) {
      showAlert(error.message || 'Could not clean up and update application.', 'danger');
      window.AsyncButtonState.reset(button);
    }
  }

  function formatDirtyFileKind(file) {
    if (!file || file.kind !== 'extra') return 'Changed';
    return 'Extra';
  }

  function buildDirtyFileList(application) {
    const files = Array.isArray(application && application.dirty_files) ? application.dirty_files : [];
    if (!files.length) return null;

    const details = document.createElement('details');
    details.className = 'app-cleanup-file-details';
    const summary = document.createElement('summary');
    summary.textContent = `Show affected files (${files.length})`;
    details.appendChild(summary);

    const list = document.createElement('ul');
    files.forEach((file) => {
      const item = document.createElement('li');
      const kind = document.createElement('span');
      kind.className = `app-cleanup-file-kind ${file && file.kind === 'extra' ? 'is-extra' : 'is-changed'}`;
      kind.textContent = formatDirtyFileKind(file);
      const path = document.createElement('code');
      path.textContent = file && file.path ? file.path : 'Unknown file';
      item.append(kind, path);
      list.appendChild(item);
    });
    details.appendChild(list);
    return details;
  }

  function confirmApplicationForceUpdate(application) {
    const body = document.createElement('div');
    body.className = 'app-cleanup-confirm';

    const message = document.createElement('p');
    message.textContent = 'SimpleSaferServer found changed or extra files in its app folder. This can happen after older installs or manual troubleshooting.';
    body.appendChild(message);

    const action = document.createElement('p');
    action.textContent = 'Clean Up and Update resets /opt/SimpleSaferServer to the selected branch, removes extra app-folder files, then runs the update.';
    body.appendChild(action);

    const keep = document.createElement('p');
    keep.textContent = 'Settings, users, logs, backups, and system config stored outside the app folder are not removed.';
    body.appendChild(keep);

    const fileList = buildDirtyFileList(application);
    if (fileList) body.appendChild(fileList);

    return window.showConfirmationDialog({
      title: 'Clean up app folder and update?',
      body,
      confirmLabel: 'Clean Up and Update',
      confirmClass: 'btn-warning'
    });
  }

  function bindActions() {
    els['apt-update-btn'].addEventListener('click', () => startOperation('update', els['apt-update-btn']));
    els['apt-upgrade-btn'].addEventListener('click', () => startOperation('upgrade', els['apt-upgrade-btn']));
    els['apt-stop-btn'].addEventListener('click', () => stopOperation(els['apt-stop-btn']));
    els['auto-updates-form'].addEventListener('submit', saveSettings);
    els['livepatch-form'].addEventListener('submit', setupLivepatch);
    els['app-update-refresh-btn'].addEventListener('click', () => refreshApplicationUpdate(els['app-update-refresh-btn']));
    els['app-update-now-btn'].addEventListener('click', () => startApplicationUpdate(els['app-update-now-btn']));
    els['app-update-force-btn'].addEventListener('click', () => startApplicationForceUpdate(els['app-update-force-btn']));
    els['app-update-switch-main-btn'].addEventListener('click', () => switchApplicationBranch(STABLE_BRANCH, els['app-update-switch-main-btn']));
    els['app-branch-advanced-trigger'].addEventListener('click', () => loadBranchChoices());
    els['app-branch-switch-form'].addEventListener('submit', (event) => {
      event.preventDefault();
      switchApplicationBranch(els['app-branch-select'].value, els['app-branch-switch-btn']);
    });
    els['remove-locks-btn'].addEventListener('click', () => removeStaleLocks(els['remove-locks-btn']));
  }

  document.addEventListener('DOMContentLoaded', () => {
    cacheElements();
    bindActions();
    loadSummary();
    pollTimer = window.setInterval(pollStatus, POLL_MS);
  });

  window.addEventListener('beforeunload', () => {
    if (pollTimer) window.clearInterval(pollTimer);
  });

  if (window.SystemUpdatesTest) {
    Object.assign(window.SystemUpdatesTest, {
      cacheElements,
      renderApplicationUpdate,
      renderBranchChoices,
      loadBranchChoices
    });
  }
})();
