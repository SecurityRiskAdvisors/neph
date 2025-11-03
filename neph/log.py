# https://github.com/SecurityRiskAdvisors/marketmaker/blob/main/libmm/log.py

import logging

from .settings import Settings


log_level: str = Settings.log_level.upper()
if not log_level in ["INFO", "DEBUG", "WARN", "ERROR"]:
    raise Exception("Invalid log level")
# dont necessarily need to do this explicitly but w/e
log_level_num: int = logging.getLevelName(log_level)

# log_fmt = "%(asctime)s | %(levelname)s | %(message)s"
log_fmt = "%(asctime)s | %(levelname)s | %(pathname)s | [%(module)s.%(funcName)s:%(lineno)d] %(message)s"

logging.basicConfig(
    filename=Settings.log_file,
    level=log_level_num,
    format=log_fmt,
    filemode="a",
)
logging.captureWarnings(True)

logger = logging.getLogger("neph")

# disable debug logging, mainly for bolt connections
logging.getLogger("neo4j").setLevel(logging.getLevelName("INFO"))


def print_and_log(msg, msg_type="info"):
    fn = getattr(logger, msg_type)
    fn(msg)
    print(msg)
