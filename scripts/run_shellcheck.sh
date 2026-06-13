#!/usr/bin/env bash
set -euo pipefail

SHELLCHECK_VERSION="0.11.0"
SHELLCHECK_PY_VERSION="0.11.0.1"
SHELLCHECK_PACKAGE_VERSION="0.11.0-2"
LIBNUMA_PACKAGE_VERSION="2.0.19-1"

# Why this helper exists:
#
# We need ShellCheck findings to be stable across developer machines and CI, so
# plain `apt install shellcheck` is not acceptable. Debian and Ubuntu can ship
# different ShellCheck versions, and testing showed they can report different
# findings on the same scripts.
#
# The official ShellCheck release tarball and `shellcheck-py` are stable, but on
# this arm64 dev machine the static 0.11.0 binary took about 15.8s to check this
# repo's shell scripts. Ubuntu's dynamically linked 0.11.0-2 package produced
# the same ShellCheck version and took about 4.6s in the Debian trixie CI image.
#
# The fast path below downloads exact package files, verifies their SHA256
# hashes, and extracts them into a user cache without installing anything into
# the host OS. If that pinned binary cannot run, we fall back to `shellcheck-py`
# through uvx. The fallback is slower, but it keeps results tied to ShellCheck
# 0.11.0 instead of drifting with the local distro.

if [[ $# -gt 0 ]]; then
  SHELL_FILES=("$@")
else
  mapfile -t SHELL_FILES < <(git ls-files '*.sh')
fi

if [[ ${#SHELL_FILES[@]} -eq 0 ]]; then
  exit 0
fi

fallback_to_uv_shellcheck() {
  local reason="$1"

  printf 'Using uvx ShellCheck fallback: %s\n' "$reason" >&2
  exec uvx --from "shellcheck-py==${SHELLCHECK_PY_VERSION}" shellcheck "${SHELL_FILES[@]}"
}

if [[ "${SSS_SHELLCHECK_FORCE_UVX:-0}" == "1" ]]; then
  fallback_to_uv_shellcheck "SSS_SHELLCHECK_FORCE_UVX=1"
fi

detect_arch() {
  local arch=""

  if command -v dpkg >/dev/null 2>&1; then
    arch="$(dpkg --print-architecture)"
  else
    arch="$(uname -m)"
  fi

  case "$arch" in
    amd64 | x86_64)
      printf 'amd64\n'
      ;;
    arm64 | aarch64)
      printf 'arm64\n'
      ;;
    *)
      return 1
      ;;
  esac
}

multiarch_for_arch() {
  case "$1" in
    amd64)
      printf 'x86_64-linux-gnu\n'
      ;;
    arm64)
      printf 'aarch64-linux-gnu\n'
      ;;
    *)
      return 1
      ;;
  esac
}

package_info_for_arch() {
  # The ShellCheck package comes from Ubuntu because Debian trixie currently
  # ships ShellCheck 0.10.0. The tiny libnuma package comes from Debian so the
  # extracted binary can run inside the same Debian image CI already uses.
  case "$1" in
    amd64)
      SHELLCHECK_URL="https://archive.ubuntu.com/ubuntu/pool/universe/s/shellcheck/shellcheck_${SHELLCHECK_PACKAGE_VERSION}_amd64.deb"
      SHELLCHECK_SHA256="06990eaf21b5dfa3d855e492f7ca2d6fcacf63b490a73a545850c50cf7af2bce"
      LIBNUMA_URL="https://deb.debian.org/debian/pool/main/n/numactl/libnuma1_${LIBNUMA_PACKAGE_VERSION}_amd64.deb"
      LIBNUMA_SHA256="e578583f73f8208564e5035b18aa729c441fc7ecb389c666923552e123f4d655"
      ;;
    arm64)
      SHELLCHECK_URL="https://archive.ubuntu.com/ubuntu/pool/universe/s/shellcheck/shellcheck_${SHELLCHECK_PACKAGE_VERSION}_arm64.deb"
      SHELLCHECK_SHA256="43a72e6d660310412907c5eb01b04a0c036650b6981e10c7554218c707de98cb"
      LIBNUMA_URL="https://deb.debian.org/debian/pool/main/n/numactl/libnuma1_${LIBNUMA_PACKAGE_VERSION}_arm64.deb"
      LIBNUMA_SHA256="23bd0d4ecdc8cb44438791c10aab969bc9eb11a4b635aae573376c4e23994ff5"
      ;;
    *)
      return 1
      ;;
  esac
}

download_checked_file() {
  local url="$1"
  local expected_sha256="$2"
  local output_path="$3"

  curl -fsSL --retry 3 --retry-delay 1 --connect-timeout 10 "$url" -o "$output_path"
  printf '%s  %s\n' "$expected_sha256" "$output_path" | sha256sum -c - >/dev/null
}

install_fast_shellcheck() {
  local install_dir="$1"
  local arch="$2"
  local work_dir=""

  mkdir -p "$(dirname -- "$install_dir")"
  work_dir="$(mktemp -d "${install_dir}.download.XXXXXX")"

  # Extract into a temp directory first so a failed download cannot poison the
  # cache with a half-installed binary.
  download_checked_file "$SHELLCHECK_URL" "$SHELLCHECK_SHA256" "$work_dir/shellcheck.deb"
  download_checked_file "$LIBNUMA_URL" "$LIBNUMA_SHA256" "$work_dir/libnuma.deb"
  dpkg-deb -x "$work_dir/shellcheck.deb" "$work_dir/root"
  dpkg-deb -x "$work_dir/libnuma.deb" "$work_dir/root"
  printf '%s\n' "$arch" >"$work_dir/root/simple-safer-server-arch"

  rm -rf "$install_dir"
  mv "$work_dir/root" "$install_dir"
  rm -rf "$work_dir"
}

run_fast_shellcheck() {
  local shellcheck_bin="$1"
  local lib_dir="$2"
  shift 2

  LD_LIBRARY_PATH="$lib_dir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$shellcheck_bin" "$@"
}

if [[ "$(uname -s)" != "Linux" ]]; then
  fallback_to_uv_shellcheck "the fast pinned binary is Linux-only"
fi

for required_command in curl dpkg-deb sha256sum; do
  if ! command -v "$required_command" >/dev/null 2>&1; then
    fallback_to_uv_shellcheck "missing ${required_command}"
  fi
done

if ! ARCH="$(detect_arch)"; then
  fallback_to_uv_shellcheck "unsupported CPU architecture"
fi

MULTIARCH="$(multiarch_for_arch "$ARCH")"
package_info_for_arch "$ARCH"

CACHE_ROOT="${SSS_SHELLCHECK_CACHE_DIR:-${XDG_CACHE_HOME:-${HOME:-/tmp}/.cache}/simple-safer-server/shellcheck}"
INSTALL_DIR="${CACHE_ROOT}/${SHELLCHECK_PACKAGE_VERSION}-${ARCH}"
SHELLCHECK_BIN="${INSTALL_DIR}/usr/bin/shellcheck"
LIB_DIR="${INSTALL_DIR}/usr/lib/${MULTIARCH}"

if [[ ! -x "$SHELLCHECK_BIN" ]]; then
  if ! install_fast_shellcheck "$INSTALL_DIR" "$ARCH"; then
    fallback_to_uv_shellcheck "could not prepare the pinned fast binary"
  fi
fi

if ! VERSION_OUTPUT="$(run_fast_shellcheck "$SHELLCHECK_BIN" "$LIB_DIR" --version 2>/dev/null)"; then
  fallback_to_uv_shellcheck "the pinned fast binary cannot run on this machine"
fi

if ! printf '%s\n' "$VERSION_OUTPUT" | grep -Fqx "version: ${SHELLCHECK_VERSION}"; then
  rm -rf "$INSTALL_DIR"
  fallback_to_uv_shellcheck "cached ShellCheck has an unexpected version"
fi

run_fast_shellcheck "$SHELLCHECK_BIN" "$LIB_DIR" "${SHELL_FILES[@]}"
