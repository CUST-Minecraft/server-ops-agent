import logging

from app.config import ServerSettings


def setup_logging() -> None:
    # TODO(你来实现)：
    #   调用 logging.basicConfig，两个关键参数：
    #   - level：从 ServerSettings().log_level 取（记得 .upper()）
    #   - format：含时间、级别、模块名、消息，例如
    #     "%(asctime)s %(levelname)s %(name)s %(message)s"
    logging.basicConfig(
        level =ServerSettings().log_level.upper(),
        format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )


