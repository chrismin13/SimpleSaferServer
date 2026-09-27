// Shared local folder picker for setup and storage maintenance.
window.openFolderPicker = function openFolderPicker(options) {
  const {
    onSelect,
    modalId,
    listUrl,
    startPath = '/',
    showFiles = false,
    emptyMessage = showFiles ? 'No folders or files in this directory.' : 'No subfolders in this directory.'
  } = options;
  const resolvedId = modalId;
  const modalEl = document.getElementById(resolvedId);
  if (!modalEl) return;
  const currentPathEl = modalEl.querySelector('.folder-picker-current-path');
  const dirsListEl = modalEl.querySelector('.folder-picker-dirs-list');
  const upBtn = modalEl.querySelector('.folder-picker-up-btn');
  const errorEl = modalEl.querySelector('.folder-picker-error');
  const selectCurrentBtn = modalEl.querySelector('.folder-picker-select-current-btn');

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
    return (data.folders || []).map(folder => ({
      name: folder,
      type: 'folder'
    }));
  }

  function loadDirs(path) {
    const loadId = Number(modalEl.dataset.folderPickerActiveLoadId || 0) + 1;
    modalEl.dataset.folderPickerActiveLoadId = String(loadId);
    currentPath = path || '/';
    parentPath = parentForPath(currentPath) || '/';
    clearError();
    if (currentPathEl) window.renderPathBreadcrumbs(currentPathEl, currentPath, loadDirs);
    if (upBtn) upBtn.disabled = !parentForPath(currentPath);
    if (dirsListEl) {
      dirsListEl.innerHTML = `
        <div class="folder-list-loading" aria-live="polite">
          <span class="spinner" aria-hidden="true"></span>
          <span class="text-muted">Loading...</span>
        </div>
      `;
    }
    const requestBody = {
      path
    };
    window.ApiClient.fetchJson(listUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
      })
      .then(({
        data
      }) => {
        if (String(loadId) !== modalEl.dataset.folderPickerActiveLoadId) return;
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
              item.addEventListener('click', function() {
                loadDirs(joinPath(currentPath, entry.name));
              });
              item.addEventListener('keydown', function(event) {
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
          emptyMsg.textContent = emptyMessage;
          dirsListEl.appendChild(emptyMsg);
        }
        clearError();
      })
      .catch(e => {
        if (String(loadId) !== modalEl.dataset.folderPickerActiveLoadId) return;
        if (dirsListEl) dirsListEl.innerHTML = '';
        showError(e.message || 'Could not load folders.');
      });
  }

  if (upBtn) upBtn.onclick = () => {
    if (parentForPath(currentPath)) loadDirs(parentPath);
  };
  if (selectCurrentBtn) selectCurrentBtn.onclick = () => {
    if (onSelect) onSelect(currentPath);
    BunkerModal.hide(resolvedId);
  };
  // Start at root
  if (!modalEl.dataset.folderPickerErrorBound) {
    modalEl.addEventListener('modal:hidden', clearError);
    modalEl.dataset.folderPickerErrorBound = 'true';
  }
  loadDirs(startPath || '/');
  BunkerModal.show(resolvedId);
};
