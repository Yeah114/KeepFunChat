from typing import Callable, Dict, List
import uuid, inspect, asyncio

class EventData:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self):
        attributes = ", ".join(f"{key}={value!r}" for key, value in self.__dict__.items())
        return f"{self.__class__.__name__}({attributes})"

class ChatData(EventData):pass

class EventManager:
    def __init__(self):
        self.events: Dict[str, Dict[str, Callable]] = {}

    def register_event(self, func: Callable):
        event_uuid = getattr(func, '__event_uuid__', None)
        event_name = getattr(func, '__event_name__', None)
        if event_uuid and event_name:
            if event_name not in self.events:
                self.events[event_name] = {}
            self.events[event_name][event_uuid] = func

    async def run_event(self, event_name: str, *args, **kwargs):
        if event_name in self.events:
            for func in self.events[event_name].values():
                func_args = []
                for arg in args[:len(inspect.getfullargspec(func).args)]:
                    if arg == "__coromega__":
                        func_args.append(func.__coromega__)
                    else:
                        func_args.append(arg)
                if inspect.iscoroutinefunction(func):
                    asyncio.create_task(func(*func_args, **kwargs))
                else:
                    asyncio.create_task(asyncio.to_thread(func, *func_args, **kwargs))

    def unregister_event(self, identifier: str):
        for event_name, funcs in self.events.items():
            if identifier in funcs:
                del funcs[identifier]
                return True
        return False

def event():
    def decorator(func):
        event_uuid = str(uuid.uuid4())
        setattr(func, 'event_name', func.__name__)
        setattr(func, 'event_uuid', event_uuid)
        return func
    return decorator

def event_decorator(**kwargs):
    stack = inspect.stack()
    
    # 检查调用栈的深度，确保至少有两层（当前函数和父调用）
    if len(stack) < 2:
        return None  # 如果没有父调用，则返回None

    # 获取上一层父调用的信息
    parent_frame = stack[1]
    # 获取父调用的函数名
    parent_caller_name = parent_frame.function
    def decorator(func):
        event_uuid = str(uuid.uuid4())
        setattr(func, '__event_name__', parent_caller_name)
        setattr(func, '__event_uuid__', event_uuid)
        setattr(func, '__event_args__', kwargs)
        return func
    return decorator

@event()
def on_startup():
    return event_decorator(**locals())
