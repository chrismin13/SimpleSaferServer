import json
import subprocess
from pathlib import Path


def test_dirty_source_switching_stays_visible_but_disabled():
    script = r"""
const fs = require('fs');
const vm = require('vm');

class ClassList {
  constructor(element) {
    this.element = element;
    this.classes = new Set((element.className || '').split(/\s+/).filter(Boolean));
  }
  add(name) {
    this.classes.add(name);
    this.element.className = Array.from(this.classes).join(' ');
  }
  remove(name) {
    this.classes.delete(name);
    this.element.className = Array.from(this.classes).join(' ');
  }
  contains(name) {
    return this.classes.has(name);
  }
}

class Element {
  constructor(id, className) {
    this.id = id;
    this.className = className || '';
    this.classList = new ClassList(this);
    this.textContent = '';
    this.disabled = false;
    this.value = '';
    this.title = '';
    this.attributes = {};
    this.style = {};
    this.children = [];
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  getAttribute(name) {
    return this.attributes[name] || null;
  }
  appendChild(child) {
    this.children.push(child);
    this.textContent += child.textContent || '';
    return child;
  }
  addEventListener() {}
}

const ids = [
  'support-status-badge', 'distro-name', 'distro-version', 'max-eol',
  'apt-lock-badge', 'apt-operation-title', 'apt-progress-bar', 'apt-phase',
  'apt-progress-text', 'apt-log', 'apt-update-btn', 'apt-upgrade-btn',
  'apt-stop-btn', 'auto-updates-badge', 'auto-updates-summary',
  'auto-updates-form', 'auto-update-lists', 'auto-unattended-upgrade',
  'auto-autoclean', 'auto-updates-hint', 'auto-updates-save-btn',
  'livepatch-badge', 'livepatch-title', 'livepatch-detail', 'livepatch-form',
  'livepatch-token', 'livepatch-setup-btn', 'livepatch-source-link',
  'app-update-title', 'app-update-detail', 'app-update-badge',
  'app-update-source', 'app-update-commit', 'app-update-checked',
  'app-update-refresh-btn', 'app-update-now-btn', 'app-update-force-btn',
  'app-update-switch-main-tooltip', 'app-update-switch-main-btn',
  'app-branch-advanced-trigger', 'app-branch-advanced-hint',
  'app-branch-switch-form', 'app-branch-select',
  'app-branch-switch-btn', 'remove-locks-btn'
];

const elements = Object.fromEntries(ids.map((id) => [id, new Element(id)]));
elements['app-update-switch-main-btn'].className = 'btn d-none';
elements['app-update-switch-main-btn'].classList = new ClassList(elements['app-update-switch-main-btn']);
elements['app-update-force-btn'].className = 'btn d-none';
elements['app-update-force-btn'].classList = new ClassList(elements['app-update-force-btn']);

const dirtyApplication = {
  status: 'dirty',
  message: 'Local edits detected.',
  source_type: 'branch',
  source_name: 'feature/demo',
  dirty: true,
  can_update: false,
  can_force_update: true,
  current_commit: 'abc123',
  last_remote_check_at: '2026-05-16T00:00:00Z'
};

const cleanApplication = {
  status: 'behind',
  message: 'Update available.',
  source_type: 'branch',
  source_name: 'feature/demo',
  dirty: false,
  can_update: true,
  can_force_update: false,
  current_commit: 'abc123',
  last_remote_check_at: '2026-05-16T00:00:00Z'
};

let application = dirtyApplication;
const window = {
  SystemUpdatesTest: {},
  ApiClient: {
    fetchJson: async (url) => {
      if (url === '/api/system_updates/summary') {
        return { data: { distribution: {}, operation: {}, settings: {}, livepatch: {}, application } };
      }
      if (url === '/api/system_updates/status') return { data: { operation: {} } };
      if (url === '/api/system_updates/application/branches') return { data: { branches: ['main', 'feature/demo'] } };
      throw new Error(url);
    }
  },
  AsyncButtonState: { start() {}, reset() {} },
  formatRelativeTimestamp: () => 'now',
  setInterval: () => 1,
  clearInterval() {},
  addEventListener() {},
  location: { href: '' }
};

const document = {
  getElementById: (id) => elements[id],
  createElement: (tag) => new Element(tag),
  addEventListener() {}
};

const context = { window, document, console };
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/js/system_updates.js', 'utf8'), context);

(async () => {
  context.window.SystemUpdatesTest.cacheElements();
  const dirtyResults = [
    dirtyApplication,
    { ...dirtyApplication, source_type: 'tag', source_name: 'v1.0.0' },
    { ...dirtyApplication, source_type: 'detached', source_name: 'abc123' }
  ].map((dirtyState) => {
    context.window.SystemUpdatesTest.renderApplicationUpdate(dirtyState);
    return {
      switchHidden: elements['app-update-switch-main-btn'].classList.contains('d-none'),
      switchDisabled: elements['app-update-switch-main-btn'].disabled,
      tooltipClass: elements['app-update-switch-main-tooltip'].className,
      tooltip: elements['app-update-switch-main-tooltip'].getAttribute('data-tooltip'),
      selectDisabled: elements['app-branch-select'].disabled,
      branchButtonDisabled: elements['app-branch-switch-btn'].disabled,
      hint: elements['app-branch-advanced-hint'].textContent
    };
  });

  application = cleanApplication;
  context.window.SystemUpdatesTest.renderApplicationUpdate(cleanApplication);
  await context.window.SystemUpdatesTest.loadBranchChoices({ force: true, quiet: true });
  const cleanResult = {
    switchHidden: elements['app-update-switch-main-btn'].classList.contains('d-none'),
    switchDisabled: elements['app-update-switch-main-btn'].disabled,
    selectDisabled: elements['app-branch-select'].disabled,
    branchButtonDisabled: elements['app-branch-switch-btn'].disabled
  };

  console.log(JSON.stringify({ dirtyResults, cleanResult }));
})();
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)

    assert result["dirtyResults"] == [
        {
            "switchHidden": False,
            "switchDisabled": True,
            "tooltipClass": "tooltip-trigger",
            "tooltip": "Clean up app folder before switching branches.",
            "selectDisabled": True,
            "branchButtonDisabled": True,
            "hint": "Clean up app folder before switching branches.",
        },
        {
            "switchHidden": False,
            "switchDisabled": True,
            "tooltipClass": "tooltip-trigger",
            "tooltip": "Clean up app folder before switching branches.",
            "selectDisabled": True,
            "branchButtonDisabled": True,
            "hint": "Clean up app folder before switching branches.",
        },
        {
            "switchHidden": False,
            "switchDisabled": True,
            "tooltipClass": "tooltip-trigger",
            "tooltip": "Clean up app folder before switching branches.",
            "selectDisabled": True,
            "branchButtonDisabled": True,
            "hint": "Clean up app folder before switching branches.",
        },
    ]
    assert result["cleanResult"] == {
        "switchHidden": False,
        "switchDisabled": False,
        "selectDisabled": False,
        "branchButtonDisabled": False,
    }


def test_application_source_switch_copy_uses_operator_wording():
    script = r"""
const fs = require('fs');
const vm = require('vm');

class ClassList {
  constructor(element) {
    this.element = element;
    this.classes = new Set((element.className || '').split(/\s+/).filter(Boolean));
  }
  add(name) {
    this.classes.add(name);
    this.element.className = Array.from(this.classes).join(' ');
  }
  remove(name) {
    this.classes.delete(name);
    this.element.className = Array.from(this.classes).join(' ');
  }
  contains(name) {
    return this.classes.has(name);
  }
}

class Element {
  constructor(id, className) {
    this.id = id;
    this.className = className || '';
    this.classList = new ClassList(this);
    this.textContent = '';
    this.disabled = false;
    this.value = '';
    this.title = '';
    this.attributes = {};
    this.style = {};
    this.children = [];
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  getAttribute(name) {
    return this.attributes[name] || null;
  }
  appendChild(child) {
    this.children.push(child);
    this.textContent += child.textContent || '';
    return child;
  }
  addEventListener() {}
}

const ids = [
  'support-status-badge', 'distro-name', 'distro-version', 'max-eol',
  'apt-lock-badge', 'apt-operation-title', 'apt-progress-bar', 'apt-phase',
  'apt-progress-text', 'apt-log', 'apt-update-btn', 'apt-upgrade-btn',
  'apt-stop-btn', 'auto-updates-badge', 'auto-updates-summary',
  'auto-updates-form', 'auto-update-lists', 'auto-unattended-upgrade',
  'auto-autoclean', 'auto-updates-hint', 'auto-updates-save-btn',
  'livepatch-badge', 'livepatch-title', 'livepatch-detail', 'livepatch-form',
  'livepatch-token', 'livepatch-setup-btn', 'livepatch-source-link',
  'app-update-title', 'app-update-detail', 'app-update-badge',
  'app-update-source', 'app-update-commit', 'app-update-checked',
  'app-update-refresh-btn', 'app-update-now-btn', 'app-update-force-btn',
  'app-update-switch-main-tooltip', 'app-update-switch-main-btn',
  'app-branch-advanced-trigger', 'app-branch-advanced-hint',
  'app-branch-switch-form', 'app-branch-select',
  'app-branch-switch-btn', 'remove-locks-btn'
];

const elements = Object.fromEntries(ids.map((id) => [id, new Element(id)]));
elements['app-update-switch-main-btn'].className = 'btn d-none';
elements['app-update-switch-main-btn'].classList = new ClassList(elements['app-update-switch-main-btn']);
elements['app-update-force-btn'].className = 'btn d-none';
elements['app-update-force-btn'].classList = new ClassList(elements['app-update-force-btn']);

const window = {
  SystemUpdatesTest: {},
  ApiClient: {
    fetchJson: async (url) => {
      if (url === '/api/system_updates/application/branches') return { data: { branches: [] } };
      throw new Error(url);
    }
  },
  AsyncButtonState: { start() {}, reset() {} },
  formatRelativeTimestamp: () => 'now',
  setInterval: () => 1,
  clearInterval() {},
  addEventListener() {},
  location: { href: '' }
};

const document = {
  getElementById: (id) => elements[id],
  createElement: (tag) => new Element(tag),
  addEventListener() {}
};

const context = { window, document, console };
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/js/system_updates.js', 'utf8'), context);

(async () => {
  context.window.SystemUpdatesTest.cacheElements();
  context.window.SystemUpdatesTest.renderApplicationUpdate({
    status: 'pinned',
    message: 'Pinned install.',
    source_type: 'detached',
    source_name: 'abc123',
    dirty: false,
    can_update: false,
    can_force_update: false,
    current_commit: 'abc123',
    last_remote_check_at: '2026-05-16T00:00:00Z'
  });
  const detached = {
    source: elements['app-update-source'].textContent,
    detail: elements['app-update-detail'].textContent,
    hint: elements['app-branch-advanced-hint'].textContent
  };

  await context.window.SystemUpdatesTest.loadBranchChoices({ force: true, quiet: true });
  const emptyBranches = {
    option: elements['app-branch-select'].children[0].textContent,
    hint: elements['app-branch-advanced-hint'].textContent
  };

  console.log(JSON.stringify({ detached, emptyBranches }));
})();
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)

    assert result == {
        "detached": {
            "source": "Locked commit",
            "detail": "This install is locked to a tag or commit. Switch to main to resume updates.",
            "hint": "Switch branches only for testing or recovery.",
        },
        "emptyBranches": {
            "option": "No branches found",
            "hint": "Switch branches only for testing or recovery.",
        },
    }


def test_branch_source_name_uses_inline_code_style():
    script = r"""
const fs = require('fs');
const vm = require('vm');

class ClassList {
  constructor(element) {
    this.element = element;
    this.classes = new Set((element.className || '').split(/\s+/).filter(Boolean));
  }
  add(name) {
    this.classes.add(name);
    this.element.className = Array.from(this.classes).join(' ');
  }
  remove(name) {
    this.classes.delete(name);
    this.element.className = Array.from(this.classes).join(' ');
  }
  contains(name) {
    return this.classes.has(name);
  }
}

class Element {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.id = tagName;
    this.className = '';
    this.classList = new ClassList(this);
    this.textContent = '';
    this.disabled = false;
    this.value = '';
    this.title = '';
    this.attributes = {};
    this.style = {};
    this.children = [];
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }
  getAttribute(name) {
    return this.attributes[name] || null;
  }
  appendChild(child) {
    this.children.push(child);
    this.textContent += child.textContent || '';
    return child;
  }
  addEventListener() {}
}

const ids = [
  'support-status-badge', 'distro-name', 'distro-version', 'max-eol',
  'apt-lock-badge', 'apt-operation-title', 'apt-progress-bar', 'apt-phase',
  'apt-progress-text', 'apt-log', 'apt-update-btn', 'apt-upgrade-btn',
  'apt-stop-btn', 'auto-updates-badge', 'auto-updates-summary',
  'auto-updates-form', 'auto-update-lists', 'auto-unattended-upgrade',
  'auto-autoclean', 'auto-updates-hint', 'auto-updates-save-btn',
  'livepatch-badge', 'livepatch-title', 'livepatch-detail', 'livepatch-form',
  'livepatch-token', 'livepatch-setup-btn', 'livepatch-source-link',
  'app-update-title', 'app-update-detail', 'app-update-badge',
  'app-update-source', 'app-update-commit', 'app-update-checked',
  'app-update-refresh-btn', 'app-update-now-btn', 'app-update-force-btn',
  'app-update-switch-main-tooltip', 'app-update-switch-main-btn',
  'app-branch-advanced-trigger', 'app-branch-advanced-hint',
  'app-branch-switch-form', 'app-branch-select',
  'app-branch-switch-btn', 'remove-locks-btn'
];

const elements = Object.fromEntries(ids.map((id) => [id, new Element(id)]));
elements['app-update-switch-main-btn'].className = 'btn d-none';
elements['app-update-switch-main-btn'].classList = new ClassList(elements['app-update-switch-main-btn']);
elements['app-update-force-btn'].className = 'btn d-none';
elements['app-update-force-btn'].classList = new ClassList(elements['app-update-force-btn']);

const window = {
  SystemUpdatesTest: {},
  AsyncButtonState: { start() {}, reset() {} },
  formatRelativeTimestamp: () => 'now',
  setInterval: () => 1,
  clearInterval() {},
  addEventListener() {},
  location: { href: '' }
};

const document = {
  getElementById: (id) => elements[id],
  createElement: (tag) => new Element(tag),
  addEventListener() {}
};

const context = { window, document, console };
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/js/system_updates.js', 'utf8'), context);

context.window.SystemUpdatesTest.cacheElements();
context.window.SystemUpdatesTest.renderApplicationUpdate({
  status: 'up_to_date',
  message: 'Up to date.',
  source_type: 'branch',
  source_name: 'vibe-changes',
  dirty: false,
  can_update: false,
  can_force_update: false,
  current_commit: 'abc123',
  last_remote_check_at: '2026-05-16T00:00:00Z'
});

const source = elements['app-update-source'];
console.log(JSON.stringify({
  text: source.textContent,
  children: source.children.map((child) => ({
    tagName: child.tagName,
    className: child.className,
    text: child.textContent
  }))
}));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )
    result = json.loads(completed.stdout)

    assert result == {
        "text": "Branch vibe-changes",
        "children": [
            {"tagName": "SPAN", "className": "", "text": "Branch "},
            {"tagName": "CODE", "className": "app-source-code", "text": "vibe-changes"},
        ],
    }


def test_source_switch_static_copy_avoids_jargon():
    template = Path("templates/system_updates.html").read_text(encoding="utf-8")
    script = Path("static/js/system_updates.js").read_text(encoding="utf-8")

    assert '<span><i class="fas fa-code-branch"></i> Advanced</span>' in template
    assert "app-branch-advanced-summary" not in template
    assert '<label class="form-label" for="app-branch-select">Branch</label>' in template
    assert '<i class="fas fa-code-branch"></i> Switch Branch' in template

    assert (
        "Switch to an origin branch only when testing or recovering the installed app."
        not in template
    )
    assert "Remote branch" not in template
    assert "Switch Source" not in template

    assert "Switch SimpleSaferServer to ${branch} and apply it immediately?" in script
    assert "Danger: switch away from main?" in script
    assert "Only do this if you are testing a specific fix or recovering this install." in script
    assert (
        "Non-main branches can be unfinished, temporary, outdated, or removed without notice."
        in script
    )
    assert "This will rerun the installer from that branch." in script
    assert "I understand, switch branch" in script
    assert "app-branch-advanced-summary" not in script
    assert "Recovery" not in script
    assert "On main" not in script
    assert "run the installer now" not in script
    assert (
        "confirmLabel: branch === STABLE_BRANCH ? 'Switch to main' : 'I understand, switch branch'"
        in script
    )
    assert "Switch Source" not in script
