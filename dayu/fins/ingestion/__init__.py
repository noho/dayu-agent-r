"""Fins ingestion 与 Host 等待契约之间的适配能力。"""

from __future__ import annotations

from .wait_adapter import (
    FINS_DOWNLOAD_AWAITING_TOOL_NAME,
    FINS_INGESTION_WAIT_ADAPTER_KEY,
    FINS_PREPROCESS_AWAITING_TOOL_NAME,
    FINS_SUPPORTED_AWAITING_TOOL_NAMES,
    FinsIngestionWaitPollAdapter,
    build_fins_wait_adapter_registry,
)

__all__ = [
    "FINS_DOWNLOAD_AWAITING_TOOL_NAME",
    "FINS_INGESTION_WAIT_ADAPTER_KEY",
    "FINS_PREPROCESS_AWAITING_TOOL_NAME",
    "FINS_SUPPORTED_AWAITING_TOOL_NAMES",
    "FinsIngestionWaitPollAdapter",
    "build_fins_wait_adapter_registry",
]
