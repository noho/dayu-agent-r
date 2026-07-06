# WU-CLI-SMOKE-01 / MANUAL-F01 修复验证记录

## 结论

MANUAL-F01 动机成立，严重性为高。问题不在 SEC / Fins 外部下载服务：direct `dayu-cli download --ticker V` 能进入下载进度，而 Agent 路径在 Host awaiting accept durable boundary 前失败，导致 `start_fins_download` 无法把长事务工具调用持久化为 `WAITING`。

修复后，真实 `dayu-cli prompt "下载Visa财报"` 等价 Agent 路径已经观察到 `start_fins_download` 进入 `TOOL_AWAITING` / `RUN_WAITING` / `ATTEMPT_SUSPENDED`，并在 `host_wait_records` 中写入完整 snapshot ref 与 snapshot digest；未再出现原来的 `HostDurableError` / failed tool result。

## Root Cause

直接日志证据来自 `workspace/tmp/wu-cli-smoke-01-manual/interactive.log`：

- Engine 请求工具：`engine.agent.tool_call_requested ... tool_name=start_fins_download`。
- Host 进入 awaiting accept：`host.waiting.accept_tool_awaiting.accepted ... adapter_key=poll:fins-ingestion`。
- 随后 Engine 接收 failed tool result：`engine.agent.tool_result_accepted ... outcome=failed`。
- 同一 run 没有 durable `TOOL_AWAITING` / `RUN_WAITING` / `ATTEMPT_SUSPENDED` 事实，`host_wait_records` 计数为 0。

直接异常探针复现到同一 durable 边界：

```text
HostDurableError: CHECK constraint failed:
(snapshot_ref IS NULL AND snapshot_captured_at IS NULL AND snapshot_digest IS NULL)
OR
(snapshot_ref IS NOT NULL AND snapshot_captured_at IS NOT NULL AND snapshot_digest IS NOT NULL)
```

代码根因为 `dayu.host.tool_runtime._wait_snapshot_ref(...)` 把 Engine 的 `ToolAwaitSnapshot(snapshot_id, captured_at)` 转成 Host `WaitSnapshotRef` 时把 `snapshot_digest` 写成 `None`。Fins awaiting 工具会为 observation start 生成 snapshot，因此 Host insert `host_wait_records` 时形成 `snapshot_ref` / `snapshot_captured_at` 非空而 `snapshot_digest` 为空，违反 durable schema 的三字段同存同缺约束。

Engine 把 ToolExecutor 抛出的 `HostDurableError` 归一成 failed tool result，所以用户看到的是工具路径失败；这不是外部下载服务失败。

## 改动

- `dayu/host/tool_runtime.py`
  - `_wait_snapshot_ref(...)` 现在为 awaiting snapshot 生成完整 `WaitSnapshotRef`。
  - 新增 `_wait_snapshot_digest(...)`，使用 Host durable `format_utc_timestamp(...)` 与 `sha256_digest_json(...)` 对 `snapshot_id`、`captured_at` 计算稳定 digest。
  - 未改动 Fins download / ingestion 业务逻辑，未绕过 Host accept barrier，未改变 Engine 公共 awaiting contract。

- `dayu/host/durable/state.py`
  - `WaitSnapshotRef.snapshot_digest` 收紧为必填 Host durable sha256 digest。
  - `deserialize_wait_snapshot_ref(...)` 在 Python row codec 层拒绝缺失 digest 的不完整 snapshot ref，避免同类错误推迟到 SQLite CHECK 才暴露。

- `tests/host/test_toolruntime_executor.py`
  - 扩展 `_AwaitingCallable` 支持携带 `ToolAwaitSnapshot`。
  - 新增测试确认 ToolRuntime 从 Engine snapshot 派生出可落库的完整 snapshot ref。

- `tests/host/test_wait_awaiting_accept.py`
  - 新增测试确认 `DefaultHostToolAwaitingAcceptPort` 能把完整 snapshot ref 真实写入 `host_wait_records`。

- `tests/host/test_wait_record_state.py`
  - 新增测试确认 `WaitSnapshotRef` 构造和三列反序列化都会拒绝缺失或无效 digest。

## 真实环境验证

命令：

```bash
source .venv/bin/activate
dayu-cli --workspace workspace --log-level debug \
  --log-file workspace/tmp/wu-cli-smoke-01-manual-validation/prompt-download-visa-after.log \
  prompt --label codex-manual-f01-after "下载Visa财报"
```

关键日志：

```text
host.waiting.accept_tool_awaiting.committed ... tool_name=start_fins_download ... wait_id=wait-66ad...
engine.agent.tool_awaiting ... tool_name=start_fins_download ... await_kind=external_job
engine.agent.terminal ... terminal_type=run_suspended
```

负向搜索：

```bash
rg -n "HostDurableError|tool_result_accepted.*failed|failed_count=1|tool_executor_exception" \
  workspace/tmp/wu-cli-smoke-01-manual-validation/prompt-download-visa-after.log
```

结果：无匹配。

DB 证据：

```text
wait-66ad...|cancelled|start_fins_download|fins-observation-start-download-20260706T111426607364Z|2026-07-06T11:14:26.607364Z|sha256:d04fbc2969f6c9306d9510572527fce0d56cd93c21935d1b3d8d4d197a38e6a1|finsobs_68be0ffd8a744a8da3ca44e1ab467683
```

说明：该记录曾成功进入 waiting，包含完整 snapshot ref / captured_at / digest。验证期间真实 SEC 下载继续运行；为避免外部下载耗时阻塞，已在收集到 committed/waiting 证据后发送 SIGINT，wait record 随后被标记为 `cancelled`。

## 自动化验证

```bash
source .venv/bin/activate
pytest tests/host/test_toolruntime_executor.py::test_awaiting_outcome_with_snapshot_builds_complete_wait_snapshot_ref \
  tests/host/test_wait_awaiting_accept.py::test_awaiting_accept_persists_complete_snapshot_ref
```

结果：2 passed。

```bash
source .venv/bin/activate
pytest tests/host/test_toolruntime_executor.py tests/host/test_wait_awaiting_accept.py
```

结果：68 passed。

```bash
source .venv/bin/activate
pytest tests/host/test_wait_record_state.py tests/host/test_toolruntime_executor.py tests/host/test_wait_awaiting_accept.py
```

结果：94 passed。

```bash
source .venv/bin/activate
pyright
```

结果：0 errors, 0 warnings, 0 informations。

```bash
git diff --check
```

结果：通过，无输出。

## README 检查

- `dayu/host/README.md` 已按触发规则检查。此次变更不改变 Host public API、状态机、扩展点或开发者稳定边界，只是补齐内部 durable snapshot ref digest 和 row codec 不变量，不更新。
- `tests/README.md` 已按触发规则检查。此次只在既有 Host 测试分层内增加回归测试，不新增测试层级或运行方式，不更新。

## 残余风险

- 真实 CLI 验证在确认 Host awaiting durable 边界修复后被 SIGINT 中止，因此没有等待 Visa 全量外部下载完成；这是外部 job 耗时风险，不是本次 HostDurableError 根因。
- 本次 digest 内容只覆盖 Engine 公共 snapshot 引用中的 `snapshot_id` 与 `captured_at`。这符合当前 `ToolAwaitSnapshot` contract；如果未来 snapshot contract 扩展可检索内容，需要同步评估 digest 输入是否应扩展。
