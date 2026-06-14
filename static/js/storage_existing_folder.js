(function () {
  const existingPathInput = document.getElementById('existingStoragePath');
  const saveExistingBtn = document.getElementById('saveExistingStorageBtn');
  const existingError = document.getElementById('existingStorageError');
  const existingStatus = document.getElementById('existingStorageStatus');

  function showInlineError(message) {
    if (!existingError) return;
    existingError.textContent = message;
    existingError.classList.remove('d-none');
  }

  function hideInlineError() {
    if (!existingError) return;
    existingError.textContent = '';
    existingError.classList.add('d-none');
  }

  function setStatus(message, type) {
    if (!existingStatus) return;
    existingStatus.textContent = message || '';
    existingStatus.className = 'drive-setup-status';
    const classMap = {
      info: 'text-info',
      success: 'text-success',
      error: 'text-danger'
    };
    existingStatus.classList.add(classMap[type || 'info'] || 'text-muted');
  }

  async function saveExistingStorage() {
    hideInlineError();
    const path = existingPathInput ? existingPathInput.value.trim() : '';
    if (!path) {
      showInlineError('Enter a storage folder path.');
      return;
    }

    setStatus('Saving storage folder...', 'info');
    window.AsyncButtonState.start(saveExistingBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/storage/existing-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      setStatus(message || 'Storage folder saved.', 'success');
      window.AsyncButtonState.success(saveExistingBtn);
      if (window.showAlert) window.showAlert(message || 'Storage folder saved.', 'success');
      window.setTimeout(() => {
        window.location.assign('/storage');
      }, 900);
    } catch (error) {
      window.AsyncButtonState.error(saveExistingBtn);
      setStatus('', 'info');
      showInlineError(error.message || 'Could not save storage folder.');
    }
  }

  if (saveExistingBtn) saveExistingBtn.addEventListener('click', saveExistingStorage);
})();
