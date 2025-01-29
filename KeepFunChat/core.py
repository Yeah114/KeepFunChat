from .manager import CallbackManager
from .event import event, event_decorator, EventManager
from uiautomator2 import Device
from .FunBuilder import Builder, logger
import asyncio, json
from datetime import datetime
from .tools import AccessPath, AccessClass, logger

default_get_result_ms_long = 2000
class Coromega:
    def __init__(self, builder: Builder = None, device: Device = None, callback_manager: CallbackManager = None):
        self.builder = builder
        self.device = device
        self.callback_manager = callback_manager
        self.config = AccessPath()
        self.config_path = ""
        self.event_manager: EventManager
        self.events = []
        self.cqhttp = AccessClass()

    def load_config(self, config_path: str):
        self.config_path = config_path
        with open(config_path, "r", encoding="utf-8") as file:
            config = json.loads(file.read()).get("配置",{})
        if isinstance(self.config, AccessPath) and self.config.path != []:
            self.config.index_collection(config)
        else:
            self.config = config

    def load_event_manager(self, event_manager: EventManager):
        self.event_manager = event_manager

    async def send_player_cmd(self, cmd: str, get_result = False, get_result_ms_long = default_get_result_ms_long):
        q = asyncio.Queue()
        def callback_func():
            now = datetime.now()
            timestamp_ms = int(now.timestamp() * 1000)
            get_command_result_timestamp_ms = timestamp_ms + get_result_ms_long
            command_result_list = self.callback_manager.values.get("command_result", [])
            command_result_list.append([q, get_command_result_timestamp_ms])
            self.callback_manager.values["command_result"] = command_result_list

        if not get_result:
            callback_func = None

        if not cmd.startswith('/'):
            cmd = "/" + cmd
        cmd = cmd.replace("\n", "\\n")
        logger.info(f"执行命令：{cmd}")

        await asyncio.to_thread(self.builder.make, self.device, {
            "type": "execute_command",
            "data": cmd
        }, callback_func)
        if get_result:
            results = []
            while True:
                result = await q.get
                if not result:
                    break
                results.append(result)
            return results

    def get_player(self, target: str):
        return Player(self, target)

    def get_player_by_name(self, player_name: str):
        return self.get_player(player_name)

    async def get_player_msg(self, player_name: str):
        return await self.callback_manager.use_callback(player_name)

    async def get_all_online_players(self):
        outputs = await self.send_player_cmd("/list", True)
        player_names = outputs[1].split(", ")
        players = []
        for player_name in player_names:
            players.append(self.get_player_by_name(player_name))
        return players

    @event()
    def when_chat_msg(self):
        args = locals()
        del args["self"]
        Edecorator = event_decorator(**args)
        def decorator(func):
            func = Edecorator(func)
            self.events.append([func, args])
        return decorator

    @event()
    def before_calling_by_game_menu(self):
        args = locals()
        del args["self"]
        Edecorator = event_decorator(**args)
        def decorator(func):
            func = Edecorator(func)
            self.events.append([func, args])
        return decorator

    @event()
    def when_called_by_game_menu(self, triggers: list, argument_hint: str, usage: str):
        args = locals()
        del args["self"]
        Edecorator = event_decorator(**args)
        def decorator(func):
            func = Edecorator(func)
            self.events.append([func, args])
        return decorator

    @event()
    def after_called_by_game_menu(self):
        args = locals()
        del args["self"]
        Edecorator = event_decorator(**args)
        def decorator(func):
            func = Edecorator(func)
            self.events.append([func, args])
        return decorator

    @event()
    def when_cqhttp_msg(self):
        args = locals()
        del args["self"]
        Edecorator = event_decorator(**args)
        def decorator(func):
            func = Edecorator(func)
            self.events.append([func, args])
        return decorator

    @event()
    def when_cqhttp_data(self):
        args = locals()
        del args["self"]
        Edecorator = event_decorator(**args)
        def decorator(func):
            func = Edecorator(func)
            self.events.append([func, args])
        return decorator

    def run(self, coromega):
        for event in self.events:
            func = event[0]
            func.__coromega__ = coromega
            args = func.__event_args__
            
            for arg in args.keys():
                if isinstance(args[arg], AccessPath):
                    args[arg] = args[arg].index_collection(coromega.config)
            func.__event_args__ = args
            coromega.event_manager.register_event(func)

        self.callback_manager = coromega.callback_manager
        self.event_manager = coromega.event_manager
        self.config_path = coromega.config_path
        self.builder = coromega.builder
        self.device = coromega.device
        self.cqhttp = coromega.cqhttp
        self.config = coromega.config

coromega = Coromega(None, None, None)

class TargetPlayerNotSpecifiedError(Exception):
    def __init__(self, message="未指定目标玩家的名称"):
        self.message = message
        super().__init__(self.message)

class Player:
    def __init__(self, coromega: Coromega, player_name: str = ""):
        self.coromega = coromega
        if not player_name == "":
            self.player_name = player_name
            self.selector = f'@a[name="{self.player_name}"]'
        else:
            raise TargetPlayerNotSpecifiedError()

    async def say(self, text: str):
        raw = {
            "rawtext": [
                {"text": text}
            ]
        }
        await self.raw_say(raw)
        return None
    
    async def ask(self, hint: str, timeout = None):
        await self.say(hint)
        return await self.coromega.get_player_msg(self.player_name)

    async def raw_say(self, raw: dict):
        await self.coromega.send_player_cmd(f"tellraw {self.selector} {json.dumps(raw, ensure_ascii=False)}")
        return None

    async def title(self, title, subtitle = None):
        title = {
            "rawtext": [
                {"text": title}
            ]
        }
        await self.coromega.send_player_cmd(f"titleraw {self.selector} title {json.dumps(title, ensure_ascii=False)}")
        if subtitle:
            await self.subtitle(subtitle)
        return None

    async def subtitle(self, subtitle, title = None):
        subtitle = {
            "rawtext": [
                {"text": subtitle}
            ]
        }
        await self.coromega.send_player_cmd(f"titleraw {self.selector} subtitle {json.dumps(subtitle, ensure_ascii=False)}")
        if title:
            await self.title(title)
        return None

    async def action_bar(self, text):
        action_bar = {
            "rawtext": [
                {"text": text}
            ]
        }
        await self.coromega.send_player_cmd(f"titleraw {self.selector} action_bar {json.dumps(action_bar, ensure_ascii=False)}")

    """
    async def get_pos(self):
        return await self.coromega.client.send_lua(f'{self.player}output = player:get_pos()')

    async def check(self, conditions: list):
        conditions_str = to_lua_value(conditions)
        return await self.coromega.client.send_lua(f'{self.player}output = player:check({conditions_str})')

    async def uuid_string(self):
        return await self.coromega.client.send_lua(f'{self.player}output = player:uuid_string()')
    """

    def name(self):
        return self.player_name