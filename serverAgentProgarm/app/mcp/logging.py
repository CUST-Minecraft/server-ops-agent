"""连接存续时隐藏 SDK 协议原文；保留应用日志和其他日志工厂的行为。"""
from contextlib import contextmanager
import logging
from pathlib import Path
from threading import RLock
import mcp

_lock = RLock()
_users = 0
_previous_factory = None
_active_factory = None
_SDK_ROOT = Path(mcp.__file__).parent


def _make_safe_factory(previous):
    # 不可变闭包：其他库捕获/包装本工厂后，再次安装也不会循环委托。
    def safe_record(*args, **kwargs):
        record = previous(*args, **kwargs)
        # SDK session 使用普通 logger 名 client，需同时按源码位置识别。
        is_sdk = (record.name == "mcp" or record.name.startswith("mcp.") or
                  Path(record.pathname).is_relative_to(_SDK_ROOT))
        if is_sdk:
            category = type(record.exc_info[1]).__name__ if record.exc_info else record.levelname
            record.msg = "MCP SDK 事件（%s；协议原文已隐藏）"
            record.args = (category,)
            record.exc_info = record.exc_text = record.stack_info = None
        return record
    return safe_record


@contextmanager
def safe_sdk_logs():
    global _users, _previous_factory, _active_factory
    with _lock:
        if _users == 0:
            _previous_factory = logging.getLogRecordFactory()
            _active_factory = _make_safe_factory(_previous_factory)
            logging.setLogRecordFactory(_active_factory)
        _users += 1
    try:
        yield
    finally:
        with _lock:
            _users -= 1
            # 若其他库已安装包装器，保留其工厂，不覆盖并发修改。
            if _users == 0 and logging.getLogRecordFactory() is _active_factory:
                logging.setLogRecordFactory(_previous_factory)
