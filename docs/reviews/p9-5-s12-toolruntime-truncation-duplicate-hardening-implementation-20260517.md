# P9.5 S12 ToolRuntime Truncation / Duplicate Hardening Implementation

## 动机判断

S12 动机成立，但不是需要重做 ToolRuntime 语义。直接证据显示现有实现已经有 run-scoped truncation / `fetch_more`、普通工具路径、duplicate governance matrix 与 reuse accept barrier；真实缺口是 focused coverage 不完整，以及 `ToolFactAcceptCandidate` 对 duplicate governed outcome 的字段组合防御偏宽。

未发现需要 durable cursor table、durable duplicate ledger、Host / Engine `fetch_more` 特化分支、duplicate policy 默认值变更或 public API / error taxonomy 变更的问题。

## 直接证据

- `tests/host/test_toolruntime_truncation_fetch_more.py` 已覆盖 `text_chars`、missing cursor、scope token mismatch、scope mismatch、TTL expired、single-use pop 后 missing cursor、remainder digest mismatch、limit prefix。
- 同文件缺少 `text_lines`、`list_items`、`binary_bytes`、显式 used cursor 与 invalid limit 测试。
- `tests/host/test_toolruntime_duplicate_governance.py` 已覆盖 `allow`、`reuse`、`hint`、`require_justification`、`hard_stop` 行为矩阵。
- `tests/host/test_toolruntime_accept_barrier.py` 已覆盖 reuse 只追加 `TOOL_CALL_REQUESTED` + `TOOL_CALL_GOVERNED`，不追加第二个 `TOOL_RESULT_ACCEPTED`。
- `dayu/host/tool_runtime.py` 中 `ToolFactAcceptCandidate.__post_init__` 原先对 `GOVERNED_ERROR` 只要求 `outcome_digest`，未校验 governed policy kind、duplicate prior refs、reason/message 与 duplicate decision 的一致性。
- 真实 scheduler build path `dayu/host/dispatch.py` 通过 `DefaultToolRuntimeFactory(...).create_tool_runtime(...)` 在 tool-enabled dispatch 构造 attempt-local ToolRuntime；`TruncationManager` 构造只保存 identity、截断声明视图和空 cursor dict，无文件、DB、后台任务或 durable cursor table 初始化。

## 修改文件

- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `dayu/host/README.md`
- `tests/README.md`

## 实现内容

- 收紧 `ToolFactAcceptCandidate` 构造期校验：
  - 普通 `COMPLETED` / `FAILED` / `CANCELLED` 结果事实必须携带 `ALLOW` policy。
  - `GOVERNED_ERROR` 不允许携带 `ALLOW` / `REUSE` policy。
  - duplicate governed outcome 的 policy kind、prior refs、reason_code、message 必须与 `HINT` / `REQUIRE_JUSTIFICATION` / `HARD_STOP` 决策一致。
  - `REUSE` fact 的 policy kind、reason_code、message 必须与 duplicate reuse 决策一致。
- 为 `TruncationManager` factory 构造路径添加注释，记录当前初始化成本判断：run-scoped 轻量对象，无生产规模修复需求。
- 补充 truncation focused tests：`text_lines`、`list_items`、`binary_bytes`、显式 used cursor、invalid limit。
- 补充 duplicate governed candidate validation tests：missing prior refs、policy kind mismatch、reason mismatch、message mismatch、`GOVERNED_ERROR` + `ALLOW` policy。
- 更新 README 中当前覆盖事实，不新增未来设计。

## 覆盖归功

- cursor missing：已有 `test_fetch_more_missing_cursor_returns_ordinary_tool_error`。
- scope token mismatch：已有 `test_fetch_more_rejects_token_mismatch`。
- scope mismatch：已有 `test_fetch_more_rejects_scope_mismatch`。
- digest mismatch：已有 `test_fetch_more_rejects_remainder_digest_mismatch`。
- expired cursor：已有 `test_fetch_more_rejects_ttl_expiry`。
- duplicate allow / reuse / hint / require_justification / hard_stop：已有 matrix tests，本轮只补 candidate 防御校验。
- reuse 不调用业务 callable：已有 duplicate reuse tests 覆盖。
- reuse 不追加第二个 `TOOL_RESULT_ACCEPTED`：已有 accept barrier test 覆盖。

## 验证

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py`
  - 结果：60 passed。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：0 errors, 0 warnings, 0 informations。
- `source .venv/bin/activate && pytest tests/host/test_toolruntime_*.py tests/host/test_phase6_toolruntime_integration.py -q`
  - 结果：67 passed。
- `git diff --check`
  - 结果：通过。

## 文档决策

`dayu/host/` 与 `tests/host/` 被触发，已更新 `dayu/host/README.md` 与 `tests/README.md` 中 ToolRuntime truncation / duplicate 当前事实描述。未更新根 README、Engine README 或其它包 README，因为本轮未改变项目级使用方式、Engine contract、配置入口或其它包职责。

## 残余风险

- truncation cursor 仍是内存、run-scoped、ToolRuntime-local capability，不支持 crash / restart / cross-run recovery；这是当前设计边界。
- duplicate registry 仍是同进程 run-local memory，不提供 durable duplicate ledger；crash / restart 后重复风险继续由 RunInputBuilder 回放 accepted facts 降低。
- `TruncationManager` 初始化未发现生产规模问题；若未来引入 durable cursor、外部缓存或后台清理任务，应重新归入 Phase 15 / 对应 owner。

## Stop Status

未触发 stop condition。实现未要求 cross-run cursor recovery、durable duplicate storage、duplicate policy default change、public API/error taxonomy change 或 business-specific rules。
