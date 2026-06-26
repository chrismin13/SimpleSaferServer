// Shared folder picker.
// MEGA still uses the original openMegaFolderPicker name; local storage uses
// the same picker with file display enabled and folder creation disabled.

window.openMegaFolderPicker = function openMegaFolderPicker(options) {
  const {
    getCredentials = () => null, // function that returns { email, password }
    onSelect,       // function(folderPath) called when folder is selected
    modalId,        // ID of the modal overlay (e.g., 'megaFolderPickerModal')
    listUrl = '/api/cloud_backup/mega/list_folders',
    createUrl = '/api/cloud_backup/mega/create_folder',
    startPath = '/',
    canCreate = true,
    showFiles = false,
    emptyMessage = showFiles ? 'No folders or files in this directory.' : 'No subfolders in this directory.',
    credentialsRequiredMessage = 'MEGA credentials are required before creating a folder.',
    copy = {}
  } = options;
  const copyOverrides = copy && typeof copy === 'object' ? copy : {};
  const pickerCopy = {
    loading: copyOverrides.loading || 'Loading...',
    emptyMessage: copyOverrides.emptyMessage || emptyMessage,
    credentialsRequired: copyOverrides.credentialsRequired || credentialsRequiredMessage,
    loadFailed: copyOverrides.loadFailed || 'Could not load folders.',
    createFailed: copyOverrides.createFailed || 'Error creating folder.'
  };

  const resolvedId = modalId;
  if (!resolvedId) return;

  const modalEl = document.getElementById(resolvedId);
  if (!modalEl) return;

  function pickerElement(selector) {
    return modalEl.querySelector(selector);
  }

  const currentPathEl = pickerElement('.folder-picker-current-path');
  const dirsListEl = pickerElement('.folder-picker-dirs-list');
  const upBtn = pickerElement('.folder-picker-up-btn');
  const createFolderBtn = pickerElement('.folder-picker-create-folder-btn');
  const newFolderNameEl = pickerElement('.folder-picker-new-folder-name');
  const saveNewFolderBtn = pickerElement('.folder-picker-save-new-folder-btn');
  const errorEl = pickerElement('.folder-picker-error');
  const selectCurrentBtn = pickerElement('.folder-picker-select-current-btn');

  let currentPath = startPath || '/';
  let parentPath = '/';

  function showError(msg) {
    if (!errorEl) return;
    errorEl.textContent = '';
    const icon = document.createElement('i');
    icon.className = 'fas fa-circle-exclamation';
    const text = document.createElement('span');
    text.textContent = msg;
    errorEl.appendChild(icon);
    errorEl.appendChild(text);
    errorEl.classList.remove('d-none');
    errorEl.classList.add('visible');
  }
  function clearError() {
    if (!errorEl) return;
    errorEl.textContent = '';
    errorEl.classList.add('d-none');
    errorEl.classList.remove('visible');
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function joinPath(basePath, name) {
    return (basePath || '/').replace(/\/$/, '') + '/' + name;
  }

  function parentForPath(path) {
    const normalized = path || '/';
    if (normalized === '/') return null;
    const withoutTrailingSlash = normalized.replace(/\/+$/, '') || '/';
    if (withoutTrailingSlash === '/') return null;
    const parent = withoutTrailingSlash.split('/').slice(0, -1).join('/');
    return parent || '/';
  }

  function responseEntries(data) {
    if (Array.isArray(data.entries)) {
      return showFiles ? data.entries : data.entries.filter(entry => entry.type === 'folder');
    }
    if (Array.isArray(data.dirs)) {
      return data.dirs.map(dir => ({ name: dir, type: 'folder' }));
    }
    return (data.folders || []).map(folder => ({ name: folder, type: 'folder' }));
  }

  function loadDirs(path) {
    const loadId = Number(modalEl.dataset.megaPickerActiveLoadId || 0) + 1;
    modalEl.dataset.megaPickerActiveLoadId = String(loadId);
    currentPath = path || '/';
    parentPath = parentForPath(currentPath) || '/';
    clearError();
    if (currentPathEl) window.renderPathBreadcrumbs(currentPathEl, currentPath, loadDirs);
    if (upBtn) upBtn.disabled = !parentForPath(currentPath);
    if (dirsListEl) {
      dirsListEl.innerHTML = `
        <div class="folder-list-loading" aria-live="polite">
          <span class="spinner" aria-hidden="true"></span>
          <span class="text-muted">${escapeHtml(pickerCopy.loading)}</span>
        </div>
      `;
    }
    const creds = getCredentials();
    const requestBody = { path };
    if (creds && creds.email) requestBody.email = creds.email;
    if (creds && creds.password) requestBody.password = creds.password;
    window.ApiClient.fetchJson(listUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    })
      .then(({ data }) => {
        if (String(loadId) !== modalEl.dataset.megaPickerActiveLoadId) return;
        currentPath = data.path;
        parentPath = data.parent || '/';
        if (currentPathEl) window.renderPathBreadcrumbs(currentPathEl, currentPath, loadDirs);
        if (dirsListEl) dirsListEl.innerHTML = '';
        if (upBtn) upBtn.disabled = !data.parent;
        const entries = responseEntries(data);
        if (entries.length > 0) {
          entries.forEach(entry => {
            const item = document.createElement('div');
            item.className = 'folder-list-item';
            const isFolder = entry.type === 'folder';
            if (!isFolder) item.classList.add('folder-list-item-file');

            const icon = document.createElement('i');
            icon.className = isFolder ? 'fas fa-folder' : 'fas fa-file';

            const nameSpan = document.createElement('span');
            nameSpan.textContent = entry.name;

            item.appendChild(icon);
            item.appendChild(document.createTextNode(' '));
            item.appendChild(nameSpan);
            item.title = entry.name;
            if (isFolder) {
              item.setAttribute('role', 'button');
              item.setAttribute('tabindex', '0');
              item.addEventListener('click', function () {
                loadDirs(joinPath(currentPath, entry.name));
              });
              item.addEventListener('keydown', function (event) {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                event.preventDefault();
                loadDirs(joinPath(currentPath, entry.name));
              });
            } else {
              item.setAttribute('aria-disabled', 'true');
            }
            dirsListEl.appendChild(item);
          });
        } else if (dirsListEl) {
          const emptyMsg = document.createElement('div');
          emptyMsg.className = 'folder-list-item text-muted';
          emptyMsg.style.cursor = 'default';
          emptyMsg.textContent = pickerCopy.emptyMessage;
          dirsListEl.appendChild(emptyMsg);
        }
        clearError();
      })
      .catch(e => {
        if (String(loadId) !== modalEl.dataset.megaPickerActiveLoadId) return;
        if (dirsListEl) dirsListEl.innerHTML = '';
        showError(e.message || pickerCopy.loadFailed);
      });
  }

  if (upBtn) upBtn.onclick = () => {
    if (parentForPath(currentPath)) loadDirs(parentPath);
  };
  if (selectCurrentBtn) selectCurrentBtn.onclick = () => {
    if (onSelect) onSelect(currentPath);
    AppModal.hide(resolvedId);
  };
  if (createFolderBtn) createFolderBtn.onclick = () => {
    if (!canCreate) return;
    newFolderNameEl.classList.remove('d-none');
    saveNewFolderBtn.classList.remove('d-none');
  };
  if (createFolderBtn) createFolderBtn.classList.toggle('d-none', !canCreate);
  if (newFolderNameEl) newFolderNameEl.classList.add('d-none');
  if (saveNewFolderBtn) saveNewFolderBtn.classList.add('d-none');
  if (saveNewFolderBtn) saveNewFolderBtn.onclick = () => {
    if (!canCreate) return;
    const folderName = newFolderNameEl.value.trim();
    if (!folderName) {
      newFolderNameEl.classList.add('is-invalid');
      return;
    }
    newFolderNameEl.classList.remove('is-invalid');
    window.AsyncButtonState.start(saveNewFolderBtn);
    const creds = getCredentials();
    if (!creds || !creds.email || !creds.password) {
      window.AsyncButtonState.error(saveNewFolderBtn);
      showError(pickerCopy.credentialsRequired);
      return;
    }
    window.ApiClient.fetchJson(createUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder_name: folderName, path: currentPath, email: creds.email, password: creds.password })
    })
      .then(() => {
        window.AsyncButtonState.success(saveNewFolderBtn);
        newFolderNameEl.value = '';
        newFolderNameEl.classList.add('d-none');
        saveNewFolderBtn.classList.add('d-none');
        loadDirs(currentPath);
      })
      .catch(e => {
        window.AsyncButtonState.error(saveNewFolderBtn);
        showError(e.message || pickerCopy.createFailed);
      });
  };

  // Clear stale modal errors when the picker closes.
  if (!modalEl.dataset.megaPickerErrorBound) {
    modalEl.addEventListener('modal:hidden', clearError);
    modalEl.dataset.megaPickerErrorBound = 'true';
  }
  loadDirs(startPath || '/');
  AppModal.show(resolvedId);
};
