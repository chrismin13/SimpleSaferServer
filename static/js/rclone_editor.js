/* This client renders rclone's questions. Provider branches stay inside rclone. */
window.RcloneEditor = {
  optionField(option) {
    // DefaultStr preserves rclone's syntax for durations, sizes, lists and
    // large integers. Converting through JavaScript numbers can lose data.
    const initial = option.DefaultStr ?? String(option.Default ?? '');
    const required = !!option.Required && initial === '';
    const secret = !!option.IsPassword;
    let choices = (option.Examples || []).map(item => ({ ...item, Value: String(item.Value) }));
    const boolean = option.Type === 'bool' || option.Type === 'Tristate';
    if (boolean && !choices.length) {
      choices = [{ Value: 'true', Help: 'Yes' }, { Value: 'false', Help: 'No' }];
      if (option.Type === 'Tristate') choices.push({ Value: 'unset', Help: 'Automatic (unset)' });
    }
    // Password handling takes precedence over examples and name-based hints.
    if (secret) choices = [];
    const compact = choices.length <= 5;
    const custom = choices.length > 0 && !option.Exclusive && !boolean;
    // Optional exclusive questions can accept an empty value, too. Do not
    // silently select the first example when rclone has supplied no default.
    if (choices.length && !required && initial === '' && !choices.some(item => item.Value === '')) {
      choices.unshift({ Value: '', Help: 'Leave empty (default)' });
    }
    const selected = choices.findIndex(item => item.Value === initial);
    return {
      initial, required, secret, choices, compact, custom,
      selection: selected >= 0 ? String(selected) : custom && initial !== '' ? 'custom' : '',
      multiline: !secret && (option.Name.includes('json') || initial.includes('\n'))
    };
  },

  mount(root) {
    if (root.dataset.mounted) return;
    root.dataset.mounted = "true";
    const overview = root.querySelector('[data-rclone-overview]');
    const overlay = root.querySelector('[data-rclone-modal]');
    // Setup's frosted container creates a containing block for fixed elements.
    // Keep the shared dialog at body level so it always fits the viewport.
    document.body.append(overlay);
    const $ = selector => root.querySelector(selector) || overlay.querySelector(selector);
    const content = overlay.querySelector('[data-rclone-content]');
    let opener = null,
      managementAction = null;
    const on = (type, handler) => {
      root.addEventListener(type, handler);
      overlay.addEventListener(type, handler);
    };
    const screen = root.dataset.setup === 'true' ? 'setup' : 'backup';
    const prefix = root.dataset.api;
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, char => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    } [char]));
    const icon = name => `<i class="fas fa-${name}" aria-hidden="true"></i>`;
    let state, providers = [],
      rawVersion = null;
    let view = 'home',
      selectedProvider = '',
      search = '',
      draft = null,
      path = '',
      folderData = [],
      folderError = '';
    let loadingFolders = false,
      folderVerified = false,
      flow = 'destination',
      polling = null,
      folderRequest = 0;
    let actionBusy = false,
      pollGeneration = 0;

    async function api(action, data) {
      if (data?.id && draft?.id === data.id) data = {
        ...data,
        revision: draft.revision
      };
      const {
        data: result
      } = await window.ApiClient.fetchJson(`${prefix}/${action}`, {
        method: data === undefined ? 'GET' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-SSS-Rclone': '1'
        },
        ...(data === undefined ? {} : {
          body: JSON.stringify(data)
        })
      });
      return result;
    }

    function toast(text) {
      window.showAlert(text, 'success');
    }

    function error(text) {
      const target = $('#action-error');
      if (target) target.textContent = text;
      else window.showAlert(text, 'danger');
    }

    async function perform(button, action) {
      if (actionBusy) return;
      actionBusy = true;
      window.AsyncButtonState.start(button);
      if ($('#action-error')) $('#action-error').textContent = '';
      try {
        await action();
        window.AsyncButtonState.success(button);
      } catch (err) {
        error(err.message);
        window.AsyncButtonState.error(button);
      } finally {
        actionBusy = false;
      }
    }

    const button = (action, text, style = 'secondary', extra = '') => `<button type="button" class="btn btn-${style} btn-sm" data-action="${action}" ${extra}>${text}</button>`;
    const remoteLabel = remote => providerLabel(providers.find(p => p.Name === remote.type) || {
      Name: remote.type,
      Description: remote.description
    });
    const providerLabel = provider => (provider.Description || provider.Name).split(' including ')[0];
    const destinationString = () => state.destination_text || '';

    function saved(next) {
      state = next;
      root.dispatchEvent(new CustomEvent('rclone:saved', {
        bubbles: true
      }));
    }

    function complete() {
      root.dispatchEvent(new CustomEvent('rclone:complete', {
        bubbles: true
      }));
    }

    function uniqueName(base) {
      let name = base || 'backup',
        index = 2;
      while (state.remotes.some(remote => remote.name === name)) name = `${base || 'backup'}-${index++}`;
      return name;
    }

    function connectionContext() {
      return draft ? `<code>${esc(draft.name)}</code>` : '';
    }

    function panel(body, actions, title, context = connectionContext()) {
      const opening = !overlay.classList.contains('visible');
      if (opening) opener = document.activeElement;
      $('#rclone-editor-title').textContent = title;
      $('#rclone-editor-context').innerHTML = context;
      // Only the dialog body scrolls. Questions of different lengths must not
      // move the page underneath or the Back/Next controls.
      content.innerHTML = `<div class="rclone-body-content">${body}</div><div class="rclone-editor-footer"><div id="action-error" class="rclone-error" role="alert"></div><div class="rclone-actions">${actions}</div></div>`;
      if (opening) {
        window.BunkerModal.show(overlay.id);
        root.inert = true;
      } else {
        $('#rclone-editor-title').focus({
          preventScroll: true
        });
      }
    }

    function closeEditor() {
      const wasOpen = overlay.classList.contains('visible');
      const menu = overlay.querySelector('.action-context-menu');
      if (menu) {
        window.ActionContextMenu.hide();
        document.body.append(menu);
      }
      window.BunkerModal.hide(overlay.id);
      content.replaceChildren();
      root.inert = false;
      if (wasOpen) {
        const target = opener?.isConnected ? opener : root.querySelector('button');
        target?.focus({
          preventScroll: true
        });
      }
    }

    async function cancelEditing() {
      if (draft) await cancelDraft();
      view = 'home';
      render();
    }

    function render() {
      if (view === 'providers') renderProviders();
      else if (view === 'question') renderQuestion();
      else if (view === 'pending') renderPending();
      else if (view === 'folders') renderFolders();
      else if (view === 'review') renderReview();
      else if (view === 'manage') renderManage();
      else if (view === 'remote-action') renderRemoteAction();
      else if (view === 'advanced') renderAdvanced();
      else if (view === 'test-cleanup') panel(
        '<p class="rclone-copy">The destination test has finished, but its connection session could not close. Retry closing it before editing connections.</p>',
        button('cancel', 'Retry closing', 'primary'), 'Finish connection test');
      else {
        renderHome();
        closeEditor();
      }
    }

    function renderProviders() {
      panel(`<div class="rclone-search">${icon('magnifying-glass')}<input class="form-control" id="provider-search" type="search" placeholder="Search services" value="${esc(search)}" aria-label="Search storage services"></div>
        <div id="provider-results" class="rclone-provider-grid"></div>
        <details class="rclone-help"><summary>Connection name</summary><div class="rclone-field"><label for="remote-name">Name</label><input id="remote-name" class="form-control" value="${esc(uniqueName('backup'))}" autocomplete="off"></div></details>`,
        `${button('home','Cancel')}<div class="rclone-actions-right">${button('advanced','Advanced config')}${button('start','Next '+icon('arrow-right'),'primary',selectedProvider ? '' : 'disabled')}</div>`,
        'Choose storage service');
      providerResults();
    }

    function providerResults() {
      const filtered = providers.filter(p => `${p.Name} ${p.Description}`.toLowerCase().includes(search.toLowerCase()));
      $('#provider-results').innerHTML = filtered.length ? filtered.map(p => `<button type="button" data-provider="${esc(p.Name)}" class="rclone-provider ${selectedProvider === p.Name ? 'selected' : ''}" aria-pressed="${selectedProvider === p.Name}"><span class="rclone-provider-copy"><strong>${esc(providerLabel(p))}</strong>${providers.some(other=>other.Name!==p.Name && providerLabel(other)===providerLabel(p)) ? `<small>${esc(p.Name)}</small>` : ''}</span>${selectedProvider === p.Name ? icon('check') : ''}</button>`).join('') : '<div class="rclone-empty">No services match your search.</div>';
    }

    function helpMarkup(text) {
      return esc(text).replace(/https?:\/\/[^\s<>]+/g, url => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
    }

    function questionDetails(option) {
      return `<details class="rclone-help"><summary>Details</summary><div class="rclone-help-content"><code>${esc(option.Name)}</code>\n\n${helpMarkup(option.Help || '')}</div></details>`;
    }

    function questionActions(submitLabel = 'Next') {
      return `<div class="rclone-actions-right">${button('back',icon('arrow-left')+' Back','secondary',draft.can_back ? '' : 'disabled')}${button('cancel','Cancel')}</div>${submitLabel ? `<button class="btn btn-primary btn-sm" form="question-form" type="submit">${submitLabel} ${icon('arrow-right')}</button>` : ''}`;
    }

    function renderAuthorizationChoice(option) {
      // These names belong to rclone's shared OAuth protocol, not a provider.
      panel(`<div class="rclone-auth-method">
        ${draft.oauth_supported ? button('auth-method','Sign in with browser','primary','data-answer="true"') : '<p class="rclone-copy">Update rclone to enable browser sign-in.</p>'}
        <p class="rclone-copy">On another computer? You may need to paste the final localhost address here.</p>
      </div><div class="rclone-auth-method">
        ${button('auth-method','Use rclone on another computer','secondary','data-answer="false"')}
        <p class="rclone-copy">Requires rclone on that computer.</p>
      </div>${questionDetails(option)}${draft.error ? `<div class="rclone-error" role="alert">${esc(draft.error)}</div>` : ''}`,
        questionActions(null), 'Sign in');
    }

    function answerInput(field) {
      const attributes = `id="answer" class="form-control${field.multiline ? ' rclone-code' : ''}" aria-labelledby="question-title" autocomplete="off" spellcheck="false" ${field.required ? 'required' : ''}`;
      if (field.multiline) return `<textarea ${attributes}>${esc(field.initial)}</textarea>`;
      // Keep text input for rclone-specific types; browser number/date inputs
      // reject valid units and sentinel values before rclone can validate them.
      return `<div class="rclone-secret"><input ${attributes} type="${field.secret ? 'password' : 'text'}" value="${esc(field.initial)}">${field.secret ? button('reveal',icon('eye'),'secondary','aria-label="Show password"') : ''}</div>`;
    }

    function answerControl(field) {
      if (!field.choices.length) return answerInput(field);
      const choices = field.choices.map((item, index) => ({ ...item, key: String(index) }));
      // Use separate selection keys so real values like "custom" or "" never
      // collide with the UI's custom-entry option.
      if (field.custom) choices.push({ key: 'custom', Help: 'Custom value', Value: '' });
      let control;
      if (field.compact) {
        control = `<div class="rclone-choice-list" role="group" aria-labelledby="question-title">${choices.map(item => `<label class="rclone-choice"><input type="radio" name="answer-choice" value="${esc(item.key)}" ${item.key === field.selection ? 'checked' : ''}><span>${esc(item.Help || item.Value)}${item.Value && item.Help && item.Help !== item.Value ? `<small>${esc(item.Value)}</small>` : ''}</span></label>`).join('')}</div>`;
      } else {
        control = `<select id="answer-choice" name="answer-choice" class="form-control" aria-labelledby="question-title"><option value="" disabled ${field.selection === '' ? 'selected' : ''}>Choose an option…</option>${choices.map(item => `<option value="${esc(item.key)}" ${item.key === field.selection ? 'selected' : ''}>${esc((item.Help || item.Value).split('\n')[0])}${item.Value && item.Help !== item.Value ? ` — ${esc(item.Value)}` : ''}</option>`).join('')}</select><div id="answer-choice-help" class="rclone-help-content"></div>`;
      }
      if (field.custom) control += `<div id="answer-custom" class="rclone-field" hidden><label for="answer">Custom value</label>${answerInput(field)}</div>`;
      return control;
    }

    function selectedAnswerChoice() {
      return $('#answer-choice')?.value ?? $('input[name="answer-choice"]:checked')?.value;
    }

    function updateAnswerChoice(focus = false) {
      const selection = selectedAnswerChoice();
      const custom = $('#answer-custom');
      if (custom) {
        custom.hidden = selection !== 'custom';
        $('#answer').disabled = custom.hidden;
        if (focus && !custom.hidden) $('#answer').focus({ preventScroll: true });
      }
      const help = $('#answer-choice-help');
      if (help) {
        const field = window.RcloneEditor.optionField(draft.option);
        help.textContent = field.choices[selection]?.Help || '';
      }
    }

    function questionAnswer() {
      const field = window.RcloneEditor.optionField(draft.option);
      if (!field.choices.length || selectedAnswerChoice() === 'custom') return $('#answer').value;
      const choice = field.choices[selectedAnswerChoice()];
      if (!choice) throw new Error('Choose an answer to continue.');
      return choice.Value;
    }

    function renderQuestion() {
      const option = draft.option;
      if (!option) {
        panel(`<p class="rclone-copy">${esc(draft.error || 'Restart this connection to continue.')}</p>`, `${button('cancel','Cancel connection')}${button('back','Go back','secondary',draft.can_back ? '' : 'disabled')}`, 'Connection needs attention');
        return;
      }
      if (option.Name === 'config_is_local' && option.Type === 'bool') {
        renderAuthorizationChoice(option);
        return;
      }
      const field = window.RcloneEditor.optionField(option);
      const initial = field.initial;
      const lines = (option.Help || '').split('\n');
      const title = lines[0] || option.Name;
      const tokenQuestion = option.Name === 'config_token';
      if (tokenQuestion) {
        panel(`
        <div class="rclone-help-content rclone-auth-instructions">${helpMarkup(option.Help || '')}</div>
        <form id="question-form"><label class="rclone-label" for="answer">Authorization result</label><textarea id="answer" class="form-control rclone-code" autocomplete="off" spellcheck="false" placeholder="Paste the result from rclone">${esc(initial)}</textarea></form>
        ${draft.error ? `<div class="rclone-error" role="alert">${esc(draft.error)}</div>` : ''}`, questionActions('Apply authorization'), 'Authorize with rclone');
        return;
      }
      const help = lines.slice(1).join('\n').trim();
      panel(`<form id="question-form"><div class="rclone-field">
        <h3 id="question-title">${esc(title)}</h3>
        <div aria-labelledby="question-title">${answerControl(field)}</div>
        ${!option.Required && !initial ? '<p class="rclone-default">Optional</p>' : ''}
        <div class="rclone-help"><div class="rclone-help-content">${helpMarkup(help)}${help ? '\n\n' : ''}<code>${esc(option.Name)}</code></div>
        </div>
        </div></form>${draft.error ? `<div class="rclone-error" role="alert">${esc(draft.error)}</div>` : ''}`,
        questionActions(), flow === 'edit' ? 'Connection settings' : 'Connect storage');
      updateAnswerChoice();
      (overlay.querySelector('input[name="answer-choice"]:checked') || $('#answer-choice') || overlay.querySelector('input[name="answer-choice"]') || $('#answer'))?.focus({
        preventScroll: true
      });
    }

    function renderPending() {
      panel(draft.oauth ? `${button('oauth-open','Open sign-in page '+icon('arrow-up-right-from-square'),'primary')}
        <details class="rclone-help"><summary>Localhost page didn’t open?</summary><p class="rclone-copy">Copy the full address from that page and paste it below.</p>
        <label class="rclone-label" for="callback-url">Final localhost address</label><input id="callback-url" class="form-control" placeholder="http://localhost:53682/?code=…&state=…" autocomplete="off">
        <div class="rclone-field">${button('oauth-return','Complete sign-in')}</div></details>` : '<p class="rclone-copy" role="status">Waiting for rclone…</p>',
        `${button('back',icon('arrow-left')+(draft.oauth ? ' Sign-in methods' : ' Back'),'secondary',draft.can_back ? '' : 'disabled')}${button('cancel','Cancel')}`,
        draft.oauth ? 'Finish sign-in' : 'Connect storage');
    }

    function acceptDraft(next) {
      if (draft && next.id === draft.id && next.revision < draft.revision) return;
      draft = next;
      clearTimeout(polling);
      if (draft.phase === 'pending') {
        const wasPending = view === 'pending';
        const oldOAuth = $('#callback-url') !== null;
        view = 'pending';
        if (!wasPending || oldOAuth !== !!draft.oauth) render();
        const generation = ++pollGeneration,
          id = draft.id;
        polling = setTimeout(async () => {
          try {
            const next = await api('poll', {
              id
            });
            if (generation === pollGeneration && draft?.id === id) acceptDraft(next);
          } catch (err) {
            if (generation === pollGeneration) {
              error(err.message);
              $('#action-error')?.insertAdjacentHTML('beforeend', '<br>' + button('poll', 'Retry'));
            }
          }
        }, 900);
      } else if (draft.phase === 'question') {
        view = 'question';
        render();
      } else if (flow === 'edit' || flow === 'manage-add') {
        view = 'review';
        render();
      } else {
        view = 'folders';
        render();
        loadFolders(path);
      }
    }

    function renderFolders() {
      const parts = path.split('/').filter(Boolean);
      const prefix = path.startsWith('/') ? '/' : '';
      panel(`<div class="rclone-folder-connection"><strong>${icon('cloud')} ${esc(draft.name)}</strong>${draft.purpose === 'choose' ? button('switch-connection','Switch storage connection') : ''}</div>
        <div class="rclone-breadcrumbs"><button type="button" data-folder-path="" aria-label="Remote root">${icon('house')}</button>${parts.map((part,i)=>`<span>/</span><button type="button" data-folder-path="${esc(prefix+parts.slice(0,i+1).join('/'))}">${esc(part)}</button>`).join('')}</div>
        <form id="path-form" class="rclone-inline-form"><input class="form-control" id="folder-path" value="${esc(path)}" placeholder="Remote root" aria-label="Destination folder path"><button class="btn btn-secondary btn-sm">Go</button></form>
        <div class="rclone-folder-toolbar"><span>${loadingFolders ? 'Loading…' : `${folderData.length} ${folderData.length === 1 ? 'folder' : 'folders'}`}</span>${button('new-folder',icon('folder-plus')+' New folder','secondary',loadingFolders ? 'disabled' : '')}</div>
        <form id="new-folder-form" class="rclone-inline-form" hidden><input id="new-folder-name" class="form-control" placeholder="Folder name" aria-label="New folder name" required><button class="btn btn-primary btn-sm">Create</button><small>Created immediately.</small></form>
        <div class="rclone-folder-list" aria-live="polite">${loadingFolders ? '<div class="rclone-empty">Loading…</div>' : folderData.length ? folderData.map(entry => `<button type="button" class="rclone-folder" data-folder-path="${esc(joinPath(path,entry.Name))}">${icon('folder')}<span>${esc(entry.Name)}</span>${icon('chevron-right')}</button>`).join('') : `<div class="rclone-empty">${folderError ? 'Cannot list this folder.' : 'No subfolders.'}</div>`}</div>
        ${folderError ? `<div class="rclone-error">${esc(folderError)}</div><p class="rclone-default">You can still enter an exact destination path.</p>` : ''}`,
        `${button('cancel','Cancel')}${button('review','Use this folder '+icon('arrow-right'),'primary',loadingFolders ? 'disabled' : '')}`, 'Destination folder', '');
    }

    function joinPath(base, name) {
      return base ? `${base.replace(/\/$/,'')}/${name}` : name;
    }

    async function loadFolders(nextPath) {
      const request = ++folderRequest;
      path = nextPath;
      folderData = [];
      folderError = '';
      loadingFolders = true;
      folderVerified = false;
      renderFolders();
      try {
        const result = await api('folders', {
          id: draft.id,
          path
        });
        if (request !== folderRequest || view !== 'folders') return;
        folderData = result.folders;
        folderVerified = true;
      } catch (err) {
        if (request !== folderRequest || view !== 'folders') return;
        folderError = err.message;
      } finally {
        if (request === folderRequest && view === 'folders') {
          loadingFolders = false;
          renderFolders();
        }
      }
    }

    function renderReview() {
      const connectionOnly = ['edit', 'manage-add'].includes(flow);
      panel(`<div class="rclone-summary-row"><span>Connection</span><code>${esc(draft.name)}</code></div>
        ${connectionOnly ? '' : `<div class="rclone-summary-row"><span>Destination</span><code>${esc(draft.name+':'+path)}</code></div>
        ${folderVerified ? '' : '<p class="rclone-default">Folder access has not been verified.</p>'}
        <div class="rclone-warning">Files in this destination will be overwritten or deleted as needed to match your server.</div>
        <label class="rclone-ack"><input id="destination-ack" type="checkbox">Use this folder only for this server’s backups.</label>`}`,
        `${connectionOnly ? button('cancel','Cancel') : button('folders',icon('arrow-left')+' Back')}${button('save',connectionOnly ? 'Save settings' : screen === 'setup' ? 'Save & continue' : 'Save destination','primary',connectionOnly ? '' : 'disabled')}`,
        connectionOnly ? 'Save connection settings' : 'Confirm destination');
    }

    function renderHome() {
      const destination = destinationString();
      const remote = state.remotes.find(item => item.name === state.destination?.name);
      const configured = !!destination;
      const mainActions = state.configuration_error ? button('advanced', 'Repair configuration', 'primary') : `${button('destination', configured ? 'Change destination' : 'Choose destination','primary')}${remote ? button('edit-current',icon('sliders')+' Connection settings','secondary','title="Account, authentication, and provider options"') : ''}`;
      overview.innerHTML = `<section class="rclone-panel rclone-overview">
        <div class="rclone-overview-heading"><h2>Backup destination</h2><span class="rclone-badge ${state.enabled ? '' : 'muted'}">${state.enabled ? 'Enabled' : 'Disabled'}</span></div>
        ${state.configuration_error ? `<p class="rclone-error">${esc(state.configuration_error)}</p>` : ''}
        <div class="rclone-destination">
          <span class="rclone-destination-icon">${icon(configured ? 'cloud' : 'cloud-arrow-up')}</span>
          <div>${remote ? `<strong>${esc(remoteLabel(remote))}</strong>` : ''}<code>${esc(destination || 'Not configured')}</code></div>
        </div>
        <div class="rclone-overview-actions">${mainActions}${button('backup-menu',icon('ellipsis')+' More','secondary','aria-label="More backup options" aria-haspopup="menu"')}</div>
        <div class="rclone-source"><span>Source</span><code>${esc(state.source || 'Not configured')}</code></div>
      </section>${screen === 'setup' ? `<div class="setup-actions">${button('skip','Skip cloud backup')}${configured ? button('complete','Continue '+icon('arrow-right'),'primary') : ''}</div>` : ''}`;
    }

    function remoteRows() {
      return state.remotes.map(remote => `<div class="rclone-management-row" data-remote-row="${esc(remote.name)}"><div><strong>${esc(remote.name)}</strong> ${state.destination?.name === remote.name ? '<span class="rclone-badge">In use</span>' : ''}<small>${esc(remoteLabel(remote))}</small></div><div class="rclone-management-actions">${button('use-remote','Select','secondary',`data-name="${esc(remote.name)}" aria-label="Use ${esc(remote.name)} as destination"`)}${flow === 'choose' ? '' : button('edit-remote','Settings','secondary',`data-name="${esc(remote.name)}" aria-label="Settings for ${esc(remote.name)}"`)+button('remote-menu',icon('ellipsis'),'secondary',`data-name="${esc(remote.name)}" aria-label="More actions for ${esc(remote.name)}"`)}</div></div>`).join('');
    }

    function renderManage() {
      panel(state.remotes.length ? remoteRows() : '<div class="rclone-empty">No saved connections.</div>',
        `${button('home','Close')}${button('add-remote',icon('plus')+' Add connection','primary')}`,
        flow === 'choose' ? 'Choose destination connection' : 'Storage connections');
    }

    function renderRemoteAction() {
      const {
        name,
        operation
      } = managementAction;
      const removing = operation === 'delete';
      panel(`<form id="remote-action-form">${removing ? `<p class="rclone-copy">Remove <strong>${esc(name)}</strong>? Remote files will be kept.</p>` : `<label class="rclone-label" for="new-remote-name">Connection name</label><input id="new-remote-name" class="form-control" value="${esc(operation === 'duplicate' ? uniqueName(name+'-copy') : name)}" required>`}</form>`,
        `${button('manage','Cancel')}<button type="submit" form="remote-action-form" class="btn btn-${removing ? 'danger' : 'primary'} btn-sm">${removing ? 'Remove' : 'Save'}</button>`,
        removing ? 'Remove connection' : operation === 'rename' ? 'Rename connection' : 'Duplicate connection');
    }

    async function renderAdvanced() {
      rawVersion = null;
      panel(`
      <form id="advanced-form"><label class="rclone-label" for="raw-config">rclone.conf <span class="text-muted">(includes credentials)</span></label><textarea id="raw-config" class="form-control rclone-code" autocomplete="off" spellcheck="false" placeholder="Loading saved configuration…" disabled></textarea>
      <div class="rclone-field"><label for="raw-destination">Exact backup destination</label><input id="raw-destination" class="form-control" placeholder="remote:folder" spellcheck="false" disabled><p class="rclone-default">Use remote:folder or an absolute local path.</p></div>
      <label class="rclone-ack"><input id="raw-enabled" type="checkbox" disabled>Enable cloud backup</label>
      <div class="rclone-warning">Files in this destination will be overwritten or deleted as needed to match your server.</div>
      <label class="rclone-ack"><input id="raw-ack" type="checkbox" disabled>This destination is dedicated to this server’s backups.</label></form>`,
        `${button('home','Cancel')}<button class="btn btn-primary btn-sm" id="raw-save" form="advanced-form" type="submit" disabled>Save configuration</button>`, 'Advanced rclone config');
      try {
        const result = await api('raw');
        if (view === 'advanced') {
          // These values share one version; page state may predate a save in
          // another tab, including a change to the destination or enable flag.
          $('#raw-config').value = result.config;
          $('#raw-destination').value = result.destination_text;
          $('#raw-enabled').checked = result.enabled;
          rawVersion = result.version;
          ['raw-config', 'raw-destination', 'raw-enabled', 'raw-ack'].forEach(id => {
            $(`#${id}`).disabled = false;
          });
          $('#raw-save').disabled = false;
        }
      } catch (err) {
        error(err.message);
      }
    }

    async function cancelDraft() {
      clearTimeout(polling);
      pollGeneration++;
      folderRequest++;
      if (draft) {
        try {
          await api('cancel', {
            id: draft.id
          });
        } catch (err) {
          if (err.status !== 409) throw err;
          // A live draft may need to save refreshed tokens once a backup finishes.
          // Only an already-ended session can be dismissed after a conflict.
          if ((await api('state')).draft?.id === draft.id) throw err;
        }
      }
      draft = null;
      path = '';
      state = await api('state');
    }

    async function startDraft(name, options = {}) {
      path = options.choose && state.destination?.name === name ? state.destination.path : '';
      const purpose = options.choose ? 'choose' : options.edit ? 'edit' : flow === 'manage-add' ? 'add' : 'destination';
      acceptDraft(await api('start', {
        name,
        type: options.type,
        purpose
      }));
    }

    function manageAction(name, operation) {
      managementAction = {
        name,
        operation
      };
      view = 'remote-action';
      render();
    }

    function showMenu(items, event) {
      const trigger = event.target.closest('button') || event.target;
      const anchor = trigger.getBoundingClientRect();
      window.ActionContextMenu.show(items, event.detail === 0 ? anchor.left : event.clientX, event.detail === 0 ? anchor.bottom : event.clientY);
      const menu = document.getElementById('globalActionContextMenu');
      (overlay.classList.contains('visible') ? overlay : document.body).append(menu);
      menu.querySelector('button')?.focus({
        preventScroll: true
      });
    }

    function backupMenu(event) {
      const items = [
        ...(state.destination ? [{
          label: 'Test destination access',
          iconClass: 'fas fa-plug',
          onSelect: () => perform(null, testDestination)
        }] : []), {
          label: 'Manage connections',
          iconClass: 'fas fa-server',
          onSelect: () => {
            flow = 'manage';
            view = 'manage';
            render();
          }
        }, {
          label: 'Advanced rclone config',
          iconClass: 'fas fa-code',
          onSelect: () => {
            view = 'advanced';
            render();
          }
        },
        ...(destinationString() ? [{
          label: state.enabled ? 'Disable cloud backup' : 'Enable cloud backup',
          iconClass: state.enabled ? 'fas fa-pause' : 'fas fa-play',
          onSelect: () => perform(null, async () => {
            saved(await api('settings', {
              enabled: !state.enabled,
              version: state.version
            }));
            renderHome();
          })
        }] : [])
      ];
      showMenu(items, event);
    }

    async function testDestination() {
      path = state.destination.path;
      draft = await api('start', {
        name: state.destination.name,
        purpose: 'choose'
      });
      try {
        await api('folders', {
          id: draft.id,
          path
        });
      } finally {
        try {
          // Listing can refresh tokens, so cleanup also reloads the saved
          // version. Keep the shared draft handle if closing needs a retry.
          await cancelDraft();
          renderHome();
        } catch (err) {
          view = 'test-cleanup';
          render();
          throw err;
        }
      }
      toast('Destination folder is accessible.');
    }

    function remoteMenu(name, event) {
      const items = [{
          label: 'Use as destination',
          iconClass: 'fas fa-folder',
          onSelect: () => perform(null, async () => {
            flow = 'destination';
            await startDraft(name, {
              edit: true,
              choose: true
            });
          })
        }, {
          label: 'Connection settings',
          iconClass: 'fas fa-pen',
          onSelect: () => perform(null, async () => {
            flow = 'edit';
            await startDraft(name, {
              edit: true
            });
          })
        },
        ...['rename', 'duplicate', 'delete'].map(operation => ({
          label: operation === 'delete' ? 'Remove connection' : operation[0].toUpperCase() + operation.slice(1),
          iconClass: `fas fa-${operation==='rename'?'i-cursor':operation==='duplicate'?'copy':'trash'}`,
          onSelect: () => manageAction(name, operation)
        }))
      ];
      showMenu(items, event);
    }

    overlay.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        if (document.getElementById('globalActionContextMenu')?.classList.contains('visible')) {
          window.ActionContextMenu.hide();
          overlay.querySelector('[data-action="remote-menu"]')?.focus();
        } else perform(null, cancelEditing);
      } else if (event.key === 'Tab') {
        const controls = [...overlay.querySelectorAll('button,input,select,textarea,a[href],summary,[tabindex="0"]')].filter(el => !el.disabled && el.getClientRects().length);
        const first = controls[0],
          last = controls.at(-1);
        if (!controls.includes(document.activeElement)) {
          event.preventDefault();
          (event.shiftKey ? last : first)?.focus();
        } else if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    });

    on('input', event => {
      if (event.target.id === 'provider-search') {
        search = event.target.value;
        providerResults();
      }
    });
    on('change', event => {
      if (event.target.id === 'destination-ack') $('[data-action="save"]').disabled = !event.target.checked;
      if (event.target.name === 'answer-choice') updateAnswerChoice(true);
    });
    on('contextmenu', event => {
      const row = event.target.closest('[data-remote-row]');
      if (row) {
        event.preventDefault();
        remoteMenu(row.dataset.remoteRow, event);
      }
    });

    on('submit', event => {
      const form = event.target;
      if (!['question-form', 'path-form', 'new-folder-form', 'advanced-form', 'remote-action-form'].includes(form.id)) return;
      event.preventDefault();
      const submitter = event.submitter;
      perform(submitter, async () => {
        if (form.id === 'question-form') {
          const answer = draft.option.Name === 'config_token' ? $('#answer').value : questionAnswer();
          acceptDraft(await api('advance', {
            id: draft.id,
            answer
          }));
        } else if (form.id === 'remote-action-form') {
          saved(await api('manage', {
            ...managementAction,
            new_name: $('#new-remote-name')?.value,
            version: state.version
          }));
          view = 'manage';
          render();
          renderHome();
          toast('Connection saved.');
        } else if (form.id === 'path-form') await loadFolders($('#folder-path').value);
        else if (form.id === 'new-folder-form') {
          await api('mkdir', {
            id: draft.id,
            path,
            name: $('#new-folder-name').value
          });
          await loadFolders(path);
          toast('Folder created.');
        } else if (form.id === 'advanced-form') {
          saved(await api('apply_raw', {
            config: $('#raw-config').value,
            destination: $('#raw-destination').value,
            enabled: $('#raw-enabled').checked,
            acknowledged: $('#raw-ack').checked,
            version: rawVersion
          }));
          view = 'home';
          render();
          toast('Configuration saved.');
        }
      });
    });

    on('click', event => {
      if (event.target === overlay) {
        event.stopPropagation();
        perform(null, cancelEditing);
        return;
      }
      const provider = event.target.closest('[data-provider]');
      if (provider) {
        selectedProvider = provider.dataset.provider;
        providerResults();
        $('[data-action="start"]').disabled = false;
        return;
      }
      const folder = event.target.closest('[data-folder-path]');
      if (folder) {
        perform(folder, () => loadFolders(folder.dataset.folderPath));
        return;
      }
      const target = event.target.closest('[data-action]');
      if (!target) return;
      const action = target.dataset.action;
      if (action === 'backup-menu') {
        event.stopPropagation();
        backupMenu(event);
        return;
      }
      if (action === 'close-editor') {
        event.stopPropagation();
        perform(target, cancelEditing);
        return;
      }
      if (action === 'remote-menu') {
        // The shared menu also listens on document to dismiss outside clicks.
        // Do not let the opening click immediately dismiss the menu it created.
        event.stopImmediatePropagation();
        remoteMenu(target.dataset.name, event);
        return;
      }
      // Open synchronously on the user gesture so popup blockers do not swallow
      // the provider tab while the private RC endpoint resolves the sign-in URL.
      const authTab = action === 'oauth-open' ? window.open('about:blank', '_blank') : null;
      perform(target, async () => {
        if (action === 'add-remote') {
          flow = action === 'add-remote' && flow !== 'choose' ? 'manage-add' : 'destination';
          selectedProvider = '';
          search = '';
          view = 'providers';
          render();
        } else if (action === 'home') {
          await cancelEditing();
        } else if (action === 'advanced') {
          view = 'advanced';
          render();
        } else if (action === 'destination') {
          flow = 'destination';
          if (state.destination) await startDraft(state.destination.name, {
            choose: true
          });
          else {
            flow = 'choose';
            view = state.remotes.length ? 'manage' : 'providers';
            selectedProvider = '';
            search = '';
            render();
          }
        } else if (action === 'switch-connection') {
          await cancelDraft();
          flow = 'choose';
          view = 'manage';
          render();
        } else if (action === 'start') {
          await startDraft($('#remote-name').value, {
            type: selectedProvider
          });
        } else if (action === 'auth-method') {
          acceptDraft(await api('advance', {
            id: draft.id,
            answer: target.dataset.answer
          }));
        } else if (action === 'cancel') {
          await cancelDraft();
          view = 'home';
          render();
        } else if (action === 'back') {
          clearTimeout(polling);
          pollGeneration++;
          acceptDraft(await api('back', {
            id: draft.id
          }));
        } else if (action === 'poll') {
          acceptDraft(await api('poll', {
            id: draft.id
          }));
        } else if (action === 'reveal') {
          const input = $('#answer');
          input.type = input.type === 'password' ? 'text' : 'password';
          target.setAttribute('aria-label', input.type === 'password' ? 'Show password' : 'Hide password');
        } else if (action === 'new-folder') {
          const form = $('#new-folder-form');
          form.hidden = !form.hidden;
          if (!form.hidden) $('#new-folder-name').focus();
        } else if (action === 'review') {
          const enteredPath = $('#folder-path').value;
          if (enteredPath !== path) {
            path = enteredPath;
            folderVerified = false;
          }
          view = 'review';
          render();
        } else if (action === 'folders') {
          view = 'folders';
          render();
          await loadFolders(path);
        } else if (action === 'save') {
          saved(await api('save', {
            id: draft.id,
            path,
            acknowledged: $('#destination-ack')?.checked === true
          }));
          draft = null;
          view = flow === 'manage-add' ? 'manage' : 'home';
          render();
          toast(flow === 'destination' ? 'Destination saved.' : 'Connection saved.');
          if (screen === 'setup' && flow !== 'edit' && flow !== 'manage-add') complete();
        } else if (action === 'edit-current' || action === 'edit-remote') {
          flow = 'edit';
          await startDraft(target.dataset.name || state.destination.name, {
            edit: true
          });
        } else if (action === 'use-remote') {
          flow = 'destination';
          await startDraft(target.dataset.name || state.destination.name, {
            edit: true,
            choose: true
          });
        } else if (action === 'manage') {
          view = 'manage';
          flow = 'manage';
          render();
        } else if (action === 'complete') {
          complete();
        } else if (action === 'skip') {
          if (draft) await cancelDraft();
          saved(await api('settings', {
            enabled: false,
            version: state.version
          }));
          view = 'home';
          render();
          complete();
        } else if (action === 'oauth-open') {
          try {
            const {
              url
            } = await api('oauth_link', {
              id: draft.id
            });
            if (authTab) {
              authTab.opener = null;
              authTab.location = url;
            } else throw new Error('Allow popups for this page and try again.');
          } catch (err) {
            authTab?.close();
            throw err;
          }
        } else if (action === 'oauth-return') acceptDraft(await api('oauth_return', {
          id: draft.id,
          url: $('#callback-url').value
        }));
      });
    });

    async function init() {
      try {
        state = await api('state');
        providers = await api('providers');
        providers.sort((a, b) => providerLabel(a).localeCompare(providerLabel(b)));
        renderHome();
        if (state.draft) {
          draft = state.draft;
          flow = draft.purpose === 'edit' ? 'edit' : draft.purpose === 'add' ? 'manage-add' : 'destination';
          if (draft.purpose === 'choose' && draft.name === state.destination?.name) path = state.destination.path;
          acceptDraft(draft);
        } else if (screen === 'setup' && !destinationString() && !state.remotes.length && !state.configuration_error) {
          view = 'providers';
          render();
        } else render();
      } catch (err) {
        state ||= {
          remotes: [],
          destination: null,
          destination_text: '',
          enabled: false
        };
        overview.innerHTML = `<div class="rclone-panel rclone-body-content"><h2>Could not load connections</h2><p class="rclone-copy">${esc(err.message)}</p><button class="btn btn-primary" onclick="location.reload()">Retry</button> ${button('advanced','Open advanced config')}</div>`;
      }
    }
    init();
  }
};
