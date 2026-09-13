#!/bin/sh
# Pinned entrypoint for the scikit-decide classical PDDL engine.
# A script, not a bare interpreter: mfw canonicalizes `program` before
# spawning (to pin a blake3 digest), which resolves .venv/bin/python to the
# uv-managed interpreter and loses the venv -- so `-m skdecide` is not
# importable. The reference engine mfw already registers (fast-downward.py)
# is a script for the same reason.
exec "$HOME/scikit-decide/.venv/bin/python3.13" -m skdecide.fabric.pddl_engine "$@"
