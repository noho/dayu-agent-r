"""原文读取公共契约；坐标仅表示严格 UTF-8 解码并移除首 BOM 后的码点。"""

from typing import Literal, TypedDict, NotRequired

TEXT_PAGE_DEFAULT = 16_384
TEXT_PAGE_MAX = 65_536
STRUCTURE_PAGE_DEFAULT = 200
STRUCTURE_PAGE_MAX = 1_000
FACT_PAGE_DEFAULT = 100
FACT_PAGE_MAX = 500
CONCEPTS_MAX = 100
PREVIEW_CHARS = 512
ATTRIBUTE_PAGE_MAX = 32
ANCESTORS_MAX = 32
SCAN_CHECK_INTERVAL = 512


class ExpandedName(TypedDict):
    """精确扩展名；URI 必须来自原文定义处 namespace 作用域。"""

    namespace_uri: str
    local_name: str


class SourceAssetIdentity(TypedDict):
    """资产内容身份；摘要覆盖含 BOM 的实际全部字节，不是业务推理依据。"""

    ticker: str
    document_id: str
    source_kind: Literal["filing", "material"]
    filename: str
    sha256: str
    size_bytes: int


class OriginalSpan(TypedDict):
    """资产内 0 基左闭右开 Unicode 码点范围。"""

    asset: SourceAssetIdentity
    start: int
    end: int


class OriginalPreview(TypedDict):
    """有界原文及完整范围；preview_complete 只说明预览是否完整。"""

    span: OriginalSpan
    preview: str
    preview_complete: bool


class SourceAsset(TypedDict):
    """storage 声明角色与格式能力；reading primary 不承诺原始提交主件。"""

    asset: SourceAssetIdentity
    is_reading_primary: bool
    role_status: Literal["recorded", "unrecorded"]
    source_role: str | None
    original_filename: str | None
    derived_from: str | None
    content_type: str | None
    text_supported: bool
    structure_supported: bool
    inline_facts_supported: bool


class DocumentAssetsResult(TypedDict):
    """完整有序资产清单，不截断。"""

    assets: list[SourceAsset]
    reading_primary_filename: str


class OriginalTextResult(TypedDict):
    """一次原文读取页；truncated 仅说明请求范围是否尚未读完。"""

    asset: SourceAssetIdentity
    encoding: Literal["utf-8"]
    bom_bytes: int
    requested_range: OriginalSpan
    returned_range: OriginalSpan
    total_chars: int
    text: str
    truncated: bool
    next_start: int | None


class ResolvedQName(TypedDict):
    """QName 原拼写与定义处绑定；不能解析时 URI 为 None。"""

    raw: str
    namespace_uri: str | None
    local_name: str
    status: Literal["resolved", "unbound", "ambiguous"]
    raw_complete: bool
    namespace_uri_complete: bool
    local_name_complete: bool


class OriginalAttribute(TypedDict):
    """保序原始属性；原始值与 HTML 解码投影分离，重复属性不丢弃。"""

    name: str
    span: OriginalSpan
    value: OriginalPreview | None
    quote: str | None
    duplicate: bool


class OriginalDiagnostic(TypedDict):
    """固定技术原因和相关原文范围，不表示业务结论。"""

    reason: str
    span: OriginalSpan


class OriginalReference(TypedDict):
    """context/continuation 解析；有歧义不挑选首项。"""

    status: Literal["resolved", "unresolved", "ambiguous", "absent"]
    reason: str | None
    target: OriginalPreview | None
    namespace_uri: NotRequired[str | None]
    resource_span: NotRequired[OriginalSpan | None]
    resource_target_raw: NotRequired[OriginalPreview | None]
    resource_target_origin: NotRequired[Literal["explicit", "implicit_default"]]


class OriginalNode(TypedDict):
    """位置保真的元素或词法节点；未知终点不伪造完整范围。"""

    kind: Literal["element", "text", "comment", "doctype", "cdata", "processing_instruction"]
    order: int
    qname: ResolvedQName | None
    opening: OriginalSpan
    content: OriginalSpan | None
    closing: OriginalSpan | None
    closure: Literal["explicit", "void", "rule", "unknown", "token"]
    parent: OriginalSpan | None
    parent_status: Literal["root", "resolved", "unknown"]
    ancestors: list[OriginalSpan]
    ancestors_complete: bool
    attributes: list[OriginalAttribute]
    attributes_complete: bool
    preview: OriginalPreview
    continuation: OriginalReference


class OriginalStructureResult(TypedDict):
    """起点落在请求范围内的节点分页，解析完整性与分页独立。"""

    asset: SourceAssetIdentity
    encoding: Literal["utf-8"]
    bom_bytes: int
    requested_range: OriginalSpan
    total_chars: int
    nodes: list[OriginalNode]
    total_matches: int
    truncated: bool
    next_start: int | None
    parse_status: Literal["complete", "partial"]
    diagnostics: list[OriginalDiagnostic]
    diagnostics_complete: bool


class OriginalVisibility(TypedDict):
    """仅交付隐藏声明证据，不执行 CSS/脚本或宣称可见。"""

    visibility_status: Literal["hidden_declaration", "unknown"]
    css_evaluated: Literal[False]
    evidence: list[OriginalPreview]
    evidence_complete: bool


class OriginalFact(TypedDict):
    """单个非数值 occurrence，不转换业务真假、不按值去重。"""

    node: OriginalNode
    name: ResolvedQName | None
    format: ResolvedQName | None
    raw_value: OriginalPreview | None
    context_ref: OriginalPreview | None
    target_raw: OriginalPreview | None
    target_origin: Literal["explicit", "implicit_default"]
    xml_lang: OriginalPreview | None
    xsi_nil: OriginalPreview | None
    escape: OriginalPreview | None
    continued_at: OriginalPreview | None
    context: OriginalReference
    visibility: OriginalVisibility


class OriginalFactsResult(TypedDict):
    """指定扩展名在当前资产内的 occurrence 分页；零命中不代表业务 false。"""

    asset: SourceAssetIdentity
    facts: list[OriginalFact]
    total_matches: int
    truncated: bool
    next_offset: int | None
    parse_status: Literal["complete", "partial"]
    diagnostics: list[OriginalDiagnostic]
    diagnostics_complete: bool
