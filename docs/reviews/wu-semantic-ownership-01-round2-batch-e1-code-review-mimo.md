# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/host-issues-control
- Base: HEAD (uncommitted changes)
- Output file: docs/reviews/wu-semantic-ownership-01-round2-batch-e1-code-review-mimo.md
- Included scope: WU-SEMANTIC-OWNERSHIP-01 Round2 Batch E1 实现
- Excluded scope: 未触及的 broad weak typing surfaces、ingestion wait_adapter Host 依赖
- Parallel review coverage: 无

## Findings

### E1-01-未修复-高-source meta 缓存键缺少 source_kind 维度

- **入口/函数**: `FinsReadRuntime._get_source_meta_cached_by_kind` (read_runtime.py:2223)
- **文件(行号)**: `dayu/fins/tools/read_runtime.py:2203-2230`
- **输入场景**: 同一 (ticker, document_id) 以不同 source_kind 调用 `_get_source_meta_cached_by_kind`
- **实际分支**: 缓存键为 `ProcessorCacheKey(ticker=ticker, document_id=document_id)`，不含 `source_kind`
- **预期行为**: 缓存键应包含 `source_kind`，确保不同来源类型的 meta 不会互相覆盖
- **实际行为**: 第一次调用缓存后，后续不同 source_kind 的调用会命中缓存返回错误的 meta
- **直接证据**: `cache_key = ProcessorCacheKey(ticker=ticker, document_id=document_id)` (L2223)；`ProcessorCacheKey` 定义只有 `ticker` 和 `document_id` 两个字段 (cache.py:20-30)
- **影响**: 如果同一 document_id 真的存在于 FILING 和 MATERIAL（虽然当前 `_resolve_source_kind` 的实现优先返回 FILING），缓存会返回错误的 meta，导致 citation、fiscal 推断等下游逻辑使用错误数据
- **建议改法和验证点**: 1) 扩展 `ProcessorCacheKey` 增加 `source_kind` 字段；或 2) 使用独立的 cache key 类型；验证点：构造测试用例验证不同 source_kind 的缓存隔离
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高（语义正确性风险，虽然当前代码路径下碰撞概率低）

### E1-02-未修复-中-guard tests 为源码扫描而非 contract-level 测试

- **入口/函数**: `test_fins_read_runtime_weak_typing_guards_lock_owner_boundaries` (test_read_runtime_semantic_ownership_guards.py:135)
- **文件(行号)**: `tests/fins/test_read_runtime_semantic_ownership_guards.py:135-186`
- **输入场景**: 测试运行时扫描源码文件内容
- **实际分支**: 使用字符串匹配 `"getattr(processor"` 等模式检查源码
- **预期行为**: 测试应验证 Protocol capability 检查的运行时行为（如 `isinstance` 返回正确结果、异常正确传播）
- **实际行为**: 测试只检查源码中不包含特定字符串模式，不验证运行时 contract 行为
- **直接证据**: `assert "getattr(processor" not in read_runtime_source` (L168-169)；无运行时 capability 检查断言
- **影响**: 源码扫描无法捕获：1) Protocol 定义与实际 processor 实现不匹配；2) `isinstance` 检查的边界情况；3) 异常传播路径错误。如果有人重命名方法但保留旧语义，源码扫描会误判为通过
- **建议改法和验证点**: 补充 contract-level 测试：构造 mock processor 验证 `isinstance(processor, _PageContentReadProcessor)` 等检查的运行时行为；验证不满足 Protocol 的 processor 返回 `NotSupportedResult`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中（测试有效性受限，但 taxonomy 测试已覆盖部分 contract 行为）

### E1-03-未修复-低-_ProcessorFinancialStatementPayload 包含结果类型不声明的字段

- **入口/函数**: `_ProcessorFinancialStatementPayload` 定义 (read_runtime.py:235-248)
- **文件(行号)**: `dayu/fins/tools/read_runtime.py:235-248`
- **输入场景**: Processor 返回包含 `data_quality` 和 `reason` 的 payload
- **实际分支**: `_ProcessorFinancialStatementPayload` 声明了 `data_quality: str` 和 `reason: str`
- **预期行为**: 如果这些字段是 processor 内部诊断信息，不应出现在 processor 返回的 payload 类型中；如果是必要字段，应在 `FinancialStatementResult` 中声明
- **实际行为**: 这些字段被 read runtime 静默丢弃（新代码显式提取字段，未提取 data_quality/reason）
- **直接证据**: `_ProcessorFinancialStatementPayload` 包含 `data_quality: str` 和 `reason: str` (L247-248)；`FinancialStatementResult` 不包含这些字段 (result_types.py:259-272)
- **影响**: 类型声明与实际语义不一致，可能误导开发者认为这些字段会传递给最终结果
- **建议改法和验证点**: 1) 从 `_ProcessorFinancialStatementPayload` 移除这些字段；或 2) 在 `FinancialStatementResult` 中声明为 `NotRequired`；验证点：确认 processor 实现是否真的返回这些字段
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（类型声明准确性问题，不影响运行时行为）

## Open Questions

- **E1-01 缓存碰撞实际风险**: 当前 `_resolve_source_kind` 实现优先返回 FILING，同一 document_id 不会同时存在于两种 source_kind。需要确认：是否存在业务场景需要同一 document_id 同时有 FILING 和 MATERIAL meta？如果不存在，此 finding 可降级为防御性改进。

- **E1-02 测试有效性边界**: 现有 taxonomy 测试已覆盖部分 contract 行为（`test_processor_taxonomy_uses_typed_protocol_not_attribute_fallback` 和 `test_processor_taxonomy_failure_propagates_without_default_fallback`）。需要确认：是否需要为 `_PageContentReadProcessor`、`_FinancialStatementReadProcessor`、`_XbrlFactsReadProcessor` 补充类似的 contract-level 测试？

## Residual Risk

- **Broad weak typing surfaces 未关闭**: read runtime search/table normalization、SEC section construction、storage raw JSON helpers、Docling payload conversion 中仍有 `dict[str, Any]` 和 `Any`。实现说明明确这些不在 Batch E scope 内。
- **result_types.py 旧字段**: search/table/citation surfaces 仍有 `dict[str, Any]` 字段未触及。
- **guard tests 有效性**: 源码扫描测试无法捕运行时 contract 违规，需补充 contract-level 测试。
