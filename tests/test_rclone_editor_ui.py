"""Browserless checks of the shared editor's questions and saved-state handling."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def check_option_fields(options):
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for the rclone editor JavaScript harness.')
    script = r"""
const assert = require('assert/strict');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('static/js/rclone_editor.js', 'utf8');
const controls = new Map();
const context = {
  window: {}, draft: {}, flow: 'edit',
  $: selector => controls.get(selector) || null,
  overlay: { querySelector: () => null },
  panel: html => { context.html = html; }
};
vm.createContext(context);
vm.runInContext(source, context);
// Exercise the shipped renderer and answer reader with a small control boundary.
// This checks what is visible and submitted, not just the normalized metadata.
for (const [start, end] of [
  ['const esc =', 'let state,'],
  ['const button =', 'const remoteLabel ='],
  ['function helpMarkup(', 'function renderAuthorizationChoice('],
  ['function answerInput(', 'function renderPending(']
]) vm.runInContext(source.slice(source.indexOf(start), source.indexOf(end)), context);

for (const option of JSON.parse(fs.readFileSync(0, 'utf8'))) {
  context.draft = { option };
  const field = context.window.RcloneEditor.optionField(option);
  const input = { value: field.initial, focus() {} };
  const selection = { value: field.selection, focus() {} };
  controls.clear();
  if (!field.choices.length || field.custom) controls.set('#answer', input);
  if (field.choices.length) controls.set(field.compact ?
    'input[name="answer-choice"]:checked' : '#answer-choice', selection);
  if (field.custom) controls.set('#answer-custom', {});
  if (!field.compact) controls.set('#answer-choice-help', {});
  context.renderQuestion();
  const html = context.html;
  assert.ok(!html.includes('<datalist'), option.Name);
  assert.ok(!html.includes('<img'), option.Name);
  assert.ok(!html.includes('<script'), option.Name);
  if (option.IsPassword) {
    assert.ok(html.includes('type="password"'), option.Name);
    assert.ok(!html.includes('<textarea'), option.Name);
    assert.equal(field.choices.length, 0);
  } else if (option.Examples?.length) {
    assert.ok(html.includes(field.compact ? 'type="radio"' : '<select'), option.Name);
    assert.equal(field.custom, !option.Exclusive && !['bool', 'Tristate'].includes(option.Type));
    for (const example of option.Examples) {
      assert.ok(field.choices.some(choice => choice.Value === example.Value), option.Name);
    }
  }
  if (field.choices.length) {
    for (const [index, choice] of field.choices.entries()) {
      // Both small radio groups and large selects must submit values, never
      // display labels, indexes, or the stale value in a hidden custom input.
      selection.value = String(index);
      assert.ok(html.includes(`value="${index}"`), option.Name);
      context.updateAnswerChoice();
      assert.equal(context.questionAnswer(), choice.Value, option.Name);
      if (field.custom) {
        assert.equal(input.disabled, true);
        assert.equal(controls.get('#answer-custom').hidden, true);
      }
      if (!field.compact) assert.equal(controls.get('#answer-choice-help').textContent, choice.Help || '');
    }
    selection.value = '';
    assert.throws(() => context.questionAnswer(), /Choose an answer/);
    if (field.custom) {
      selection.value = 'custom';
      context.updateAnswerChoice(true);
      assert.equal(input.disabled, false);
      assert.equal(controls.get('#answer-custom').hidden, false);
      input.value = 'custom,"quoted,comma", 001\nnext line';
      assert.equal(context.questionAnswer(), input.value);
    } else {
      assert.ok(!html.includes('id="answer-custom"'));
    }
    selection.value = field.selection;
  }
  input.value = field.initial;
  // Reopening or going Back must retain the exact current/default value.
  if (!field.choices.length || field.selection !== '') {
    assert.equal(context.questionAnswer(), field.initial, option.Name);
  }
  if (option.Required && field.initial === '' && !field.choices.length) {
    assert.ok(html.includes(' required'), option.Name);
  }
  if (option.Type === 'Tristate' && !option.Examples?.length) {
    assert.deepEqual(Array.from(field.choices, choice => choice.Value), ['true', 'false', 'unset']);
  }
}
"""
    subprocess.run(
        [node, '-e', script],
        input=json.dumps(options),
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_question_controls_cover_metadata_combinations_and_preserve_answers():
    examples = [
        {'Value': 'drive', 'Help': 'Full access'},
        {'Value': 'drive.readonly', 'Help': 'Read-only access'},
        {'Value': 'drive.file', 'Help': 'Files created by rclone\nAdditional guidance'},
        {'Value': 'custom', 'Help': 'A real value named custom'},
        {'Value': '<img src=x onerror=alert(1)>', 'Help': '<script>untrusted</script>'},
        {'Value': 'last', 'Help': 'The last option\nWith a long description'},
    ]
    options = [
        {
            'Name': 'scope',
            'Type': 'string',
            'DefaultStr': initial,
            'Examples': examples[:count],
            'Exclusive': exclusive,
            'Required': required,
        }
        for count in (0, 1, 5, 6)
        for exclusive in (False, True)
        for required in (False, True)
        for initial in ('', 'drive', 'drive,drive.file')
    ]
    options.extend(
        {'Name': 'value', 'Type': kind, 'DefaultStr': value}
        for kind, value in (
            ('bool', 'false'),
            ('bool', 'true'),
            ('Tristate', 'unset'),
            ('Tristate', 'false'),
            ('Tristate', 'true'),
            ('int', '9007199254740993'),
            ('float64', '0.00001'),
            ('SizeSuffix', '128Mi'),
            ('Duration', '1h30m'),
            ('Time', 'off'),
            ('CommaSepList', 'one,"two,three"'),
            ('SpaceSepList', 'one "two three"'),
            ('stringArray', '"one,two",three'),
            ('Encoding', 'Slash,BackSlash,Del'),
            ('Bits', 'one,two'),
            ('FutureRcloneType', '001:off'),
            ('string', 'line one\nline two'),
        )
    )
    options.extend(
        [
            {'Name': 'bool_fallback', 'Type': 'bool', 'Default': False},
            {'Name': 'credentials_json', 'Type': 'string', 'DefaultStr': '{"key":"value"}'},
            {
                'Name': 'password_json',
                'Type': 'string',
                'DefaultStr': 'stored-secret',
                'IsPassword': True,
                'Examples': examples,
            },
            {
                'Name': 'empty_example',
                'Type': 'string',
                'DefaultStr': '',
                'Exclusive': True,
                'Examples': [{'Value': '', 'Help': 'None'}, *examples],
            },
        ]
    )
    check_option_fields(options)


@pytest.mark.skipif(not shutil.which('rclone'), reason='Requires installed rclone')
def test_question_renderer_accepts_every_installed_provider_option():
    result = subprocess.run(
        ['rclone', 'config', 'providers'],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    # A live catalog catches new metadata combinations as installed rclone
    # changes; synthetic cases above also run without rclone or cloud accounts.
    providers = json.loads(result.stdout)
    options = [option for provider in providers for option in provider['Options']]
    assert options
    check_option_fields(options)


def test_cancel_preserves_live_drafts_on_conflict_and_allows_retry():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for the rclone editor JavaScript harness.')
    script = r"""
const assert = require('assert/strict');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('static/js/rclone_editor.js', 'utf8');
// Exercise the shipped cancellation handler with its closure state and API boundary.
const handler = source.slice(source.indexOf('async function cancelDraft()'),
                             source.indexOf('async function startDraft('));
(async () => {
  for (const scenario of ['busy', 'expired', 'error', 'success']) {
    let conflict = scenario !== 'success';
    const context = {
      polling: null, pollGeneration: 0, folderRequest: 0,
      draft: { id: 'draft' }, path: 'Backups', state: {}, clearTimeout,
      api: async action => {
        if (action === 'cancel') {
          if (conflict) throw Object.assign(new Error(scenario), {
            status: scenario === 'error' ? 500 : 409
          });
          return {};
        }
        if (action === 'state') return {
          draft: conflict && scenario === 'busy' ? { id: 'draft' } : null
        };
        throw new Error(action);
      }
    };
    vm.runInNewContext(handler, context);
    if (scenario === 'busy' || scenario === 'error') {
      await assert.rejects(context.cancelDraft(), { message: scenario });
      assert.equal(context.draft.id, 'draft');
      assert.equal(context.path, 'Backups');
      conflict = false;
    }
    await context.cancelDraft();
    assert.equal(context.draft, null);
    assert.equal(context.path, '');
    assert.equal(context.state.draft, null);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    subprocess.run(
        [node, '-e', script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_advanced_form_submits_the_fresh_snapshot_instead_of_old_page_settings():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for the rclone editor JavaScript harness.')
    script = r"""
const fs = require('fs');
const vm = require('vm');
const elements = new Map();
class Element {
  constructor(id = '') {
    this.id = id;
    this.dataset = {};
    this.listeners = {};
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.isConnected = true;
    this.classList = { contains: () => false };
    elements.set('#' + id, this);
  }
  set innerHTML(html) {
    // Materialize the actual form markup, so stale input values and checkbox
    // defaults are exercised without adding a DOM dependency to Python CI.
    for (const match of html.matchAll(/<(input|textarea|button)\b([^>]*)>/g)) {
      const attributes = match[2];
      const id = attributes.match(/\bid="([^"]+)"/)?.[1];
      if (!id) continue;
      const element = new Element(id);
      element.value = attributes.match(/\bvalue="([^"]*)"/)?.[1] || '';
      element.disabled = /\bdisabled\b/.test(attributes);
      element.checked = /\bchecked\b/.test(attributes);
    }
  }
  querySelector(selector) { return elements.get(selector) || null; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  dispatchEvent() {}
  focus() {}
  replaceChildren() {}
  closest(selector) { return selector === '[data-action]' ? this : null; }
}
const root = new Element('rclone-editor');
root.dataset = { api: '/editor', setup: 'false' };
const overlay = new Element('rclone-workspace');
elements.set('[data-rclone-modal]', overlay);
elements.set('[data-rclone-overview]', new Element('overview'));
elements.set('[data-rclone-content]', new Element('content'));
new Element('rclone-editor-title');
new Element('rclone-editor-context');
const page = {
  remotes: [], destination: null, destination_text: 'disk:old',
  enabled: true, version: 'old', source: '/source'
};
const fresh = {
  config: '[disk]\ntype = local\n', destination_text: 'disk:new',
  enabled: false, version: 'fresh'
};
let resolveRaw, submitted;
const pendingRaw = new Promise(resolve => { resolveRaw = resolve; });
const window = {
  ApiClient: { fetchJson: async (url, options) => {
    if (url.endsWith('/state')) return { data: page };
    if (url.endsWith('/providers')) return { data: [] };
    if (url.endsWith('/raw')) return pendingRaw;
    if (url.endsWith('/apply_raw')) {
      submitted = JSON.parse(options.body);
      return { data: { ...page, ...fresh } };
    }
    throw new Error(url);
  } },
  BunkerModal: { show() {}, hide() {} },
  AsyncButtonState: { start() {}, success() {}, error() {} },
  showAlert(message, kind) { if (kind === 'danger') throw new Error(message); }
};
const context = {
  window, document: { body: { append() {} }, activeElement: root },
  CustomEvent: class {}, setTimeout, clearTimeout
};
vm.runInNewContext(fs.readFileSync('static/js/rclone_editor.js', 'utf8'), context);
const flush = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  window.RcloneEditor.mount(root);
  await flush();
  const advancedButton = new Element();
  advancedButton.dataset.action = 'advanced';
  root.listeners.click({ target: advancedButton });
  await flush();
  const ids = ['raw-config', 'raw-destination', 'raw-enabled', 'raw-ack', 'raw-save'];
  const disabledWhileLoading = ids.every(id => elements.get('#' + id).disabled);
  resolveRaw({ data: fresh });
  await flush();
  const displayed = {
    destination: elements.get('#raw-destination').value,
    enabled: elements.get('#raw-enabled').checked
  };
  const enabledAfterLoading = ids.every(id => !elements.get('#' + id).disabled);
  elements.get('#raw-ack').checked = true;
  overlay.listeners.submit({
    target: { id: 'advanced-form' }, submitter: elements.get('#raw-save'),
    preventDefault() {}
  });
  await flush();
  console.log(JSON.stringify({ disabledWhileLoading, enabledAfterLoading, displayed, submitted }));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        [node, '-e', script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    output = json.loads(result.stdout)
    assert output['disabledWhileLoading']
    assert output['enabledAfterLoading']
    assert output['displayed'] == {'destination': 'disk:new', 'enabled': False}
    assert output['submitted'] == {
        'config': '[disk]\ntype = local\n',
        'destination': 'disk:new',
        'enabled': False,
        'acknowledged': True,
        'version': 'fresh',
    }


def test_destination_access_test_reconciles_tokens_and_exposes_cleanup_retry():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for the rclone editor JavaScript harness.')
    script = r"""
const assert = require('assert/strict');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('static/js/rclone_editor.js', 'utf8');
(async () => {
  for (const scenario of ['success', 'busy', 'cleanup-error', 'listing-error']) {
    let serverDraft = null, serverVersion = 'old';
    let cleanupBlocked = ['busy', 'cleanup-error'].includes(scenario);
    const context = {
      draft: null, path: '', view: 'home', polling: null,
      pollGeneration: 0, folderRequest: 0, clearTimeout,
      state: { version: 'old', destination: { name: 'cloud', path: 'Backups' } },
      toast(message) { context.success = message; },
      renderHome() { context.renderedVersion = context.state.version; },
      panel(body, actions, title) { context.panel = { body, actions, title }; },
      api: async (action, data) => {
        if (action === 'start') {
          assert.equal(serverDraft, null);
          serverDraft = { id: 'test-draft', revision: 0 };
          return serverDraft;
        }
        if (action === 'folders') {
          assert.equal(data.id, serverDraft.id);
          assert.equal(data.path, 'Backups');
          if (scenario === 'listing-error') throw new Error('Cannot list folder');
          return {};
        }
        if (action === 'cancel') {
          assert.equal(data.id, serverDraft.id);
          if (cleanupBlocked) throw Object.assign(new Error('Cannot close yet'), {
            status: scenario === 'busy' ? 409 : 500
          });
          serverDraft = null;
          serverVersion = 'refreshed-token-version';
          return {};
        }
        if (action === 'state') return { version: serverVersion, draft: serverDraft };
        throw new Error(action);
      }
    };
    vm.createContext(context);
    for (const [start, end] of [
      ['const button =', 'const remoteLabel ='],
      ['function render()', 'function renderProviders('],
      ['async function cancelDraft()', 'async function startDraft('],
      ['async function testDestination()', 'function remoteMenu(']
    ]) vm.runInContext(source.slice(source.indexOf(start), source.indexOf(end)), context);
    if (cleanupBlocked) {
      await assert.rejects(context.testDestination(), /Cannot close yet/);
      assert.equal(context.draft.id, serverDraft.id);
      assert.equal(context.path, 'Backups');
      assert.equal(context.view, 'test-cleanup');
      assert.ok(context.panel.actions.includes('data-action="cancel"'));
      assert.ok(context.panel.actions.includes('Retry closing'));
      assert.equal(context.success, undefined);
      cleanupBlocked = false;
      // The visible retry uses the same cancellation path as the editor.
      await context.cancelDraft();
    } else if (scenario === 'listing-error') {
      await assert.rejects(context.testDestination(), /Cannot list folder/);
      assert.equal(context.success, undefined);
      assert.equal(context.renderedVersion, serverVersion);
    } else {
      await context.testDestination();
      assert.equal(context.success, 'Destination folder is accessible.');
      assert.equal(context.renderedVersion, serverVersion);
    }
    assert.equal(context.draft, null);
    assert.equal(serverDraft, null);
    assert.equal(context.state.version, 'refreshed-token-version');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    subprocess.run(
        [node, '-e', script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
