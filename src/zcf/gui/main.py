"""
zcf-gui standalone executable entrypoint.
Invoked by application launcher or 'zcf-gui' command.
"""

import sys
from zcf.gui.app import launch_gui


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: zcf-gui [options]\n")
        print("Zyntrix Compatibility Fabric (ZCF) - Graphical Control Center")
        print("Options:")
        print("  -h, --help    Show this help message and exit")
        return

    try:
        launch_gui()
    except Exception as e:
        print(f"[ZCF GUI Error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
