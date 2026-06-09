"""Fins 下载器子包。

本 Slice 仅装配 SEC 下载器；CN/HK 下载器会在后续 Slice 单独迁移。
"""

from .sec_downloader import SecDownloader

__all__ = ["SecDownloader"]
