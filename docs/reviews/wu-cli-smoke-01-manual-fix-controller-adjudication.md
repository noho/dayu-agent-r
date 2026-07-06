# WU-CLI-SMOKE-01 / MANUAL-F01 Controller Adjudication

## 结论

MANUAL-F01 fix gate accepted。

用户发现的问题与代码 root cause 同源：Agent 工具路径 `start_fins_download` 在 Host awaiting accept 写入 `host_wait_records` 时生成了不完整 `WaitSnapshotRef`，`snapshot_ref` 与 `snapshot_captured_at` 非空而 `snapshot_digest` 为空，违反 durable schema 的三字段同存同缺 CHECK，最终被 Engine 归一为 failed tool result / `HostDurableError`。Direct `dayu-cli download --ticker V` 不经过 Host awaiting wait record，因此能正常进入 Fins progress。

## 已接受改动

- `dayu/host/tool_runtime.py`
  - `_wait_snapshot_ref(...)` 不再写入 `snapshot_digest=None`。
  - 新增 `_wait_snapshot_digest(...)`，由 Host 使用 `snapshot_id` 与 canonical UTC `captured_at` 派生 stable sha256 digest。

- `dayu/host/durable/state.py`
  - `WaitSnapshotRef.snapshot_digest` 收紧为必填 `str`。
  - `WaitSnapshotRef.__post_init__` 使用 `require_sha256_digest` 校验 digest。
  - `deserialize_wait_snapshot_ref(...)` 在 Python row codec 层拒绝缺失 digest 的不完整三列组合。

- 测试
  - `tests/host/test_toolruntime_executor.py` 覆盖 ToolRuntime 从 Engine snapshot 派生完整 Host wait snapshot ref。
  - `tests/host/test_wait_awaiting_accept.py` 覆盖 Host accept port 真实持久化完整 snapshot ref。
  - `tests/host/test_wait_record_state.py` 覆盖 digest 构造校验和三列反序列化 fail-fast。

## Review 裁决

- AgentMiMo implementation review：`docs/reviews/wu-cli-smoke-01-manual-fix-implementation-review-mimo.md`，verdict `pass`。
- AgentDS implementation review：`docs/reviews/wu-cli-smoke-01-manual-fix-implementation-review-ds.md`，verdict `pass`。

裁决：

- Required findings：无。
- MiMo F01 informational：测试 digest timestamp 与 `captured_at` 不同源。Controller 复核发现 `_NOW` 实际同值，但为降低维护歧义，已将测试 digest 输入改为 `format_utc_timestamp(_NOW)`，该 finding resolved。
- MiMo F02 / DS F-LOW-01：digest 输入范围只覆盖当前 `ToolAwaitSnapshot` contract 的 `snapshot_id` 与 `captured_at`。当前非 defect，作为 contract 演进 residual risk 保留：未来若 `ToolAwaitSnapshot` 扩展可持久化语义字段，需要重新评估 digest 输入。

## 验证

AgentCodex 真实验证：

- `dayu-cli --workspace workspace --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-manual-validation/prompt-download-visa-after.log prompt --label codex-manual-f01-after "下载Visa财报"`
- 日志出现 `host.waiting.accept_tool_awaiting.committed`、`engine.agent.tool_awaiting`、`terminal_type=run_suspended`。
- 负向搜索未再出现原始 `HostDurableError` / failed tool result。
- DB `host_wait_records` 有 `start_fins_download` wait row，包含完整 `snapshot_ref`、`snapshot_captured_at`、`snapshot_digest` 与 external job id。

Controller 复跑：

```bash
source .venv/bin/activate && pytest tests/host/test_wait_record_state.py tests/host/test_toolruntime_executor.py tests/host/test_wait_awaiting_accept.py
```

结果：94 passed。

```bash
source .venv/bin/activate && pyright
```

结果：0 errors, 0 warnings, 0 informations。

```bash
git diff --check
```

结果：通过，无输出。

## README 裁决

- `dayu/host/README.md`：无需更新。本次只补齐 Host 内部 durable snapshot digest 与 row codec invariant，不改变 Host public API、状态机、扩展点或开发者稳定边界。
- `tests/README.md`：无需更新。本次只在既有 Host 测试分层内增加回归测试，不新增测试层级、测试运行方式或测试维护规则。

## Residual Risk

- 真实 CLI 验证在确认 Host awaiting durable 边界修复后以 SIGINT 中止，没有等待 Visa 全量外部下载完成。这不影响 MANUAL-F01 root cause closure，因为本次问题发生在 awaiting durable accept 前。
- `ToolAwaitSnapshot` 未来如果新增持久化语义字段，需要重新评估 `_wait_snapshot_digest(...)` 的 digest 输入。
