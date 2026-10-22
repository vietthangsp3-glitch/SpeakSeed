"""Initialize an empty Docker volume from the content-only image seed."""
from pathlib import Path
import os
import shutil

target = Path(os.environ.get("DB_PATH", "/data/speakseed.db"))
seed = Path("/app/seed.db")
target.parent.mkdir(parents=True, exist_ok=True)
if not target.exists():
    shutil.copy2(seed, target)

