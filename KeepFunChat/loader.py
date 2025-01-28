import os
import sys
import importlib
import json

from .core import Coromega, logger
from .event import EventManager
def load_plugins(event_manager: EventManager, coromega: Coromega, config_dir: str, plugins_dir: str):
    sys.path.insert(0, str(plugins_dir))

    def load_from_json_file(json_file_path):
        with open(json_file_path, 'r') as file:
            config = json.load(file)
            if config.get("是否禁用", True): return
            plugin_name = config.get("名称")
            if plugin_name and plugin_name.endswith('.py'):
                module_name = plugin_name[:-3]
                module = importlib.import_module(module_name)
                for attribute_name in dir(module):
                    attribute = getattr(module, attribute_name)
                    if callable(attribute):
                        event_uuid = getattr(attribute, '__event_uuid__', None)
                        if event_uuid:
                            vice_coromega = Coromega(coromega.builder, coromega.device, coromega.callback_manager)
                            vice_coromega.cqhttp = coromega.cqhttp
                            vice_coromega.load_config(json_file_path)
                            setattr(attribute, '__config__', {
                                "path": json_file_path,
                                "content": config
                            })
                            vice_coromega.load_event_manager(event_manager)
                            setattr(attribute, '__coromega__', vice_coromega)
                            event_manager.register_event(attribute)

    def walk_directory(directory):
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith('.json'):
                    json_file_path = os.path.join(root, file)
                    load_from_json_file(json_file_path)

    walk_directory(config_dir)