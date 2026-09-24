"""Print the app version from src/app_info.py (used by the build scripts)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "src", "app_info.py"), encoding="utf-8") as f:
    print(re.search(r'APP_VERSION\s*=\s*"([^"]+)"', f.read()).group(1))
