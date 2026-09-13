#!/usr/bin/env bash
#
# Cloud Agent install script for scikit-decide (autofde-lab).
#
# Prepares a full development environment: the C++ hub extension is compiled
# and the library is installed in editable mode with every optional extra
# (`domains`, `solvers`, `pddl`, `dspy`) plus the dev/test dependency groups.
#
# This script is idempotent and non-interactive: it is safe to run repeatedly
# and against a partially prepared (e.g. snapshotted) machine.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------------------
# 1. System build dependencies
#    - build-essential/cmake/ninja: compile the C++ solvers (pybind11 module)
#    - libboost-dev: C++ header-only utilities used by the solvers
#    - python3-dev: Python.h, required by scikit-build-core for the extension
#    - libeccodes-dev: runtime for pygrib (flight-planning weather grids)
#    - libegl1: OpenGL/EGL runtime pulled in by cartopy / rendering backends
# ---------------------------------------------------------------------------
log "Installing system build dependencies"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends \
  build-essential \
  cmake \
  ninja-build \
  git \
  curl \
  ca-certificates \
  libboost-dev \
  python3-dev \
  libeccodes-dev \
  libegl1

# ---------------------------------------------------------------------------
# 2. uv package manager (drives the editable build + dependency resolution)
# ---------------------------------------------------------------------------
log "Installing uv"
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
# Expose uv on the default PATH for interactive agent shells.
sudo ln -sf "$HOME/.local/bin/uv" /usr/local/bin/uv
[ -x "$HOME/.local/bin/uvx" ] && sudo ln -sf "$HOME/.local/bin/uvx" /usr/local/bin/uvx

# ---------------------------------------------------------------------------
# 3. MiniZinc (constraint-programming backend for the scheduling DOSolver)
#
#    The official AppImage bundles a full set of system libraries. Those must
#    NEVER be placed on the global linker path (e.g. /etc/ld.so.conf.d): doing
#    so shadows the host libselinux/libpam/... and breaks sudo and PAM. Instead
#    a thin wrapper scopes LD_LIBRARY_PATH to the minizinc process only.
# ---------------------------------------------------------------------------
log "Installing MiniZinc"
MZN_VERSION="2.8.5"
MZN_DIR="$HOME/.local/minizinc"
if [ ! -x "$MZN_DIR/squashfs-root/usr/bin/minizinc" ]; then
  mkdir -p "$MZN_DIR"
  curl --fail --location --silent --show-error \
    --output "$MZN_DIR/minizinc.AppImage" \
    "https://github.com/MiniZinc/MiniZincIDE/releases/download/${MZN_VERSION}/MiniZincIDE-${MZN_VERSION}-x86_64.AppImage"
  chmod +x "$MZN_DIR/minizinc.AppImage"
  ( cd "$MZN_DIR" && ./minizinc.AppImage --appimage-extract >/dev/null )
fi
sudo tee /usr/local/bin/minizinc >/dev/null <<'WRAPPER'
#!/usr/bin/env bash
# Scope the AppImage's bundled libraries to this process only. Putting them on
# the global linker path shadows system libs (libselinux/libpam) and breaks sudo.
MZN_ROOT="$HOME/.local/minizinc/squashfs-root/usr"
export LD_LIBRARY_PATH="$MZN_ROOT/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$MZN_ROOT/bin/minizinc" "$@"
WRAPPER
sudo chmod +x /usr/local/bin/minizinc

# ---------------------------------------------------------------------------
# 4. C++ SDK git submodules (pybind11, nng, nngpp, spdlog, json, PEGTL, ...)
# ---------------------------------------------------------------------------
log "Initializing C++ SDK submodules"
git submodule update --init --recursive --jobs 4

# ---------------------------------------------------------------------------
# 5. Build the C++ extension + install all Python dependencies (editable)
# ---------------------------------------------------------------------------
log "Building scikit-decide (C++ hub + all extras)"
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-$(nproc)}"
uv sync --extra=all --python 3.12

log "autofde-lab development environment ready"
uv run --no-sync python -c "from autofde_lab import utils; \
print('solvers:', len(utils.get_registered_solvers()), '| domains:', len(utils.get_registered_domains()))"
