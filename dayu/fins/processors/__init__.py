"""金融域处理器子包。"""

from .bs_def14a_processor import BsDef14AFormProcessor
from .bs_ten_k_processor import BsTenKFormProcessor
from .fins_bs_processor import FinsBSProcessor
from .def14a_processor import Def14AFormProcessor
from .eight_k_processor import EightKFormProcessor
from .fins_docling_processor import FinsDoclingProcessor
from .fins_markdown_processor import FinsMarkdownProcessor
from .registry import build_bs_experiment_registry, build_fins_processor_registry
from .sc13_processor import Sc13FormProcessor
from .bs_six_k_processor import BsSixKFormProcessor
from .sec_processor import SecProcessor
from .ten_k_processor import TenKFormProcessor
from .ten_q_processor import TenQFormProcessor
from .twenty_f_processor import TwentyFFormProcessor

__all__ = [
    "BsDef14AFormProcessor",
    "BsTenKFormProcessor",
    "SecProcessor",
    "FinsBSProcessor",
    "FinsDoclingProcessor",
    "FinsMarkdownProcessor",
    "Sc13FormProcessor",
    "BsSixKFormProcessor",
    "Def14AFormProcessor",
    "EightKFormProcessor",
    "TenKFormProcessor",
    "TenQFormProcessor",
    "TwentyFFormProcessor",
    "build_bs_experiment_registry",
    "build_fins_processor_registry",
]
