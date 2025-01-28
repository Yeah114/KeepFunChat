"""
此插件作为菜单项前置处理
Author: Mono
"""
import asyncio
import inspect
import os
import json
import queue
from KeepFunChat.config import config
from KeepFunChat.event import ChatData, on_startup  # 导入ChatData类和on_startup装饰器
from KeepFunChat.FunBuilder import logger  # 导入日志记录器
from KeepFunChat.core import Coromega  # 导入coromega核心模块
from KeepFunChat.tools import prefix
coromega = Coromega()
# 使用on_startup装饰器，在程序启动时执行该函数
q = queue.Queue()
q1 = queue.Queue()

@on_startup()
async def startup(omega):
   # 启动coromega模块，传入omega对象
    coromega.run(omega)

class ChatbarMenu:

    def __init__(self, num: int = 1):
        """
        num: int -> 页数
        """
        self.num = num
        self.main = []
        self.core = coromega
        self.data = config
        self.menu_items = self.core.event_manager.events.get(
            "when_called_by_game_menu", {})  # {"uid":func,"e"}
        self.start: str = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["菜单标题"]
        self.end: str = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["菜单末尾"]
        self.Trigger_words: list = self.data["游戏菜单模块配置"]["菜单选项"]["菜单触发词"]
        self.text_style: str = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["菜单显示格式"]
        self.when_input: str = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["等待输入时提示"]
        self.when_ask_for_accept: dict = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["要求确认时提示"]
        self.when_input_error: str = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["输入有误时提示"]
        self.when_cannot_explain: str = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["无法理解指令时提示"]
        self.when_no_menu_tip: bool = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["没有菜单项时是否提示"]
        self.when_no_menu_trigger: str = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["没有菜单项时提示"]
        self.close_menu: str = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["关闭菜单时的提示"]
        self.max_page: int = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["单页最大选项"]
        self.is_go: bool = self.data["游戏菜单模块配置"]["菜单选项"]["默认菜单"]["菜单打开后是否继续询问操作"]

        # 菜单项
        self.menu_choice_for_num = []

    def get_page(self, page_num: int):
        """
        page_num: int -> 页数
        """
        start = (page_num - 1) * self.max_page
        end = page_num * self.max_page
        menu = []
        num = 0
        menu_item_infos = []
        for uuid in self.menu_items.keys():
            menu_item_info = self.menu_items[uuid].__event_args__
            menu_item_info["uuid"] = uuid
            menu_item_infos.append(menu_item_info)
        for i in menu_item_infos:
            self.menu_choice_for_num.append({i["uuid"]: i["triggers"]})
        for i in menu_item_infos[start:end]:
            num += 1
            menu.append(self.text_style.replace("[num]", str(num)).replace("[defaultTrigger]", i["triggers"][0]).replace(
                "[argumentHint]", i["argument_hint"]).replace("[usage]", i["usage"]).replace("[index]", str(num)))
        return menu, menu_item_infos

    def get_max_page(self):
        _, menu_item_infos = self.get_page(1)
        return int(len(menu_item_infos) / self.max_page) + 1

    def return_menu(self, playername: str = "", num: int = 1):
        if num > self.get_max_page():
            return "页数超出范围"
        end = self.end.replace("[page]", str(num)).replace(
            "[total_page]", str(self.get_max_page()))
        menu, menu_item_infos = self.get_page(num)
        return self.start.replace("[page]", str(num)).replace("[total_page]", str(self.get_max_page())) + "\n" + "\n".join(menu) + "\n\n" + end

    async def on_message(self, chat_data: ChatData):
        msg = chat_data.msg
        chat_data.msg = msg[1:]
        player = coromega.get_player_by_name(chat_data.name)

        called = False
        for func in list(self.core.event_manager.events["when_called_by_game_menu"].values()):
            info = func.__event_args__
            if msg[0] not in info["triggers"]:
                continue
            called = True
            args = [chat_data, func.__coromega__]
            args = args[:len(inspect.getfullargspec(func).args)]

            await self.core.event_manager.run_event('before_calling_by_game_menu', chat_data, func, "__coromega__")
            if inspect.iscoroutinefunction(func):
                await func(*args)
            else:
                await asyncio.to_thread(func, *args)
            await self.core.event_manager.run_event('after_called_by_game_menu', chat_data, func, "__coromega__")
        if not called and self.when_no_menu_tip:
            await player.say(self.when_no_menu_trigger)

    async def wait_for_player_next_message(self, playername: str, res: str = ""):
        player = self.core.get_player_by_name(playername)
        if not self.is_go:
            return

        msg = await player.ask(res + self.when_input)
        if msg:
            if not msg.isdigit():
                await player.say(self.when_input_error.replace("[error]", f"输入的页数不是数字:{msg}"))
                return

            _, menu_item_infos = self.get_page(1)
            for i in menu_item_infos:
                self.menu_choice_for_num.append({i["uuid"]: i["triggers"]})
            for i in self.menu_choice_for_num:
                for index, item in i.items():
                    (key, value), = self.menu_choice_for_num[int(msg) - 1].items()
                    if value == item:
                        func = self.core.event_manager.events.get("when_called_by_game_menu")[
                            index]
                        chat_data = ChatData(
                            name = playername, msg = [], raw_msg = "")
                        args = [chat_data, func.__coromega__]
                        args = args[:len(
                            inspect.getfullargspec(func).args)]
                        if inspect.iscoroutinefunction(func):
                            await func(*args)
                        else:
                            await asyncio.to_thread(func, *args)
                        return
                    else:
                        continue

@coromega.when_chat_msg()
async def chat(chat_data: ChatData):
    msg: list = chat_data.msg
    res = ""
    if not isinstance(chat_data.name, str):
        return
    if len(msg) == 0 or len(chat_data.name) == 0:
        return
    menu = ChatbarMenu()
    player = coromega.get_player_by_name(chat_data.name)
    if msg[0] in menu.Trigger_words:
        if len(msg) == 1:
            res = menu.return_menu(chat_data.name)
            if menu.is_go:
                asyncio.create_task(menu.wait_for_player_next_message(chat_data.name, res))
            else:
                await player.say(res)
            return
        elif len(msg) == 2:
            try:
                int(msg[1])
            except ValueError:
                res = menu.when_input_error.replace(
                    "[error]", f"输入的页数不是数字:{msg[1]}")
            res = menu.return_menu(chat_data.name, int(msg[1]))
            await player.say(res)
            if menu.is_go:
                asyncio.create_task(menu.wait_for_player_next_message(chat_data.name))
            return
    elif prefix_str := prefix(msg[0], menu.Trigger_words):
        if not prefix_str: return
        chat_data.msg[0] = chat_data.msg[0][len(prefix_str):]
        chat_data.raw_msg = chat_data.raw_msg[len(prefix_str):]
        asyncio.create_task(menu.on_message(chat_data))
    else:
        asyncio.create_task(menu.on_message(chat_data))
    if res != "":
        await player.say(res)
