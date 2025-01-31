import json, time, re, os, sys, traceback, warnings, logging, argparse, typing, apkutils2, queue, threading
from BDXConverter.Converter.ErrorClassDefine import *
from BDXConverter.Converter.Converter import BDX
from BDXConverter.Converter.FileOperation import *
from adbutils._device import _DEFAULT_SOCKET_TIMEOUT, BaseDevice
from adbutils._utils import humanize, ReadProgress
from adbutils.install import InstallExtension
from adbutils._proto import ShellReturn
from adbutils.errors import *
from adbutils import adb
from uiautomator2._input import BroadcastResult
from uiautomator2.utils import list2cmdline
from uiautomator2.exceptions import *
from uiautomator2 import connect
from uiautomator2 import Device
import uiautomator2
from tqdm.std import TqdmExperimentalWarning
from tqdm.rich import tqdm, trange
from rich.logging import RichHandler
from prompt_toolkit import prompt
from prompt_toolkit.completion import PathCompleter
from typing import Optional, Dict, Union
start_build_delay = 5 # 开始导入延迟
OpenChatBoxDelay = 0.5 # 打开聊天框延迟
TpLoadDelay = 1 # 传送加载延迟
OpenCommandBlockDelay = 0.5 # 打开命令方块延迟
CommandBlockCloseDelay = 0 # 关闭命令方块延迟
ChatBoxCloseDelay = 0.5 # 关闭聊天框延迟

# 禁用 TqdmExperimentalWarning 警告
warnings.filterwarnings("ignore", category=TqdmExperimentalWarning)

# 配置日志记录器
handler = RichHandler(markup=True, rich_tracebacks=True)
logging.basicConfig(
    level = logging.INFO,
    format = "%(message)s",
    handlers = [handler]
)
# 创建 logger
logger = logging.getLogger("Yeah")
logger.setLevel(logging.DEBUG)

# 修改 BaseDevice.shell2 防止出现 "shell output invalid"
def shell2(
        self,
        cmdargs: Union[str, list, tuple],
        timeout: Optional[float] = _DEFAULT_SOCKET_TIMEOUT,
        encoding: str | None = "utf-8",
        rstrip=False,
    ) -> ShellReturn:
        """
        Run shell command with detail output
        Args:
            cmdargs (str | list | tuple): command args
            timeout (float): set shell timeout, seconds
            encoding (str): set output encoding (Default: utf-8), set None to make return bytes
            rstrip (bool): strip the last empty line, only work when encoding is set

        Returns:
            ShellOutput

        Raises:
            AdbTimeout
        """
        if isinstance(cmdargs, (list, tuple)):
            cmdargs = list2cmdline(cmdargs)
        assert isinstance(cmdargs, str)
        MAGIC = "X4EXIT:"
        newcmd = cmdargs + f"; echo {MAGIC}$?"
        output = self.shell(newcmd, timeout=timeout, encoding=encoding, rstrip=True)
        rindex = output.rfind(MAGIC if encoding else MAGIC.encode())
        if rindex == -1:  # normally will not possible
            return ShellReturn(command=cmdargs, returncode=0, output=output)#raise AdbError("shell output invalid", newcmd, output)
        returncoode = int(output[rindex + len(MAGIC) :])
        output = output[:rindex]
        if rstrip and encoding:
            output = output.rstrip()
        return ShellReturn(command=cmdargs, returncode=returncoode, output=output)
# 应用修改
BaseDevice.shell2 = shell2

# 为 Device 添加 enter 方法
def enter(self, text: str):
    self._broadcast("clipper.set", {"text": text})
    self.keyevent("279")
# 应用修改
Device.enter = enter

# 修改 InstallExtension.install 防止部分系统出现权限问题
def install(self,
            path_or_url: str,
            nolaunch: bool = False,
            uninstall: bool = False,
            silent: bool = False,
            callback: typing.Callable[[str], None] = None,
            flags: list = ["-r", "-t"]):
    """
    Install APK to device

    Args:
        path_or_url: local path or http url
        nolaunch: do not launch app after install
        uninstall: uninstall app before install
        silent: disable log message print
        callback: only two event now: <"BEFORE_INSTALL" | "FINALLY">
        flags (list): default ["-r", "-t"]

    Raises:
        AdbInstallError, BrokenPipeError
    """
    if re.match(r"^https?://", path_or_url):
        resp = requests.get(path_or_url, stream=True)
        resp.raise_for_status()
        length = int(resp.headers.get("Content-Length", 0))
        r = ReadProgress(resp.raw, length)
        logger.info("tmpfile path:", r.filepath())
    else:
        length = os.stat(path_or_url).st_size
        fd = open(path_or_url, "rb")
        r = ReadProgress(fd, length, source_path=path_or_url)

    def _dprint(*args):
        if not silent:
            logger.info(' '.join(args))

    dst = "/storage/emulated/0/tmp-%d.apk" % (int(time.time() * 1000))
    _dprint("push to %s" % dst)

    start = time.time()
    self.sync.push(r, dst)

    # parse apk package-name
    apk = apkutils2.APK(r.filepath())
    package_name = apk.manifest.package_name
    main_activity = apk.manifest.main_activity
    if main_activity and main_activity.find(".") == -1:
        main_activity = "." + main_activity

    version_code = apk.manifest.version_code
    _dprint("packageName:", package_name)
    _dprint("mainActivity:", main_activity)
    _dprint("apkVersion: {}".format(apk.manifest.version_name))
    _dprint("Success pushed, time used %d seconds" % (time.time() - start))

    new_dst = "/storage/emulated/0/{}-{}.apk".format(package_name,
                                                 version_code)
    _dprint("Rename to {}".format(new_dst))
    self.shell(["mv", dst, new_dst])

    dst = new_dst
    info = self.sync.stat(dst)
    logger.info("verify pushed apk, md5: %s, size: %s" %
          (r._hash, humanize(info.size)))
    assert info.size == r.copied

    if uninstall:
        _dprint("Uninstall app first")
        self.uninstall(package_name)

    _dprint("install to android system ...")
    start = time.time()
    if callback:
        callback("BEFORE_INSTALL")

    # 部分设备直接安装会出现权限问题 所以这里使用am
    self.shell(["am", "start", "-a", "android.intent.action.VIEW", "-t", "application/vnd.android.package-archive", "-d", "file://" + dst])
    _dprint("Success installed, time used %d seconds" %
            (time.time() - start))
    if not nolaunch:
        _dprint("Launch app: %s/%s" % (package_name, main_activity))
        self.app_start(package_name, main_activity)
# 应用修改
InstallExtension.install = install

data_directory = "data"
runtime_block_pools = {
    117: json.load(open(os.path.join(data_directory, "runtimeIds_117.json")))
}
block_states = json.load(open(os.path.join(data_directory, "Block-States.json")))
command_blocks = [
    "command_block",
    "repeating_command_block",
    "chain_command_block"
]

class Position:
    def __init__(self, x: int, y: int, z: int):
        self.x: int = x
        self.y: int = y
        self.z: int = z

    def __str__(self):
        return f"{self.x} {self.y} {self.z}"

class Builder:
    def __init__(self):
        self.init()

    def init(self):
        self.queues = {}
        self.pos: Position = Position(0, 0, 0)
        self.block_pool: list = []
        self.runtime_block_pool: list = []
        self.use_CreateConstantString_times: int = 0
        self.build_operations = []
        self.bdx_contents: list = []
        self.commands = {
            1: self.CreateConstantString,
            5: self.PlaceBlockWithBlockStates,
            6: self.AddInt16ZValue0,
            7: self.PlaceBlock,
            8: self.AddZValue0,
            9: self.NOP,
            12: self.AddInt32ZValue0,
            13: self.PlaceBlockWithBlockStates,
            14: self.AddXValue,
            15: self.SubtractXValue,
            16: self.AddYValue,
            17: self.SubtractYValue,
            18: self.AddZValue,
            19: self.SubtractZValue,
            20: self.AddInt16XValue,
            21: self.AddInt32XValue,
            22: self.AddInt16YValue,
            23: self.AddInt32YValue,
            24: self.AddInt16ZValue,
            25: self.AddInt32ZValue,
            26: self.SetCommandBlockData,
            27: self.PlaceBlockWithCommandBlockData,
            28: self.AddInt8XValue,
            29: self.AddInt8YValue,
            30: self.AddInt8ZValue,
            31: self.UseRuntimeIDPool,
            32: self.PlaceRuntimeBlock,
            33: self.placeBlockWithRuntimeId,
            34: self.PlaceRuntimeBlockWithCommandBlockData,
            35: self.PlaceRuntimeBlockWithCommandBlockDataAndUint32RuntimeID,
            36: self.PlaceCommandBlockWithCommandBlockData,
            37: self.PlaceRuntimeBlockWithChestData,
            38: self.PlaceRuntimeBlockWithChestDataAndUint32RuntimeID,
            39: self.AssignDebugData,
            40: self.PlaceBlockWithChestData,
            41: self.PlaceBlockWithNBTData,
            88: self.Terminate
        }

    def reset(self):
        self.init()

    def set_pos(self, x: int, y: int, z: int):
        self.pos: Position = Position(int(x), int(y), int(z))

    def load_from_bdx(self, bdx: BDX):
        self.bdx_contents = bdx.BDXContents
        for bdx_content in tqdm(self.bdx_contents, desc="解析BDX"):
            command = None
            if bdx_content.operationNumber in self.commands:
                command = self.commands[bdx_content.operationNumber]
            if command is not None:
                command(bdx_content)

    def CreateConstantString(self, operation):
        self.block_pool.append(operation.constantString)
        self.use_CreateConstantString_times += 1

    def PlaceBlockWithBlockStates(self, operation):
        block = self.block_pool[operation.blockConstantStringID]
        block_states_str = self.block_pool[operation.blockStatesConstantStringID]
        self.build_operations.append({
            "type": "execute_command",
            "data": f"/setblock {str(self.pos)} {block} {block_states_str}"
        })

    def AddInt16ZValue0(self, operation):
        self.pos.z -= operation.value

    def PlaceBlock(self, operation):
        block = self.block_pool[operation.blockConstantStringID]
        block_data = operation.blockData
        self.build_operations.append({
            "type": "execute_command",
            "data": f"/setblock {str(self.pos)} {block} {block_data}"
        })

    def AddZValue0(self, operation):
        self.pos.z += 1

    def NOP(self, operation):
        pass

    def AddInt32ZValue0(self, operation):
        self.pos.z += operation.value

    def AddXValue(self, operation):
        self.pos.x += 1

    def SubtractXValue(self, operation):
        self.pos.x -= 1

    def AddYValue(self, operation):
        self.pos.y += 1

    def SubtractYValue(self, operation):
        self.pos.y -= 1

    def AddZValue(self, operation):
        self.pos.z += 1

    def SubtractZValue(self, operation):
        self.pos.z -= 1

    def AddInt16XValue(self, operation):
        self.pos.x += operation.value

    def AddInt32XValue(self, operation):
        self.pos.x += operation.value

    def AddInt16YValue(self, operation):
        self.pos.y += operation.value

    def AddInt32YValue(self, operation):
        self.pos.y += operation.value

    def AddInt16ZValue(self, operation):
        self.pos.z += operation.value

    def AddInt32ZValue(self, operation):
        self.pos.z += operation.value

    def SetCommandBlockData(self, operation):
        self.build_operations.append({
            "type": "enter_command",
            "data": operation.Dumps()
        })

    def PlaceBlockWithCommandBlockData(self, operation):
        block = self.block_pool[operation.blockConstantStringID]
        data = operation.blockData
        self.build_operations.append([
            {
                "type": "execute_command",
                "data": f"/setblock {str(self.pos)} {block} {block_states[mode][str(data)]}"
            },
            {
                "type": "execute_command",
                "data": f"/tp {str(self.pos.x)} {str(self.pos.y + 1)} {str(self.pos.z)}"
            },
            {
                "type": "enter_command",
                "data": operation.Dumps()
            }
        ])

    def AddInt8XValue(self, operation):
        self.pos.x += operation.value

    def AddInt8YValue(self, operation):
        self.pos.y += operation.value

    def AddInt8ZValue(self, operation):
        self.pos.z += operation.value

    def UseRuntimeIDPool(self, operation):
        pool_id = operation.poolId
        self.runtime_block_pool = runtime_block_pools.get(pool_id, [])

    def PlaceRuntimeBlock(self, operation):
        runtime_id = operation.runtimeId
        block = self.runtime_block_pool[runtime_id][0]
        self.build_operations.append({
            "type": "execute_command",
            "data": f"/setblock {str(self.pos)} {block}"
        })

    def placeBlockWithRuntimeId(self, operation):
        runtime_id = operation.runtimeId
        block = self.runtime_block_pool[runtime_id][0]
        self.build_operations.append({
            "type": "execute_command",
            "data": f"/setblock {str(self.pos)} {block}"
        })

    def PlaceRuntimeBlockWithCommandBlockData(self, operation):
        mode = self.runtime_block_pool[operation.runtimeId][0]
        data = self.runtime_block_pool[operation.runtimeId][1]
        self.build_operations.append([
            {
                "type": "execute_command",
                "data": f"/setblock {str(self.pos)} {mode} {block_states[mode][str(data)]}"
            },
            {
                "type": "execute_command",
                "data": f"/tp {str(self.pos.x)} {str(self.pos.y + 1)} {str(self.pos.z)}"
            },
            {
                "type": "enter_command",
                "data": operation.Dumps()
            }
        ])

    def PlaceRuntimeBlockWithCommandBlockDataAndUint32RuntimeID(self, operation):
        mode = self.runtime_block_pool[operation.runtimeId][0]
        data = self.runtime_block_pool[operation.runtimeId][1]
        self.build_operations.append([
            {
                "type": "execute_command",
                "data": f"/setblock {str(self.pos)} {mode} {block_states[mode][str(data)]}"
            },
            {
                "type": "execute_command",
                "data": f"/tp {str(self.pos.x)} {str(self.pos.y + 1)} {str(self.pos.z)}"
            },
            {
                "type": "enter_command",
                "data": operation.Dumps()
            }
        ])

    def PlaceCommandBlockWithCommandBlockData(self, operation):
        mode = command_blocks[operation.mode]
        self.build_operations.append([
            {
                "type": "execute_command",
                "data": f"/setblock {str(self.pos)} {mode} {block_states[mode][str(operation.data)]}"
            },
            {
                "type": "execute_command",
                "data": f"/tp {str(self.pos.x)} {str(self.pos.y + 1)} {str(self.pos.z)}"
            },
            {
                "type": "enter_command",
                "data": operation.Dumps()
            }
        ])

    def PlaceRuntimeBlockWithChestData(self, operation):
        runtime_id = operation.runtimeId
        block = self.runtime_block_pool[runtime_id][0]
        slot_count = operation.slotCount
        chest_data = operation.chestData
        self.build_operations.append({
            "type": "execute_command",
            "data": f"/setblock {str(self.pos)} {block} {block_states[str(self.runtime_block_pool[runtime_id][1])]}"
        })

    def PlaceRuntimeBlockWithChestDataAndUint32RuntimeID(self, operation):
        runtime_id = operation.runtimeId
        block = self.runtime_block_pool[runtime_id][0]
        slot_count = operation.slotCount
        chest_data = operation.chestData
        self.build_operations.append({
            "type": "execute_command",
            "data": f"/setblock {str(self.pos)} {block} {block_states[str(self.runtime_block_pool[runtime_id][1])]}"
        })

    def AssignDebugData(self, operation):
        pass

    def PlaceBlockWithChestData(self, operation):
        block = self.block_pool[operation.blockConstantStringID]
        block_states_str = self.block_pool[operation.blockStatesConstantStringID]
        self.build_operations.append({
            "type": "execute_command",
            "data": f"/setblock {str(self.pos)} {block} {block_states_str}"
        })

    def PlaceBlockWithNBTData(self, operation):
        block = self.block_pool[operation.blockConstantStringID]
        block_states_str = self.block_pool[operation.blockStatesConstantStringID]
        self.build_operations.append({
            "type": "execute_command",
            "data": f"/setblock {str(self.pos)} {block} {block_states_str}"
        })

    def Terminate(self, operation):
        # This is a pseudo-command that indicates the end of the file.
        # It should not be used to execute any commands.
        pass

    def isSigned(self, operation):
        signature_size = operation.signatureSize
        pass

    def make(self, device: Device, build_operation, callback_func = None):
        if device not in self.queues:
            self.queues[device] = queue.Queue(maxsize=1)
        self.queues[device].put(None)
        current_ime = device.shell(['settings', 'get', 'secure', 'default_input_method']).output[:-1]
        device.shell(['settings', 'put', 'secure', 'default_input_method', "com.github.uiautomator/.AdbKeyboard"])
        if isinstance(build_operation, list):
            for operation in build_operation:
                self.run(device, operation)
            return
        if build_operation["type"] == "execute_command":
            width, height = device.window_size() # 获取设备屏幕分辨率
            center_x = width // 1.5 # 计算屏幕点X坐标
            center_y = height // 1.5 # 计算屏幕点Y坐标
            device.click(center_x, center_y) # 点击屏幕中心点
            time.sleep(ChatBoxCloseDelay)
            device._broadcast("clipper.set", {"text": build_operation["data"][1:]})
            device.keyevent("KEYCODE_T")
            time.sleep(OpenChatBoxDelay)
            device.keyevent("KEYCODE_SLASH")
            device.keyevent("279")
            if callback_func:
                thread = threading.Thread(target = callback_func)
                thread.start()
            device.shell(['settings', 'put', 'secure', 'default_input_method', "deny"])
            device.keyevent("KEYCODE_ENTER")
            device.shell(['settings', 'put', 'secure', 'default_input_method', current_ime])
        elif build_operation["type"] == "enter_command":
            time.sleep(TpLoadDelay)
            data = build_operation["data"]["operationData"]
            
            # 打开命令方块
            width, height = device.window_size() # 获取设备屏幕分辨率
            center_x = width // 2 # 计算屏幕点X坐标
            center_y = height // 2 # 计算屏幕中心点Y坐标
            device.click(center_x, center_y) # 点击屏幕中心点
            time.sleep(OpenCommandBlockDelay)
            
            # 输入命令
            device.keyevent("KEYCODE_SLASH")
            device.keyevent("KEYCODE_DEL")
            device.enter(data["command"])
            device.keyevent("KEYCODE_BACK")
            device.keyevent("KEYCODE_DPAD_LEFT")
            
            # 输入命令方块显示名
            device.keyevent("KEYCODE_SLASH")
            device.keyevent("KEYCODE_DEL")
            device.enter(data["customName"])
            device.keyevent("KEYCODE_BACK")
            device.keyevent("KEYCODE_DPAD_DOWN")
            
            # 调整命令方块模式
            device.keyevent("KEYCODE_ENTER")
            for i in range(data["mode"]):
                device.keyevent("KEYCODE_DPAD_DOWN")
            device.keyevent("KEYCODE_ENTER")
            device.keyevent("KEYCODE_DPAD_DOWN")
            device.keyevent("KEYCODE_DPAD_DOWN")
            
            # 调整命令方块条件
            device.keyevent("KEYCODE_ENTER")
            if not data["conditional"]:
                device.keyevent("KEYCODE_DPAD_DOWN")
            device.keyevent("KEYCODE_ENTER")
            device.keyevent("KEYCODE_DPAD_DOWN")
            device.keyevent("KEYCODE_DPAD_DOWN")
            device.keyevent("KEYCODE_DPAD_DOWN")
            
            # 调整命令方块是否需要红石
            device.keyevent("KEYCODE_ENTER")
            if data["needsRedstone"]:
                device.keyevent("KEYCODE_DPAD_DOWN")
            device.keyevent("KEYCODE_ENTER")
            device.keyevent("KEYCODE_DPAD_DOWN")
            device.keyevent("KEYCODE_DPAD_DOWN")
            device.keyevent("KEYCODE_DPAD_DOWN")
            device.keyevent("KEYCODE_DPAD_DOWN")
            
            # 调整命令方块是否在第一个刻度执行（循环命令方块）
            if not data["executeOnFirstTick"]:
                device.keyevent("KEYCODE_ENTER")
            if  data["mode"] == 2:
                device.keyevent("KEYCODE_DPAD_DOWN")
            
            # 调整命令方块延迟
            device.keyevent("KEYCODE_1")
            device.keyevent("KEYCODE_DEL")
            device.keyevent("KEYCODE_DEL")
            device.enter(str(data["tickDelay"]))
            device.keyevent("KEYCODE_BACK")
            
            # 调整命令方块是否显示上一个输出
            if not data["trackOutput"]:
                device.keyevent("KEYCODE_DPAD_RIGHT")
                device.keyevent("KEYCODE_ENTER")
            
            # 退出命令方块
            device.keyevent("KEYCODE_BACK")
            time.sleep(CommandBlockCloseDelay)
        time.sleep(ChatBoxCloseDelay)
        self.queues[device].get()
        self.queues[device].task_done()

    def run(self, device: Device, build_operation, breakpoint_continuation = None, breakpoint_continuation_file_path = None):
        current_ime = device.shell(['settings', 'get', 'secure', 'default_input_method']).output[:-1]
        device.shell(['settings', 'put', 'secure', 'default_input_method', "com.github.uiautomator/.AdbKeyboard"])
        i = 0
        if breakpoint_continuation:
            i = breakpoint_continuation["times"]
            build_operation = build_operation[i:]
        for operation in tqdm(build_operation, desc="执行构建操作"):
            if breakpoint_continuation:
                breakpoint_continuation["times"] = i
            if breakpoint_continuation and breakpoint_continuation_file_path:
                breakpoint_continuation["times"] = i
                open(breakpoint_continuation_file_path, "w").write(json.dumps(breakpoint_continuation))
            self.make(device, operation)
            i += 1
        device.shell(['ime', 'enable', current_ime])
        device.shell(['ime', 'set', current_ime])
        device.shell(['settings', 'put', 'secure', 'default_input_method', current_ime])
        if breakpoint_continuation and breakpoint_continuation_file_path:
            os.remove(breakpoint_continuation_file_path)

    def build(self, device: Device, breakpoint_continuation_file_path = None):
        breakpoint_continuation = None
        if breakpoint_continuation_file_path:
            if not os.path.exists(breakpoint_continuation_file_path):
                open(breakpoint_continuation_file_path, "w").write('{"times":0}')
            breakpoint_continuation = json.load(open(breakpoint_continuation_file_path))
        self.run(device, self.build_operations, breakpoint_continuation, breakpoint_continuation_file_path)

def connect_to_device(device_id=None):
    def connect_device(device_serial):
        logger.info(f"正在尝试连接到设备 {device_serial}")
        try:
            device = connect(device_serial)
            logger.info("设备连接成功")
            return device
        except ConnectError:
            logger.error("连接设备时发生错误：")
            logger.error(traceback.format_exc())
            logger.error("无法连接到设备：设备不存在")
        except Exception:
            logger.error("连接设备时发生错误：")
            logger.error(traceback.format_exc())
            logger.error("无法连接到设备")
        return None

    if device_id:
        device = connect_device(device_id)
        if device: return device

    devices = adb.device_list()
    if os.name == "nt":
        import socket
        logger.info("检测当您的系统为Windows,您系统的局域网ip为:%s"% socket.gethostbyname(socket.gethostname()))
    if devices:
        logger.info("找到以下在线设备：")
        for index, device in enumerate(devices):
            logger.info(f"{index + 1}: {device.serial}")
    else:
        logger.warning("没有找到在线设备")

    while True:
        logger.info("请输入设备的序号或手动输入设备：")
        choice = prompt(">>> ")
        if choice.isdigit():
            choice = int(choice)
            if 1 <= choice <= len(devices):
                device_id = devices[choice - 1].serial
                logger.info(f"正在尝试连接到设备 {device_id}")
                device = connect(device_id)
                if device:
                    return device
            else:
                logger.error("输入的设备序号无效，请重新输入")
        else:
            device = connect(choice)
            if device:
                return device
            else:
                logger.error("无法连接到设备，请检查输入是否正确或设备是否在线")

def init_clipper(device, clipper_path):
    if "ca.zgrs.clipper" not in device.app_list():
        logger.warning("未检测到应用 Clipper，正在尝试安装")
        device.app_install(os.path.join(data_directory, "Clipper.apk"))
        logger.info("安装请求已发送，请手动点击安装")
        logger.info("按回车键确认已安装应用 Clipper")
        prompt()

def start_clipper_service(device):
    result = device.shell(["am", "startservice", "-n", "ca.zgrs.clipper/.ClipboardService"])
    if result.exit_code == 255:
        logger.error("Clipper 服务启动失败")
        logger.error(result.output)
        return False
    return True

def main():
    # 创建 ArgumentParser 对象
    parser = argparse.ArgumentParser(description='基于ADB的超慢网易我的世界导入 Author: Yeah QQ: 1246517085')

    # 添加参数
    parser.add_argument('build_file_path', nargs='?', help='构建文件的路径')
    parser.add_argument('coordinates', nargs='?', help='坐标，以逗号分隔')
    parser.add_argument('device_id', nargs='?', help='设备ID')

    # 解析命令行参数
    args = parser.parse_args()
    build_file_path = args.build_file_path
    coordinates = args.coordinates or ""
    coordinates = coordinates.split(',')
    device_id = args.device_id
 
    if not build_file_path:
        logger.info("请输入BDX文件路径：")
        build_file_path = prompt(">>> ", completer=PathCompleter())

    bdx = None
    try:
        # 读取BDX文件
        bdx = ReadBDXFile(build_file_path)
    except FileNotFoundError:
        logger.error("解析 BDX 时发生错误：")
        logger.error(traceback.format_exc())
        logger.error("BDX 文件不存在，请检查你的输入路径")
    except IsADirectoryError:
        logger.error("解析 BDX 时发生错误：")
        logger.error(traceback.format_exc())
        logger.error("你输入的是一个文件夹，请检查你的输入路径")
    except HeaderError:
        logger.error("解析 BDX 时发生错误：")
        logger.error(traceback.format_exc())
        logger.error("BDX 文件无效，请检查你的 BDX")
    except Exception:
        logger.error("解析 BDX 时发生错误：")
        logger.error(traceback.format_exc())
    if not bdx:
        return

    while not coordinates or len(coordinates) != 3:
        logger.info("请输入坐标（格式：x,y,z）：")
        coordinates = prompt(">>> ").split(',')

    device = None
    # 连接到设备
    device = connect_to_device(device_id)
    if not device:
        return
    init_clipper(device, os.path.join(data_directory, "Clipper.apk"))

    logger.info("按回车键启动 Clipper 服务")
    prompt()
    logger.info("正在进行启动 Clipper 服务")
    device.shell(["am", "start", "-n", "ca.zgrs.clipper/.Main"])
    if not start_clipper_service(device): return
    logger.info("Clipper 服务已启动")
    logger.info("开始进行导入")
    logger.info("正在创建 Builder")
    builder = Builder()
    logger.info("正在设置坐标为 " + " ".join(coordinates))
    builder.set_pos(*coordinates)
    logger.info("正在加载 BDX")
    builder.load_from_bdx(bdx)
    open("build_operations.json", "w+").write(json.dumps(builder.build_operations))
    logger.info(f"预计操作总量为 {str(len(builder.build_operations))} 次")
    breakpoint_continuation_file_path = build_file_path + ".json"
    if os.path.exists(breakpoint_continuation_file_path):
        breakpoint_continuation = json.load(open(breakpoint_continuation_file_path))
        logger.info(f"检测到断点续导文件：{breakpoint_continuation_file_path}")
        logger.info(f'导入将从第 {str(breakpoint_continuation["times"])} 步开始')
    logger.info(f"按回车键 {str(start_build_delay)} 秒后开始导入")
    prompt()
    for i in trange(start_build_delay, desc="导入倒计时"):
        time.sleep(i)
    builder.build(device, breakpoint_continuation_file_path)

if __name__ == "__main__":
    main()

# 以下是一个不使用 BDX 去指定 ADB 干的事情的示例
"""
builder.make(device, [
{"type": "execute_command", "data": "/tp 0 100 0"},
[{'type': 'execute_command', 'data': '/setblock 4 104 6 chain_command_block ["conditional_bit"=false,"facing_direction"=0]'}, {'type': 'execute_command', 'data': '/tp 4 105 6'}, {'type': 'enter_command', 'data': {'operationNumber': 34, 'operationName': 'PlaceRuntimeBlockWithCommandBlockData', 'operationData': {'runtimeId': 1054, 'mode': 1, 'command': 'say 基于ADB', 'customName': '测试2', 'lastOutput': 'commands.scoreboard.players.add.multiple.success', 'tickDelay': 0, 'executeOnFirstTick': False, 'trackOutput': True, 'conditional': False, 'needsRedstone': False}}}],
[{'type': 'execute_command', 'data': '/setblock 4 105 6 repeating_command_block ["conditional_bit"=false,"facing_direction"=0]'}, {'type': 'execute_command', 'data': '/tp 4 106 6'}, {'type': 'enter_command', 'data': {'operationNumber': 34, 'operationName': 'PlaceRuntimeBlockWithCommandBlockData', 'operationData': {'runtimeId': 1054, 'mode': 2, 'command': 'say 导入命令方块', 'customName': '测试1', 'lastOutput': 'commands.scoreboard.players.add.multiple.success', 'tickDelay': 5, 'executeOnFirstTick': True, 'trackOutput': False, 'conditional': False, 'needsRedstone': True}}}]
])
"""