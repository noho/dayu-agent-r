# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Production Defect Controller Adjudication

## 1. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU 或新 issue。
- Gate：Slice 3 test-only implementation stop condition 的 Controller 独立复核与 plan-correction 裁决。
- Immutable slice base：`9e7a4e9d4796b9c382d44494bb10efa64787b199`。
- AgentCodex stop artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-codex.md`。

## 2. Independent reproduction

Controller 独立运行：

```text
pytest tests/documents/test_processors.py::test_docling_json_processor_projects_referenced_table_caption -q
```

结果为真实 `1 failed`：公开 `DoclingProcessor.list_tables()[0]["caption"]` 实际为 `None`，而真实 Docling JSON 中 `TableItem.captions=[RefItem("#/texts/1")]` 指向的 `TextItem.text` 为 `Consolidated statements of operations`。

当前依赖的直接类型证据：

- `docling-core==2.74.0`。
- `TableItem.model_fields["captions"]` 是 `list[RefItem]`，默认空列表。
- `RefItem.resolve(self, doc)` 是 Docling public document-reference resolution method。
- production `_build_tables()` 已持有同一 `DoclingDocument`，但调用 `_extract_table_caption(table_item)` 时丢弃该真源。
- `_extract_table_caption()` 读取不存在的旧单数 `caption` 属性并返回 `None`。

因此根因不是测试 fixture、Docling serializer、下游 display 或 coverage 工具；它是 `dayu/documents/processors/docling_processor.py` 表格投影 owner 没有按当前 Docling contract解析 caption refs。

## 3. Motivation / semantic owner decision

问题真实且严重性评估成立：caption 是表格的业务可读语义，缺失后 LLM/tool consumer 难以识别表格含义；不能在测试、下游 renderer、adapter 或 LLM prompt 中猜回。唯一正确修复边界是 Docling processor 的 table projection owner，并必须消费 `_build_tables()` 已持有的同一 `DoclingDocument`。

```text
S3-STOP-F01 = ACCEPTED / PRODUCTION_CORRECTNESS_DEFECT / PLAN_CORRECTION_REQUIRED
```

AgentCodex 正确执行 stop condition：生产、utility、README零diff；最小失败复现保留；未继续用其它coverage case掩盖失败；未宣称未运行门禁通过。

## 4. Plan-correction boundary

本裁决只授权 AgentCodex 做 plan-only correction：

- 修改 `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，将 `M dayu/documents/processors/docling_processor.py` 加入 Slice 3 correction-only production allowlist。
- 在 Slice 3 中固定 owner contract：`_build_tables()` 把同一 `DoclingDocument` 交给 caption resolver；resolver只读取当前 `TableItem.captions` refs，经 Docling public reference resolution取得文本，形成唯一 public `caption`；不得保留旧单数 `caption` fallback、`getattr`兼容、下游猜测或第二套 resolver。
- 明确空列表、无效/越界/非文本引用、多caption与空白文本的 fail-safe/投影规则，并要求 public result tests；不得只满足当前单例 fixture。
- 当前六路径测试 diff、Controller-owned control/review artifacts、accepted plan以外所有文件都作为 protected state；plan-only gate不得改 production/tests/README/utility。

具体多caption连接/去重、invalid ref fail-safe 与异常边界必须在 corrected plan 中由第一性原理写清，再交两路完整 plan review挑战；Controller不在此 artifact偷跑 implementation。

## 5. Finding / residual ledger

```text
AR-F02 = CLOSED
AR-F05 = BLOCKED_BY_ACCEPTED_S3-STOP-F01 / PLAN_CORRECTION
AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX
AR-F07 = PENDING_RELEASE_BLOCKER / REAL_REMOTE_WINDOWS_EVIDENCE
```

- Gemini quota仍是`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。
- Config/Host internal SQLite/EventLog仍为`ACCEPTED_TRUSTED_INTERNAL`；Tool Trace/audit/public/LLM/log/output/diff/review仍为`ZERO_REQUIRED`。
- 不实施统一tool authorization framework、secret infrastructure、Topic 8/9或Issues 142/151/175/177/178。

## 6. Decision

```text
STOP_CONFIRMED / S3-STOP-F01_ACCEPTED / READY_FOR_AGENTCODEX_PLAN_CORRECTION
```

Corrected plan 未经 AgentMiMo/AgentDS 双路完整 review、accepted finding fix与双路完整 re-review前，不得修改 production、继续测试实现、进入code review、commit、aggregate、push、PR或closeout。
