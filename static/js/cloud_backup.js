// Cloud Backup Page JS

function renderStatusBadge(status) {
  if (status === 'Success') return '<span class="badge badge-success"><i class="fas fa-circle-check"></i> Success</span>';
  if (status === 'Failure') return '<span class="badge badge-danger"><i class="fas fa-circle-xmark"></i> Failure</span>';
  if (status === 'Running') return '<span class="badge badge-info"><i class="fas fa-spinner fa-spin"></i> Running</span>';
  if (status === 'Missing') return '<span class="badge badge-warning"><i class="fas fa-circle-exclamation"></i> Missing</span>';
  if (status === 'Not Run Yet') return '<span class="badge badge-neutral"><i class="fas fa-clock"></i> Not Run Yet</span>';
  if (status === 'Error') return '<span class="badge badge-danger"><i class="fas fa-triangle-exclamation"></i> Error</span>';
  if (status === 'Disabled') return '<span class="badge badge-neutral">Disabled</span>';
  return '<span class="badge badge-neutral">Unknown</span>';
}

function loadStatus() {
  const statusBadge = document.getElementById('cloud-backup-status-badge');
  const lastRun = document.getElementById('cloud-backup-last-run');
  const nextRun = document.getElementById('cloud-backup-next-run');
  const lastDuration = document.getElementById('cloud-backup-last-duration');

  window.ApiClient.fetchJson('/api/cloud_backup/status')
    .then(({
      data
    }) => {
      const s = data;
      document.getElementById('cloud-backup-run-btn').disabled = ['Disabled', 'Running'].includes(s.status);
      statusBadge.innerHTML = renderStatusBadge(s.status);
      lastRun.textContent = window.formatRelativeTimestamp(s.last_run, {
        fallback: '-'
      });
      lastRun.title = s.last_run || '';
      nextRun.textContent = window.formatRelativeTimestamp(s.next_run, {
        fallback: '-',
        futurePrefix: false
      });
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

  window.ApiClient.fetchJson('/api/cloud_backup/run', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    })
    .then(({
      message
    }) => {
      window.AsyncButtonState.success(runBtn, {
        restoreDisabled: false
      });
      showAlert(message || 'Cloud backup started.', 'success');
      loadStatus();
    })
    .catch(e => {
      window.AsyncButtonState.error(runBtn);
      showAlert(e.message || 'Could not start backup.', 'danger');
    });
}

document.addEventListener('DOMContentLoaded', () => {
  const editor = document.getElementById('rclone-editor');
  window.RcloneEditor.mount(editor);
  editor.addEventListener('rclone:saved', loadStatus);
  document.getElementById('cloud-backup-run-btn').addEventListener('click', runBackupNow);
  const form = document.getElementById('cloud-backup-schedule-form');
  const time = document.getElementById('backupTime');
  const bandwidth = document.getElementById('bandwidthLimit');
  window.ApiClient.fetchJson('/api/cloud_backup/schedule').then(({
    data
  }) => {
    const parts = (data.backup_cloud_time || '').split(':');
    time.value = parts.length >= 2 ? `${parts[0].padStart(2,'0')}:${parts[1]}` : '';
    bandwidth.value = data.bandwidth_limit || '';
  }).catch(error => showAlert(error.message, 'danger'));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!time.value) {
      time.reportValidity();
      return;
    }
    const button = event.submitter;
    window.AsyncButtonState.start(button);
    try {
      await window.ApiClient.fetchJson('/api/cloud_backup/schedule', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          backup_cloud_time: time.value,
          bandwidth_limit: bandwidth.value.trim()
        })
      });
      window.AsyncButtonState.success(button);
      showAlert('Schedule saved.', 'success');
      loadStatus();
    } catch (error) {
      window.AsyncButtonState.error(button);
      showAlert(error.message, 'danger');
    }
  });
  loadStatus();
  setInterval(() => {
    if (!document.hidden) loadStatus();
  }, 10000);
});
