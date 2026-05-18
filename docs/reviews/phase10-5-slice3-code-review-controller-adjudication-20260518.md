# P10.5 Slice 3 Code Review Controller Adjudication

## Gate

当前 gate：P10.5 Slice 3 code review adjudication。

## Inputs

- Implementation artifact: `docs/reviews/phase10-5-slice3-implementation-codex-20260518.md`
- MiMo code review: `docs/reviews/phase10-5-slice3-code-review-mimo-20260518.md`
- DS code review: `docs/reviews/phase10-5-slice3-code-review-ds-20260518.md`
- Approved plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`

## Verdict

MiMo 与 DS 均为 PASS，blocking count = 0。Slice 3 implementation 满足主目标：typed `SubmitFollowupRequest`、per-run
effective config field-level partial merge、`tool_names` semantics、EventLog payload freeze、dispatch 读取冻结视图、`command_watermark`
和 focused tests 均已落地，且未改 durable schema / state machine。

总控裁决：进入 Slice 3 fix gate。原因是部分 non-blocking finding 直接触碰本项目编码约束或低成本测试完整性，应在当前 slice 内收口，
避免把重复序列化逻辑和测试缺口带入后续 slices。

## Accepted For Fix

### F1. Extract duplicated runner / provider request projection logic

来源：MiMo F1、DS N1。

裁决：accepted for current Slice 3 fix。

理由：`admission.py`、`command.py`、`dispatch.py` 三处维护同一 runner config / provider request JSON 映射，违反项目“重复逻辑必须抽取”
硬约束。Fix 应在 `dayu/host/` 下新增或使用模块级私有 helper，统一序列化 / 反序列化 / digest projection；不得引入 public API、
不得改变 EventLog payload shape、semantic digest 或 dispatch behavior。

### F2. Add focused `agent_policy` override coverage

来源：MiMo F4。

裁决：accepted for current Slice 3 fix。

理由：plan 明确要求 `runner_spec` / `runner_options` / `agent_policy` 三个字段独立 partial merge。当前 tests 间接覆盖
`agent_policy` fallback，但没有单独覆盖 override。补一个 focused test 可防止三字段逻辑未来分叉。

### F3. Add baseline-none fail-early test or explicit residual owner

来源：DS N4。

裁决：accepted for current Slice 3 fix if feasible; otherwise fix artifact must explain why the existing low-level command-handle scope cannot
exercise it without exceeding allowed boundaries。

理由：Slice 3 新增 `submit_followup` 对 opener ordinary baseline 的依赖。若低层 `create_host_command_handle` 路径缺少 baseline，
fail-early 是刻意边界，应该有测试或明确 residual owner，避免后续误判为 regression。

## Accepted As Residual / No Fix Required

### R1. EventLog payload `system_prompt` / display text coexistence

来源：MiMo F2。

裁决：no fix。

理由：`system_prompt` 与 user prompt display text 是不同语义字段，不是同一值双写。保留 `display_text` 维持当前用户输入 fact 可读性，
`system_prompt` 独立服务 RunInputBuilder，当前不构成重复 truth。

### R2. `FollowupSnapshot` validation exclusion style

来源：MiMo F3、DS N3。

裁决：no fix。

理由：queue idempotency 可能返回已推进后的状态；显式排除 `RECOVERING` 与 P10.5 scope 一致。后续若 public status matrix 收紧，可由
Slice 5 / aggregate review 再评估。

### R3. ToolRuntime defense-in-depth `ValueError`

来源：DS N2。

裁决：no fix。

理由：admission 已在 canonical facts 前返回 structured `HostApiError`；ToolRuntime 分支只防御损坏 / bypassed payload，不是 Service-facing
API 错误面。

## Fix Requirements

Fix agent 只允许修改 Slice 3 范围内相关实现 / focused tests / fix artifact：

- `dayu/host/admission.py`
- `dayu/host/command.py`
- `dayu/host/dispatch.py`
- new internal helper under `dayu/host/` if needed
- `tests/host/test_effective_execution_config.py`
- existing focused tests only if projection helper extraction requires import path updates
- `docs/reviews/phase10-5-slice3-fix-codex-20260518.md`

必须保持：

- 无 public API 变化；
- 无 durable schema / state-machine 变化；
- EventLog payload shape、semantic digest、dispatch `AgentRunRequest` behavior 与当前 Slice 3 implementation 等价；
- pyright 0 errors。

必须运行：

- `source .venv/bin/activate && pytest tests/host/test_submit_followup_public_contract.py tests/host/test_per_run_tool_selection.py tests/host/test_effective_execution_config.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`

## Next Gate

P10.5 Slice 3 fix。
