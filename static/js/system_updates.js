(function () {
  const POLL_MS = 2000;
  let pollTimer = null;

  const els = {};
  const defaultCopy = {
    badges: {
      eolSoon: 'EOL Soon',
      supported: 'Supported',
      pastSupport: 'Past support',
      datesPending: 'Dates pending',
      unknown: 'Unknown',
      locked: 'Locked',
      externalAptLock: 'External apt lock',
      free: 'Free',
      enabled: 'Enabled',
      manual: 'Manual',
      ubuntuOnly: 'Ubuntu only',
      installed: 'Installed',
      notInstalled: 'Not installed',
      upToDate: 'Up to date',
      updateAvailable: 'Update available',
      unavailable: 'Unavailable'
    },
    distribution: {
      unknownLinux: 'Unknown Linux',
      unknown: 'Unknown'
    },
    operation: {
      idle: 'Idle',
      packageManager: 'Package Manager',
      noAptOutput: 'No apt output yet.'
    },
    settings: {
      enabled: 'Enabled',
      disabled: 'Disabled',
      autocleanEveryDays: 'Every {days} day(s)',
      upgrades: 'Upgrades',
      listsOnly: 'Lists only',
      autoclean: 'Autoclean',
      manual: 'Manual',
      readOnlyHint: 'Showing current system apt periodic policy. SSS does not install, enable, or configure automatic OS updates.'
    },
    livepatch: {
      unavailableDetail: 'Livepatch status unavailable.',
      notAvailable: 'Not available',
      protected: 'Protected',
      installed: 'Installed',
      notInstalled: 'Not installed'
    },
    application: {
      title: 'Application',
      unavailableDetail: 'Application update status unavailable.',
      installerArchive: 'Installer archive',
      package: 'Package',
      release: 'Release',
      unknown: 'Unknown',
      notTracked: 'Not tracked',
      notChecked: 'Not checked',
      refreshSuccess: 'Application update status refreshed.',
      refreshFailure: 'Could not refresh application update status.',
      started: 'Application update started.',
      startFailure: 'Could not start application update.'
    },
    errors: {
      loadSummary: 'Could not load system updates.'
    }
  };

  function deepMerge(base, overrides) {
    if (!overrides || typeof overrides !== 'object') return base;
    Object.keys(overrides).forEach((key) => {
      if (
        overrides[key]
        && typeof overrides[key] === 'object'
        && !Array.isArray(overrides[key])
        && base[key]
        && typeof base[key] === 'object'
      ) {
        deepMerge(base[key], overrides[key]);
      } else {
        base[key] = overrides[key];
      }
    });
    return base;
  }

  function readCopy() {
    const script = document.getElementById('system-updates-copy');
    if (!script) return defaultCopy;
    try {
      const parsed = JSON.parse(script.textContent || '{}');
      return deepMerge(JSON.parse(JSON.stringify(defaultCopy)), parsed);
    } catch (error) {
      console.error('Could not read System Updates page copy:', error);
      return defaultCopy;
    }
  }

  const copy = readCopy();

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
      'auto-updates-badge',
      'auto-updates-summary',
      'auto-update-lists-status',
      'auto-upgrades-status',
      'auto-autoclean-status',
      'auto-updates-hint',
      'livepatch-summary-item',
      'livepatch-badge',
      'livepatch-title',
      'livepatch-section',
      'livepatch-detail',
      'livepatch-source-link',
      'app-update-title',
      'app-update-detail',
      'app-update-badge',
      'app-update-source',
      'app-update-commit',
      'app-update-checked',
      'app-update-refresh-btn',
      'app-update-now-btn'
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
    return copy.operation.idle;
  }

  function renderDistribution(distribution) {
    if (!distribution) return;
    const support = distribution.support || {};
    els['distro-name'].textContent = distribution.pretty_name || copy.distribution.unknownLinux;
    els['distro-version'].textContent = [
      distribution.version_id,
      distribution.version_codename ? `(${distribution.version_codename})` : ''
    ].filter(Boolean).join(' ') || copy.distribution.unknown;
    els['max-eol'].textContent = support.max_eol_display || copy.distribution.unknown;

    if (support.is_supported === true && support.approaching_eol) {
      setBadge(els['support-status-badge'], copy.badges.eolSoon, 'warning');
    } else if (support.is_supported === true) {
      setBadge(els['support-status-badge'], copy.badges.supported, 'success');
    } else if (support.is_supported === false) {
      setBadge(els['support-status-badge'], copy.badges.pastSupport, 'danger');
    } else if (support.known) {
      setBadge(els['support-status-badge'], copy.badges.datesPending, 'warning');
    } else {
      setBadge(els['support-status-badge'], copy.badges.unknown, 'neutral');
    }
  }

  function renderOperation(operation) {
    const status = operation && operation.status ? operation.status : 'idle';
    const progress = Math.max(0, Math.min(100, Number(operation && operation.progress ? operation.progress : 0)));
    const lock = operation && operation.lock ? operation.lock : {};
    const running = status === 'running';
    const locked = Boolean(lock.locked);

    els['apt-operation-title'].textContent = running ? operationLabel(operation.operation) : copy.operation.packageManager;
    if (els['apt-progress-bar']) {
      els['apt-progress-bar'].style.width = `${progress}%`;
      els['apt-progress-bar'].setAttribute('aria-valuenow', String(progress));
      els['apt-progress-bar'].className = `progress-bar-fill ${
        status === 'failure' ? 'danger' : status === 'stopped' ? 'warning' : status === 'success' ? 'success' : ''
      }`;
    }
    const phase = operation && operation.phase ? operation.phase : copy.operation.idle;
    const logText = operation && operation.log ? operation.log : copy.operation.noAptOutput;
    els['apt-phase'].textContent = phase;
    els['apt-progress-text'].textContent = window.AppFormat
      ? window.AppFormat.percent(progress / 100)
      : `${progress}%`;
    els['apt-log'].textContent = logText;
    els['apt-log'].scrollTop = els['apt-log'].scrollHeight;

    if (running) {
      setBadge(els['apt-lock-badge'], copy.badges.locked, 'info');
    } else if (locked) {
      setBadge(els['apt-lock-badge'], copy.badges.externalAptLock, 'warning');
    } else {
      setBadge(els['apt-lock-badge'], copy.badges.free, 'success');
    }
  }

  function renderSettings(settings) {
    if (!settings) return;
    els['auto-update-lists-status'].textContent = settings.update_package_lists ? copy.settings.enabled : copy.settings.disabled;
    els['auto-upgrades-status'].textContent = settings.unattended_upgrade ? copy.settings.enabled : copy.settings.disabled;
    els['auto-autoclean-status'].textContent = settings.autoclean
      ? copy.settings.autocleanEveryDays.replace('{days}', settings.autoclean_interval || '?')
      : copy.settings.disabled;
    if (settings.update_package_lists || settings.unattended_upgrade || settings.autoclean) {
      setBadge(els['auto-updates-badge'], copy.badges.enabled, 'success');
      els['auto-updates-summary'].textContent = settings.unattended_upgrade
        ? copy.settings.upgrades
        : (settings.update_package_lists ? copy.settings.listsOnly : copy.settings.autoclean);
    } else {
      setBadge(els['auto-updates-badge'], copy.badges.manual, 'neutral');
      els['auto-updates-summary'].textContent = copy.settings.manual || copy.badges.manual;
    }
    els['auto-updates-badge'].classList.remove('d-none');
    els['auto-updates-hint'].textContent = copy.settings.readOnlyHint;
  }

  function renderLivepatch(livepatch) {
    if (!livepatch) return;
    els['livepatch-detail'].textContent = livepatch.status_text || copy.livepatch.unavailableDetail;
    els['livepatch-source-link'].href = livepatch.source_url || 'https://ubuntu.com/security/livepatch/docs/livepatch/how-to/status';

    if (!livepatch.supported_distro) {
      els['livepatch-summary-item'].classList.add('d-none');
      els['livepatch-section'].classList.add('d-none');
      setBadge(els['livepatch-badge'], copy.badges.ubuntuOnly, 'neutral');
      els['livepatch-title'].textContent = copy.livepatch.notAvailable;
      els['livepatch-badge'].classList.add('d-none');
      return;
    }

    els['livepatch-summary-item'].classList.remove('d-none');
    els['livepatch-section'].classList.remove('d-none');
    if (livepatch.enabled) {
      setBadge(els['livepatch-badge'], copy.badges.enabled, 'success');
      els['livepatch-title'].textContent = copy.livepatch.protected;
      els['livepatch-badge'].classList.add('d-none');
    } else if (livepatch.installed) {
      setBadge(els['livepatch-badge'], copy.badges.installed, 'neutral');
      els['livepatch-title'].textContent = copy.livepatch.installed;
      els['livepatch-badge'].classList.remove('d-none');
    } else {
      setBadge(els['livepatch-badge'], copy.badges.notInstalled, 'neutral');
      els['livepatch-title'].textContent = copy.livepatch.notInstalled;
      els['livepatch-badge'].classList.remove('d-none');
    }
  }

  function appUpdateBadgeType(status) {
    if (status === 'up_to_date') return 'success';
    if (status === 'behind') return 'warning';
    return 'neutral';
  }

  function appUpdateBadgeText(status) {
    if (status === 'up_to_date') return copy.badges.upToDate;
    if (status === 'behind') return copy.badges.updateAvailable;
    return copy.badges.unavailable;
  }

  function sourceLabel(application) {
    const sourceType = application && application.source_type ? application.source_type : 'unknown';
    const sourceName = application && application.source_name ? application.source_name : '';
    if (sourceType === 'archive') return sourceName || copy.application.installerArchive;
    if (sourceType === 'package') return sourceName || copy.application.package;
    if (sourceType === 'release') return sourceName || copy.application.release;
    return copy.application.unknown;
  }

  function renderApplicationUpdate(application) {
    if (!application) return;
    const status = application.status || 'unavailable';
    const lastRemoteCheck = application.last_remote_check_at || application.checked_at || '';
    els['app-update-title'].textContent = copy.application.title;
    els['app-update-detail'].textContent = application.message || copy.application.unavailableDetail;
    els['app-update-source'].textContent = sourceLabel(application);
    els['app-update-commit'].textContent = application.current_commit || copy.application.notTracked;
    els['app-update-checked'].textContent = window.AppFormat.relativeTimestamp(lastRemoteCheck, {
      fallback: copy.application.notChecked,
      compact: true
    });
    els['app-update-checked'].title = window.AppFormat.dateTime(lastRemoteCheck, {
      fallback: copy.application.notChecked
    });
    setBadge(els['app-update-badge'], appUpdateBadgeText(status), appUpdateBadgeType(status));
    els['app-update-now-btn'].disabled = !application.can_update;
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
      showAlert(error.message || copy.errors.loadSummary, 'danger');
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

  async function refreshApplicationUpdate(button) {
    window.AsyncButtonState.start(button);
    try {
      const { data } = await window.ApiClient.fetchJson('/api/system_updates/application/refresh', {
        method: 'POST',
        headers: { 'Accept': 'application/json' }
      });
      renderApplicationUpdate(data.application);
      showAlert(copy.application.refreshSuccess, 'success');
    } catch (error) {
      showAlert(error.message || copy.application.refreshFailure, 'danger');
    } finally {
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
      showAlert(message || copy.application.started, 'success');
      window.location.href = data.task_url || '/task/App%20Update';
    } catch (error) {
      showAlert(error.message || copy.application.startFailure, 'danger');
      window.AsyncButtonState.reset(button);
    }
  }

  function bindActions() {
    els['app-update-refresh-btn'].addEventListener('click', () => refreshApplicationUpdate(els['app-update-refresh-btn']));
    els['app-update-now-btn'].addEventListener('click', () => startApplicationUpdate(els['app-update-now-btn']));
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
      renderApplicationUpdate
    });
  }
})();
