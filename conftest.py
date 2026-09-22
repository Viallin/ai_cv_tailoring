import sys
from pathlib import Path
print("CONFTEST LOADED, cwd =", Path.cwd())
sys.path.insert(0, str(Path(__file__).parent))
print("sys.path[:5] =", sys.path[:5])