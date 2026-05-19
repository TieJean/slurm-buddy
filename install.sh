#!/usr/bin/env bash
# Idempotent installer for slurm-buddy: symlinks `sb` into ~/bin.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${REPO_ROOT}/bin/sb"
BIN_DIR="${HOME}/bin"
DEST="${BIN_DIR}/sb"

chmod +x "${SRC}"

mkdir -p "${BIN_DIR}"
ln -sfn "${SRC}" "${DEST}"
echo "Linked ${DEST} -> ${SRC}"

case ":${PATH}:" in
  *":${BIN_DIR}:"*)
    echo "~/bin is already on PATH. Run: sb --help"
    ;;
  *)
    echo
    echo "~/bin is NOT on your PATH. Add this line to ~/.bashrc, then restart your shell:"
    echo
    echo "    export PATH=\"\$HOME/bin:\$PATH\""
    echo
    echo "Or, without installing, alias it:  alias sb='python3 ${SRC}'"
    ;;
esac
