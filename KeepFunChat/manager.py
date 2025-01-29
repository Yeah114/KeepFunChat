from .tools import WebSocketClient
from .event import ChatData
from .tools import logger
import asyncio, json, traceback, random

class CallbackManager:
    def __init__(self):
        self.callbacks = {}
        self.queues = {}
        self.values = {}

    async def callback(self, callback_id):
        queue = self.queues[callback_id]
        value = await queue.get()
        return value

    async def set_value(self, value, callback_id):
        if callback_id in self.queues:
            queue = self.queues[callback_id]
            asyncio.create_task(queue.put(value))

    async def add_callback(self, callback_id, callback):
        if callback_id in self.callbacks:
            # 等待上一个任务完成
            await self.callbacks[callback_id]

        # 创建一个队列来存储回调的结果
        queue = asyncio.Queue()
        self.queues[callback_id] = queue
        # 启动回调任务
        task = asyncio.create_task(callback(callback_id, queue))
        self.callbacks[callback_id] = task

    async def use_callback(self, callback_id):
        async def wrapped_callback(cb_id, queue):
            result = await self.callback(cb_id)
            await queue.put(result)

        await self.add_callback(callback_id, wrapped_callback)
        result = await self.callback(callback_id)
        del self.queues[callback_id]
        task = self.callbacks.pop(callback_id, None)
        if task:
            task.cancel()
        return result

class Cqhttp:
    def __init__(self, uri, token, event_manager, autoreconnect=True, reconnect_interval=2, max_reconnect_attempts=5):
        self.uri = uri
        self.token = token
        self.autoreconnect = autoreconnect
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.callback_manager = CallbackManager()
        self.event_manager = event_manager
        self.client = WebSocketClient(
            uri=self.uri,
            headers=self.headers,
            autoreconnect=self.autoreconnect,
            reconnect_interval=self.reconnect_interval,
            max_reconnect_attempts=self.max_reconnect_attempts,
            on_connect=self.on_connect,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_try_connect=self.on_try_connect
        )

    async def on_connect(self, ws):
        logger.info("CQHTTP 连接成功")

    async def on_message(self, ws, message):
        data = json.loads(message)
        echo = data.get("echo", None)
        if echo:
            self.callback_manager.set_value(data, echo)
            return
        asyncio.create_task(self.event_manager.run_event('when_cqhttp_data', data, "__coromega__"))
        post_type = data.get("post_type", None)
        if post_type == "message":
            sender = data.get("sender", {})
            group_id = data.get("group_id", None)
            user_id = data.get("user_id", None)
            raw_msg = data.get("message", "")
            asyncio.create_task(self.event_manager.run_event(
                'when_cqhttp_msg',
                ChatData(
                    message_type = data.get("message_type", None),
                    message_id = data.get("message_id", None),
                    msg = raw_msg.split(" "),
                    raw_msg = raw_msg,
                    name = sender.get("card", None) or sender.get("nickname", None),
                    user_id = user_id,
                    group_id = group_id,
                    source_id = group_id or user_id
                ), "__coromega__")
            )

    async def on_error(self, error):
        tb = error.__traceback__
        tb_str = ''.join(traceback.format_tb(tb))
        logger.info(f"CQHTTP 发生错误：\n{tb_str}\n{str(error)}")

    async def on_close(self, ws, close_code):
        logger.warning("CQHTTP 连接已关闭")

    async def on_try_connect(self):
        logger.info("正在尝试连接到 CQHTTP...")

    async def connect(self):
        await self.client.connect()

    async def send(self, data):
        await self.client.send(data)

    async def request(self, action: str, params: dict, get_result = True):
        echo = random.randint(0, 2147483647)
        data = {
            "action": action,
            "params": params,
            "echo": echo
        }
        await self.send(data)
        return self.callback_manager.use_callback(echo)

    def __getattr__(self, name):
        async def action(params):
            self.request(name, params)
        return action

    """ Available soon..
    async def send_cqhttp_message(self, target, message):
        data = {
            "action": "send_msg",
            "params": {
                "message_type": "private" if ":" not in target else "group",
                "user_id" if ":" not in target else "group_id": target.split(":")[-1],
                "message": message
            }
        }
        await self.client.send(json.dumps(data))

    async def send_cqhttp_message_to_id(self, id, message):
        data = {
            "action": "send_private_msg",
            "params": {
                "user_id": id,
                "message": message
            }
        }
        await self.client.send(json.dumps(data))

    async def send_cqhttp_message_to_group(self, group_id, message):
        data = {
            "action": "send_group_msg",
            "params": {
                "group_id": group_id,
                "message": message
            }
        }
        await self.client.send(json.dumps(data))

    async def send_cqhttp_message_to_guild(self, guild_id, channel_id, message):
        data = {
            "action": "send_guild_channel_msg",
            "params": {
                "guild_id": guild_id,
                "channel_id": channel_id,
                "message": message
            }
        }
        await self.client.send(json.dumps(data))

    async def get_cqhttp_group_members_info(self, group_id):
        data = {
            "action": "get_group_member_list",
            "params": {
                "group_id": group_id
            }
        }
        await self.client.send(json.dumps(data))

    async def get_cqhttp_guild_channels(self, guild_id):
        data = {
            "action": "get_guild_channel_list",
            "params": {
                "guild_id": guild_id
            }
        }
        await self.client.send(json.dumps(data))

    async def get_cqhttp_joined_guilds(self):
        data = {
            "action": "get_guild_list"
        }
        await self.client.send(json.dumps(data))

    async def get_cqhttp_guild_member(self, guild_id, member_id):
        data = {
            "action": "get_guild_member",
            "params": {
                "guild_id": guild_id,
                "member_id": member_id
            }
        }
        await self.client.send(json.dumps(data))
    """