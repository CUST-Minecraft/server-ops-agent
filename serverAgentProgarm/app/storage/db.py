""" 数据库层唯一入口：engine、会话工厂、建表。"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.storage.models import Base
from app.config import ServerSettings


def _build_engine():
    settings = ServerSettings()
    return create_engine(settings.db_url, echo=False)

engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """建表（只建缺失的表）。每个进程入口调用一次。"""
    #   1) 先 import app.storage.models（为什么顺序重要？--不导入则模型类从未被
    #      Python 执行定义，Base 根本不知道有任何表）
    #   2) 再调用 Base.metadata.create_all(engine)
    Base.metadata.create_all(engine)



if __name__ == "__main__":
    init_db()








