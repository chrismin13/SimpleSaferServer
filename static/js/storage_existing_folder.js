(function () {
  const existingPathInput = document.getElementById('existingStoragePath');
  const saveExistingBtn = document.getElementById('saveExistingStorageBtn');
  const browseExistingBtn = document.getElementById('browseExistingStorageBtn');
  const existingError = document.getElementById('existingStorageError');
  const existingStatus = document.getElementById('existingStorageStatus');
  const defaultCopy = {
    messages: {
      pathRequired: 'Enter a storage folder path.',
      saving: 'Saving storage folder...',
      saved: 'Storage folder saved.',
      saveFailed: 'Could not save storage folder.'
    },
    folderPicker: {
      loading: 'Loading...',
      emptyMessage: 'No folders or files in this directory.',
      loadFailed: 'Could not load folders.'
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
    const script = document.getElementById('storage-existing-folder-copy');
    if (!script) return defaultCopy;
    try {
      return mergeCopy(JSON.parse(JSON.stringify(defaultCopy)), JSON.parse(script.textContent || '{}'));
    } catch (error) {
      console.error('Could not read Storage existing-folder page copy:', error);
      return defaultCopy;
    }
  }

  const copy = readCopy();

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
      showInlineError(copy.messages.pathRequired);
      return;
    }

    setStatus(copy.messages.saving, 'info');
    window.AsyncButtonState.start(saveExistingBtn);
    try {
      const { message } = await window.ApiClient.fetchJson('/api/storage/existing-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      setStatus(message || copy.messages.saved, 'success');
      window.AsyncButtonState.success(saveExistingBtn);
      if (window.showAlert) window.showAlert(message || copy.messages.saved, 'success');
      window.setTimeout(() => {
        window.location.assign('/storage');
      }, 900);
    } catch (error) {
      window.AsyncButtonState.error(saveExistingBtn);
      setStatus('', 'info');
      showInlineError(error.message || copy.messages.saveFailed);
    }
  }

  function browseExistingStorage() {
    if (!window.openMegaFolderPicker || !existingPathInput) return;
    window.openMegaFolderPicker({
      modalId: 'existingStorageFolderPickerModal',
      listUrl: '/api/storage/list-path',
      startPath: existingPathInput.value.trim() || '/',
      canCreate: false,
      showFiles: true,
      copy: copy.folderPicker,
      onSelect: (folderPath) => {
        existingPathInput.value = folderPath;
        hideInlineError();
      }
    });
  }

  if (browseExistingBtn) browseExistingBtn.addEventListener('click', browseExistingStorage);
  if (saveExistingBtn) saveExistingBtn.addEventListener('click', saveExistingStorage);
})();
