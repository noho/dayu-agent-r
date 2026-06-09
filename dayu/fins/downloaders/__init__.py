"""Fins 下载器子包。

本包承载 SEC、巨潮与披露易等来源侧下载器；下载器只负责远端 discovery /
下载，不直接写入 Fins workspace。
"""

from .cninfo_downloader import CninfoDiscoveryClient
from .hkexnews_downloader import HkexnewsDiscoveryClient
from .sec_downloader import SecDownloader

__all__ = [
    "CninfoDiscoveryClient",
    "HkexnewsDiscoveryClient",
    "SecDownloader",
]
