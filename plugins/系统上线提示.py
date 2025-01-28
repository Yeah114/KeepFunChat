from KeepFunChat.event import ChatData, on_startup  # 导入ChatData类和on_startup装饰器
from KeepFunChat.FunBuilder import logger  # 导入日志记录器
from KeepFunChat.core import Coromega  # 导入Coromega核心模块
coromega = Coromega()
# 使用on_startup装饰器，在程序启动时执行该函数
@on_startup()
async def startup(omega):
   # 启动coromega模块，传入omega对象
    coromega.run(omega)
    player = coromega.get_player(coromega.config["启动时信息显示"][0][0])
    player.selector = player.player_name
    await player.say(coromega.config["启动时信息显示"][0][1])