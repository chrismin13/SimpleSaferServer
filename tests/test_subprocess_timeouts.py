import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOT = REPO_ROOT / "simple_safer_server"
EXEMPT_FUNCTIONS = {
    ("simple_safer_server/adapters/storage_commands.py", "reboot"),
    ("simple_safer_server/adapters/storage_commands.py", "poweroff"),
}
EXEMPT_FILES = {
    # CommandRunner is the one wrapper allowed to forward an optional timeout.
    "simple_safer_server/adapters/command_runner.py",
}


class RunCallVisitor(ast.NodeVisitor):
    def __init__(self, relative_path):
        self.relative_path = relative_path
        self.function_stack = []
        self.missing_timeouts = []

    def visit_FunctionDef(self, node):
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Call(self, node):
        if self._is_command_runner_run(node) and not self._has_timeout(node):
            current_function = self.function_stack[-1] if self.function_stack else ""
            if (self.relative_path, current_function) not in EXEMPT_FUNCTIONS:
                self.missing_timeouts.append((node.lineno, current_function))
        self.generic_visit(node)

    def _is_command_runner_run(self, node):
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "run":
            return False
        target = node.func.value
        if isinstance(target, ast.Attribute):
            return target.attr == "_command_runner"
        if isinstance(target, ast.Name):
            return target.id in {"command_runner", "runner"}
        return False

    def _has_timeout(self, node):
        return any(keyword.arg == "timeout" for keyword in node.keywords)


def test_production_command_runner_calls_have_timeouts():
    missing = []
    for path in sorted(PRODUCTION_ROOT.rglob("*.py")):
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        if relative_path in EXEMPT_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = RunCallVisitor(relative_path)
        visitor.visit(tree)
        for line_number, function_name in visitor.missing_timeouts:
            location = f"{relative_path}:{line_number}"
            if function_name:
                location = f"{location} in {function_name}()"
            missing.append(location)

    assert missing == []
