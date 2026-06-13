import os
import shutil
import tempfile
from pathlib import Path

from simple_safer_server.adapters.smb_commands import SmbCommandAdapter
from simple_safer_server.services.runtime import get_runtime

SSS_GLOBALS_FILENAME = "simple_safer_server_globals.conf"
SSS_SHARES_FILENAME = "simple_safer_server_shares.conf"

SSS_GLOBALS_INCLUDE_BEGIN = "# BEGIN SimpleSaferServer global include"
SSS_GLOBALS_INCLUDE_END = "# END SimpleSaferServer global include"
SSS_SHARES_INCLUDE_BEGIN = "# BEGIN SimpleSaferServer shares include"
SSS_SHARES_INCLUDE_END = "# END SimpleSaferServer shares include"


class SambaLayoutError(RuntimeError):
    """Raised when SSS-owned Samba layout changes cannot be published safely."""


class SambaLayoutService:
    """Owns the small Samba include surface that SimpleSaferServer may repair."""

    def __init__(self, runtime=None, command_adapter=None):
        self.runtime = runtime or get_runtime()
        self.command_adapter = command_adapter or SmbCommandAdapter()
        self.samba_dir = self.runtime.samba_dir
        self.smb_conf_path = self.samba_dir / "smb.conf"
        self.globals_path = self.samba_dir / SSS_GLOBALS_FILENAME
        self.shares_path = self.samba_dir / SSS_SHARES_FILENAME

    def ensure_layout(self):
        """Create or repair SSS-owned Samba include files and wiring."""
        self.samba_dir.mkdir(parents=True, exist_ok=True)
        original_state = self._snapshot_paths(
            [self.smb_conf_path, self.globals_path, self.shares_path]
        )

        try:
            main_content = self._read_main_config()
            updated_main_content = self._ensure_include_blocks(main_content)

            self._write_owned_config(self.globals_path, self._globals_template())
            if not self.shares_path.exists():
                self._write_owned_config(self.shares_path, self._shares_header())

            self._validate_candidate_main_config(updated_main_content)
            self._write_owned_config(self.smb_conf_path, updated_main_content)
        except Exception as exc:
            self._restore_snapshot(original_state)
            if isinstance(exc, SambaLayoutError):
                raise
            raise SambaLayoutError(str(exc)) from exc

    def _snapshot_paths(self, paths):
        snapshot = {}
        for path in paths:
            if path.exists():
                snapshot[path] = (path.read_bytes(), path.stat().st_mode & 0o777)
            else:
                snapshot[path] = None
        return snapshot

    def _restore_snapshot(self, snapshot):
        for path, state in snapshot.items():
            if state is None:
                if path.exists():
                    path.unlink()
                continue

            content, mode = state
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            os.chmod(str(path), mode)
            self._chown_root_if_real(path)

    def _read_main_config(self):
        if self.smb_conf_path.exists():
            return self.smb_conf_path.read_text(encoding="utf-8")
        return "[global]\n"

    def _write_owned_config(self, path: Path, content: str):
        # Samba reads these files directly, so publish with a complete same-dir
        # rename instead of leaving a partially written config on interruption.
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                delete=False,
                dir=str(path.parent),
                prefix=f"{path.name}.",
                suffix=".tmp",
                encoding="utf-8",
            ) as handle:
                handle.write(content)
                temp_path = Path(handle.name)
            os.chmod(str(temp_path), 0o644)
            self._chown_root_if_real(temp_path)
            os.replace(str(temp_path), str(path))
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()

    def _chown_root_if_real(self, path: Path):
        if self.runtime.is_fake:
            return
        os.chown(str(path), 0, 0)

    def _globals_template(self):
        template_path = Path(__file__).with_name("templates") / SSS_GLOBALS_FILENAME
        return template_path.read_text(encoding="utf-8")

    def _shares_header(self):
        return (
            "# SimpleSaferServer-managed Samba shares\n"
            "#\n"
            "# normal share changes should use the Web UI.\n"
            "# unsupported manual directives may be overwritten by Web UI edits because\n"
            "# SimpleSaferServer writes the supported share shape it can validate and maintain.\n"
        )

    def _global_include_block(self):
        return [
            f"{SSS_GLOBALS_INCLUDE_BEGIN}\n",
            f"   include = {self.globals_path}\n",
            f"{SSS_GLOBALS_INCLUDE_END}\n",
        ]

    def _shares_include_block(self):
        return [
            f"{SSS_SHARES_INCLUDE_BEGIN}\n",
            f"include = {self.shares_path}\n",
            f"{SSS_SHARES_INCLUDE_END}\n",
        ]

    def _ensure_include_blocks(self, content: str):
        lines = content.splitlines(keepends=True)
        lines = self.strip_owned_include_blocks_from_lines(lines)
        lines = self._insert_global_include(lines)
        lines = self._append_shares_include(lines)
        return "".join(lines)

    def strip_owned_include_blocks(self, content: str):
        """Remove only SimpleSaferServer-owned include marker blocks."""
        return "".join(self.strip_owned_include_blocks_from_lines(content.splitlines(True)))

    def strip_owned_include_blocks_from_lines(self, lines: list[str]):
        lines = self._remove_marker_block(
            lines,
            SSS_GLOBALS_INCLUDE_BEGIN,
            SSS_GLOBALS_INCLUDE_END,
        )
        return self._remove_marker_block(
            lines,
            SSS_SHARES_INCLUDE_BEGIN,
            SSS_SHARES_INCLUDE_END,
        )

    def _remove_marker_block(self, lines: list[str], begin_marker: str, end_marker: str):
        result = []
        index = 0
        removed = False

        while index < len(lines):
            stripped = lines[index].strip()
            if stripped == end_marker:
                raise SambaLayoutError("SSS Samba include marker block is malformed.")
            if stripped != begin_marker:
                result.append(lines[index])
                index += 1
                continue

            if removed:
                raise SambaLayoutError("SSS Samba include marker block is malformed.")
            removed = True
            index += 1
            while index < len(lines) and lines[index].strip() != end_marker:
                if lines[index].strip() == begin_marker:
                    raise SambaLayoutError("SSS Samba include marker block is malformed.")
                index += 1
            if index >= len(lines):
                raise SambaLayoutError("SSS Samba include marker block is malformed.")
            index += 1
            if (
                result
                and not result[-1].strip()
                and index < len(lines)
                and not lines[index].strip()
            ):
                index += 1

        return result

    def _insert_global_include(self, lines: list[str]):
        global_start = self._find_section_start(lines, "global")
        if global_start is None:
            prefix = ["[global]\n"]
            if lines and lines[0].strip():
                prefix.append("\n")
            lines = prefix + lines
            global_start = 0

        insert_at = len(lines)
        for index in range(global_start + 1, len(lines)):
            section_name = self._section_name(lines[index])
            if section_name is not None and section_name.lower() != "global":
                insert_at = index
                break

        new_lines = list(lines)
        self._ensure_blank_before(new_lines, insert_at)
        insert_at = self._adjust_insert_at_after_blank(new_lines, insert_at)
        block = self._global_include_block()
        new_lines[insert_at:insert_at] = block
        self._ensure_blank_after(new_lines, insert_at + len(block))
        return new_lines

    def _append_shares_include(self, lines: list[str]):
        new_lines = list(lines)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] = new_lines[-1] + "\n"
        if new_lines and new_lines[-1].strip():
            new_lines.append("\n")
        new_lines.extend(self._shares_include_block())
        return new_lines

    def _ensure_blank_before(self, lines: list[str], insert_at: int):
        if insert_at > 0 and lines[insert_at - 1].strip():
            lines.insert(insert_at, "\n")

    def _adjust_insert_at_after_blank(self, lines: list[str], insert_at: int):
        if insert_at > 0 and not lines[insert_at - 1].strip():
            return insert_at
        return insert_at + 1

    def _ensure_blank_after(self, lines: list[str], insert_at: int):
        if insert_at < len(lines) and lines[insert_at].strip():
            lines.insert(insert_at, "\n")

    def _find_section_start(self, lines: list[str], section_name: str) -> int | None:
        for index, line in enumerate(lines):
            current = self._section_name(line)
            if current is not None and current.lower() == section_name:
                return index
        return None

    def _section_name(self, line: str) -> str | None:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]") and len(stripped) > 2:
            return stripped[1:-1].strip()
        return None

    def _validate_candidate_main_config(self, content: str):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                delete=False,
                dir=str(self.samba_dir),
                prefix=f"{self.smb_conf_path.name}.",
                suffix=".candidate",
                encoding="utf-8",
            ) as handle:
                handle.write(content)
                temp_path = Path(handle.name)
            os.chmod(str(temp_path), 0o644)

            validator = shutil.which("testparm") or "testparm"
            result = self.command_adapter.validate_config(validator, temp_path)
            if result.returncode != 0:
                details = (
                    result.stderr.strip() or result.stdout.strip() or "unknown validation error"
                )
                raise SambaLayoutError(f"Samba layout validation failed: {details}")
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
