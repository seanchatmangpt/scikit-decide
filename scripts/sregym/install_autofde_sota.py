from __future__ import annotations

import argparse
import shutil
from pathlib import Path

AGENT_STANZA = (
    """
  - name: autofde-sota
    kickoff_command: python -m clients.autofde.driver
    kickoff_workdir: .
    kickoff_env:
      PYTHONPATH: "../src"
    install_script: null
    agent_version: SRE-SIG-003
    container_isolation: false
""".rstrip()
    + "\n"
)


DRIVER_SOURCE = """from __future__ import annotations

import sys
import types
from pathlib import Path

# The legacy autofde_lab package root eagerly imports the historical planning
# stack. SREGym needs only the POWL execution substrate, so manufacture a
# package namespace pointing at the exact AutoFDE source tree without executing
# autofde_lab/__init__.py. Importing autofde_lab.powl.* then executes only the
# admitted POWL package and its local closure.
_autofde_source = Path(__file__).resolve().parents[3] / "src" / "autofde_lab"
if not _autofde_source.is_dir():
    raise RuntimeError(f"AutoFDE source package not found: {_autofde_source}")
if "autofde_lab" not in sys.modules:
    _package = types.ModuleType("autofde_lab")
    _package.__path__ = [str(_autofde_source)]
    _package.__package__ = "autofde_lab"
    sys.modules["autofde_lab"] = _package

from clients.autofde.autofde_sota.agent import main


if __name__ == "__main__":
    main()
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sregym-dir", required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    source = repo / "src" / "autofde_lab" / "sregym_sota"
    target_root = Path(args.sregym_dir).resolve()
    target = target_root / "clients" / "autofde"
    target.mkdir(parents=True, exist_ok=True)
    (target / "__init__.py").write_text("")
    copied = target / "autofde_sota"
    if copied.exists():
        shutil.rmtree(copied)
    shutil.copytree(source, copied)
    (target / "driver.py").write_text(DRIVER_SOURCE)

    agents = target_root / "agents.yaml"
    text = agents.read_text()
    if "name: autofde-sota" not in text:
        agents.write_text(text.rstrip() + "\n" + AGENT_STANZA)
    print(f"installed autofde-sota from {source} into {target_root}")


if __name__ == "__main__":
    main()
