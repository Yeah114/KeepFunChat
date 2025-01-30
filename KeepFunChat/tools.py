import re, json, inspect, ctypes, asyncio, websockets, logging, requests, os, zipfile, tempfile, shutil, sys
from tqdm.rich import tqdm
from .config import data_dir
logger = logging.getLogger("Yeah")

def cq_code_escape(text):
    text = text.replace("&amp;", "&").replace("&#91;", "[").replace("&#93;", "]").replace("&#44;", ",")
    return text

def restart_program():
    logger.info("正在重启程序...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

def get_zip_file_size(zip_path):
    """获取压缩包内所有文件的总大小"""
    total_size = 0
    with zipfile.ZipFile(zip_path, 'r') as z:
        for info in z.infolist():
            total_size += info.file_size
    return total_size

def extract_zip_with_progress(zip_path, extract_path, auto_remove_zip = True):
    """带进度条地解压压缩包"""
    with zipfile.ZipFile(zip_path, 'r') as z:
        total_size = get_zip_file_size(zip_path)
        extracted_size = 0

        with tqdm(total=total_size, unit='B', unit_scale=True, desc='解压压缩包') as pbar:
            for file in z.infolist():
                z.extract(file, extract_path)
                extracted_size += file.file_size
                pbar.update(file.file_size)
    if auto_remove_zip:
        os.remove(zip_path)

def update_directory(zip_path, zip_folder, target_folder, skip_extensions=None):
    """更新目标文件夹内容，如果文件扩展名在扩展名列表中则不复制"""
    # 创建一个临时文件夹
    with tempfile.TemporaryDirectory() as temp_dir:
        logger.info(f"压缩包 {zip_path} 将被解压到目录 {temp_dir}")
        # 解压压缩包到临时文件夹
        extract_zip_with_progress(zip_path, temp_dir)

        # 获取压缩包内文件夹的完整路径
        extracted_folder = os.path.join(temp_dir, zip_folder)

        # 计算需要复制的文件数量
        files_to_copy = []
        for root, dirs, files in os.walk(extracted_folder):
            for file in files:
                src_file_path = os.path.join(root, file)
                target_file_path = src_file_path.replace(extracted_folder, target_folder, 1)
                # 检查文件扩展名是否在跳过列表中
                if skip_extensions and any(file.lower().endswith(ext.lower()) for ext in skip_extensions) and os.path.exists(target_file_path):
                    continue  # 如果文件扩展名在列表中，则跳过复制

                # 只有当目标文件不存在，或者源文件大小或修改时间不同时才复制
                if not os.path.exists(target_file_path) or \
                   os.stat(src_file_path).st_size != os.stat(target_file_path).st_size or \
                   os.stat(src_file_path).st_mtime > os.stat(target_file_path).st_mtime:
                    files_to_copy.append((src_file_path, target_file_path))

        # 创建进度条
        with tqdm(total=len(files_to_copy), desc="更新文件") as progress_bar:
            for src_file_path, target_file_path in files_to_copy:
                # 创建目标文件夹（如果不存在）
                os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
                # 复制文件
                shutil.copy2(src_file_path, target_file_path)
                # 更新进度条
                progress_bar.update(1)

def download_file(url: str, filename: str, size: int = 0):
    # 发起网络请求获取文件内容
    with requests.get(url, stream=True) as r:
        # 获取文件总大小
        total_size = int(r.headers.get('content-length', size))
        # 初始化tqdm进度条
        tqdm_bar = tqdm(total=total_size, unit='iB', unit_scale=True, desc=filename)
        
        # 以写入二进制的形式打开文件
        with open(filename, 'wb') as f:
            for data in r.iter_content(1024*1024): # 1024*1024 bytes each time
                tqdm_bar.update(len(data))
                f.write(data)
        tqdm_bar.close()

    if total_size != 0 and tqdm_bar.n != total_size:
        logger.warning("下载的文件大小与预计文件大小不一致")

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