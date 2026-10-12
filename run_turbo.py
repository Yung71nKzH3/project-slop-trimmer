"""Single executable entrypoint for mcp-turbo."""

import sys
from pathlib import Path

# Ensure src is in sys.path
root_dir = Path(__file__).resolve().parent / "src"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from mcp_turbo.server import main

if __name__ == "__main__":
    main()
