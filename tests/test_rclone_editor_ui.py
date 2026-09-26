"""Browserless checks of the shared editor's saved-state handling."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


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
