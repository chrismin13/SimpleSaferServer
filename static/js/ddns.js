document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('ddns-config-form');
  const saveBtn = document.getElementById('ddns-save-btn');
  const runBtn = document.getElementById('ddns-run-btn');

  // Load config and status
  async function loadData() {
    try {
      const response = await fetch('/api/ddns/config');
      const data = await response.json();

      if (data.success) {
        populateForm(data.config);
        updateStatusTiles(data.status, data.config, data);
      } else {
        showAlert(data.message || 'Failed to load DDNS configuration', 'error');
      }
    } catch (error) {
      console.error('Error fetching DDNS config:', error);
      showAlert('Connection error while loading DDNS configuration.', 'error');
    }
  }

  function populateForm(config) {
    if (!config) return;

    if (config.duckdns) {
      document.getElementById('duckdnsEnabled').checked = config.duckdns.enabled;
      document.getElementById('duckdnsDomain').value = config.duckdns.domain || '';
      document.getElementById('duckdnsToken').value = config.duckdns.token ? '********' : '';
    }

    if (config.cloudflare) {
      document.getElementById('cloudflareEnabled').checked = config.cloudflare.enabled;
      document.getElementById('cfZoneId').value = config.cloudflare.zone || '';
      document.getElementById('cfRecordName').value = config.cloudflare.record || '';
      document.getElementById('cfToken').value = config.cloudflare.token ? '********' : '';
      document.getElementById('cfProxyStatus').checked = config.cloudflare.proxy;
    }
  }

  function formatTime(isoString) {
    if (!isoString) return 'Never';
    try {
      return new Date(isoString).toLocaleString();
    } catch (e) {
      return isoString;
    }
  }

  function updateStatusTiles(status, config, dt) {
    // DuckDNS Status
    const duckEnabled = config?.duckdns?.enabled;
    const duckBadge = document.getElementById('duckdns-status-badge');
    const duckStatus = status?.duckdns;
    
    if (!duckEnabled) {
      duckBadge.textContent = 'Disabled';
      duckBadge.className = 'badge badge-secondary';
      document.getElementById('duckdns-message').textContent = '—';
    } else if (duckStatus) {
      let isError = duckStatus.status !== 'Success';
      duckBadge.textContent = duckStatus.status || 'Unknown';
      duckBadge.className = isError ? 'badge badge-danger' : 'badge badge-success';
      document.getElementById('duckdns-message').textContent = duckStatus.message || '—';
      document.getElementById('duckdns-message').title = duckStatus.message || '';
    } else {
      duckBadge.textContent = 'Pending';
      duckBadge.className = 'badge badge-warning';
    }
    document.getElementById('duckdns-last-sync').textContent = formatTime(status?.last_check);
    document.getElementById('duckdns-next-run').textContent = config?.duckdns?.enabled ? (dt?.next_run || '—') : '—';
    document.getElementById('duckdns-ipv4').textContent = status?.ipv4 || '—';

    // Cloudflare Status
    const cfEnabled = config?.cloudflare?.enabled;
    const cfBadge = document.getElementById('cf-status-badge');
    const cfStatus = status?.cloudflare;

    if (!cfEnabled) {
      cfBadge.textContent = 'Disabled';
      cfBadge.className = 'badge badge-secondary';
      document.getElementById('cf-message').textContent = '—';
    } else if (cfStatus) {
      let isError = cfStatus.status !== 'Success';
      cfBadge.textContent = cfStatus.status || 'Unknown';
      cfBadge.className = isError ? 'badge badge-danger' : 'badge badge-success';
      document.getElementById('cf-message').textContent = cfStatus.message || '—';
      document.getElementById('cf-message').title = cfStatus.message || '';
    } else {
      cfBadge.textContent = 'Pending';
      cfBadge.className = 'badge badge-warning';
    }
    document.getElementById('cf-last-sync').textContent = formatTime(status?.last_check);
    document.getElementById('cf-next-run').textContent = config?.cloudflare?.enabled ? (dt?.next_run || '—') : '—';
    document.getElementById('cf-ipv4').textContent = status?.ipv4 || '—';
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

    if (duckdnsToken && duckdnsToken !== '********') {
      payload.duckdns.token = duckdnsToken;
    }
    if (cfToken && cfToken !== '********') {
      payload.cloudflare.token = cfToken;
    }

    try {
      const response = await fetch('/api/ddns/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();

      if (data.success) {
        window.AsyncButtonState.success(saveBtn);
        showAlert(data.message, 'success');
        // Refresh to show newly triggered sync
        setTimeout(loadData, 2000);
      } else {
        window.AsyncButtonState.error(saveBtn);
        showAlert(data.message || 'Failed to save configuration', 'error');
      }
    } catch (error) {
      console.error('Error saving:', error);
      window.AsyncButtonState.error(saveBtn);
      showAlert('Connection error while saving.', 'error');
    }
  });

  // Force sync handling
  if (runBtn) {
    runBtn.addEventListener('click', async () => {
      // Because we use data-confirm, standard global handler intercepts it, 
      // but we override or attach. Simple approach for custom routes:
    });

    const observer = new MutationObserver((mutations) => {
         // Because common.js handles data-confirm, it will replace this button's functionality
         // wait I can just call the POST to task since its standard. Let's do it manually if custom.
         // Actually the standard data-confirm requires an href or form.
         // Let's implement our own confirm for AJAX. 
    });
  }

  document.addEventListener('click', async (e) => {
    if (e.target && e.target.id === 'confirmationModalConfirmBtn') {
        const title = document.getElementById('confirmationModalTitle').textContent;
        if (title === "Run DDNS Checks") {
             const btn = document.getElementById('confirmationModalConfirmBtn');
             btn.disabled = true;
             btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Running...';
             try {
                const response = await fetch('/task/DDNS%20Update/start', { 
                   method: 'POST',
                   headers: {
                       'Accept': 'application/json'
                   }
                });
                const json = await response.json();
                if (json.success) {
                     showAlert('DDNS Sync started successfully.', 'success');
                     setTimeout(loadData, 3000);
                } else {
                     showAlert('Started check remotely...', 'info'); // if it doesn't return json
                     setTimeout(loadData, 3000);
                }
             } catch (err) {
                 setTimeout(loadData, 2000);
             } finally {
                 document.getElementById('confirmationModalCancelBtn').click();
                 btn.disabled = false;
                 btn.textContent = 'Confirm';
             }
        }
    }
  });

  // Init
  loadData();
});
