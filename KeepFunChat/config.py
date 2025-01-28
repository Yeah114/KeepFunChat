import json
from pathlib import Path
config = json.load(open("config.json"))
main_dir = Path(__file__).parent.parent
data_dir = main_dir / 'data'
