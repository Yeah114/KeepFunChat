from KeepFunChat.tools import convert_cqhttp_source, convert_cqhttp_target, prefix, cq_code_escape
from KeepFunChat.event import ChatData, on_startup  # 导入ChatData类和on_startup装饰器
from KeepFunChat.core import Coromega, logger  # 导入coromega核心模块和日志记录器
coromega = Coromega()
# 使用on_startup装饰器，在程序启动时执行该函数
@on_startup()
async def startup(omega):
   # 启动coromega模块，传入omega对象
    coromega.run(omega)

# 使用coromega模块的when_chat_msg装饰器，当接收到聊天消息时执行该函数
@coromega.when_chat_msg()
async def game_to_qq(chat_data: ChatData):
    raw_msg = chat_data.raw_msg
    name = chat_data.name
    if not name and not coromega.config["启用所有消息转发"]: return
    message = f"<{name}> {raw_msg}"
    if not name: message = raw_msg
    if prefix(message, coromega.config["游戏消息没有这些前缀时才转发"]) and not prefix(message, coromega.config["游戏消息满足以下任一前缀时才转发"]): return
    for source in coromega.config["消息互通目标"]:
        source_type, source_id = convert_cqhttp_source(source)
        await coromega.cqhttp.send_msg({
            f"{source_type}_id": source_id,
            "message": coromega.config["QQ群内接受服务器内转发消息的前缀"] + message,
            "auto_escape": True # 避免CQ码乱转义
        })

@coromega.when_cqhttp_msg()
async def qq_to_game(chat_data: ChatData):
    raw_msg = chat_data.raw_msg
    message = f"<{chat_data.name}> {raw_msg}"
    repost = False
    for source in coromega.config["消息互通目标"]:
        source_type, source_id = convert_cqhttp_source(source)
        if chat_data.source_type == source_type and chat_data.source_id == source_id:
            repost = True 
            break
    if not repost: return
    if prefix(raw_msg, coromega.config["QQ消息满足以下任一前缀时才处理命令"]):
        command = raw_msg[1:]
        execute = False
        for target, commands in coromega.config["命令权限"].items():
            if (target == "*" or chat_data.user_id == convert_cqhttp_target(target).get("user_id", None)) and (prefix(command, commands) or "" in commands):
                await coromega.send_player_cmd(raw_msg)
                execute = True
                break
        if not execute:
            await coromega.cqhttp.send_msg({
                f"{chat_data.message_type}_id": chat_data.source_id,
                "message": "你没有权限使用该命令"
            })
        return
    if prefix(raw_msg, coromega.config["QQ消息没有这些前缀时才转发"]) and not prefix(raw_msg, coromega.config["QQ消息满足以下任一前缀时才转发"]): return
    player = coromega.get_player("@a")
    player.selector = player.player_name
    await player.say(coromega.config["服务器内接受QQ群内转发消息的前缀"] + raw_msg)