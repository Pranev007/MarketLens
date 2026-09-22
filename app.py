"""MarketLens Streamlit Dashboard Entry Point.

Allows seamless launch via `streamlit run app.py` or default configuration
on platforms like Streamlit Community Cloud, Hugging Face Spaces, or Render.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root and src/ directory to Python module search path
PROJECT_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dashboard.app import main

if __name__ == "__main__":
    main()
