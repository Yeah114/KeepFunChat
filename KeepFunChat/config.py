import json
from pathlib import Path
with open("config.json", "r", encoding="utf-8") as f:
    config = json.loads(f.read())
main_dir = Path(__file__).parent.parent
data_dir = main_dir / 'data'
