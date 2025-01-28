import re, json, inspect, ctypes, asyncio, websockets, queue
from tqdm.rich import tqdm
from .config import data_dir
import logging
logger = logging.getLogger("Yeah")

def prefix(string, prefixes):
    for prefix in prefixes:
        if string.startswith(prefix):
            return prefix
    return None

def convert_cqhttp_source(source_info):
    # 进一步分割来源信息
    source_parts = source_info.split(':')
    source_type = 'private' if source_parts[0] == '好友' else 'group'
    source_id = int(source_parts[1])
    return source_type, source_id

def convert_cqhttp_target(target):
    # 分割字符串以获取各个部分
    parts = target.split('#')
    name = parts[0].strip()
    user_id = int(parts[1].split('@')[0])
    source_info = parts[1].split('@')[1]
    source_type, source_id = convert_cqhttp_source(source_info)

    # 构建并返回字典
    return {
        "name": name,
        "user_id": user_id,
        "source_type": source_type,
        "source_id": source_id
    }

class WebSocketClient:
    def __init__(self, uri, headers=None, autoreconnect=False, reconnect_interval=1, max_reconnect_attempts=None,
                 on_connect=None, on_message=None, on_error=None, on_close=None, on_try_connect=None):
        """
        初始化WebSocket客户端。

        :param uri: WebSocket服务器的URI地址。
        :param headers: 连接时使用的HTTP头。
        :param autoreconnect: 是否自动重连。
        :param reconnect_interval: 重连尝试之间的时间间隔（秒）。
        :param max_reconnect_attempts: 最大重连尝试次数，None表示无限制。
        :param on_connect: 连接成功时调用的函数。
        :param on_message: 收到消息时调用的函数。
        :param on_error: 发生错误时调用的函数。
        :param on_close: 连接关闭时调用的函数。
        :param on_try_connect: 尝试连接时调用的函数。
        """
        self.uri = uri
        self.headers = headers
        self.autoreconnect = autoreconnect
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self.on_connect = on_connect
        self.on_message = on_message
        self.on_error = on_error
        self.on_close = on_close
        self.on_try_connect = on_try_connect
        self.reconnect_attempts = 0
        self.queue = asyncio.Queue()

    async def connect(self):
        """
        后台连接WebSocket服务器。
        """
        # 创建一个任务来运行start_connect函数，这样它就会在后台运行
        self.connect_task = asyncio.create_task(self.start_connect())
        return await self.queue.get()

    async def start_connect(self):
        """
        连接WebSocket服务器。
        """
        while True:
            try:
                # 尝试连接前触发事件
                if self.on_try_connect:
                    await self.on_try_connect()
                
                # 连接到服务器
                self.ws = await websockets.connect(self.uri, additional_headers=self.headers)

                await self.queue.put(True)
                # 连接成功后触发事件
                if self.on_connect:
                    await self.on_connect(self.ws)

                # 开始接收消息
                async for message in self.ws:
                    if self.on_message:
                        await self.on_message(self.ws, message)

            except websockets.exceptions.ConnectionClosed as e:
                # 连接关闭时触发事件
                if self.on_close:
                    await self.on_close(self.ws, e)

            except Exception as e:
                # 发生错误时触发事件
                if self.on_error:
                    await self.on_error(e)

            if self.reconnect():
                continue
            break


    async def reconnect(self):
        """
        准备重连到WebSocket服务器。
        """
        # 如果设置了自动重连，则进行重连尝试
        if self.autoreconnect:
            self.reconnect_attempts += 1
            if self.max_reconnect_attempts is None or self.reconnect_attempts <= self.max_reconnect_attempts:
                await asyncio.sleep(self.reconnect_interval * self.reconnect_attempts)
                return True
            else:
                return False
        else:
            return False
    async def send(self, message):
        """
        发送消息到WebSocket服务器。

        :param message: 要发送的消息。
        """
        await self.ws.send(message)

class AccessPath:
    def __init__(self):
        self.path = []

    def __getitem__(self, key):
        new_obj = AccessPath()
        new_obj.path = self.path + [key]
        return new_obj

    def __str__(self):
        return str(self.path)

    def index_collection(self, collection):
        # 递归地遍历路径并索引集合
        for key in self.path:
            if isinstance(key, slice):
                collection = collection[key]
            elif isinstance(collection, dict):
                collection = collection[key]
            elif isinstance(collection, list) and isinstance(key, int):
                collection = collection[key]
            else:
                raise IndexError("Invalid index for the collection type.")
        return collection

class AccessClass:
    def __getattr__(self, name):
        async def method(*args, **kwargs):
            # 获取当前函数的调用栈
            stack = inspect.stack()
            # 获取上一级调用者的信息
            caller = stack[1]
            # 获取调用的文件路径和行号
            file_path = caller.filename
            line_number = caller.lineno
            # 获取调用的代码行
            code_line = caller.code_context[0].strip() if caller.code_context else "No code context available"
            # 获取参数
            args_str = ', '.join([repr(arg) for arg in args])
            kwargs_str = ', '.join([f"{k}={v!r}" for k, v in kwargs.items()])
            all_args = ', '.join(filter(None, [args_str, kwargs_str]))

            # 检查是否使用了await
            is_awaited = 'await' in code_line

            logger.warning("CQHTTP 方法被调用，但被阻止了(因为被禁用)")
            logger.warning(f"调用者文件路径: {file_path}")
            logger.warning(f"调用者行号: {line_number}")
            logger.warning(f"调用者代码行: {code_line}")
            logger.warning(f"调用方法名: {name}")
            logger.warning(f"调用参数: {all_args}")
            return AccessPath()
        return method

ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
def remove_ansi(text):
    """
    Remove ANSI escape codes from the string.
    """
    return ansi_escape.sub('', text)

def repair_skin_title(text):
    # 使用正则表达式匹配文本开头的模式 "<x1><x2>"
    # 并捕获 "x2" 部分
    match = re.match(r'^<[^>]*><([^>]*)>', text)
    if match:
        # 如果匹配成功，则替换为捕获的 "x2" 部分
        return match.group(1) + text[match.end():]
    else:
        # 如果没有匹配到，则返回原始文本
        return text

"""
expressions = []
for expression in tqdm(json.load(open(data_dir / "prohibited.json"))):
    expressions.append(re.compile(expression))

def detect_prohibited_words(text):
    for expression in expressions:
        match = expression.match(text)
        if match:
            return match
"""

def stop_thread(thread, exctype=SystemExit):
    """在指定线程上设置异步异常，迫使线程停止。

    Args:
        thread (threading.Thread): 要停止的线程对象。
        exctype (type): 要抛出的异常类型，默认为 SystemExit。

    Raises:
        ValueError: 如果提供的线程ID无效。
        SystemError: 如果设置异步异常失败。
    """
    if not inspect.isclass(exctype):
        exctype = type(exctype)
    if not issubclass(exctype, BaseException):
        raise TypeError("Only types can be raised (not instances)")

    tid = thread.ident
    if tid == 0:
        raise ValueError("invalid thread id")

    tid = ctypes.c_long(tid)
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        # 第二次调用是为了清理，如果第一次调用失败
        ctypes.pythonapi.PyThreadState_SetAsyncExc(tid, None)
        raise SystemError("PyThreadState_SetAsyncExc failed")