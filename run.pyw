"""Console-free launcher. Double-click this file, or run: pythonw run.pyw"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qwerty_bar.__main__ import main  # noqa: E402

sys.exit(main())
