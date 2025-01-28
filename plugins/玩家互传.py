from KeepFunChat.event import on_startup, ChatData
from KeepFunChat.core import Coromega
import asyncio

coromega = Coromega()
global last_request_time
# 用于存储上次请求时间的字典
last_request_time = {}

@on_startup()
async def startup(omega):
    coromega.run(omega)

@coromega.when_called_by_game_menu(
    triggers=coromega.config["触发词"],
    usage="玩家互传",
    argument_hint="[玩家名字]"
)
async def tpa(chat_data: ChatData):
    current_time = asyncio.get_event_loop().time()
    player = coromega.get_player_by_name(chat_data.name)
    
    # 检查冷却时间
    if player.name() in last_request_time:
        if current_time - last_request_time[player.name()] < coromega.config["请求冷却时间"]:
            await player.say(coromega.config["请求过于频繁时提示"])
            return

    # 尝试从消息中获取目标玩家名字
    player_name = chat_data.msg[0] if len(chat_data.msg) > 0 else None
    online_players = await coromega.get_all_online_players()
    player_names = [p.name() for p in online_players if p.name() != player.name()]
    
    # 如果没有指定玩家，则显示选择菜单
    if not player_name:
        await show_player_selection_menu(player, player_names)
        return

    target_player = coromega.get_player_by_name(player_name)

    # 发送传送请求
    await send_tpa_request(player, target_player)

    

async def show_player_selection_menu(player, player_names):
    if not player_names:
        await player.say(coromega.config["没有对应玩家时提示"])
        return

    menu_text = coromega.config["没有指定玩家时提示"]
    for index, name in enumerate(player_names, start=1):
        menu_text += f"[{index}] {name}\n"

    choice = await player.ask(menu_text + "请输入数字选择玩家：")
    try:
        selected_index = int(choice) - 1
        if 0 <= selected_index < len(player_names):
            selected_player_name = player_names[selected_index]
            selected_player = coromega.get_player_by_name(selected_player_name)
            await send_tpa_request(player, selected_player)
        else:
            await player.say("输入的数字无效，互传已退出")
    except ValueError:
        await player.say("输入的数字无效，互传已退出")

async def send_tpa_request(src_player, dst_player):
    global last_request_time
    await src_player.say(coromega.config["请求发送时提示"].replace("[dst]", dst_player.name()))
    response = await dst_player.ask(coromega.config["询问是否同意传送"].replace("[src]", src_player.name()))
    if response.lower() in ["yes", "y", "是"]:
        # 执行传送指令
        await coromega.send_player_cmd(coromega.config["传送指令"].replace("[src]", src_player.name()).replace("[dst]", dst_player.name()))
    else:
        await src_player.say(coromega.config["目标玩家拒绝时提示"].replace("[dst]", dst_player.name()))
    # 更新请求时间
    current_time = asyncio.get_event_loop().time()
    last_request_time[src_player.name()] = current_time