# P10.5 Slice 2 Code Review Controller Adjudication

## Gate

当前 gate：P10.5 Slice 2 code review adjudication。

## Inputs

- Approved plan: `docs/host/phase10-5-ordinary-local-multiturn-public-contract-plan.md`
- Implementation artifact: `docs/reviews/phase10-5-slice2-implementation-codex-20260518.md`
- MiMo code review: `docs/reviews/phase10-5-slice2-code-review-mimo-20260518.md`
- DS code review: `docs/reviews/phase10-5-slice2-code-review-ds-20260518.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`

## Verdict

MiMo 与 DS 均为 PASS，blocking count = 0。Slice 2 implementation 未越界到 Slice 3/4/5/6，且已验证 focused tests 与 pyright。

总控裁决：进入 Slice 2 fix gate。虽然 review 没有 blocking finding，但 DS N1 暴露的是 opener close 清理链路的直接资源释放风险，
属于 Slice 2 lifecycle root cause，不应推迟到 Phase 11；DS N2 / MiMo N3 暴露 `context_budget_policy=None` fallback 的契约清晰度不足，
应在不改变 public API 的前提下收口为显式代码 / docstring 语义。

## Accepted For Fix

### F1. `_PublicHostHandle.close()` must close durable resources even if scheduler close raises

来源：DS N1。

裁决：accepted for current Slice 2 fix。

理由：`open_host(options)` 的 lifecycle 是 Slice 2 的核心交付物。若 `scheduler.close()` 抛异常后跳过 `command_handle.close()`，
调用方会看到 handle 已关闭但 durable store 连接仍泄露，这违反 `docs/host/design.md` 中 opener close 最后关闭 durable resources 的
设计语义。修复应使用 `try/finally` 保证 projection flush 与 command handle close 尽力执行；不得写 cancel / failed terminal facts。

### F2. Make context budget fallback explicit

来源：MiMo N3、DS N2。

裁决：accepted for narrow clarification fix。

理由：`context_budget_policy=None` 时使用 fallback 不应是隐式魔法行为。当前不改变 `OpenHostOptions` public shape，不把默认值提升为新的
public API；但必须在 constants、helper docstring 或 `OpenHostOptions` / mapping 注释中写明：fallback 只用于构造当前内部
`HostCommandHandleOptions`，调用方若需要生产级预算必须传入显式 `ContextBudgetPolicy`。不得从 Engine、extra payload 或 profile
lookup 推导预算。

## Deferred / Accepted Residual

- MiMo N1: `HostLocalExecutionOptions` 构造冗余。若 F1 / F2 fix 触及同一 helper，可顺手消除；否则不要求当前修。
- MiMo N2 / DS O1: 跨模块私有 mapper import。当前复用唯一规范映射优于复制逻辑，后续 internal helper cleanup 可处理。
- MiMo N4: close docstring 粒度较粗。F1 fix 若修改 close，可同步细化；否则不阻塞。
- MiMo N5: `watch_session_events` placeholder。Slice 4 owner。
- MiMo N6: 测试轮询等待。当前 focused tests 可接受，若后续 flaky 再处理。
- DS O2: `_MemoryProjectionCatchupPort` 持有完整 `OpenHostOptions`。内部实现细节，暂不阻塞。
- DS O3: 测试直读 SQLite。Slice 4/Slice 6 public event path owner。

## Fix Requirements

Fix agent 只允许修改 Slice 2 文件范围内的实现 / focused tests / implementation artifact：

- `dayu/host/open_host.py`
- `dayu/host/api.py` only if needed for docstring clarification
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_public_lifecycle_smoke.py`
- `docs/reviews/phase10-5-slice2-fix-codex-20260518.md`

必须运行：

- `source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py tests/host/test_public_lifecycle_smoke.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`

## Next Gate

P10.5 Slice 2 fix。
