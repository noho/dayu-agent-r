# Code Review — Rereview

## Scope

- Mode: targeted rereview (post-fix verification)
- Branch: phaseflow/host-issues-control
- Base: HEAD (uncommitted changes)
- Output file: docs/reviews/wu-semantic-ownership-01-round2-batch-e1-rereview-mimo.md
- Included scope: 验证 WU-SEMANTIC-OWNERSHIP-01 Round2 Batch E1 controller accepted findings 的修复是否正确关闭
- Excluded scope: controller rejected/deferred items（_ProcessorFinancialStatementPayload data_quality/reason、_iter_sections Any、broad Any、wait_adapter）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Accepted Findings Verification

### ACCEPT-1 / MiMo E1-01: source meta cache key 缺 source_kind — 已关闭

- **验证点**: `ProcessorCacheKey` 增加 `source_kind: str | None = None`（cache.py:28-34）
- **验证点**: `_get_source_meta_cached_by_kind` 使用 `source_kind.value` 作为缓存键维度（read_runtime.py:2227）
- **验证点**: processor 实例缓存与构建锁保持 `source_kind=None`，符合设计意图
- **行为测试**: `test_read_runtime_source_meta_cache_is_partitioned_by_source_kind` 验证同一 (ticker, document_id) 在 FILING 和 MATERIAL 下缓存隔离，且各自的 `get_source_meta` 只调用一次
- **结论**: 修复正确。缓存键语义与使用场景一致。

### ACCEPT-2 / DS finding 1: `_parse_source_document_meta` bool bad type 静默默认 — 已关闭

- **验证点**: `_read_bool_meta_field` 在字段存在但非 bool 时抛出 `ValueError`（read_runtime.py:379-399）
- **验证点**: `amended`、`is_deleted`、`ingest_complete` 三个字段均通过 `_read_bool_meta_field` 读取（read_runtime.py:369-376）
- **验证点**: 缺省字段使用 storage contract 默认值（amended=False, is_deleted=False, ingest_complete=True）
- **行为测试**: `test_parse_source_document_meta_preserves_bool_and_defaults` 验证显式 bool 保留与缺省默认；`test_parse_source_document_meta_rejects_non_bool_fields` 参数化验证 1, "false", None 三种非 bool 值均触发 ValueError
- **结论**: 修复正确。bool 字段严格校验，缺省值有明确 contract。

### ACCEPT-3 / DS finding 2: `_normalize_json_scalar_text` 双 owner — 已关闭

- **验证点**: `_normalize_json_scalar_text` 唯一定义在 `read_runtime_helpers.py:437-452`
- **验证点**: `read_runtime.py:97` 从 helpers 导入，无本地重复定义
- **AST 测试**: `test_fins_read_runtime_weak_typing_guards_lock_owner_boundaries` 中 `_function_returns_list_dict_any` 间接覆盖了 read_runtime 的函数签名，确认无重复
- **结论**: 修复正确。单一 owner，无重复。

### ACCEPT-4 / DS finding 6: `get_financial_statement` rows 非 list 未 fail loud — 已关闭

- **验证点**: `get_financial_statement` 在 `rows` 缺失或非 list 时抛出 `ValueError`（read_runtime.py:1639-1641）
- **验证点**: `isinstance(rows, list)` 检查在 `for _row in rows` 取消检查循环之前执行
- **行为测试**: `test_get_financial_statement_rejects_missing_or_non_list_rows` 参数化验证 `{}` 和 `{"rows": {"unexpected": "dict"}}` 两种场景；`test_get_financial_statement_accepts_list_rows` 验证正常 list 路径
- **结论**: 修复正确。processor 返回非法 rows 时 fail loud，不静默吞掉。

### ACCEPT-5 / MiMo E1-02 + DS findings 3/4: guard tests brittle/private-field — 已关闭

- **验证点**: source meta cache bounded 测试改用 `_CountingSourceRepository.get_source_meta_calls` 计数仓储调用次数，验证缓存命中后不再触发 IO（test_read_runtime_semantic_ownership_guards.py:612-634）
- **验证点**: weak typing guards 改用 AST 检查 `_getattr_processor_call_lines`、`_function_returns_list_dict_any`、`_function_argument_has_weak_annotation`，不依赖运行时私有字段访问
- **验证点**: `_CountingSourceRepository` 继承 `FsSourceDocumentRepository`，使用真实仓储行为，仅叠加调用计数
- **结论**: 修复正确。测试从源码扫描升级为 AST 级结构断言，从私有字段访问升级为计数仓储行为验证。

## Open Questions

- 无。

## Residual Risk

- **Broad weak typing surfaces 未关闭**: read runtime search/table normalization、SEC section construction、storage raw JSON helpers、Docling payload conversion 中仍有 `dict[str, Any]` 和 `Any`。Controller 已明确这些不在 Batch E scope 内。
- **result_types.py 旧字段**: search/table/citation surfaces 仍有 `dict[str, Any]` 字段未触及。
- **`_get_document_meta_cached` 缓存键无 source_kind**: 该方法通过 `_resolve_source_kind` 内部解析后缓存，键不含 `source_kind`。当前实现中 `_resolve_source_kind` 优先返回 FILING，同一 document_id 不会同时存在于两种 source_kind，碰撞风险为理论性。若未来业务场景允许同一 document_id 同时有两种 source_kind，此路径需同步修复。
