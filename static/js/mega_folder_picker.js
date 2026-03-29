// Shared MEGA Folder Picker
// Usage: openMegaFolderPicker({ getCredentials, onSelect, modalId })

window.openMegaFolderPicker = function openMegaFolderPicker(options) {
  const {
    getCredentials, // function that returns { email, password }
    onSelect,       // function(folderPath) called when folder is selected
    modalId,        // ID of the modal overlay (e.g., 'megaFolderPickerModal')
    // Support legacy modalSelector option
    modalSelector,
    listUrl = '/api/cloud_backup/mega/list_folders',
    createUrl = '/api/cloud_backup/mega/create_folder'
  } = options;

  // Resolve modal element from modalId or modalSelector
  const resolvedId = modalId || (modalSelector ? modalSelector.replace('#', '') : null);
  if (!resolvedId) return;

  const modalEl = document.getElementById(resolvedId);
  if (!modalEl) return;

  const currentPathEl = modalEl.querySelector('.mega-picker-current-path') || document.getElementById('megaPickerCurrentPath');
  const dirsListEl = modalEl.querySelector('.mega-picker-dirs-list') || document.getElementById('megaPickerDirsList');
  const upBtn = modalEl.querySelector('.mega-picker-up-btn') || document.getElementById('megaPickerUpBtn');
  const createFolderBtn = modalEl.querySelector('.mega-picker-create-folder-btn') || document.getElementById('megaPickerCreateFolderBtn');
  const newFolderNameEl = modalEl.querySelector('.mega-picker-new-folder-name') || document.getElementById('megaPickerNewFolderName');
  const saveNewFolderBtn = modalEl.querySelector('.mega-picker-save-new-folder-btn') || document.getElementById('megaPickerSaveNewFolderBtn');
  const errorEl = modalEl.querySelector('.mega-picker-error') || document.getElementById('megaPickerError');
  const selectCurrentBtn = modalEl.querySelector('.mega-picker-select-current-btn') || document.getElementById('megaPickerSelectCurrentBtn');

  let currentPath = '/';
  let parentPath = '/';

  function showError(msg) {
    if (errorEl) {
      errorEl.innerHTML = `<i class="fas fa-circle-exclamation"></i><span>${msg}</span>`;
      errorEl.classList.add('visible');
    }
  }
  function clearError() {
    if (!errorEl) return;
    errorEl.textContent = '';
    errorEl.classList.remove('visible');
  }

  function parseJsonResponse(response) {
    return response.text().then(text => {
      try {
        return JSON.parse(text);
      } catch (error) {
        throw new Error(`Unexpected response from server (${response.status})`);
      }
    });
  }

  function loadDirs(path) {
    clearError();
    if (dirsListEl) {
      dirsListEl.innerHTML = `
        <div class="folder-list-loading" aria-live="polite">
          <span class="spinner" aria-hidden="true"></span>
          <span class="text-muted">Loading...</span>
        </div>
      `;
    }
    const creds = getCredentials();
    fetch(listUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, email: creds ? creds.email : null, password: creds ? creds.password : null })
    })
      .then(parseJsonResponse)
      .then(data => {
        if (!data.success && data.error) throw new Error(data.error);
        currentPath = data.path;
        parentPath = data.parent;
        if (currentPathEl) window.renderPathBreadcrumbs(currentPathEl, currentPath, loadDirs);
        if (dirsListEl) dirsListEl.innerHTML = '';
        if (data.folders && data.folders.length > 0) {
          data.folders.forEach(folder => {
            const item = document.createElement('div');
            item.className = 'folder-list-item';

            const icon = document.createElement('i');
            icon.className = 'fas fa-folder';

            const nameSpan = document.createElement('span');
            nameSpan.textContent = folder;

            item.appendChild(icon);
            item.appendChild(document.createTextNode(' '));
            item.appendChild(nameSpan);
            item.title = folder;
            item.setAttribute('role', 'button');
            item.setAttribute('tabindex', '0');
            item.addEventListener('click', function () {
              loadDirs(currentPath.replace(/\/$/, '') + '/' + folder);
            });
            dirsListEl.appendChild(item);
          });
        } else if (dirsListEl) {
          const emptyMsg = document.createElement('div');
          emptyMsg.className = 'folder-list-item text-muted';
          emptyMsg.style.cursor = 'default';
          emptyMsg.textContent = 'No subfolders in this directory.';
          dirsListEl.appendChild(emptyMsg);
        }
        clearError();
      })
      .catch(e => {
        if (dirsListEl) dirsListEl.innerHTML = '';
        showError(e.message || 'Could not load folders.');
      });
  }

  if (upBtn) upBtn.onclick = () => loadDirs(parentPath);
  if (selectCurrentBtn) selectCurrentBtn.onclick = () => {
    if (onSelect) onSelect(currentPath);
    BunkerModal.hide(resolvedId);
  };
  if (createFolderBtn) createFolderBtn.onclick = () => {
    newFolderNameEl.classList.remove('d-none');
    saveNewFolderBtn.classList.remove('d-none');
  };
  if (saveNewFolderBtn) saveNewFolderBtn.onclick = () => {
    const folderName = newFolderNameEl.value.trim();
    if (!folderName) {
      newFolderNameEl.classList.add('is-invalid');
      return;
    }
    newFolderNameEl.classList.remove('is-invalid');
    window.AsyncButtonState.start(saveNewFolderBtn);
    const creds = getCredentials();
    fetch(createUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder_name: folderName, path: currentPath, email: creds.email, password: creds.password })
    })
      .then(parseJsonResponse)
      .then(data => {
        if (data.success) {
          window.AsyncButtonState.success(saveNewFolderBtn);
          newFolderNameEl.value = '';
          newFolderNameEl.classList.add('d-none');
          saveNewFolderBtn.classList.add('d-none');
          loadDirs(currentPath);
        } else {
          window.AsyncButtonState.error(saveNewFolderBtn);
          showError(data.error || 'Failed to create folder.');
        }
      })
      .catch(e => {
        window.AsyncButtonState.error(saveNewFolderBtn);
        showError(e.message || 'Error creating folder.');
      });
  };

  // Start at root
  if (!modalEl.dataset.megaPickerErrorBound) {
    modalEl.addEventListener('modal:hidden', clearError);
    modalEl.dataset.megaPickerErrorBound = 'true';
  }
  loadDirs('/');
  BunkerModal.show(resolvedId);
};
