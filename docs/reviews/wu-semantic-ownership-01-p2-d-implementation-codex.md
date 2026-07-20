# WU-SEMANTIC-OWNERSHIP-01 P2-D Implementation - AgentCodex

## Motivation / Root Cause / Owner Boundary

动机成立。public compact smoke 的原始 residual 是 accepted tool evidence 缺业务 source refs 时，pre-dispatch compact material 通过 `projection.source.text` 构造 evidence block，而 accepted-result projection 在 source unavailable 时返回 `None`，与 evidence material 的非空 source contract 冲突。

Root cause 是 accepted-result projection 的 source contract 半结构化：query 已有非空 LLM-facing unavailable 文案，但 source 只用 `state` / `diagnostic_reason` 表达 unavailable，`text` 仍为 `None`，导致下游消费者倾向局部 fallback 或 fail closed。

Owner boundary：

- 事实产生：ToolRuntime / Host accept path 写入 `TOOL_RESULT_ACCEPTED`、accepted evidence envelope 与 raw outcome。
- 事实校验：accepted evidence envelope、request atom identity、result payload descriptor / digest 校验。
- 事实持久化：canonical EventLog row 与 payload descriptor / raw outcome。
- LLM-facing 投影 owner：`dayu/host/accepted_result_projection.py::project_accepted_tool_result`。
- 消费者：compact material、RunInputBuilder、Conversation Memory、Tool Trace / Read API。消费者只消费 projection，不补造 source 文案。

## Production Changes

- `dayu/host/accepted_result_projection.py`
  - 新增 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT = "业务来源不可用；工具结果未提供可安全展示的来源。"`。
  - 将 `AcceptedToolResultSourceProjection.text` 从 `str | None` 收紧为 `str`。
  - `_source_projection(...)` 在 envelope 缺失或业务 source refs 被过滤为空时返回该常量，并继续用 `state=UNAVAILABLE` / `diagnostic_reason` 区分原因。
  - 内部 refs 过滤规则不变，不把 event / payload / digest 等 refs 投影成 source。
- `dayu/host/durable/memory.py`
  - 仅同步 docstring，说明 accepted result 正常路径由统一 projection owner 提供非空 source 文本；未改行为。

未修改 durable `TOOL_RESULT_ACCEPTED` schema，未新增兼容读取、helper、facade，也未在 compact material 下游添加 fallback 分支。

## Test / README Changes

- `tests/host/test_accepted_result_projection.py`
  - 覆盖 available source 保持业务 refs。
  - 覆盖 envelope missing 与 business source unavailable 都返回共享常量，且通过 `diagnostic_reason` 区分。
  - 跨消费者测试改为 source-unavailable accepted result，验证 compact material / RunInput / Memory / Tool Trace 不泄漏 internal refs。
- `tests/host/test_compact_material.py`
  - 新增缺业务 source refs 的 pre-dispatch evidence 测试，断言 source 文本来自 projection 常量。
- `tests/host/test_run_input_builder.py`
  - 更新 accepted evidence content 测试，确认 RunInputBuilder 消费 projection owner 给出的 source text，不输出 event refs。
- `tests/host/test_memory_projection.py`
  - 更新 accepted evidence memory 测试，确认 Conversation Memory 使用 projection source-unavailable 文案。
- `tests/host/test_tool_trace_projection.py`
  - 增加 internal source ref 输入与 no-leak 断言；Tool Trace 不新增 source 展示能力。
- `tests/host/test_public_compact_smoke.py`
  - 对 raw accepted evidence compact fact reuse smoke，将 recent raw turn floor 覆盖为 0，使“刚产生的 evidence 进入 compactor”这个测试目标成立；未给 fixture 补 source refs。

README 检查：

- `dayu/host/README.md` 已说明 accepted 工具结果投影给 Tool Trace、Read API、Conversation Memory、RunInputBuilder 与 compact material 时，query/status/result/source 由 Host 统一投影，下游只消费该投影；无需更新。
- `tests/README.md` 已覆盖 Host accepted result projection、compact material、RunInputBuilder、Conversation Memory 与 Tool Trace 测试职责；本次未新增测试层级或运行方式；无需更新。

## Propagation Audit

1. Durable truth：`TOOL_RESULT_ACCEPTED` payload、accepted evidence envelope 与 raw outcome 仍是唯一持久事实；schema 未变。
2. Projection：`project_accepted_tool_result(...)` 统一投影 query/status/result/source。source available 时输出业务 refs；source unavailable 时输出唯一共享 LLM-facing 文案，并保留结构化诊断原因。
3. Compact material：`_accepted_tool_evidence_delta_blocks(...)` 继续直接使用 `projection.source.text`，无 `or ...` fallback；evidence block 不暴露 event id、payload ref 或 digest 作为 source。
4. Compactor input：public smoke 中 source-unavailable evidence 进入 `evidence_material`，fake compactor 只用 prompt-local label 生成 fact candidate。
5. Accepted compact fact：stable fact 从 raw accepted evidence material 派生；source-unavailable 文案只表示来源状态，不升级为财报事实。
6. Follow-up visible outputs：RunInputBuilder、Conversation Memory 与 Tool Trace 均从同一 accepted-result projection 派生；测试覆盖 no internal source ref leakage。

## Validation

已执行并通过：

```bash
source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py::test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence -q
# 1 passed

source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py -q
# 13 passed

source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
# 206 passed

source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q
# 46 passed

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations

git diff --check
# passed
```

Source-leak scan:

```bash
rg -n "event_id|payload_ref|payload_digest|cursor|policy|ToolRuntime|Host governance|digest" dayu/host/accepted_result_projection.py tests/host/test_accepted_result_projection.py
```

结果有命中，但均为内部实现字段、diagnostic payload refs、digest 校验、测试 fixture 输入或 no-leak 断言；新增 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 未包含 event id、payload ref、digest、cursor、policy、ToolRuntime 或 Host governance 文本。

## Residual Risks

- Tool Trace 当前不展示 source 文本，本次只验证它不从 internal refs 重建 source；未扩大 Tool Trace public summary contract。
- public smoke 的 recent raw floor 覆盖只服务“立即 compact 刚产生 accepted evidence”的测试目标；生产 recent raw tail selection 语义未改。
- 本次不关闭 WU-SEMANTIC-OWNERSHIP-01 umbrella 的其它 semantic ownership backlog。
