# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 complete code re-review Controller 裁决

## 范围与真源

- 本裁决属于既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S2 complete cumulative code re-review，不是新 WU。
- 固定计划：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`。
- 上游 fix：`docs/reviews/wu-semantic-ownership-01-r12-s2-code-review-fix-codex.md`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-r12-s2-code-review-fix-controller-validation.md`。
- 双路复审：
  - `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r12-s2-code-rereview-ds.md`

## 已关闭 finding

`R12-S2-CR-F01..F03` 均已由两路复审确认主体关闭：POSIX/Windows 持久化中断携带脱敏 durable truth，plain/typed interrupt 都进入 workspace transaction abort，既有直接探针不再留下原先的 private transaction path。该 closure 不覆盖下述新故障组合。

## 新 finding 裁决

### R12-S2-RR-F01 — ACCEPTED / MEDIUM

DS 直接指出 `run_init_command` 的 typed persistence interrupt 分支先调用 `_report_persisted_environment_names`，后调用 `_abort_prepared_transaction_after_persistence_interrupt`。当 stderr 写入抛 `OSError` 时，prepared transaction 的 abort 未执行，异常语义从 `KeyboardInterrupt`/exit 130 漂移到普通失败/exit 1。

MiMo 也识别了同一控制流，但以“pre-existing stderr 传播模式”为由未立 finding。Controller 不接受该排除理由：缺陷发生在本轮新增 typed interrupt handler 的具体排序中，并直接违反 fixed plan 的 interrupt/abort contract。

修复必须：

- 任何可能失败的 diagnostic I/O 都不得阻止 identity-safe abort；
- typed/plain persistence interrupt 均保持 exit 130；
- abort 自身失败后的 retained-path diagnostic 写入失败也不得覆盖原始中断；
- 测试用真实 prepared transaction 或等价 owner-level evidence 注入 broken stderr，断言 abort 已尝试/完成、无 private transaction 遗留且 exit 130。

### R12-S2-RR-F02 — ACCEPTED / HIGH

两路复审都把 `_cleanup_owned_profile_temporary` 的 `unlink`/identity-read 不确定性视为可接受或极端 residual，但 fixed plan §10.1 并没有接受 secret-bearing POSIX profile temp 的静默遗留。计划的 S1 contract 明确要求任一失败不 publish、不注入，异常与残留证据不得泄漏 sentinel secret。

Controller 直接探针在 owner lookup boundary 注入：

1. `os.replace` 调用前抛 `KeyboardInterrupt`；
2. `_cleanup_owned_profile_temporary` 的 `os.unlink` 抛 `OSError`。

实际结果为：typed interrupt 正常返回，public profile absent，但保留一个 `.dayu-init-env-*`，其内容包含 `CONTROLLER_SECRET_SENTINEL`。因此当前实现静默宣称 interruption truth，却丢失了 secret-bearing retained temp 的安全真值。

修复必须：

- 不按名称猜测或删除 identity 漂移对象；identity 不确定仍须 fail closed；
- owner temp cleanup 失败时，typed interruption/failure 必须携带最小、脱敏、显式的 retained-path truth，不能打印 secret value；
- CLI 在 workspace publish 前收到该 truth 时，先 abort prepared transaction，再做不会覆盖原始中断的 best-effort diagnostic；
- 覆盖 unlink failure 与 identity-read failure，证明 owner temp/unknown replacement 的真实状态被准确报告，外部/identity-drift object 不被误删，exit 130 与 redaction 保持；
- 不引入通用 filesystem/cancellation framework、兼容分支或测试 seam。

## 边界与下一 gate

- 允许修改仅限当前 owner：`dayu/cli/init_environment.py`、`dayu/cli/commands/init.py` 及对应 `tests/cli/test_init_environment.py`、`tests/cli/test_init_command.py`。
- S3 prewarm、真实 smoke、README、Windows workflow 与 stale explicit-interaction test migration 仍不得偷带。
- 先由 AgentCodex 修复两项 accepted findings，Controller 完成 focused/full validation 后，再由 AgentMiMo / AgentDS 并发 complete cumulative re-review。
- 当前 open accepted findings：2；进入 S3 的条件仍是 0。
