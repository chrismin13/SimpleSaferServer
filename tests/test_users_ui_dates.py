import shutil
import subprocess
import unittest
from pathlib import Path


def _run_node_script(script):
    node_binary = shutil.which("node")
    if node_binary is None:
        # These checks run the same small JavaScript helpers used by the Users
        # page. Python-only environments can still run the rest of the suite.
        raise unittest.SkipTest("Node.js is required for the users JavaScript harness.")

    return subprocess.run(
        [node_binary, "-e", script],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        text=True,
        capture_output=True,
    )


def test_users_page_date_formatter_handles_current_and_old_records():
    template = Path("templates/users.html").read_text(encoding="utf-8")
    helper_block = template.split("function renderUsersTable()", 1)[0].rsplit(
        "function parseUserTimestamp", 1
    )[1]
    date_helpers = f"function parseUserTimestamp{helper_block}"

    script = f"""
const assert = require('assert');

{date_helpers}

const examples = [
  '2026-06-16T10:15:30+00:00',
  '2026-06-16T10:15:30Z',
  '2026-06-16T10:15:30',
  '2026-06-16 10:15:30+00:00'
];

for (const value of examples) {{
  const parsed = parseUserTimestamp(value);
  assert(parsed, `${{value}} should parse`);
  assert(!Number.isNaN(parsed.getTime()), `${{value}} should be a valid date`);
  assert.notStrictEqual(formatUserDate(value, 'Unknown'), 'Invalid Date');
  assert.notStrictEqual(formatUserDateTime(value, 'Never'), 'Invalid Date');
}}

assert.strictEqual(parseUserTimestamp(null), null);
assert.strictEqual(formatUserDate(null, 'Unknown'), 'Unknown');
assert.strictEqual(formatUserDate('', 'Unknown'), 'Unknown');
assert.strictEqual(formatUserDate('not a date', 'Unknown'), 'Unknown');
assert.strictEqual(formatUserDateTime(null, 'Never'), 'Never');
assert.strictEqual(formatUserDateTime('not a date', 'Never'), 'Never');
"""
    _run_node_script(script)
