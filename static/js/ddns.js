document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('ddns-config-form');
  const saveBtn = document.getElementById('ddns-save-btn');
  const runBtn = document.getElementById('ddns-run-btn');
  const defaultCopy = {
    status: {
      never: 'Never',
      disabled: 'Disabled',
      pending: 'Pending',
      unknown: 'Unknown',
      success: 'Success',
      dash: '—'
    },
    secrets: {
      showToken: 'Show token',
      hideToken: 'Hide token'
    },
    messages: {
      loadFailure: 'Connection error while loading DDNS configuration.',
      saveSuccess: 'DDNS configuration saved.',
      saveFailure: 'Connection error while saving.',
      runSuccess: 'DDNS sync started successfully.',
      runFailure: 'Failed to start DDNS sync.'
    },
    confirmation: {
      title: 'Run DDNS Checks',
      message: 'Are you sure you want to run DDNS checks manually now?',
      confirm: 'Run Now',
      running: 'Running...'
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
    const script = document.getElementById('ddns-copy');
    if (!script) return defaultCopy;
    try {
      return mergeCopy(JSON.parse(JSON.stringify(defaultCopy)), JSON.parse(script.textContent || '{}'));
    } catch (error) {
      console.error('Could not read DDNS page copy:', error);
      return defaultCopy;
    }
  }

  const copy = readCopy();

  // Guard: bail out if critical elements are missing
  if (!form || !saveBtn) {
    console.error('DDNS: Required form elements not found');
    return;
  }

  function setupSecretToggles() {
    document.querySelectorAll('[data-secret-toggle]').forEach((button) => {
      const input = document.getElementById(button.dataset.secretToggle);
      if (!input) return;
      button.addEventListener('click', () => {
        const visible = input.type === 'text';
        input.type = visible ? 'password' : 'text';
        button.setAttribute('aria-label', visible ? copy.secrets.showToken : copy.secrets.hideToken);
        button.title = visible ? copy.secrets.showToken : copy.secrets.hideToken;
        const icon = button.querySelector('i');
        if (icon) icon.className = visible ? 'fas fa-eye' : 'fas fa-eye-slash';
      });
    });
  }

  // Load config and status
  async function loadData() {
    try {
      const { data } = await window.ApiClient.fetchJson('/api/ddns/config');
      populateForm(data.config);
      updateStatusTiles(data.status, data.config, data);
    } catch (error) {
      console.error('Error fetching DDNS config:', error);
      showAlert(error.message || copy.messages.loadFailure, 'error');
    }
  }

  function populateForm(config) {
    if (!config) return;

    if (config.duckdns) {
      document.getElementById('duckdnsEnabled').checked = config.duckdns.enabled;
      document.getElementById('duckdnsDomain').value = config.duckdns.domain || '';
      document.getElementById('duckdnsToken').value = config.duckdns.token || '';
    }

    if (config.cloudflare) {
      document.getElementById('cloudflareEnabled').checked = config.cloudflare.enabled;
      document.getElementById('cfZoneId').value = config.cloudflare.zone || '';
      document.getElementById('cfRecordName').value = config.cloudflare.record || '';
      document.getElementById('cfToken').value = config.cloudflare.token || '';
      document.getElementById('cfProxyStatus').checked = config.cloudflare.proxy;
    }
  }

  function formatTime(isoString) {
    if (!isoString) return copy.status.never;
    if (window.parseServerDateTime && !window.parseServerDateTime(isoString)) {
      return copy.status.never;
    }
    return window.AppFormat
      ? window.AppFormat.dateTime(isoString, { fallback: copy.status.never })
      : isoString;
  }

  function updateStatusTiles(status, config, dt) {
    // DuckDNS Status
    const duckEnabled = config?.duckdns?.enabled;
    const duckBadge = document.getElementById('duckdns-status-badge');
    const duckStatus = status?.duckdns;

    if (!duckEnabled) {
      duckBadge.textContent = copy.status.disabled;
      duckBadge.className = 'badge badge-neutral';
      document.getElementById('duckdns-message').textContent = copy.status.dash;
      document.getElementById('duckdns-message').title = '';
    } else if (duckStatus) {
      let isError = duckStatus.status !== 'Success';
      duckBadge.textContent = duckStatus.status || copy.status.unknown;
      duckBadge.className = isError ? 'badge badge-danger' : 'badge badge-success';
      document.getElementById('duckdns-message').textContent = duckStatus.message || copy.status.dash;
      document.getElementById('duckdns-message').title = duckStatus.message || '';
    } else {
      duckBadge.textContent = copy.status.pending;
      duckBadge.className = 'badge badge-warning';
      document.getElementById('duckdns-message').textContent = '';
      document.getElementById('duckdns-message').title = '';
    }
    document.getElementById('duckdns-last-sync').textContent = formatTime(status?.last_check);
    document.getElementById('duckdns-next-run').textContent = config?.duckdns?.enabled ? (dt?.next_run || copy.status.dash) : copy.status.dash;
    document.getElementById('duckdns-ipv4').textContent = status?.ipv4 || copy.status.dash;

    // Cloudflare Status
    const cfEnabled = config?.cloudflare?.enabled;
    const cfBadge = document.getElementById('cf-status-badge');
    const cfStatus = status?.cloudflare;

    if (!cfEnabled) {
      cfBadge.textContent = copy.status.disabled;
      cfBadge.className = 'badge badge-neutral';
      document.getElementById('cf-message').textContent = copy.status.dash;
      document.getElementById('cf-message').title = '';
    } else if (cfStatus) {
      let isError = cfStatus.status !== 'Success';
      cfBadge.textContent = cfStatus.status || copy.status.unknown;
      cfBadge.className = isError ? 'badge badge-danger' : 'badge badge-success';
      document.getElementById('cf-message').textContent = cfStatus.message || copy.status.dash;
      document.getElementById('cf-message').title = cfStatus.message || '';
    } else {
      cfBadge.textContent = copy.status.pending;
      cfBadge.className = 'badge badge-warning';
      document.getElementById('cf-message').textContent = '';
      document.getElementById('cf-message').title = '';
    }
    document.getElementById('cf-last-sync').textContent = formatTime(status?.last_check);
    document.getElementById('cf-next-run').textContent = config?.cloudflare?.enabled ? (dt?.next_run || copy.status.dash) : copy.status.dash;
    document.getElementById('cf-ipv4').textContent = status?.ipv4 || copy.status.dash;
  }

  // Tabs handling
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      // Remove active from all
      tabBtns.forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-selected', 'false');
      });
      tabPanes.forEach(p => p.classList.remove('active'));

      // Add active to current
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      const targetId = btn.getAttribute('aria-controls');
      document.getElementById(targetId).classList.add('active');
    });
  });

  // Save form
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    window.AsyncButtonState.start(saveBtn);

    const duckdnsToken = document.getElementById('duckdnsToken').value;
    const cfToken = document.getElementById('cfToken').value;

    const payload = {
      duckdns: {
        enabled: document.getElementById('duckdnsEnabled').checked,
        domain: document.getElementById('duckdnsDomain').value
      },
      cloudflare: {
        enabled: document.getElementById('cloudflareEnabled').checked,
        zone: document.getElementById('cfZoneId').value,
        record: document.getElementById('cfRecordName').value,
        proxy: document.getElementById('cfProxyStatus').checked
      }
    };

    // Blank token fields mean "keep the current token"; leaving these
    // properties undefined prevents the server from storing an empty token.
    if (duckdnsToken) {
      payload.duckdns.token = duckdnsToken;
    }
    if (cfToken) {
      payload.cloudflare.token = cfToken;
    }

    try {
      const { message } = await window.ApiClient.fetchJson('/api/ddns/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      window.AsyncButtonState.success(saveBtn);
      showAlert(message || copy.messages.saveSuccess, 'success');
      // Refresh to show newly triggered sync
      setTimeout(loadData, 2000);
    } catch (error) {
      console.error('Error saving:', error);
      window.AsyncButtonState.error(saveBtn);
      showAlert(error.message || copy.messages.saveFailure, 'error');
    }
  });

  // Force sync: show the app's confirmation dialog, then POST to the task endpoint via AJAX
  // so the user stays on this page and sees real-time feedback.
  if (runBtn) {
    runBtn.addEventListener('click', async (e) => {
      e.preventDefault();

      const confirmed = await window.showConfirmationDialog({
        title: copy.confirmation.title,
        message: copy.confirmation.message,
        confirmLabel: copy.confirmation.confirm,
        confirmClass: 'btn-primary'
      });

      if (!confirmed) return;

      const originalHtml = runBtn.innerHTML;
      runBtn.disabled = true;
      runBtn.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${copy.confirmation.running}`;

      try {
        const { message } = await window.ApiClient.fetchJson('/api/ddns/run', {
          method: 'POST',
          headers: { 'Accept': 'application/json' }
        });

        showAlert(message || copy.messages.runSuccess, 'success');

        setTimeout(loadData, 3000);
      } catch (err) {
        console.error('Error starting DDNS sync:', err);
        showAlert(err.message || copy.messages.runFailure, 'error');
        setTimeout(loadData, 2000);
      } finally {
        runBtn.disabled = false;
        runBtn.innerHTML = originalHtml;
      }
    });
  }

  // Init
  setupSecretToggles();
  loadData();
});
