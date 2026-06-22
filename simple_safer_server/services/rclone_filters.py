import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from simple_safer_server.services.file_persistence import atomic_write_text
from simple_safer_server.web.problems import ValidationProblem

RCLONE_INCLUDE_PATTERNS_FILENAME = "rclone_include_patterns.txt"
RCLONE_EXCLUDE_PATTERNS_FILENAME = "rclone_exclude_patterns.txt"


def rclone_pattern_paths(runtime: Any) -> tuple[Path, Path]:
    """Return the app-owned include and exclude pattern files."""
    return (
        runtime.config_dir / RCLONE_INCLUDE_PATTERNS_FILENAME,
        runtime.config_dir / RCLONE_EXCLUDE_PATTERNS_FILENAME,
    )


def normalize_rclone_pattern_text(value: Any) -> str:
    """Return plain rclone patterns, one per line, ready for app-owned files."""
    if value is None:
        return ""

    patterns: list[str] = []
    for line in str(value).splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith(("#", ";")):
            continue
        if pattern[0] in {"+", "-", "!"}:
            raise ValidationProblem(
                "Use plain rclone patterns only. Do not start lines with +, -, or !."
            )
        patterns.append(pattern)
    if not patterns:
        return ""
    return "\n".join(patterns) + "\n"


def read_rclone_pattern_texts(runtime: Any) -> dict[str, str]:
    include_path, exclude_path = rclone_pattern_paths(runtime)
    return {
        "rclone_include_patterns": _read_text_file(include_path),
        "rclone_exclude_patterns": _read_text_file(exclude_path),
    }


def write_rclone_pattern_texts(
    runtime: Any,
    *,
    include_patterns: Any,
    exclude_patterns: Any,
) -> None:
    include_path, exclude_path = rclone_pattern_paths(runtime)
    runtime.config_dir.mkdir(parents=True, exist_ok=True)
    runtime.config_dir.chmod(0o700)
    atomic_write_text(
        include_path,
        normalize_rclone_pattern_text(include_patterns),
        mode=0o600,
    )
    atomic_write_text(
        exclude_path,
        normalize_rclone_pattern_text(exclude_patterns),
        mode=0o600,
    )


def build_rclone_filter_text(*, include_patterns: Any, exclude_patterns: Any) -> str:
    exclude_text = normalize_rclone_pattern_text(exclude_patterns)
    include_text = normalize_rclone_pattern_text(include_patterns)
    rules = [f"- {pattern}" for pattern in exclude_text.splitlines()]
    include_rules = [f"+ {pattern}" for pattern in include_text.splitlines()]
    rules.extend(include_rules)
    if include_rules:
        # rclone --filter rules do not add the implicit final exclude that
        # --include adds, so add it when the admin configured an allow-list.
        rules.append("- **")
    if not rules:
        return ""
    return "\n".join(rules) + "\n"


def write_temp_rclone_filter_file(runtime: Any) -> str | None:
    pattern_texts = read_rclone_pattern_texts(runtime)
    filter_text = build_rclone_filter_text(
        include_patterns=pattern_texts["rclone_include_patterns"],
        exclude_patterns=pattern_texts["rclone_exclude_patterns"],
    )
    if not filter_text:
        return None

    directory = getattr(runtime, "volatile_dir", None)
    if directory is not None:
        directory.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        delete=False,
        mode="w",
        prefix="rclone-filter-",
        suffix=".txt",
        dir=directory,
    ) as filter_file:
        filter_file.write(filter_text)
        temp_path = filter_file.name
    os.chmod(temp_path, 0o600)
    return temp_path


def _read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text()
