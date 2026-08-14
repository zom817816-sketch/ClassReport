"""Single-file GUI entry point; --run-cli is used by the GUI worker process."""

from __future__ import annotations

import sys

from classreport.cli import main as cli_main
from classreport.gui import launch


if __name__ == "__main__":
    if "--run-cli" in sys.argv:
        sys.argv.remove("--run-cli")
        cli_main()
    else:
        launch()
