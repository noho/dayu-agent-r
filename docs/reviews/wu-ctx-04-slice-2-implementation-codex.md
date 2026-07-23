# WU-CTX-04 Slice 2 implementation（AgentCodex）

## Gate metadata

- Work unit：`WU-CTX-04`。
- Slice：`2/3`；accepted Slice 1 baseline：
  `eda1d70eb2c2252570807e1fcdb1cd234a5aae7a`。
- Coverage 的 WU baseline：
  `974f9e1686f6e26f96830cd3478edc9d0d686c45`。
- Gate：implementation；result：`pass`。
- Controller-owned control doc final protected Git blob hash：
  `61a662c5813d553fe021ed7ff8b971b571b03ee6`。
- Controller-owned scope amendment final Git blob hash：
  `371cda2819c5aa170819e6960d7d895950b0bf0d`。
- Slice 1：accepted；Slice 2 attachment/recovery/proactive 联合 checkpoint：
  complete；Slice 3：未开始。

## First-principles / semantic-owner conclusion

原问题成立。SQLite transaction/CAS 只能约束 durable commit，不能约束事务外
provider/compactor side effect；多个独立 `open_host(...)` 若没有 per-Session 唯一新工作 owner，
会并行进入 pre-start governance。最终实现保持以下唯一 owner：

- `HostSessionAttachmentRegistry` 拥有 attachment mode、mutation access、new-work access、
  mutation/work lease 与 closing lifecycle；native mutex 只提供跨 opener 机械互斥。
- `_PublicHostHandle` 统一拥有 public mutation admission；Service、watcher、read API 都不产生
  attachment truth。
- `HostDispatchScheduler` 只消费 mandatory `SessionNewWorkAccessPort`，stable Attempt 的继续执行
  不依赖 attachment，新 Attempt/promotion/pre-start 必须持 work lease。
- `SessionAttachmentRecoveryScanner` 只读取目标 Session durable truth；mutex 状态不参与 orphan
  分类。
- proactive request fact、runner-call manifest 与 `ProactiveCompactionState` 分别拥有 operation
  identity、prepared attempt 与 crash-resume projection；typed schedule 是 attempt number→stage 的
  单一真源。
- transaction-owned `PayloadStore` 是 compactor proposal manifest payload 的唯一 storage owner。

没有引入 alias/default、soft fallback、Service 代持、workspace-wide writer、lease/fence/proxy，
也没有提前实现 Slice 3 physical cancel reconcile。

## Allowlist blocker 与三次 Controller amendment 历史

### 初始 blocked 证据（保留）

初始 implementation 在 production edit 前因 accepted plan consumer 枚举漏项停止：

- `B-001`：`tests/host/test_public_host_admin.py` 直接 import/type/monkeypatch
  `StartupRecoveryScanner`；删除 stale production owner 后该测试必然 import/pyright/pytest 失败，
  保留 alias 又违反无兼容代码约束。
- `B-002`：`tests/host/test_active_cancel_dispatch.py` 直接构造 scheduler 并调用 pre-start；mandatory
  access port/work lease 落地后，测试若不机械迁移就只能迫使 production 增加错误 default。
- 同一路径还发现 `tests/host/test_terminal_post_commit.py` 冻结了旧 recovery qualified name。

这三项被 Controller 裁决为 accepted plan 的 test consumer 枚举漏项，不重开目标、架构或 plan gate。
初始 blocked artifact 的 control hash 是
`d1d9a1368ef9f135f08fd34f24674e74f1fe0786`；恢复指令阶段 control hash 为
`1af0e1016a97798b0767b3ca351146141f5b00ca`。

第一次窄 amendment 的机械边界最终保持为：

- `test_public_host_admin.py` 只有 recovery import/type/monkeypatch 改为
  `SessionAttachmentRecoveryScanner`；“HostAdmin 不启动 scheduler/recovery、不改变 durable facts”
  断言未改。
- `test_active_cancel_dispatch.py` 只有 scheduler construction 注入
  `ExplicitFakeSessionAccess`，直接 pre-start helper 取得/传入/释放真实 work lease；cancel state
  machine、业务期望与 Slice 3 owner 语义未改。
- `test_terminal_post_commit.py` 只有 recovery owner/method qualified-name oracle 同步；terminal
  transition/promotion ownership 断言未改。

### 第二次窄 amendment：tier 2 request owner

默认 budget=5 首次让 `root → root-repair → tier1 → tier2 → tier3` 全部可达后，直接证据证明
`build_tier_recovery_request_plans` 的 tier2 仍错误复用 root selection。Controller 仅授权：

- `dayu/host/compact_pipeline.py`：tier2 `selected_segment` 从 root 改为既有
  `bounded_selection`，其它 pipeline 语义不变。
- `tests/host/test_compact_pipeline.py`：只新增 tier2 selection 等于 tier1 bounded、且不等于 root
  的两条 owner 断言。

该 checkpoint 的 frozen hashes 为 control
`fcd362340c551c9ffac5ef3afa2f158e1c065203`、scope amendment
`605161bd67d6f74572d48c03b36d7e7f6284b88a`。

### 第三次窄 amendment：post-coverage mechanical oracles

第一次完整 coverage 面运行暴露两个 Slice 1/旧 owner 静态 oracle：

- `tests/host/test_session_attachment_registry.py` 只把“Slice 1 package root 不公开”迁移为
  Slice 2 public attachment value/export contract；registry conflict/lease/close primitive 断言未改，
  internal registry/work port/lease 仍不得导出。
- `tests/host/test_terminal_post_commit.py` 只把 active-cancel producer qualified name从 public
  wrapper 同步为共享 private owner
  `HostDispatchScheduler._tick_active_cancel_watchdog._operation`；producer 闭集与 promotion owner
  未改。

最终 frozen hashes 即 metadata 所列 `61a662...` / `371cda...`。

## Exact changes 1–17 completion map

1. **Public attachment/API/export：pass。** `HostSessionAttachment`、mode/error value types与
   `Host.attach_session` 已公开；registry/work port/lease 保持 internal。
2. **统一 mutation owner：pass。** `_PublicHostHandle._invoke_session_mutation` 同时消费 health
   admission 与 registry mutation lease；lease 跟随 actor Future，而不是 caller awaiter。Run-id API
   先只读解析 Session id。
3. **七类 mutation gate：pass。** submit、steer、cancel、retry、replay、close、drain 均在创建
   mutation Future/durable fact/wake 前拒绝 unattached/RO；read、watch、resolve_wait 保持 ungated。
4. **Scheduler work gate：pass。** constructor 无默认值地强制注入 access port；wake、actual
   promotion、pre-start 与 new Attempt 取得真实 work lease；existing dispatch continuation不 gate。
5. **Owned-session periodic reconcile：pass。** ACTIVE RW record 才进入
   `reconcile_owned_sessions_once(fixed_now=...)`；production loop 与 direct test 共用同一 one-shot，
   target-only、幂等且不 sleep。
6. **Target-only recovery：pass。** 删除 `StartupRecovery*` 与 production 无 caller 的全局
   `read_non_terminal_runs`；scanner/keyset/watermark/SQL 全部要求 Session id。单独 `open_host` 不再
   startup scan/tick。
7. **RW attach recovery lifecycle：pass。** RW 依次做 target watchdog、fixed-page recovery、
   activation；RO/open_host 零 recovery/wake 副作用；failure/cancellation 等 actor Future drain 后才
   release mutex。
8. **Host scheduler-before-unlock close barrier：pass。** Host close 保持 attachment CLOSING/mutex，
   直到 actor/pre-start drain、scheduler background/promotion/token/hook/worker/task/handle/lane mandatory
   cleanup 与 host instance `STOPPED` 全部完成。单 attachment close不关闭 scheduler/stable Attempt。
9. **CLI ownership：pass。** prompt/interactive/session UI lifecycle 显式 attach+shielded close；
   Service 没有 attachment API、缓存或状态推断。
10. **同 handle duplicate：pass。** live record 在任何第二次 native acquire 前 typed conflict；
    close 后 fresh attach 才重新竞争。
11. **Periodic wiring：pass。** interval loop 只调用生产/test共用的 target one-shot，direct test不用
    wall-clock sleep。
12. **Close failure/retry：pass。** mandatory residual worker handle close 与 `STOPPED` 写入任一失败，
    `_close_cleanup_done`/`close_done`/mark-closed均不成功，health/attachment保持CLOSING、mutex busy、
    下游 owner 不关闭；retry 才完成并 unlock。只有 `on_cancel` hook 是 best-effort，且先于 unlock。
13. **Proactive request/state owner：pass。** request schema含 operation id/frozen budget/material；
    bounded EventLog reader与 typed ABSENT/INCOMPLETE/COMPACTED/FAILED/INVALID projection 已落地。
14. **Global attempt range/schedule：pass。** `run_compaction_operation` 的 first/max required且无
    compatibility default；proactive 用 typed single-attempt owner与 schedule。max 1..5依次为
    `[root]`、`[root,t1]`、`[root,t1,t2]`、`[root,t1,t2,t3]`、
    `[root,root-repair,t1,t2,t3]`；更大预算把额外次数给 root repair，再保留三个 tier。
15. **Engine ingest reactive mechanical adaptation：pass。** request event id即 operation id，pending
    policy冻结同一 max；owner spy 直接观察 `first_attempt_number=1` 与同一 snapshot max。reactive
    count/overflow/recovery/fallback未改。
16. **旧 proactive count 配置删除：pass。** policy/config loader/Service assembly/四个 profile与测试
    输入全链删除；无 alias/default/stale active surface。
17. **Direct/headless/test/utils caller lifecycle：pass。** 所有 public mutation caller显式 attach+
    close或明确断言 typed拒绝；option/read helper不隐式 attach，Service不代持。

Attachment-only 与 proactive-only 都没有作为 completion signal；以上 17 项与联合矩阵一起通过后才
形成当前 pass。

## Strong owner-level acceptance evidence

### Attachment / close / lease / recovery

`tests/host/test_public_session_attachment.py` 使用两个真实独立 `open_host`、同 DB/Session证明：

- A RW/B RO；B 七类 mutation typed拒绝，EventLog（使用 schema owner `TABLE_EVENT_LOG`）、provider、
  wake 均 0 增量，同时 B read/watch可用。
- 同 workspace 不同 Session 双 RW并行；并发 fresh attach只有一个RW；A close后B原RO仍RO，B自身
  close/fresh attach后才RW。
- RO attach/open_host零副作用；recovery failure/cancel drain 后mutex可fresh取得；periodic
  reconcile one-shot只处理ACTIVE RW目标。
- actor Future已drain但真实 pre-start provider/work lease未释放时 mutex仍busy；放行后 closing gate
  不创建错误 owner，fresh RW可取得。
- 独立 stable Attempt 用例证明单 attachment close不等 terminal、不关闭scheduler、不cancel Attempt；
  fresh RW后旧 Attempt正常终态。
- mandatory handle cleanup或STOPPED失败保持CLOSING/mutex/RO second opener/downstream owner；retry后
  才STOPPED+unlock。`on_cancel` 抛错不阻断token与mandatory cleanup，且hook发生在unlock前。

`tests/host/test_recovery_scan.py` 保留同一 target Session 跨页故障的
`test_second_target_page_failure_rolls_back_without_wake_and_rerun_converges`；另由
`test_target_scan_does_not_enter_foreign_session_failure_injection` 独立证明 foreign-session
isolation，后者没有替代前者。fixed watermark、64 page、keyset ties与commit-after-wake既有矩阵保持。

consumer-started barrier 在 owner task 进入 `try/finally` 后立即建立；run-session读取、
`EngineEventIngestor`构造或 `handle.events()` 同步初始化失败都能释放 caller，不使用 timeout 伪修复。

### Proactive operation / crash / storage

- `test_proactive_compaction_operation.py` 自足使用 production owner API与最小 durable fixture，覆盖
  ABSENT、INCOMPLETE、terminal、INVALID、mismatch、multi-terminal、budget projection与 max1..6
  schedule；没有 cross-test-module private import。
- default budget集成冻结每个 attempt request/stage：root、root-repair共享 root material；tier1使用
  bounded selection；tier2继续使用同一 bounded selection但降级 previous view/renderer；tier3继续
  bounded selection并使用空 previous view/对应 renderer。各 stage request digest不同，只在同
  attempt 与 schedule digest冲突时 INVALID。
- manifest 1..5 任一 prepared 后进程级 crash，fresh scheduler都按 attempt number恢复确定的下一
  stage；attempt 5耗尽时同operation FAILED、provider 0调用。测试使用 manifest提交后抛出的
  `BaseException` crash sentinel，避免 `Task.cancel()` 与合法业务取消收口产生次序竞争。
- projection按首轮 validated request建立 operation id→trigger source；只忽略有合法 reactive
  REQUESTED owner的后续 rows，未知/第二 proactive operation fail closed。proactive terminal后一个或
  多个合法 reactive operation不污染projection。
- 每 attempt 保留 manifest ref/digest/request digest；accepted terminal必须精确关联该 attempt 的
  runner-call manifest，已 rejected attempt不得再accepted，terminal后不得追加 operation row；FAILED
  attempt_count按 producer contract校验。

Storage root-cause decision：采用 transaction-owned `PayloadStore.write_bounded_json_payload` 作为唯一
真源，由它按 threshold自行 inline/artifact到 durable `artifact_root`。删除两次显式
`LocalArtifactStore.write_artifact_bytes`、被丢弃的 refs、LocalArtifactStore字段以及 recorder无效的
`artifact_root/create_artifact_root` constructor args；所有真实 callers/tests已迁移。不存在双写、
orphan artifact或reader fallback root。

## Caller migration / grep audit

### Public mutation classification

同一 lexical/object lifecycle 显式 attach+shielded close：

- Host support/integration：`recovery_support.py`、`test_open_host_runtime.py`的 mutation blocks、
  `test_effective_execution_config.py`、`test_host_activity_event_projection.py`、
  `test_host_production_stress.py`、`test_per_run_tool_selection.py`、
  `test_transient_delta_stress.py`、`test_watch_session_events.py`。
- Public smoke/contracts：`test_submit_followup_public_contract.py`、`test_public_steer.py`、
  `test_public_retry_replay.py`、`test_public_cancel_smoke.py`、`test_public_compact_smoke.py`、
  `test_public_open_host_multiturn_smoke.py`、`test_public_lifecycle_smoke.py`、
  `test_public_offline_outbox_smoke.py`、`test_public_outbox_api.py`、
  `test_public_resolve_wait_resume.py`、`test_public_tool_wiring_smoke.py`、
  `test_public_real_runner_matrix_smoke.py`。
- CLI：`test_prompt_command.py`、`test_interactive_command.py`、`test_session_command.py`、
  `test_transient_delivery_interruption_path.py` 的 fake/real UI owner都表达 attachment+close。
- Utils：五个 `utils/smoke_host_public_*` direct mutation脚本均由脚本 lifecycle持有唯一attachment。

故意无RW attachment的命中：

- `test_public_session_attachment.py` 的 unattached/RO七类 typed rejection矩阵。
- `test_purge_session.py` 在 Session已purge后对retry/replay断言 `NOT_FOUND`；Session只读解析先失败，
  不会进入 attachment/mutation Future。
- `test_admission_queue.py` / `test_admission_multiprocess.py` 命中的是 lower-level
  `HostAdmissionService` owner，不是 public `Host` Protocol caller。
- `dayu/service/entrypoint_runtime.py` 调用 public mutation但 attachment由UI caller lifecycle拥有；
  精确 `rg "attach_session|HostSessionAttachment" tests/service dayu/service` 为零输出。

纯 read/open/options case明确不 attach：`test_public_open_host_options.py`、
`test_public_session_api.py`、`test_open_host_runtime.py`中仅 `get_run(snapshot/final_run)` 的 reopen blocks
以及其它 get/read/watch-only blocks。watcher是subscription，不是access truth。HostAdmin也不 attach且
继续证明不启动 execution/recovery。

### Required-signature audit

`rg -n "run_compaction_operation\(" dayu tests` 已逐项检查：

- production direct caller仅 `dayu/host/engine_ingest.py`，显式传 `first_attempt_number=1` 与
  `pending.policy.max_compaction_attempts_per_operation`；proactive dispatcher使用更窄的 typed
  `run_compaction_attempt` stage owner。
- `test_compaction_operation.py`、`test_compaction_cancellation_scope.py`与新增 EngineIngest owner spy的
  每个 direct call都显式传first/max；无兼容 default/alias。

## Changed-files / scope audit

- Production/config：accepted Slice 2 allowlist内的
  `dayu/cli/session_execution.py`、`dayu/config/execution_profiles.json`、`dayu/host/{__init__,api,
  compaction_operation,context_events,context_policy,dispatch,engine_ingest,open_host,recovery,
  session_attachment,proactive_compaction}.py`、`dayu/host/durable/{event_log,state}.py`、
  `dayu/runtime/config_loader.py`、`dayu/service/host_assembly.py`，以及第二 amendment精确授权的
  `dayu/host/compact_pipeline.py`。
- Test/support/utils：全部位于 accepted Slice 2 allowlist、五个 utils allowlist或三次窄 amendment
  列出的机械文件；没有新增测试模块间 private import。
- 唯一 implementation doc是本文件；没有创建额外 implementation artifact。
- `docs/host/issues-implementation-control.md` 与 scope amendment是 Controller-owned；implementation
  未编辑，final hash已校验。
- `README.md`、各层README、design均未修改。

## Validation

### Pytest

- Accepted plan §8.2 exact matrix：`639 passed, 1 skipped, 6 deselected`，43.60s。
- Accepted plan §8.3 exact matrix：`579 passed, 1 skipped`，8.10s。
- 完整 coverage affected surface
  `pytest tests/host tests/runtime tests/service tests/cli --cov=dayu --cov-report=`：最终
  `3520 passed, 8 skipped, 6 deselected`，128.92s。首次运行的
  `3517 passed / 3 failed` 不是豁免：第三 amendment迁移两个旧oracle，并把 crash fixture从
  `Task.cancel()` race改为manifest后进程级crash sentinel后，完整重跑全绿。
- latest proactive/native focused coverage面：`133 passed`；runtime suite：`595 passed`。
- projection owner after duplicate-read cleanup：`17 passed`；EngineIngest/crash/oracle收口 subset：
  `8 passed`。
- pytest warnings均为环境中 `edgar` deprecated imports，共3条；无本 Slice warning。

### Full pyright / ruff

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- modified/new、基线clean Python文件 `ruff check`：`All checks passed!`。
- 仓库级 `ruff check dayu tests utils` 仍报告130条既存告警，主要在未授权 documents/fins/tools；
  对本 Slice触及且基线已有告警的8个文件逐个以 baseline内容从stdin复跑，恰为当前同位69条
  （3个F401、3个E402、1个F841及utils既有E402集合）。其余modified/new文件零告警，因此本次新增/
  扩散ruff violation为0；未越界清理既存问题。

### Per-file coverage（每个均单独 `--fail-under=80`）

| Modified production Python | Coverage |
| --- | ---: |
| `dayu/cli/session_execution.py` | 81% |
| `dayu/host/__init__.py` | 100% |
| `dayu/host/api.py` | 94% |
| `dayu/host/compact_pipeline.py` | 94% |
| `dayu/host/compaction_operation.py` | 94% |
| `dayu/host/context_events.py` | 90% |
| `dayu/host/context_policy.py` | 94% |
| `dayu/host/dispatch.py` | 89% |
| `dayu/host/durable/event_log.py` | 91% |
| `dayu/host/durable/state.py` | 88% |
| `dayu/host/engine_ingest.py` | 91% |
| `dayu/host/open_host.py` | 89% |
| `dayu/host/proactive_compaction.py` | 87% |
| `dayu/host/recovery.py` | 92% |
| `dayu/host/session_attachment.py` | 88% |
| `dayu/runtime/config_loader.py` | 96% |
| `dayu/service/host_assembly.py` | 95% |
| Slice 1 carryover `dayu/runtime/__init__.py` | 100% |
| Slice 1 carryover `dayu/runtime/native_mutex.py` | 92% |

前17项是相对 accepted Slice 1 baseline `eda1d70...` 的 Slice 2 production Python；最后两项按
§8.6 WU baseline `974f9e...` 补入。config JSON与utils不属于Python单文件coverage。

### Grep / whitespace / hash / scope

- 旧 proactive count字段/常量/reason stale grep：零输出。
- runtime reverse-import grep：零输出。
- `StartupRecovery` 与精确 `read_non_terminal_runs(`：零输出；target-only
  `read_non_terminal_runs_for_session*`保留。
- §8.7 首组当前精确剩余3个 `read_cancelling_runs` 命中：
  `dayu/host/durable/state.py`定义、`dayu/host/dispatch.py` global periodic watchdog调用、
  `tests/host/test_state_schema.py` owner测试。直接数据路径证明它属于 accepted Slice 3 Exact change 2
  “删除 workspace-wide periodic cancelling scan/query”，不是 Slice 2 target recovery owner。Controller已
  裁决为 later-slice/deferred-to-Slice-3；§8.7 是 WU final invariant，将在 Slice 3 后归零，不构成
  Slice 2 blocker，也未改名消音。
- `git diff --check`：pass；README status：无修改。
- final control/scope hashes：`61a662...` / `371cda...`，均与Controller冻结值一致。
- relative `eda1d70...` changed-files逐项与 accepted allowlist + 三次窄 amendment核对通过。

## README / docs decision

Controller明确裁决 README 全部 defer 给 Slice 3，且本轮禁止修改；因此根README、
`dayu/{host,config,service}/README.md`、`dayu/README.md`、`tests/README.md`均保持不动。Slice 3 在
physical cancel reconcile完成后，按最终 current behavior一次性更新；本 Slice不提前写未来事实。

## Classified residual risks

- **Later slice（已分类，不是 blocker）**：workspace-wide `read_cancelling_runs` periodic owner将在
  Slice 3 Exact change 2改为target execution-owner cancel reconcile，并令WU final §8.7归零。
- **Cross-platform**：本机实际验证POSIX native mutex；Windows backend需在Windows运行同一
  `test_native_mutex.py`。unsupported/unrecognized errno仍fail closed。
- **Provider crash**：manifest已提交但provider结果未durable时，prepared attempt保守耗费预算并从
  下一schedule stage恢复；没有provider idempotency证据，因此不承诺外部调用exactly-once。
- **Detach/reconcile latency**：已开始provider受既有Runner/provider timeout与frozen semantic budget
  约束；cross-opener promotion liveness最多一个既有poll interval，没有force unlock或新默认timeout。
- **Fresh schema**：旧config/request shape严格拒绝；本WU不提供旧workspace迁移。
- **Pre-existing lint debt**：仓库级130条ruff告警未在本封闭scope清理；baseline comparison证明本
  Slice新增/扩散为0。
- Unclassified residual risk：None。

## Completion decision

- Slice 2联合 checkpoint：`pass / complete`。
- Blocking open questions：None。
- 未 commit、未 push、未创建PR、未进入code review/deepreview、未实施Slice 3。
