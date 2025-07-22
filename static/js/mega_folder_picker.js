// Shared MEGA Folder Picker
// Usage: openMegaFolderPicker({ getCredentials, onSelect, modalSelector })

window.openMegaFolderPicker = function openMegaFolderPicker(options) {
  const {
    getCredentials, // function that returns { email, password }
    onSelect,       // function(folderPath) called when folder is selected
    modalSelector   // selector for the modal (e.g., '#megaFolderPickerModal')
  } = options;

  // Modal elements
  const modalEl = document.querySelector(modalSelector);
  if (!modalEl) return;
  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
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
      errorEl.textContent = msg;
      errorEl.classList.remove('d-none');
    }
  }
  function clearError() {
    if (errorEl) errorEl.classList.add('d-none');
  }

  function loadDirs(path) {
    clearError();
    if (dirsListEl) dirsListEl.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Loading...';
    const creds = getCredentials();
    fetch('/api/cloud_backup/mega/list_folders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, email: creds ? creds.email : null, password: creds ? creds.password : null })
    })
      .then(r => r.json())
      .then(data => {
        if (!data.success && data.error) throw new Error(data.error);
        currentPath = data.path;
        parentPath = data.parent;
        if (currentPathEl) currentPathEl.textContent = currentPath;
        if (dirsListEl) dirsListEl.innerHTML = '';
        if (data.folders && data.folders.length > 0) {
          data.folders.forEach(folder => {
            const item = document.createElement('a');
            item.className = 'list-group-item list-group-item-action';
            item.textContent = folder;
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
          emptyMsg.className = 'list-group-item disabled text-muted';
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
    modal.hide();
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
    saveNewFolderBtn.disabled = true;
    saveNewFolderBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Creating...';
    const creds = getCredentials();
    fetch('/api/cloud_backup/mega/create_folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder_name: folderName, path: currentPath, email: creds.email, password: creds.password })
    })
      .then(r => r.json())
      .then(data => {
        saveNewFolderBtn.disabled = false;
        saveNewFolderBtn.innerHTML = 'Create';
        if (data.success) {
          newFolderNameEl.value = '';
          newFolderNameEl.classList.add('d-none');
          saveNewFolderBtn.classList.add('d-none');
          loadDirs(currentPath);
        } else {
          showError(data.error || 'Failed to create folder.');
        }
      })
      .catch(e => {
        saveNewFolderBtn.disabled = false;
        saveNewFolderBtn.innerHTML = 'Create';
        showError(e.message || 'Error creating folder.');
      });
  };

  // Start at root
  loadDirs('/');
  modal.show();
}; 