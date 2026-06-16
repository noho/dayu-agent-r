# WU-CLI-FINS-OBS-01 Plan Review Fix

## Scope

- work unit：`WU-CLI-FINS-OBS-01`
- gate：fix after plan review
- fixed plan artifact：`docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`
- source adjudication：`docs/reviews/wu-cli-fins-obs-01-plan-review-adjudication-20260615-180440.md`
- execution constraint：只修 plan artifact，不做 implementation、review、commit、push、PR 或控制文档修改。

## Reviewed Findings Fixed List

- DS-001 / MiMo-001：已修复。S2 改为当前 work unit 采用低风险 runtime-owned coarse progress；不修改 adapter protocol；不要求同步 adapter 消费 async pipeline stream。细粒度 async pipeline stream consumption deferred 到后续 work unit，除非 implementation 证明无需协议变更且可安全复用已有同步桥接。
- DS-002 / MiMo-002：已修复。删除 mandatory `event_sink` adapter/runner protocol change；plan 明确本轮不修改 `FinsSourceDownloadAdapter.download(...)` 与 `FinsUploadRunner.run_upload(...)` 签名。
- DS-003 / MiMo-003：已修复。progress/observation event append failure 改为 bounded WARN + continue；terminal job record 仍是真源；terminal event append failure 也 WARN 并允许 Service terminal fallback。
- MiMo-004：已修复。event sidecar append/read sequence allocation 明确使用 `FsFinsIngestionJobStore` 同一 runtime file lock，除非 implementation 以并发测试证明更窄 lock 安全。
- DS-004 / MiMo-005：已修复。`stream_job_events_until_terminal` 明确复用 `FinsDirectCommandService.poll_interval_seconds`，empty read 后 sleep，测试要求 no tight loop。
- DS-005 / MiMo-006：已修复。S5 明确 `dayu/cli/main.py` 调用已有 `dayu.runtime.log.set_level_from_flags(...)`，不手写 log-level precedence 映射。
- DS-006 / MiMo-007：已修复。Service synthesized terminal fallback 必须记录 bounded WARN。
- MiMo-008：已修复。plan 明确 status transition events 与 observation/progress events 语义区别；单 enum 可接受，但必须用 docstring/helper 分类。

## Plan Sections Changed

- Goal / Motivation / Success Signal：把 root cause 从 adapter 丢失 pipeline live events 收敛为 runtime 没有 Service/CLI progress observation。
- First-principles Judgment and Direct Code Evidence：明确当前 work unit 不强行改造同步 adapter 消费 async pipeline stream。
- Affected Files / Modules：移除默认修改 pipeline implementation/tests 的要求，仅保留安全复用同步桥接时的例外。
- Contract / Schema / State-machine / Public-interface Changes：删除 mandatory adapter protocol changes，补充 event type 语义、sidecar lock、deferred async stream consumption。
- Implementation Decisions：改为 runtime-owned coarse progress；日志装配改为复用 `set_level_from_flags`。
- Small Implementation Slices S1-S5：同步更新锁、失败传播、runtime progress、poll interval、WARN fallback、CLI logging helper 和测试断言。
- Tests / Validation Commands and Expected Assertions：移除默认 pipeline stream tests，增加 no tight loop、bounded WARN、同锁 sequence、helper 调用等断言。
- Risks / Open Questions / Residual Risk Owner：将细粒度 stream consumption、progress gap、poll interval 等风险分配到当前或后续 owner。
- Plan Status：更新为 `ready after fix`。

## Decisions After Fix

- 当前 work unit 不改 `FinsSourceDownloadAdapter` / `FinsUploadRunner` protocol。
- 当前 work unit 不改 `FinsIngestionThreadExecutor` threading model，不引入 event loop ownership 变更。
- `FinsIngestionRuntime` 是 progress event 产生 owner；Service 是事件消费和投影 owner；CLI 是 UI renderer。
- progress / observation event 是 UI/observability signal，不是业务 terminal truth；写入失败只 WARN，不影响业务终态。
- terminal job record 是业务状态真源；terminal event append failure 只 WARN，Service 可以合成 terminal event 防止 UI 悬挂。
- sidecar event sequence allocation 使用 `FsFinsIngestionJobStore` 同一 runtime file lock。
- `stream_job_events_until_terminal` 复用 `poll_interval_seconds`，empty read 后 sleep。
- `dayu/cli/main.py` 复用 `dayu.runtime.log.set_level_from_flags(...)`。

## Validation Performed

- 静态核对 controller adjudication 的 8 个 accepted findings，确认 plan 中均有对应修复点。
- 静态 grep 检查 mandatory `event_sink`、手写 log-level 映射、progress write failure 导致 job failed 等旧表述；剩余 `event_sink` 仅用于“本轮不修改协议”的否定说明。
- 静态分段读取 S1-S5，确认切片结构完整，未进入 implementation。
- 未运行测试、pyright 或 review；本 gate 明确只修 plan artifact。

## Residual Risks / Deferred Owners

- 细粒度 async pipeline stream consumption deferred 到后续 Fins pipeline live-event refinement work unit；当前 owner 仅负责 runtime-owned coarse progress。
- `.events.jsonl` retention / compaction deferred 到后续 Fins job storage retention work unit。
- prompt / interactive token/content streaming deferred 到后续 Agent command streaming/UI work unit。
- progress event write failure 造成 UI progress gap 的风险由当前 S1/S2 用 bounded WARN、terminal job record truth 和 Service terminal fallback 收口。
- poll interval 行为由当前 S3 用 `poll_interval_seconds` 和 no-tight-loop 测试收口。

## Files Changed

- `docs/host/wu-cli-fins-obs-01-fins-direct-live-events-plan.md`
- `docs/reviews/wu-cli-fins-obs-01-plan-review-fix-codex.md`

## Completion Status

`ready`

Blocking open questions：无。所有 accepted findings 都已通过 plan 修订收敛，未发现需要停止为 blocked 的问题。
