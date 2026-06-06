"""fins 业务域处理器注册构建器。

本模块负责在 engine 核心处理器注册表基础上，追加 fins 业务特化处理器。
设计原则：注册责任由调用方显式触发，不在模块导入时自动注册。
"""

from __future__ import annotations

from dayu.fins._log import Log
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.documents.processors.registry import build_engine_processor_registry

from .fins_bs_processor import FinsBSProcessor
from .fins_docling_processor import FinsDoclingProcessor
from .fins_markdown_processor import FinsMarkdownProcessor
from .bs_def14a_processor import BsDef14AFormProcessor
from .def14a_processor import Def14AFormProcessor
from .bs_eight_k_processor import BsEightKFormProcessor
from .bs_sc13_processor import BsSc13FormProcessor
from .eight_k_processor import EightKFormProcessor
from .sc13_processor import Sc13FormProcessor
from .bs_six_k_processor import BsSixKFormProcessor
from .bs_ten_k_processor import BsTenKFormProcessor
from .bs_ten_q_processor import BsTenQFormProcessor
from .bs_twenty_f_processor import BsTwentyFFormProcessor
from .sec_processor import SecProcessor
from .ten_k_processor import TenKFormProcessor
from .ten_q_processor import TenQFormProcessor
from .twenty_f_processor import TwentyFFormProcessor

_SPECIAL_FORM_PRIORITY = 200
_REPORT_FORM_FALLBACK_PRIORITY = 190
_SEC_PROCESSOR_PRIORITY = 120
_FINS_DOC_MARKDOWN_PRIORITY = 100
_FINS_BS_PRIORITY = 80

MODULE = "FINS.PROCESSOR_REGISTRY"


def build_fins_processor_registry() -> ProcessorRegistry:
    """构建 fins 默认处理器注册表。

    注册顺序：
    1. 先加载 engine 核心处理器。
    2. 覆盖注册 fins 业务增强处理器（Docling/Markdown/BS）。
    3. 注册 SEC 表单专项处理器（SC13/6-K/DEF 14A/8-K/10-K/10-Q/20-F）。
       BS 路线为主处理器，edgartools 路线为回退。
    4. 注册 `SecProcessor` 作为通用 SEC 兜底。

    Args:
        无。

    Returns:
        新创建并完成注册的 `ProcessorRegistry`。

    Raises:
        RuntimeError: 注册流程失败时抛出。
    """

    registry = build_engine_processor_registry()
    registry.register(
        FinsDoclingProcessor,
        name="docling_processor",
        priority=_FINS_DOC_MARKDOWN_PRIORITY,
        overwrite=True,
    )
    registry.register(
        FinsMarkdownProcessor,
        name="markdown_processor",
        priority=_FINS_DOC_MARKDOWN_PRIORITY,
        overwrite=True,
    )
    registry.register(
        FinsBSProcessor,
        name="bs_processor",
        priority=_FINS_BS_PRIORITY,
        overwrite=True,
    )
    # BsSc13FormProcessor 为 SC 13 主路径，Sc13FormProcessor 为回退
    registry.register(
        BsSc13FormProcessor,
        name="sc13_section_processor",
        priority=_SPECIAL_FORM_PRIORITY,
        overwrite=True,
    )
    registry.register(
        Sc13FormProcessor,
        name="sc13_section_processor_fallback",
        priority=_REPORT_FORM_FALLBACK_PRIORITY,
        overwrite=True,
    )
    registry.register(
        BsSixKFormProcessor,
        name="six_k_section_processor",
        priority=_SPECIAL_FORM_PRIORITY,
        overwrite=True,
    )
    # BsDef14AFormProcessor 为 DEF 14A 主路径，Def14AFormProcessor 为回退
    registry.register(
        BsDef14AFormProcessor,
        name="def14a_section_processor",
        priority=_SPECIAL_FORM_PRIORITY,
        overwrite=True,
    )
    registry.register(
        Def14AFormProcessor,
        name="def14a_section_processor_fallback",
        priority=_REPORT_FORM_FALLBACK_PRIORITY,
        overwrite=True,
    )
    # BsEightKFormProcessor 为 8-K 主路径，EightKFormProcessor 为回退
    registry.register(
        BsEightKFormProcessor,
        name="eight_k_section_processor",
        priority=_SPECIAL_FORM_PRIORITY,
        overwrite=True,
    )
    registry.register(
        EightKFormProcessor,
        name="eight_k_section_processor_fallback",
        priority=_REPORT_FORM_FALLBACK_PRIORITY,
        overwrite=True,
    )
    # BsTenKFormProcessor 为 10-K 主路径，TenKFormProcessor 为回退
    registry.register(
        BsTenKFormProcessor,
        name="ten_k_section_processor",
        priority=_SPECIAL_FORM_PRIORITY,
        overwrite=True,
    )
    registry.register(
        TenKFormProcessor,
        name="ten_k_section_processor_fallback",
        priority=_REPORT_FORM_FALLBACK_PRIORITY,
        overwrite=True,
    )
    # BsTenQFormProcessor 为 10-Q 主路径，TenQFormProcessor 为回退
    registry.register(
        BsTenQFormProcessor,
        name="ten_q_section_processor",
        priority=_SPECIAL_FORM_PRIORITY,
        overwrite=True,
    )
    registry.register(
        TenQFormProcessor,
        name="ten_q_section_processor_fallback",
        priority=_REPORT_FORM_FALLBACK_PRIORITY,
        overwrite=True,
    )
    # BsTwentyFFormProcessor 为 20-F 主路径，TwentyFFormProcessor 为回退
    registry.register(
        BsTwentyFFormProcessor,
        name="twenty_f_section_processor",
        priority=_SPECIAL_FORM_PRIORITY,
        overwrite=True,
    )
    registry.register(
        TwentyFFormProcessor,
        name="twenty_f_section_processor_fallback",
        priority=_REPORT_FORM_FALLBACK_PRIORITY,
        overwrite=True,
    )
    registry.register(
        SecProcessor,
        name="sec_processor",
        priority=_SEC_PROCESSOR_PRIORITY,
        overwrite=True,
    )
    Log.verbose("已构建 fins 处理器注册表", module=MODULE)
    return registry


def build_bs_experiment_registry() -> ProcessorRegistry:
    """构建 BS 实验注册表。

    在标准注册表基础上，将 10-K 专项处理器替换为
    ``BsTenKFormProcessor``（基于 BeautifulSoup），用于对比实验。

    Args:
        无。

    Returns:
        使用 BS 路线 10-K 处理器的注册表。

    Raises:
        RuntimeError: 注册流程失败时抛出。
    """

    # BsTenKFormProcessor 已在默认注册表中作为主路径，此函数保持向后兼容
    return build_fins_processor_registry()
