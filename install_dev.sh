#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON_BIN="${VENV_DIR}/bin/python"

# Keep all paths anchored to the repository so the script works from any
# current directory, including after copying the command from another shell.
python3 -m venv "${VENV_DIR}"

PYTHON_VERSION="$("${PYTHON_BIN}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
PYTHON_VERSION_CLASS="$("${PYTHON_BIN}" -c 'import sys; print("legacy" if sys.version_info < (3, 9) else "current")')"

if [[ "${PYTHON_VERSION_CLASS}" == "legacy" ]]; then
  RUNTIME_REQUIREMENTS="requirements-legacy-py37.txt"
  PIP_SPEC="pip<24.1"
else
  RUNTIME_REQUIREMENTS="requirements.txt"
  PIP_SPEC="pip"
fi

for required_file in "${RUNTIME_REQUIREMENTS}" "requirements-dev.txt"; do
  if [[ ! -f "${SCRIPT_DIR}/${required_file}" ]]; then
    printf 'Missing %s next to install_dev.sh in %s\n' "${required_file}" "${SCRIPT_DIR}" >&2
    exit 1
  fi
done

# pip 24.1 dropped support for legacy dependency specifiers that some Debian
# 10/Python 3.7-compatible packages still expose. Only pin pip on old Python so
# the security-supported lane keeps using current packaging behavior.
"${PYTHON_BIN}" -m pip install --upgrade "${PIP_SPEC}" wheel
"${PYTHON_BIN}" -m pip install -r "${SCRIPT_DIR}/${RUNTIME_REQUIREMENTS}"
"${PYTHON_BIN}" -m pip install -r "${SCRIPT_DIR}/requirements-dev.txt"

if ! command -v rclone >/dev/null 2>&1; then
  printf '%s\n' "Note: rclone is not installed. Fake mode will still boot, but MEGA and real cloud backup runs will not work until rclone is available."
fi

printf 'Development environment ready in %s using Python %s and %s.\n' "${VENV_DIR}" "${PYTHON_VERSION}" "${RUNTIME_REQUIREMENTS}"
printf '%s\n' "Start fake mode with: bash run_fake.sh"
printf 'Optional: install commit hooks with %s/bin/pre-commit install\n' "${VENV_DIR}"
printf '%s\n' "To reset fake-mode setup data later, run: bash reset_fake_mode.sh"
