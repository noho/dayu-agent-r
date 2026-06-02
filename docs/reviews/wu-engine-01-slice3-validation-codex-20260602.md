# WU-ENGINE-01 Slice 3 Validation Report

## Gate / Role / Scope

- Gate: `implementation`。
- Work unit: `WU-ENGINE-01 Runner diagnostic payload audit`。
- Slice: `Slice 3 Full Validation / Docs Sync`。
- Approved plan: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`。
- Role: implementation / validation worker；不是 controller。
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`。
- Accepted slice commits observed in local history: `dba6513` / `748b743` for Slice 1, `3857e23` / `08fd353` for Slice 2。

## Motivation Check

本 slice 的动机成立。Slice 1 / Slice 2 已改变 OpenAI-compatible runner diagnostic `raw_payload` 的稳定语义：该字段不再承诺 provider 原始 JSON 精确保留，而是有界、脱敏、摘要化的诊断 JSON。Slice 3 只需要验证受影响边界和 README 同步，不需要新增功能、Host production 变更或 schema 变更。

## Changed Files

- `docs/reviews/wu-engine-01-slice3-validation-codex-20260602.md`

未修改 `dayu/engine/README.md`。未修改 Host production。未修改 schema。

## README / Docs Decision

结论：不需要继续修改 README。

直接证据：

- `dayu/engine/README.md:190` 已说明 `raw_payload` 是 Runner / Provider 诊断事件上的可选诊断 JSON，并明确“有界、脱敏、摘要化”，且“不保证保留 provider 原始 payload”。该说明属于 Engine 开发手册的公共契约层级，不写过程状态、未来计划或 helper 实现细节。
- `dayu/engine/contracts/runner_events.py` 中 `RunnerProtocolErrorData.raw_payload` 与 `RunnerHTTPErrorData.raw_payload` docstring 均说明有界诊断载荷，并明确不承诺保留 provider 原始报错载荷。
- `dayu/engine/contracts/engine_events.py` 中 `ProviderProtocolErrorData.raw_payload` docstring 同步为有界诊断载荷语义。
- `rg` 检查未发现 `dayu/engine/README.md` 中存在旧的 `raw_payload` 原始载荷承诺。

其它 README 决策：

- 根目录 `README.md`：未发现项目级使用方式、CLI、trace/render 入口或用户手册职责内的行为变化；不更新。
- `dayu/host/README.md`：Host production 行为、Host 状态机和 durable schema 未变；现有 diagnostic 说明仍属 Host EventLog / Context Governance 范围；不更新。
- `tests/README.md`：OpenAI runner 测试目录说明已经覆盖协议错误、HTTP error、非法 UTF-8、SSE 与 non-stream 边界；本 slice 没有改变测试分层或维护约定；不更新。

未发现需要 design_doc 或 public contract 重新裁决的 README/doc mismatch。

## Boundary Audit

执行的边界检查：

- `git status --short`：起始 worktree 为空。
- `git log --oneline -n 12`：确认本地历史包含 Slice 1 / Slice 2 accepted commits 与 record commits。
- `rg -n "raw_payload\\s*=\\s*dict\\(|raw_payload=dict\\(|raw_payload.*parsed|原始载荷|provider 原始|完整 provider|完整 prompt|provider payload" dayu/engine tests/engine tests/host dayu/engine/README.md`。

结果：

- 未发现 `raw_payload=dict(parsed)` 或 `raw_payload = dict(parsed)` 残留。
- OpenAI-compatible runner 的 provider error、protocol object、invalid UTF-8、HTTP JSON error body 均通过 `dayu/engine/runners/openai/diagnostic_payload.py` helper 写入诊断 payload。
- 搜索命中的“provider 原始报错载荷”均处在“不承诺保留”语义中，不是旧承诺残留。

## Validation Commands / Results

命令：

```bash
source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_engine_ingest_mapping.py
```

结果：

```text
95 passed in 0.56s
```

命令：

```bash
source .venv/bin/activate && pyright
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

备注：pyright 输出包含版本提示 `v1.1.409 -> v1.1.410`，不是类型错误或 warning 诊断。

## Residual Risks / Uncovered Areas

- 未运行全仓 pytest；本 slice 按 approved plan 运行指定 full target validation。
- 未执行真实 provider 网络 smoke；本 work unit 目标是 diagnostic payload 语义与边界验证，真实 provider 可用性不属于当前 slice。
- 未做 aggregate deepreview；该动作属于 controller 后续 gate，不由本 worker 进入。

## Stop Condition Status

- README/doc mismatch requiring design_doc or public contract re-decision: not triggered。
- Full target validation failure: not triggered。
- pyright existing error or new / expanded error: not triggered。
- Need to change Host production or schema: not triggered。
- Blocking open questions: none。

## Recommendation For Next Gate

建议 controller 进入 WU-ENGINE-01 的 Slice 3 code review / validation artifact review gate。若 review 通过，可由 controller 按 Gateflow 状态推进到 accepted Slice 3 checkpoint；不要由本 worker commit、push、创建 PR 或进入 aggregate deepreview。
