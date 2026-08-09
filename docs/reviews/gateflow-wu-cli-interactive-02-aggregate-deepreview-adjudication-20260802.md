# wu-cli-interactive-02 aggregate deepreview adjudication

## Gate metadata

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Gate：aggregate deepreview initial adjudication
- Branch：`codex/interactive-oracle`
- Base：`main`
- Reviewed HEAD：`cf041c2c564bbc1ad9edca579dfc74f8fcab0f3a`
- AgentMiMo artifact：
  `docs/reviews/aggregate-deepreview-wu-cli-interactive-02-mimo-20260802.md`
- AgentDS artifact：
  `docs/reviews/aggregate-deepreview-wu-cli-interactive-02-ds-20260802.md`
- Decision：`4 accepted / 19 rejected / 0 deferred / 0 unclassified`
- Next gate：AgentCodex aggregate finding fix

## Controller decision

两路 reviewer 均独立审查了 `main...cf041c2c` 的完整提交链。Controller
没有把 reviewer 的 PASS、severity 或建议直接当作 gate 结论，而是逐项回到冻结
F01–F13、代码 owner、提交来源、测试和 durable validation 重新裁决。

本 gate 接受四项且只接受四项：

1. **AGG-A01 / accepted-medium / F08 non-TTY SIGINT lifecycle**：
   `_run_interactive_non_tty_batch` 创建 active turn 后只等待
   `active.submit_task`；invocation 已安装的 `CliSigintMonitor` 没有传入该
   helper，也没有任何 waiter 消费 signal count。同步 fallback handler 不抛
   `KeyboardInterrupt`，因此 active batch 中 Ctrl+C 会被吞掉直到 Run 自行终结。
   这直接违反“active turn 任意阶段第一次 Ctrl+C 登记同一 graceful cancel
   intent；第二次只登记 exit-after-cancel；等待 canonical terminal 和 cleanup
   后 exit 130”。修复必须复用 TTY 路径的 acceptance barrier、canonical cancel
   waiter 与 terminal owner，不得取消 submit/cancel waiter或强关 Host。
2. **AGG-A02 / accepted-medium / F08 Ctrl+T must not erase exit intent**：
   `_drive_interactive_tty_repl` 的 `TOGGLE_ACTIVITY` 分支无条件执行
   `exit_intent = CONTINUE`。在第二次 Ctrl+C 已登记
   `EXIT_AFTER_CANCEL` 后，CANCELLING phase 仍允许 Ctrl+T，因而会把冻结的
   exit-after-cancel contract 撤销。Ctrl+T 只能切换 activity display，不得修改
   cancel/exit owner。
3. **AGG-A03 / accepted-medium / F11 deterministic writer competition proof**：
   当前 `test_compaction_terminal.py` 证明 first/late/invalid-multiple 和 writer
   inventory，但没有用户在本 work unit 明确要求的“同一 operation 两个 terminal
   writer 竞争、只有一个获得 commit permit”的确定性并发测试。生产 owner 仍是
   SQLite write transaction 内的 `begin_compaction_terminal_commit_in_transaction`；
   只补 owner-level competition proof，不引入新锁、CAS owner或调度框架。
4. **AGG-A04 / accepted-low / F13 validation owner message**：
   `SuccessfulRunnerResponseIdentity.__post_init__` 复用
   `_validate_non_empty_text`，但 helper 抛出的消息硬编码
   `RunnerRequestIdentity.<field>`。这会把 F13 成功 response identity 的字段错误
   归给错误 owner。最小修复应让同一 typed validator 接收明确 owner 名称，并补齐
   request/response 两类 contract tests；不得改 schema 或 identity wire shape。

## Finding adjudication

| Finding | Final status | Controller evidence and boundary |
|---|---|---|
| MiMo-01 interactive oracle accepted but no scenarios | `rejected-intended-calibration-boundary` | `docs/cli_ci_scenarios.json` 明确为 `registry_status=calibration`，global readiness 只含 init/prompt，interactive 明确在 calibration scopes。accepted oracle 冻结产品 predicate，不等于 accepted scenario/readiness；正式 interactive scenarios 必须等 G01–G07 补跑，当前创建会伪造 evidence。 |
| MiMo-02 terminal guard should raise internally | `rejected-no-current-correctness-defect` | shared owner 返回 closed disposition 是 typed CAS 结果；五个 production callers 都显式 fail closed，writer inventory 已固定。为假设中的未来 caller 新增 wrapper 属于无关重构。 |
| MiMo-03 readiness counts are `None` | `rejected-factual-error` | reviewer 查询了不存在的 `mandatory_count/covered_count`；真实字段 `mandatory_obligation_count/covered_obligation_count` 为 prompt `383/383`、init `59/59`。 |
| MiMo-04 I0554 refs missing | `rejected-frozen-static-proof-boundary` | 用户明确裁决 succeeded 必须有非空 final answer，I0554 只保留 Engine/Host owner-level static proof，不得动态伪造 succeeded/no-final scenario。 |
| MiMo-05 response validator reports wrong owner | `accepted` | 归入 AGG-A04。 |
| MiMo-06 terminal coordinator close barrier | `rejected-pre-existing-and-unproven` | 代码由 `974f9e168` 引入，不是本分支变更；reviewer 只提出可被 durable reconciliation 补偿的假设，没有 F10/F11 regression evidence。 |
| MiMo-07 `resolve_explicit_config_dir` dead export | `rejected-factual-error` | 该 helper 仍由独立 `session` 命令在 `dayu/cli/commands/session.py` 使用；F01 只移除 prompt/interactive `--config`，不得破坏 session 产品面。 |
| MiMo-08 composer result alias dead | `rejected-factual-error` | `InteractiveComposerCompletionResult` 被 `_drive_interactive_tty_repl` 的 `wait_tasks` 类型使用。 |
| DS-AG001 mixed idle OS/composer interrupt count | `rejected-non-frozen-idle-mixed-source-policy` | 冻结 contract 分别规定 composer idle 连续两次 Ctrl+C，以及 composer 建立前 startup 一次 OS SIGINT；两者已有 owner tests。F08 的统一 lifecycle 针对 active turn，不在本 WU 新增 mixed-source idle policy。 |
| DS-AG002 legacy compaction schema | `rejected-explicit-non-goal` | AGENTS.md 与用户均禁止旧 schema 兼容读取；strict fail closed 正是 owner contract。 |
| DS-AG003 pending promotion set not cleared | `rejected-no-leak-evidence` | close 取消并 join promotion task，scheduler 不再复用；set 与 scheduler 同生命周期，reviewer 声称的 close queue-drain 代码并不存在。没有 retained scheduler/reference-cycle evidence。 |
| DS-AG004 continuation only keeps terminal call identity | `rejected-frozen-owner-contract` | Engine/Host design 明确 identity 是“实际终结回答的 Runner 调用”，F13 还要求 length continuation 的最终 runner call index 如实保存；identity chain 会扩张 schema。 |
| DS-AG005 stale `<=` to `<` | `rejected-intended-threshold-semantics` | S3 已裁决 exact threshold 进入 stale classification；只有“早于 stale threshold”才产生同源 delayed deadline。这正是 immediate attach 在 deadline 时重新分类的条件。 |
| DS-AG006 no deterministic terminal competition test | `accepted` | 归入 AGG-A03。 |
| DS-AG007 no microsecond stale boundary test | `rejected-covered-by-owner-decision` | S3 owner tests、真实越阈值同 invocation SIGKILL smoke 与 final adjudication已固定 `<` 语义；不为 reviewer 假设的错误期望补测试。 |
| DS-AG008 unreachable invalid RunnerSpec fallback | `rejected-downstream-fallback` | `RunnerSpec` owner 已严格校验；在下游捕获不可能状态并合成另一 terminal 违反 owner 约束。 |
| DS-AG009 force-answer empty failure request id | `rejected-outside-success-identity-contract` | F13 owner 是成功 response identity 与 accepted/rejected compactor proposal 的绑定；该 finding 是普通 Engine failure telemetry 扩张，且 client correlation 已保留。 |
| DS-AG010 promotion helper duplication | `rejected-style-refactor` | 当前两入口生命周期前置条件不同且行为正确；抽象 helper 不关闭冻结 F 项。 |
| DS-AG012 Ctrl+T erases exit intent | `accepted` | 归入 AGG-A02。 |
| DS-AG013 edit then delete should preserve idle pending | `rejected-policy-invention` | calibration 已冻结“正常输入/编辑重置 idle Ctrl+C pending”；按最终 buffer digest 重解释“实质编辑”会新增未裁决 UI policy。 |
| DS-AG014 non-TTY SIGINT | `accepted-reclassified-medium` | 归入 AGG-A01；不是“错误消息不精确”，而是 monitor signal 完全没有 active lifecycle consumer。 |
| DS-AG015 binary stdin guards dead | `rejected-valid-control-flow-guard` | `effective_binary_stdin` 在 TTY 分支确为 `None`；显式 guard 固定 non-TTY assembly invariant并帮助 pyright narrowing，不是兼容或 fallback。 |
| DS-AG011 no interactive scenarios | `rejected-known-next-calibration-gate` | 与 MiMo-01 同一观察；G01–G07 和正式 scenario 生成明确是后续阶段，不是本 work unit。 |

## Validation and residual-risk decision

- 两路 reviewer 均确认 F01–F13 的主要 owner implementation、pyright、secret
  边界与现有受影响测试没有 high/critical regression。
- MiMo artifact 的“行为项 29 未修复”“prompt legacy config scenarios 仍存在”是
  过期结论：S6 已用真实 compactor success evidence 裁决行为项 29，并精确删除 17
  条 removed `--config` scenarios；这些不进入 residual risk。
- G01–G07、formal interactive scenarios 与外部 provider smoke 的可复跑性继续作为
  已分类的后续 calibration boundary，不得在本 fix 中实现。
- 只有 AGG-A01–A04 进入 fix；没有 deferred 或未分类 finding。

## Next gate

AgentCodex 只修复 AGG-A01–A04，补 owner-level tests、运行受影响测试与全仓
pyright，写 aggregate fix artifact。随后 AgentMiMo、AgentDS 在 clean context 中并行
re-review；未通过双路 re-review 前不得创建 aggregate accepted commit。
