# WU-CLI-INTERACTIVE-02 S6 Implementation

## 1. Gate facts

- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Slice：S6 — 跨切片集成、职责内文档、CLI registry/oracle proof 一致性与 smoke/evidence
- Branch：`codex/interactive-oracle`
- Accepted base / current HEAD：`9ad45cf717f192b12f411d03332b971f30aff472`
- 执行日期：2026-08-02（Asia/Shanghai）
- 初始工作树：clean
- 约束：未新建分支，未 commit/push/PR，未 stash/checkout/reset/rebase；未修改生产代码、测试或 utils；未改冻结 calibration adjudication。

直接证据确认 S6 动机成立：accepted registry 仍含 17 条实际 argv 使用已删除 prompt
`--config` 的 scenario，`prompt.P37` 把同命令复用误记为 cross-command，README/design
仍陈述旧 parser、slot、interactive input 或缺失 F10-F13 owner contract。修复边界因此只在各自
文档/registry owner，不向 production 或 test consumer 增加补偿逻辑。

## 2. Exact files

本 slice 精确修改：

- `README.md`
- `dayu/README.md`
- `dayu/host/README.md`
- `dayu/engine/README.md`
- `tests/README.md`
- `docs/host/design.md`
- `docs/engine/design.md`
- `docs/cli_ci.md`
- `docs/cli_ci_scenarios.json`
- `docs/reviews/gateflow-wu-cli-interactive-02-s6-implementation-codex-20260802.md`（唯一新增 implementation artifact）

`docs/cli_ci_oracles.json` 经检查无需 proof/ref/applicability 修正，保持 byte-identical，SHA-256
为 `99c0d1aea2fdfea922c73d1a5b88b6c7e275d79a5589d07f904fe39c6d1802c9`。其它
§10.1 allowed file 均未触及；production、tests（除职责内 `tests/README.md`）与 utils diff 为零。

## 3. Docs decision 与 owner contract

五份 README 与两份 design 只记录 S1-S5 已接受实现及本次已验证事实：

- F01-F03：prompt/interactive 不接受 explicit config，interactive 不接受 ticker；有 label 的
  prompt/interactive 共用 `cli.agent` slot，anonymous invocation 保持 fresh。
- F04-F09：session selector 删除 kind；interactive TTY composer 独占 stdin，明确
  Shift+Enter/Ctrl+J、Escape/CSI/Alt/paste、Ctrl+C closeout、type-ahead/sole QUEUE、Ctrl+D；
  non-TTY whole UTF-8 stream 至多提交一个 Run。
- F10：`docs/host/design.md` 的 recovery owner 段明确写入 fresh `READ_WRITE` 首次扫描早于
  stale threshold 时，由当前 attachment recovery owner 安排单个 target-scoped bounded delayed
  reclassification；到期以 fresh `now` 重跑同一 positive-orphan classifier，并继续服从 fixed
  watermark、bounded page、CAS、positive proof 与 dispatch 上限；attachment close 取消并 join，
  `READ_ONLY` 不安排任务也不执行 target scan。
- F11：Host 共享 compaction terminal helper 在 transaction 内按 request/trigger 发放 first-committer
  permit；late loser 在 artifact、terminal、fallback、Attempt start 前变成 no-op，多 terminal 或身份
  不一致 fail closed。
- F12：同一 live read-write Session 的 pre-start governance 由 scheduler-local single-flight owner
  串行化；wake/periodic signal 合并，caller cancellation 不取消共享 flight，close 取消并 join，fresh
  owner 只从 durable pending operation 恢复。
- F13：Engine 成功 final/outcome 携带同一个 required `SuccessfulRunnerResponseIdentity`；Host
  compactor 将它与 operation、attempt、proposal manifest、candidate/output 同源绑定，provider request
  id 采用 `present + value` / `unavailable + None`，不从配置、manifest、usage 或相邻事件反推，且不投影
  endpoint、credential、header、secret 或 provider raw payload。

根 README 只写用户可操作 CLI 事实；`dayu/README.md` 只写跨层稳定边界；Host/Engine README
与两份 design 写各自 owner contract；`tests/README.md` 移除 ticker/config、single-byte monitor、第二次
Ctrl+C 提前退出等旧测试陈述并换成当前 suite 事实；`docs/cli_ci.md` 补充 parser inventory 与
evidence-before-registration 规则。没有写入未验证的成功 scenario 或 G01-G07 裁决。

## 4. Scenario registry exact delta

### 4.1 Scenario objects

- 原 registry：459 条（prompt 400 / init 59）。
- 删除计划 §10.3 指定的精确 17 条：
  `prompt.P25-config-missing`、`prompt.P26-config-outside`、
  `prompt.P35-explicit-config-unicode-multiline`、`prompt.P35R-explicit-config-positive`、
  `prompt.PC-PW-R2-01/-02/-05/-07/-09/-11/-12/-13/-14/-15/-16/-17/-18`。
- 新 registry：442 条（prompt 383 / init 59）；未新增 scenario。
- 精确保留 `prompt.PC-PW-R2-03/-04/-06/-08/-10`。每条只从
  `coverage_claims.command_parameter_ids` 与 `coverage_claims.raw_stable_claims` 各删除一次
  `parameter:config:default`；两处 `init-deepseek-config-explicit` precondition 与其它字段不变。
- `prompt.P37-label-followup` 仅在上述两个 claim 数组把
  `cross-command:label-session-reuse` 改为
  `same-command:prompt-label-session-reuse`；memory/prior-turn evidence 不变。
- `prompt.P29R-config-not-directory`、`prompt.P30-default-no-init`、
  `prompt.P32-existing-dayu-no-config`、`prompt.P11-empty-label`、
  `prompt.P36-label-first-tool-call` 保持不变。
- 以 HEAD registry 做对象级比较：除上述 5 条 pairwise row、P37 和 17 条删除外，其余 436 条
  scenario object 完全相同；prompt argv 中 `--config` 为零。

### 4.2 Parser inventory 与 readiness proof

先运行现有命令：

```bash
source .venv/bin/activate
python workspace/tmp/interactive_calibration_plan.py \
  --repo-root /Users/leo/workspace/dayu-agent-r \
  --run-root /Users/leo/workspace/.dayu-cli-ci/interactive-s6-20260802-Meo1Jt
```

该 generator 针对 HEAD 生成 552 个 obligations，静态 plan validation 通过；但其 obligation builder
仍硬编码已删除的 config/ticker runtime obligations。因此该输出只作为 candidate-plan evidence，不能用来
登记当前 accepted interactive scenario。S6 随后直接从 production `build_parser()` 按现有 canonical
serializer 机械派生 leaf inventory，并用对象/ref validator 重算 registry proof：

| Leaf | Inventory version | actions | canonical SHA-256 | source commit |
|---|---:|---:|---|---|
| prompt | 2 | 27 | `e83f3d12ab5eba99cdfb586e5b15cd99e01451c23b66ec2f9d7dd7ce94f1b9b3` | `9ad45cf717f192b12f411d03332b971f30aff472` |
| interactive | 2 | 25 | `1b4a980923f85536accb8da5f714d5329cc8724114219aa3fea5dd6d5d72c5f6` | `9ad45cf717f192b12f411d03332b971f30aff472` |

prompt proof 为 mandatory/covered/accepted `383/383/383`、gap `0`；dimension scenario counts 为
`33/383/16/8/319/5`（command parameter / precondition / interactive branch / input class /
high-risk combination / cross-command assertion）。scenario id、oracle、predicate、correctness surface、
evidence ref 均无 dangling；frozen report digests 覆盖所有 observed report digest。
`implementation_findings_do_not_reduce_readiness=[]`。prompt 保持 `ready`；init 保持 `ready`；因为
interactive 等 command 尚未完成正式 calibration，global validation 与 `registry_status` 均保持
`calibration`，没有手工翻转 ready。

## 5. 实际 scenario 与 evidence

### 5.1 Credential/config preflight

只检查 availability，不输出值：DeepSeek credential 可用、credential ref 已声明、包内配置文件可用、
default compactor config 可解析；输出值计数为零。所有 candidate 写入 CI-owned repo 外目录
`/Users/leo/workspace/.dayu-cli-ci/interactive-s6-20260802-Meo1Jt`。

### 5.2 Candidate 运行结果

| Candidate | 实际结果 | 登记决策 |
|---|---|---|
| `interactive.I0543-memory-compaction-trigger` | 真实 argv，pipe，exit 0，未 timeout；durable 产生 `CONTEXT_COMPACTION_FAILED`，reason=`hard_threshold_before_dispatch`，随后 `RUN_FAILED` | 不是 successful compactor evidence，不登记 |
| `interactive.S6-compaction-provider-identity-attempt-02` | 真实 argv，pipe，exit 0，未 timeout；durable sequence 5 `CONTEXT_COMPACTION_REQUESTED`、6 proposal `RUNNER_CALL_INPUT_ASSEMBLED`、7 `CONTEXT_COMPACTED`，随后 ordinary Run `RUN_SUCCEEDED` | raw candidate/evidence 成功；不越权登记 accepted scenario |

第二条 candidate 的 `CONTEXT_COMPACTED.payload_json.successful_response_identity` 已从 durable snapshot
实际读取并脱敏核对：effective provider=`deepseek`，effective model=`deepseek-v4-flash`，provider
request id availability=`present` 且 value 存在（值不输出），RunnerRequestIdentity 的 run、iteration、
client correlation 均存在，`runner_call_index=1`；accepted attempt number=`1`，operation、proposal
manifest ref/digest 与 candidate 同一 payload 绑定。未从配置推断该 identity。

冻结 raw evidence refs/digests：

- `evidence/interactive.I0543-memory-compaction-trigger/command.json`
  `3cd04aa63ff52027ba658750d17fe5f3ee360ae6338eb69cadf677b715f27d9b`
- `evidence/interactive.I0543-memory-compaction-trigger/sqlite-after.json`
  `c2083a374a85d48e470fe2eb0e5bb5add3dbf9115b67a5148a009df495478463`
- `evidence/interactive.S6-compaction-provider-identity-attempt-02/command.json`
  `94d4f168b2006e8b859c4415648b5f412266a9abf3debbc962717421f21ab8be`
- `evidence/interactive.S6-compaction-provider-identity-attempt-02/sqlite-after.json`
  `af839974ddfabb917179b07553162403a6440a58000349e77b843bbf29900c61`
- `evidence/interactive.S6-compaction-provider-identity-attempt-02/stdout.txt`
  `c60aba7da49e012c6cf61ac62930b93c5700263eec56f3ca28488242d3f1d6f3`

现有 formal report renderer 硬编码旧 target commit，且本 WU 禁止新建通用 harness；因此没有生成可供
accepted registry 引用的当前 target formal observed-behavior report，也没有运行或登记其它新增 F
scenario。行为项 29 的 S6 live validation 已取得真实 successful compactor durable identity raw
evidence；其正式 scenario/ref/readiness 登记仍待授权 campaign/report owner 完成。冻结 calibration
adjudication 不变，G06 与 G01-G07 均未裁决。

## 6. S6 validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

| Validation | Result |
|---|---|
| CLI focused 六文件 | `605 passed, 3 warnings` |
| Service prompt/interactive focused | `13 passed, 3 warnings` |
| S3 recovery focused 六文件 | `116 passed` |
| S4 compaction terminal/dispatch/operation/event/ingest focused | `367 passed` |
| Engine identity focused 七文件 | `173 passed` |
| S5 26-file focused closure | `883 passed, 1 skipped, 6 failed`；六条均为已接受 phase5 baseline race |
| CLI + Service affected integration | `1181 passed, 7 skipped, 3 warnings` |
| Host affected integration | `775 passed` |
| Full `pytest tests/engine tests/host -q` | `2957 passed, 1 skipped, 6 deselected, 6 failed`；六条精确为 `test_phase5_local_execution_integration.py` 的既有 `drain.dispatched == 0` |
| I0554 三条 owner proof | `3 passed` |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `python -m json.tool` 两个 registry | 通过 |
| registry object/ref/readiness validator | 通过；dangling oracle/predicate/surface/evidence 均为 0 |
| removed option / namespace static scan | 七组 production 查询均零命中；public `parse_cli_args` 对 root/command config、interactive ticker、session kind 均 exit 2 |
| `git diff --check` | 通过 |

六条 baseline failure 节点为
`test_start_run_fake_worker_final_answer_succeeds`、
`test_start_run_fake_worker_run_failed_fails`、
`test_start_run_fake_worker_clean_eof_fails`、
`test_start_run_fake_worker_crash_loses`、
`test_cancel_active_fake_worker_closes_cancelled` 与
`test_queue_promotion_after_terminal_and_cancel_wakes_dispatch`；均在首次
`scheduler.drain_once()` 得到 `dispatched == 0`，与 S5 clean-base 裁决一致。

I0554 保留且显式复验的三条静态 owner proof：

- `tests/engine/test_agent_phase3_tool_call.py::test_normal_final_empty_content_is_fail_closed`
- `tests/host/test_engine_ingest_mapping.py::test_engine_owned_empty_final_failure_closes_failed`
- `tests/host/test_public_host_event.py::test_succeeded_event_requires_inline_final_answer_view`

### 6.1 Frozen utils smoke

命令保持计划原文：

```bash
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/wu-cli-interactive-02-s5-awaiting-identity

DEEPSEEK_API_KEY=test-provider-key \
python utils/smoke_host_public_conversation_memory_scenarios.py \
  --suite memory-reactive-compact \
  --log-level CRITICAL

DEEPSEEK_API_KEY=test-provider-key \
python utils/smoke_host_public_conversation_memory_scenarios.py \
  --suite memory-compact-fallback \
  --pressure-mode auto \
  --log-level CRITICAL
```

- awaiting：仍在 `run_accepted` 前断于既有
  `callback_execution_port is required when callbacks are set`，随后 overall deadline exhausted；只记录
  已知 clean-base harness/public-contract drift，未改 utils 或生产代码。
- `memory-reactive-compact`：PASS；accepting compactor outcome、一次 reactive compact 与 ordinary final
  均存在。
- `memory-compact-fallback`：PASS；rejected attempts、failed operation、fallback dispatch 与 ordinary
  final 均存在。

### 6.2 Secret/proof checks

- 最终扫描 10 个 exact-scope 修改/新增文件及外部 evidence，共 38 个文件；对 16 个当前环境中的已知 secret
  value 只做内存比较，不输出值：raw hits `0`，token/Bearer shape hits `0`，values emitted=`false`。
- durable success identity key set 精确为 effective model/provider、provider request id/value
  availability 与 RunnerRequestIdentity；敏感字段 `0`。
- `docs/cli_ci_oracles.json` 与 HEAD byte-identical；accepted predicate 没有任何修改。
- current scenario registry SHA-256（artifact 写入前）为
  `cf913441e8c192bc7b7c96f2aa939cd1240a15bd9ace54c5a86d34be6c8ac393`。

## 7. 既有逐文件 coverage evidence

S6 未改生产代码，按批准计划不重复 coverage；以下是 S1-S5 accepted implementation artifact 中的
逐文件 branch coverage，均 `>=80%`：

- S1（`gateflow-wu-cli-interactive-02-s1-implementation-20260801-154645.md`）：
  `dayu/cli/arg_parsing.py` 99.48%，`host_context.py` 97.87%，`session_identity.py` 100.00%，
  `session_execution.py` 82.05%，`commands/prompt.py` 92.42%，
  `commands/interactive.py` 88.71%，`commands/session.py` 82.11%。
- S2（`gateflow-wu-cli-interactive-02-s2-implementation-20260801-171554.md`）：
  `dayu/cli/commands/interactive.py` 90%，`composer.py` 93%，`run_keys.py` 91%，
  `session_execution.py` 84%。
- S3（`gateflow-wu-cli-interactive-02-s3-implementation-20260801-192426.md`）：
  `dayu/host/open_host.py` 80%，`recovery.py` 84%，`recovery_process.py` 91%。
- S4（`gateflow-wu-cli-interactive-02-s4-implementation-20260801-205047.md`）：
  `dayu/host/compaction_terminal.py` 85%，`dispatch.py` 87%，`engine_ingest.py` 89%，
  `proactive_compaction.py` 85%。
- S5（`gateflow-wu-cli-interactive-02-s5-implementation-codex-20260802.md`）：
  `dayu/engine/__init__.py` 100.00%，`agent.py` 87.51%，`contracts/__init__.py` 100.00%，
  `contracts/agent_run.py` 97.87%，`contracts/engine_events.py` 97.48%，
  `contracts/runner_identity.py` 92.37%，`dayu/host/compact_pipeline.py` 91.75%，
  `compaction.py` 82.86%，`compaction_operation.py` 85.62%，`context_events.py` 84.72%，
  `dispatch.py` 84.05%，`engine_ingest.py` 85.35%，`llm_compaction.py` 88.96%。

## 8. Residual risks 与 next gate

- 六条 phase5 local execution failure 已在 S5 clean accepted base 独立复现并由 Controller 裁为既有
  scheduler/test race；S6 没有修改相关代码、测试或时序。
- awaiting entrypoint smoke 的 callback execution port drift 仍未关闭；本次只按要求复现并记录。
- `interactive_calibration_plan.py` 的 removed option obligations 与 formal report renderer 的旧 target
  pin 属于 harness owner gap；它们不在 §10.1，S6 fail closed 未改。其它 F scenario 因此未获得当前
  target formal report，不登记 accepted，不伪造 ready。
- 行为项 29 已有本次真实 provider successful compaction raw durable evidence，但 G06 及 G01-G07
  仍冻结为未裁决；需要后续有授权的 formal campaign/report owner 完成 evidence ref 与 adjudication。
- 下一 gate：Controller 对本 artifact、exact uncommitted diff、已分类 baseline failure 与 external
  report gap 做 S6 review/closeout。当前保持 HEAD 不变且所有 S6 修改未提交。
