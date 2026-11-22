"""Optional launcher: open the Retarget editor inside the regular NLTA form.

AutoInstall.py is the preferred launch route. This file is kept for people
who previously saved RetargetTool.show() on a Maya shelf.
"""
from pathlib import Path
import sys


def show():
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import Github as GH
    return GH.CreateTool({
        "toolFolder": str(root),
        "paths": [],
        "UI": {
            "windowName": "NLTA_Form", "windowTitle": "NLTA Tools",
            "column": 1,
            "layouts": [{
                "module": "Retarget", "title": "Retarget",
                "parent": "MainLayout"
            }],
        },
    })


if __name__ == "__main__":
    show()
