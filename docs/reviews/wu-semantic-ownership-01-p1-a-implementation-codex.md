# WU-SEMANTIC-OWNERSHIP-01 P1-A Implementation Report

## Owner Boundary

- 事实产生：ToolRuntime accept barrier 产生 accepted tool result canonical fact 与 raw outcome payload；tool-call request atom 是工具请求参数与 semantic query 的 durable 真源。
- 事实校验：`dayu.host.accepted_result_projection.project_accepted_tool_result(...)` 负责校验 accepted envelope、result payload digest、request atom identity 与可投影字段安全性。
- 事实持久化：EventLog canonical fact、payload store、tool-call request atom 表继续是 durable truth；本次不引入新 durable schema。
- 事实投影：Tool Trace、Read API、durable memory、Conversation Memory、RunInputBuilder、CompactMaterial 与 compact pipeline 只消费 accepted result projection 输出的 query / status / source / result 文本，不各自回读 request atom 或重建 LLM-facing source。

## Changed Files

- 新增 `dayu/host/accepted_result_projection.py`，提供 accepted 工具结果 typed projection contract，集中产出 `AcceptedToolResultProjection`、query/status/source 枚举、不可用查询文案和 projection helper。
- 迁移 `dayu/host/tool_trace.py`、`dayu/host/read_api.py`、`dayu/host/durable/memory.py`、`dayu/host/memory.py`、`dayu/host/run_input.py`、`dayu/host/compact_material.py`、`dayu/host/compact_pipeline.py` 到同一 projection helper。
- 新增 `tests/host/test_accepted_result_projection.py`，并更新 Tool Trace、memory、compact material、RunInputBuilder 相关测试断言。
- 更新 `dayu/host/README.md` 与 `tests/README.md`，记录已实现的 Host accepted result projection 稳定边界与测试覆盖事实。

## Consumer Migration Checklist

- Tool Trace：`TOOL_RESULT_ACCEPTED` summary 通过 projection helper 取得 query/status/result/source；仅保留 display-only 参数摘要，不再自行读取 request atom。
- Read API：canonical `TOOL_RESULT_ACCEPTED` activity 通过 projection helper 取得 typed 状态与展示文本；PREVIEW path 仍只消费 preview payload，不 fallback 到 canonical projection。
- Durable Memory：accepted evidence payload view 通过 projection helper 得到 tool/query/result/source 字段；durable memory consumer 不再自行 join request atom。
- Conversation Memory：selected evidence 优先消费 durable memory 传入的 projection 字段；旧 payload fallback 仅用于无 projection 字段的降级输入。
- RunInputBuilder：accepted evidence 与 wait resume 通过 projection helper 取得 LLM-safe query/status/source/arguments，digest mismatch 或 request identity mismatch 降级为有限语义输入。
- CompactMaterial / compact pipeline：accepted raw evidence block 的 readable query/source/result 由 projection helper 统一生成，pipeline 只搬运已清洗字段。

## Propagation Audit

- 产生路径：Engine ingest / ToolRuntime accept barrier 写入 accepted tool result canonical fact、payload digest 与 tool-call request atom。
- 持久化路径：EventLog row、payload store 与 request atom 表保持原 schema；accepted result projection 在读取时校验 digest 与 identity。
- 审计与诊断路径：Tool Trace hot summary / cold JSONL 读取 projection 后输出 query/status/result/source；大参数仍只做有界 display-only 摘要。
- Memory 路径：durable memory projection 保存 projection-cleaned evidence 字段，Conversation Memory 从同一字段渲染 LLM-readable evidence。
- Compact 路径：compact material 将 projection-cleaned accepted evidence 放入 evidence material；compact pipeline 不再自行过滤 internal source refs。
- LLM 输入路径：RunInputBuilder 在普通上下文与 wait resume 中使用同一 projection helper；敏感参数、路径参数、缺失或 mismatch request atom 均不会展开给 LLM。
- 用户可见读取路径：Read API canonical activity 使用同一 status/query/result/source 投影；PREVIEW activity 保持 preview-only 语义。

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_accepted_result_projection.py`：4 passed。
- `source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py`：46 passed。
- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_host_activity_event_projection.py`：220 passed。
- `source .venv/bin/activate && rg -n "_readable_query_text_from_envelope|_tool_result_query_text|_tool_result_status|def _llm_facing_evidence_source_text|_is_internal_evidence_source_part|_readable_source_text_from_refs|source_note|tool_call_request_atoms" dayu/host`：仅剩 schema 字段 `source_note`、projection owner 对 `tool_call_request_atoms` 的读取、以及 payload primitive 定义/导出；未发现下游消费者继续重建旧语义。
- `source .venv/bin/activate && pyright`：0 errors。
- `git diff --check`：通过。

## README / Design Decisions

- `dayu/host/README.md` 已按触发规则补充当前实现的 accepted result projection 边界。
- `tests/README.md` 已按触发规则补充新增测试与 Host 测试覆盖事实。
- `docs/host/design.md` 与 `docs/engine/design.md` 未修改；本次没有改变 Host/Engine 分层设计或 durable schema，只是在 Host 内部收敛 accepted result 投影 owner。

## Residual Risks

- Conversation Memory 中保留了无 projection 字段时的旧 payload fallback，作为历史输入降级路径；新 durable projection 路径已经优先消费 typed projection 字段。
- `source_note` 仍作为 compact schema 字段名存在，但其值由 accepted result projection 清洗后写入；该 grep 命中不是 source 过滤逻辑残留。
- 工作区中 `docs/host/issues-implementation-control.md` 在本次开始前已有未提交修改，本实现未触碰该控制文档。
