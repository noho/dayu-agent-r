# WU-CLI-CONFORMANCE-F01-F07 S4/F04 Code Review — Controller Adjudication

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Slice：`S4 / F04`
- Gate：`code review -> controller adjudication`
- Entry HEAD：`25400fba`
- Review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-ds.md`
- 状态：`FIX REQUIRED — attachment close failure state需收敛，无 blocking open question`

## Finding 逐项裁决

| 来源 / finding | 裁决 | 理由与 required action |
|---|---|---|
| MiMo-1 / DS-3：`close()`失败后可再次close，违背“一次/幂等” | `accepted` | Controller拥有本地attachment生命周期引用，不能在底层close抛错后继续把同一对象视为可安全重试。调用close前先把controller标记terminal、移除current，再shield调用底层close；异常原样传播。后续`close()`必须no-op，保证exactly-once close attempt。补失败测试。 |
| MiMo-2 / DS-1：refresh close失败后stale current导致outer double-close | `accepted` | Plan要求旧attachment完整close后才fresh open，且不得double-close。调用refresh close前先把`current=None`；close失败则保留`refresh_required=True`、不open fresh、异常传播并终止当前mutation；outer final close因current为空不重试。若调用方显式继续同controller，下一次mutation只fresh open，不再次close旧对象。补close失败/下一次fresh open测试。 |
| MiMo-3：close/refresh failure测试缺口 | `accepted` | 与上两项同一root cause，必须用owner test锁定exactly-once attempt、state、exception与open偏序。 |
| DS-2：typed enum使用`is` | `rejected-with-reason` | `HostSessionMutationErrorDetail.reason`和`actual_mode`是typed enum contract；CLI只能接受typed owner输出。改为StrEnum `==`会把裸字符串也视为合法，形成用户明令禁止的loose parsing。任何wire反序列化必须在Host API/schema boundary恢复typed enum或失败，不能由CLI下游补偿。增加裸字符串无法通过typed判据的对抗test即可，但不得改为值兼容。 |
| MiMo residual：queued + READ_ONLY无独立test | `rejected-as-required-fix` | 两路代码走读均证明mutation等待阶段不读取composer，RO在acceptance前不会进入queued/active slot；现有accepted-only barrier测试已覆盖owner contract。未来driver改为后台常读时由未来变更owner重评，不扩张本slice。 |
| S8 real two-process/PTy risk | `classified` | 由已批准S8真实并发CLI evidence收敛。 |

## Required fix contract

AgentCodex 只在S4 allowlist内：

1. `close()`：在任何await前原子地设置`_closed=True`并take-and-clear `current`；底层close异常原样传播；第二次调用no-op。
2. `attachment_for_mutation()` refresh：take-and-clear旧`current`后shield close；close成功才`open_fresh()`；close失败不open、`refresh_required`保持true、异常传播。下一次显式mutation可fresh open，不再close旧对象。
3. Open fresh失败时`current`保持None、`refresh_required`保持true、异常传播；下一次显式mutation可再次fresh open。不得后台重试或吞错。
4. Tests锁定close attempt count、state、exception、no double-close、no premature open与下一次fresh open；typed enum继续identity匹配，并可加入裸字符串不被下游兼容接受的test。
5. 新增`docs/reviews/wu-cli-conformance-f01-f07-s4-fix-codex.md`，运行focused/coverage/full pyright/diff/hash；不stage/commit/push。

修复后进入两路re-review。没有unclassified residual risk或blocking open question。

## Artifact path

`docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-controller-adjudication.md`
