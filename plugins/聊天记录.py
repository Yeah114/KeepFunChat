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
def chat(chat_data: ChatData):
    # 检查聊天数据中是否包含用户名
    if chat_data.name:
        # 如果包含用户名，使用配置的消息模板记录日志，包含用户名和原始消息
        logger.info(coromega.config["消息模板"] % (chat_data.name, chat_data.raw_msg))
    else:
        # 如果不包含用户名，仅记录原始消息
        logger.info(chat_data.raw_msg)
