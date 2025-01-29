import time, os
start_time = time.time()
from tqdm.rich import tqdm, trange
from pathlib import Path
import threading, warnings
warnings.filterwarnings("ignore")
main_dir = Path(__file__).parent
plugins_dir = main_dir / 'plugins'
config_dir = main_dir / 'config'
data_dir = main_dir / 'data'
log_dir = main_dir / 'log'
last_startup_time_filename = data_dir / "last_startup_time"
os.makedirs(log_dir / "run", exist_ok = True)

class BackgroundProgressBar:
    def __init__(self, total, postpone = 0.01, *args, **kwargs):
        self.total = total
        self.n = 0
        self.time = 0
        self.postpone = postpone
        self.args = args
        self.kwargs = kwargs

    def start(self):
        self.thread = threading.Thread(target = self._run)
        self.thread.start()

    def _run(self):
        with tqdm(total = self.total, *self.args, **self.kwargs) as progress:
            for _ in range(self.total):
                if self.total <= self.n:
                    progress.update(self.total - self.time)
                    break
                time.sleep(self.postpone / 2)
                progress.update(1)
                self.n += 1
                self.time += 1

    def stop(self):
        self.n = self.total

last_startup_time = 0
if os.path.exists(last_startup_time_filename):
    last_startup_time = float(open(last_startup_time_filename, "r", encoding = "utf-8").read())
    program_loading_progress = BackgroundProgressBar(int(last_startup_time * 100), postpone = 0.01, desc = "正在启动程序")
    program_loading_progress.start()

version = open("version", "r", encoding="utf-8").read()
import sys, io
global display
display = True
class Tee(io.TextIOBase):
    def __init__(self, original_stdout, original_stderr):
        self.original_stdout = original_stdout
        self.original_stderr = original_stderr
        self.captured_output = io.StringIO()
        self.captured_error = io.StringIO()

    def write(self, s):
        if display:
            self.original_stdout.write(s)
            self.captured_output.write(s)

    def flush(self):
        if display:
            self.original_stdout.flush()
            self.captured_output.flush()

    def error_write(self, s):
        if display:
            self.original_stderr.write(s)
            self.captured_error.write(s)

    def error_flush(self):
        if display:
            self.original_stderr.flush()
            self.captured_error.flush()

    def getvalue(self):
        return self.captured_output.getvalue()

    def geterrorvalue(self):
        return self.captured_error.getvalue()

    def isatty(self):
        return self.original_stdout.isatty()

# 创建Tee对象，它将同时写入StringIO和原始stdout以及stderr
original_stdout = sys.stdout
original_stderr = sys.stderr
sys.stdout = Tee(original_stdout, original_stderr)
sys.stderr = sys.stdout

import atexit
def on_exit():
    print("")
    text = "Good Bye! --by Yeah"
    try:
        logger.info(text)
    except:
        print(text)
    tee_instance = sys.stderr
    sys.stdout = original_stdout
    sys.stderr = original_stderr
    record = True
    try:
        record = config["记录日志"]
    except:
        pass
    if record:
        import datetime
        from KeepFunChat.tools import remove_ansi
        current_time = datetime.datetime.now()
        formatted_time = current_time.strftime('%Y-%m%d#%H:%M:%S.%f')
        open(log_dir / 'run' / f"{formatted_time}.log", "w+").write(remove_ansi(tee_instance.getvalue() or ""))
    # 关闭StringIO对象
    tee_instance.captured_output.close()
atexit.register(on_exit)

from fastapi import FastAPI, Request
from KeepFunChat.tools import remove_ansi, repair_skin_title, stop_thread, download_file, update_directory, restart_program
from KeepFunChat.FunBuilder import Builder, connect_to_device, handler, init_clipper, start_clipper_service
from KeepFunChat.manager import CallbackManager, Cqhttp
from KeepFunChat.event import EventManager, event, EventData, ChatData
from KeepFunChat.core import Coromega, logger
from KeepFunChat.loader import load_plugins
from KeepFunChat.config import config
from fastapi.responses import PlainTextResponse
from rich.logging import RichHandler
import uvicorn, asyncio, logging, datetime, requests, queue, signal, time, inspect, tracemalloc, traceback
tracemalloc.start()
# Ctrl+C 信号处理
def signal_handler(sig, frame):
    print("")
    logger.warning('检测到信号: SIGINT (Ctrl+C), 程序即将关闭')
    """ 在 Windows 平台上，此代码无法正常使用
    active_threads = threading.enumerate()
    for thread in tqdm(active_threads, desc = "关闭线程"):
        if thread is threading.current_thread():
            continue
        try:
            stop_thread(thread)
        except Exception as e:
            logger.error(f"无法关闭线程 {thread.name}: {e}")
    sys.exit(0)
    """
    on_exit()
    os._exit(0)
signal.signal(signal.SIGINT, signal_handler)

global device, coromega
q = queue.Queue()
app = FastAPI()
callback_manager = CallbackManager()
builder = Builder()
today = str(datetime.date.today())
address = f'{config["主机"]}:{config["端口"]}'
process_id = os.getpid()
event_manager = EventManager()
record_handler = logging.handlers.RotatingFileHandler(log_dir / f"{today}.log",mode="a")
record_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
if config["记录日志"]:
    logger.addHandler(record_handler)

async def startup():
    global device, coromega, display
    display = True
    coromega = Coromega(builder, device, callback_manager)
    if config["CQHTTP正向WebSocket连接地址"]:
        cqhttp = Cqhttp(config["CQHTTP正向WebSocket连接地址"], config["CQHTTP连接密钥"])
        await cqhttp.connect()
        coromega.cqhttp = cqhttp
    else:
        logger.warning("没有启用 CQHTTP")
        logger.warning("CQHTTP 相关功能被禁用")
    load_plugins(event_manager, coromega, config_dir, plugins_dir)
    uvicorn_logger = logging.getLogger("uvicorn.access")
    uvicorn_logger.handlers = []
    uvicorn_logger.addHandler(handler)
    if config["记录日志"]:
        uvicorn_logger.addHandler(record_handler)
    q.put(None)
    display = False
app.add_event_handler("startup", startup)

@app.post("/")
async def handle_post(request: Request):
    global coromega
    message = await request.body()
    message = message.decode()
    now = datetime.datetime.now()
    timestamp_ms = int(now.timestamp() * 1000)
    get_commands_result = callback_manager.values.get("command_result", [])
    if len(get_commands_result) >= 1:
        get_command_result = get_commands_result[0][0]
        get_command_result_ms = get_commands_result[0][1]
        
        if get_command_result_ms >= timestamp_ms:
            await get_command_result.put(message)
            async def task():
                ms = (get_command_result_ms - timestamp_ms) / 1000
                await asyncio.sleep(ms)
                get_commands_result = callback_manager.values.get("command_result", [])
                if len(get_commands_result) > 0 and get_commands_result[0][0] == get_command_result:
                    await get_command_result.put(None)
                    del get_commands_result[0]
            task = asyncio.create_task(task())
            callback_manager.values["command_result"][0].append(task)
            return
        else:
            await get_command_result.put(None)
            del get_commands_result[0]

    data = message.split(" 说 ", 1)
    raw_msg = data[0]
    name = None
    if len(data) == 2:
        name = repair_skin_title(data[0])
        raw_msg = data[1]
    msg = raw_msg.split(" ")
    if name in callback_manager.callbacks:
        await callback_manager.set_value(raw_msg, name)
        return
    chat_data = ChatData(name=name, msg=msg, raw_msg=raw_msg)
    await event_manager.run_event('when_chat_msg', chat_data, "__coromega__")

    """ 相关代码已经移动到 menu.py
    for func in list(event_manager.events["when_called_by_game_menu"].values()):
        info = func.__event_args__
        if msg[0] not in info["triggers"]:
            continue
        args = [chat_data, func.__coromega__]
        args = args[:len(inspect.getfullargspec(func).args)]

        await event_manager.run_event('before_calling_by_game_menu', chat_data, func, "__coromega__")
        if inspect.iscoroutinefunction(func):
            await func(*args)
        else:
            await asyncio.to_thread(func, *args)
        await event_manager.run_event('after_called_by_game_menu', chat_data, func, "__coromega__")
    """

    return PlainTextResponse("", status_code=200)

@app.get("/info")
async def info():
    return PlainTextResponse("", status_code=200)

def run_server():
    uvicorn.run(app, host=config["主机"], port=config["端口"])

def main():
    global device, display
    end_time = time.time()
    startup_time = round(end_time - start_time, 2)
    try:
        program_loading_progress.stop()
    except:
        pass
    time.sleep(0.02)
    logger.info(f"启动用时：{startup_time}秒")
    open(data_dir / "last_startup_time", "w+", encoding = "utf-8").write(str(startup_time))
    logger.info(f"当前版本：{version}")
    logger.info("正在获取更新中...")
    new_version = None
    try:
        new_version = requests.get(f"https://ghproxy.cn/https://raw.githubusercontent.com/Yeah114/KeepFunChat/refs/heads/main/version")
        new_version = new_version.text
    except Exception as error:
        tb = error.__traceback__
        logger.error("获取更新失败：")
        logger.error(''.join(traceback.format_tb(tb)))
        logger.error(str(error))
    if not new_version:
        logger.warning("无法判断当前是否为最新版本")
    elif version != new_version:
        logger.info(f"检测到新版本：{new_version}")
        logger.info("正在获取更新文件大小中...")
        version_size = 0
        try:
            version_size = requests.get(f"https://ghproxy.cn/https://raw.githubusercontent.com/Yeah114/KeepFunChat/refs/heads/main/size")
            version_size = int(version_size.text)
            logger.info(f"更新文件大小为：{version_size}B")
        except Exception as error:
            tb = error.__traceback__
            logger.error("获取更新文件大小失败：")
            logger.error(''.join(traceback.format_tb(tb)))
            logger.error(str(error))
        logger.info("正在下载中...")
        download_file("https://ghproxy.cn/https://github.com/Yeah114/KeepFunChat/archive/refs/heads/main.zip", "KeepFunChat.zip", version_size)
        update_directory("KeepFunChat.zip", "KeepFunChat-main", ".")
        restart_program()
    device = connect_to_device(config["默认连接设备"])
    if not device: return
    init_clipper(device, data_dir / "Clipper.apk")
    start_clipper_service(device)
    logger.info(f"已启动服务器进程 [{process_id}]")
    logger.info("正在等待应用程序启动")
    display = False
    thread = threading.Thread(target=run_server)
    thread.start()
    q.get()
    while True:
        try:
            requests.get(f"http://{address}/info")
            break
        except:
            pass
    display = True
    logger.info("应用程序启动完成")
    logger.info(f"Uvicorn在http://{address}上运行（按Ctrl+C退出）")
    asyncio.run(event_manager.run_event('on_startup', "__coromega__"))
    thread.join()

if __name__ == '__main__':
    main()