(function () {
  const POLL_MS = 2000;
  let pollTimer = null;

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
    els['apt-progress-bar'].className = `progress-bar-fill ${
      status === 'failure' ? 'danger' : status === 'stopped' ? 'warning' : status === 'success' ? 'success' : ''
    }`;
    els['apt-phase'].textContent = operation.phase || 'Idle';
    els['apt-progress-text'].textContent = `${progress}%`;
    els['apt-log'].textContent = operation.log || 'No apt output yet.';
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
    if (settings.update_package_lists || settings.unattended_upgrade) {
      setBadge(els['auto-updates-badge'], 'Enabled', 'success');
      els['auto-updates-summary'].textContent = settings.unattended_upgrade ? 'Upgrades' : 'Lists only';
    } else {
      setBadge(els['auto-updates-badge'], 'Manual', 'neutral');
      els['auto-updates-summary'].textContent = 'Manual';
    }
    els['auto-updates-badge'].classList.add('d-none');
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

  async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok || data.success === false) {
      throw new Error(data.error || data.message || 'Request failed.');
    }
    return data;
  }

  async function loadSummary() {
    try {
      const data = await fetchJson('/api/system_updates/summary');
      renderDistribution(data.distribution);
      renderOperation(data.operation);
      renderSettings(data.settings);
      renderLivepatch(data.livepatch);
    } catch (error) {
      showAlert(error.message || 'Could not load system updates.', 'danger');
    }
  }

  async function pollStatus() {
    try {
      const data = await fetchJson('/api/system_updates/status');
      renderOperation(data.operation);
    } catch (error) {
      console.error(error);
    }
  }

  async function startOperation(operation, button) {
    window.AsyncButtonState.start(button);
    let latestOperation = null;
    try {
      const data = await fetchJson(`/api/system_updates/${operation}/start`, {
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
      const data = await fetchJson('/api/system_updates/stop', {
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
      const data = await fetchJson('/api/system_updates/settings', {
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
      const data = await fetchJson('/api/system_updates/livepatch/setup', {
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
      const data = await fetchJson('/api/system_updates/remove_stale_locks', {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      });
      showAlert(data.message || 'Stale apt locks removed.', 'success');
      pollStatus();
    } catch (error) {
      showAlert(error.message || 'Could not remove apt locks.', 'danger');
    } finally {
      window.AsyncButtonState.reset(button);
    }
  }

  function bindActions() {
    els['apt-update-btn'].addEventListener('click', () => startOperation('update', els['apt-update-btn']));
    els['apt-upgrade-btn'].addEventListener('click', () => startOperation('upgrade', els['apt-upgrade-btn']));
    els['apt-stop-btn'].addEventListener('click', () => stopOperation(els['apt-stop-btn']));
    els['auto-updates-form'].addEventListener('submit', saveSettings);
    els['livepatch-form'].addEventListener('submit', setupLivepatch);
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
})();
