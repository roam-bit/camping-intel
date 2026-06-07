"""结构化 JSON 日志（P3-1）。

设计:
- 每行一条 JSON，stdout 输出
- 字段: time / level / logger / msg + 任何 extra={} 自定义键
- 异常会被 stringify 进 exc 字段
- import 时自动初始化 root logger 的 handler（only-once 防叠加）

用法:
    from app.utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("ai_search.start", extra={"query": q, "limit": limit})
    logger.warning("ark.timeout", extra={"elapsed_s": 12.3})

部署:
- 生产环境 stdout 由 ELK / Loki / Cloudwatch 等采集
- dev 环境直接看 terminal（每行 JSON 易读）
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

# logging.LogRecord 自带这些字段（不属于业务 extra），打 JSON 时跳过
_RESERVED_RECORD_KEYS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_KEYS:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_configured = False


def _configure_root_logging() -> None:
    """初始化 root logger 的 JsonFormatter handler，幂等。"""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    # 防止 uvicorn 或别人事先注册过普通 handler 导致双重输出
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure_root_logging()
    return logging.getLogger(name)
