"""Day 4 最小 Demo：五分钟看懂 SQLAlchemy 2.x 的三个概念。"""
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):          # 概念1：所有表类的公共基类
    pass


class Note(Base):                     # 概念2：一个类 = 一张表
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))


engine = create_engine("sqlite:///scratch_demo.db")   # 概念3：engine = 数据库连接的源头
Base.metadata.create_all(engine)                      # 建表（已存在则跳过）
Session = sessionmaker(bind=engine)

with Session() as session:            # 会话 = 一次工作单元
    session.add(Note(text="第一次用 ORM"))
    session.commit()                                   # 提交才真正写入

with Session() as session:
    for n in session.query(Note).all():
        print(n.id, n.text, n.created_at)