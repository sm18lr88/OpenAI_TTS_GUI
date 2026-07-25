from __future__ import annotations

import sys
from pathlib import Path

from gui_baseline_support import write_gui_baseline


def main() -> int:
    arguments = sys.argv[1:]
    inject_primary_undersize = "--inject-primary-undersize" in arguments
    paths = tuple(argument for argument in arguments if not argument.startswith("--"))
    if len(paths) != 2:
        raise SystemExit(
            "usage: gui_baseline_support.py OUTPUT.json OUTPUT.png [--inject-primary-undersize]"
        )
    write_gui_baseline(
        Path(paths[0]), Path(paths[1]), inject_primary_undersize=inject_primary_undersize
    )
    return 0
