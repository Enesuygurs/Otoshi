import os
import sys
import tempfile
from pathlib import Path

# Keep tests away from the real %APPDATA%\Otoshi folder.
os.environ.setdefault("OTOSHI_DATA_DIR", tempfile.mkdtemp(prefix="otoshi-tests-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
