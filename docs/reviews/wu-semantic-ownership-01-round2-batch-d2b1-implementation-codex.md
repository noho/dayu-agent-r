# WU-SEMANTIC-OWNERSHIP-01 / Round2 Batch D2b1 Implementation

## Scope

- 本轮只处理 `144159-05`：cancelled accepted tool outcome 在普通 ToolRuntime 与 wait resolution 路径的 canonical atom/codec 分叉。
- 未处理 compaction `evidence_kind`、memory fallback、reactive compact、Engine fallback 或 D2a terminal/start contract。
- 未 commit，未 push，未修改 unrelated files。

## Changed Files

- `dayu/host/accepted_tool_outcome.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/durable/wait_resolution_digest.py`
- `dayu/host/waiting.py`
- `dayu/host/run_input.py`
- `tests/host/test_accepted_tool_outcome_codec.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_run_input_builder.py`

## Semantic Owner Decisions

- 新增 `dayu.host.accepted_tool_outcome` 作为 Host accepted tool outcome canonical atom owner，覆盖 completed / failed / cancelled。
- 普通 ToolRuntime 的 accepted `raw_tool_outcome`、`outcome_digest` 和 inline size 估算改为复用同一 codec。
- wait resolution payload plan 不再自行序列化 completed / failed / cancelled result body；它只保留 wait envelope 元数据、payload/provider refs，并把 accepted atom 原样写入 `result` 与 `raw_tool_outcome`。
- wait resolution digest material 的 completed / failed / cancelled 部分改为携带 `tool_outcome` canonical atom，wait-specific `payload_ref` 仍留在 envelope 外层。
- RunInput resume 消费 `raw_tool_outcome` canonical atom；cancelled 不再读取 wait-only nested `result.result` shape。
- 测试 fixture 按全新 schema 起库迁移：wait resume 事件始终携带 canonical `raw_tool_outcome`，不保留旧 shape 兼容读取。

## Validation

- `source .venv/bin/activate && pytest -q tests/host/test_accepted_tool_outcome_codec.py tests/host/test_toolruntime_executor.py tests/host/test_resolve_wait_command.py tests/host/test_run_input_builder.py`
  - 结果：`179 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。
- 额外检查：
  - 搜索 `resolve_wait_(completed|failed|cancelled)_result_json`、`_tool_cancelled_json`、旧 `resume wait result body` 等残留旧 serializer/consumer 关键字，无命中。

## README Decision

- 已阅读 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】` 与 `tests/README.md` 的 `README 更新边界`。
- 本轮改动没有改变 Host public API、开发手册中的稳定架构边界、测试目录层级、测试运行方式或测试维护规则。
- 因此不更新 README。

## Residual Risks

- 未跑全量 pytest；本轮验证覆盖受影响 Host tests、owner codec parity、direct resolve wait resume continuity、RunInput canonical consumer、全量 pyright 与 diff whitespace。
- `resolve_wait_outcome_json` 的 digest envelope 字段从 wait-local `result` 改为 `tool_outcome`，本轮按“全新 schema 起库”处理，未提供旧 digest shape 兼容。

## Stop Status

COMPLETE
