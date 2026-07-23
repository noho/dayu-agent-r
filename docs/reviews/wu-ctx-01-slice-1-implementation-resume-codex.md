# WU-CTX-01 Slice 1 Implementation Resume Handoff

## 0. Gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- gate：`implementation / Slice 1 resume`
- lane：`AgentCodex implement`
- accepted plan amendment commit：`ff28cbc4`
- status：`blocked`
- decision：`revised stop condition reached`
- next entry point：只交回 Gateflow Controller 裁决 reactive post-compact hard 的
  terminal owner / allowlist；未进入 dual code review、commit、push 或 PR

本轮完整读取了 revised plan、plan amendment、plan amendment re-review Controller
adjudication、Slice 1 stop Controller adjudication、已提交的 blocked implementation
handoff及相关 production 直接证据。当前 partial production/tests、Controller
`docs/host/issues-implementation-control.md` 改动均保留；未回退或编辑 Controller
改动，未编辑 design、plan或既有 review artifacts。

## 1. First-principles judgment

原 blocker 与 amendment 动机成立。compact coverage、Conversation Memory selected
recent projection以及 stage-aware pressure/action 都有唯一清晰 owner，本轮已能在
Slice 1 allowlist内继续实现。

恢复过程中出现一条 revised plan 未覆盖的 production 直接证据：proactive
post-compact hard 与 reactive post-compact hard 所处 Run state不同。前者 Run仍为
`ACCEPTED/QUEUED`，可以复用 plan冻结的
`fail_unstarted_run_in_transaction`；后者在 Engine ingest关闭旧Attempt后已经是
`RECOVERING`，该 transition拒绝此状态。

`RECOVERING`现有唯一失败 transition是
`fail_recovering_run_in_transaction(FailRecoveringRunInput)`，但 exact typed input
强制要求`context_compaction_failed_event_id`，其 RUN_FAILED payload语义也明确引用
`CONTEXT_COMPACTION_FAILED`。reactive accepted compact 后若complete candidate仍为
hard，当前operation已经提交`CONTEXT_COMPACTED`；为调用该transition伪造或再追加
`CONTEXT_COMPACTION_FAILED`，会违反 revised plan §6.5：

- accepted operation不得再写矛盾failed fact；
- hard必须在当前transaction显式Run terminal failure；
- 不得由下游直接改state/event绕过lifecycle owner。

因此无法同时满足“reactive exact candidate参与同一stage action”“post-compact hard
显式terminal”“不写矛盾failed fact”“不修改`run_transition.py`”。这不是fixture或
adapter问题，已命中 §8.2：

> post-compact/fallback hard无法通过既有Run failure owner显式收口，或需要allowed
> files外production修改。

## 2. Direct production evidence

| evidence | observed truth | consequence |
| --- | --- | --- |
| `dayu/host/engine_ingest.py::_execute_reactive_compaction` | accepted compact先写`CONTEXT_COMPACTED`，随后返回`_ReactiveRecoveryAccepted` | exact post-compact candidate只能在accepted fact与memory catch-up之后形成 |
| `dayu/host/engine_ingest.py::_StartReactiveRecoveryOperation` | recovery start读取`RECOVERING` Run并调用`start_recovery_run_with_starting_attempt_in_transaction` | reactive dispatch不是unstarted `ACCEPTED/QUEUED` flow |
| `dayu/host/durable/run_transition.py::fail_unstarted_run_in_transaction` | 只拥有未启动Run failure语义 | 不能收口`RECOVERING` |
| `dayu/host/durable/run_transition.py::FailRecoveringRunInput` / `fail_recovering_run_in_transaction` | typed input必填`context_compaction_failed_event_id`，RUN_FAILED语义绑定compact failed fact | accepted post-compact hard不能无损复用 |
| revised plan §6.5 / §8.2 | accepted post-compact不得追加矛盾failed fact；若existing failure owner不能收口则stop | 禁止在`engine_ingest.py`局部直写state/event或伪造ref |

没有发现可在当前allowlist内复用的另一条`RECOVERING -> FAILED` typed transition。
`lose_recovering_run_in_transaction`属于startup orphan的`RUN_LOST`语义，不是context
hard failure owner，不能挪用。

## 3. Resumed partial changes

以下修改均为当前 partial implementation，尚未完成最终 tests/type/coverage，不应进入
review或commit：

1. `dayu/host/compact_payload.py`
   - strict parser成为raw `source_boundary_refs`唯一reader；
   - 非空、非空字符串、全局唯一校验；
   - typed投影`current_input_ref`与`compacted_source_refs`；
   - `[current_input_ref]`合法表示无covered material。
2. `dayu/host/memory.py`
   - accepted compact按`event_id + source_refs`过滤selected recent；
   - current input优先保留；
   - covered older raw删除，uncovered protected raw保留；
   - existing bounded policy之后同源重建recent evidence；
   - RunInput未新增coverage filter。
3. `dayu/host/context_budget.py`
   - producer与`ContextSizingResult.__post_init__`复用同一stage-aware
     pressure/action helper；
   - ordinary normal/soft/hard为allow/compact/block；
   - post-compact/fallback normal/soft/hard为allow/allow/block；
   - soft pressure未改写为normal。
4. `dayu/host/dispatch.py`
   - proactive post-compact/fallback候选使用封闭
     `pending_dispatch | terminal_notice` private outcome；
   - hard在同一transaction复用`fail_unstarted_run_in_transaction`；
   - commit后交付typed terminal notice；
   - soft直接dispatch且不启动第二次proactive operation。
5. `dayu/host/run_input.py`
   - 修正logical `input_snapshot_digest` owner：只覆盖messages、selected tools、
     policy与request semantics；
   - source cursor/ref/governance sequence只属于candidate projection lineage；
   - 同一logical snapshot恢复既有proactive operation时不因新manifest event改变
     estimator/input identity。
6. tests
   - compact parser current/covered roles与invalid matrix；
   - memory covered/current/uncovered/new delta/recent evidence及
     rebuild/incremental/persisted reload一致性；
   - 9-cell stage matrix及`__post_init__`反例；
   - partial dispatch fixture按complete candidate阈值语义迁移。

`CONTEXT_BUDGET_EVALUATED`、anchor resolver、signed delta、provider usage prediction与
Issue #119 correlation仍未进入Slice 1。

## 4. Validation evidence

### 4.1 Tests

恢复前owner baseline：

```bash
source .venv/bin/activate
pytest -q tests/host/test_context_budget.py \
  tests/host/test_context_compact_events.py \
  tests/host/test_memory_projection.py \
  tests/host/test_memory_repair.py --maxfail=30 --tb=short
```

结果：`152 passed`。

新增parser/memory/stage tests后同一suite结果：`169 passed`。

dispatch全文件中间结果：

```bash
source .venv/bin/activate
pytest -q tests/host/test_dispatch_scheduler.py --maxfail=30 --tb=short
```

结果：`90 passed, 12 failed`。其中：

- 已修复/局部复验：governed-start helper返回类型、complete candidate阈值fixture、
  proactive resume logical digest漂移；
- reactive recovery三项失败直接暴露“新Attempt已有state但缺pre-start frozen
  candidate/manifest”，继续正确修复必须让reactive recovery消费同一exact candidate
  与stage action，进而触发本artifact blocker；
- 其余fixture migration与memory catch-up failure expectation尚未收敛。

定点复验：

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_dispatch_scheduler.py::test_second_proactive_compact_uses_previous_view_without_old_raw_replay \
  'tests/host/test_dispatch_scheduler.py::test_proactive_manifest_crash_resumes_deterministic_next_stage[1-root_repair]' \
  --tb=short
```

结果：`2 passed`，证明logical input digest不再因governance event cursor变化而使同一
snapshot启动/转入另一operation。

### 4.2 Type check

scoped命令：

```bash
source .venv/bin/activate
python -m pyright \
  dayu/host/dispatch.py dayu/host/context_budget.py \
  dayu/host/compact_payload.py dayu/host/memory.py \
  tests/host/test_context_budget.py \
  tests/host/test_context_compact_events.py \
  tests/host/test_memory_projection.py
```

结果：`0 errors, 0 warnings, 0 informations`。

命中stop condition后未运行full
`python -m pyright dayu/ tests/ utils/`，不能声明full pyright通过。

### 4.3 Coverage

focused suite尚未完成，未生成可接受的per-file coverage。所有新增/修改production
文件coverage状态为`not measured / blocked`，不能声明达到`>=80%`。

### 4.4 Static / diff

- `git diff --check`：通过。
- `git diff --exit-code -- dayu/host/durable/run_transition.py`：通过，零diff。
- 当前production/tests diff均在 revised Slice 1 allowlist内。
- `docs/host/issues-implementation-control.md`为既有Controller diff，本Agent未编辑。
- 未commit、push或创建PR。

## 5. README audit

已读取：

- `dayu/host/README.md`的`Agent更新约束【必须遵守】`；
- `tests/README.md`的`README 更新边界`。

当前实现被stop且尚无可交付稳定contract、focused suite/full pyright/coverage均未完成，
因此不把partial过程状态写入README。本轮README零diff；Controller解除blocker并完成
Slice 1后，仍需按plan §11更新Host稳定owner contract与tests现有验证入口。

## 6. Diff scope

本轮新增允许production diff：

- `dayu/host/compact_payload.py`
- `dayu/host/memory.py`

本轮继续修改既有partial allowed production：

- `dayu/host/context_budget.py`
- `dayu/host/dispatch.py`
- `dayu/host/run_input.py`

本轮新增/继续修改allowed tests：

- `tests/host/test_context_budget.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_dispatch_scheduler.py`

worktree中其它Slice 1 partial production/tests来自blocked implementation并继续保留。
唯一新增交付artifact为本文件。

## 7. Blocking question and required adjudication

Controller需要选择并冻结以下之一；implementation agent不能自行扩大权限：

1. 扩充Slice 1 production allowlist，允许在`dayu/host/durable/run_transition.py`
   增加不依赖`CONTEXT_COMPACTION_FAILED`的typed
   `RECOVERING -> RUN_FAILED` context-hard closeout input/transition，并补owner tests；
2. 明确提供另一个现有typed owner及其exact语义，证明accepted
   `CONTEXT_COMPACTED`之后可以无矛盾收口reactive post-compact hard；
3. 修订Slice 1目标，明确reactive recovery不消费exact stage-aware sizing/action。
   该选择会违反当前complete candidate与all dispatch-relevant stage目标，不能由本
   Agent默认采用。

禁止的局部方案：

- 把accepted compact event id写进名为
  `context_compaction_failed_event_id`的字段；
- accepted后追加矛盾`CONTEXT_COMPACTION_FAILED`；
- 在`engine_ingest.py`直接写Run terminal row/event绕过transition owner；
- 用`RUN_LOST` startup orphan语义冒充context hard failure；
- reactive recovery仍创建无candidate/manifest的新Attempt；
- 跳过reactive exact sizing而声称Slice 1 complete。

## 8. Residual risks

| risk | classification / owner |
| --- | --- |
| reactive recovery新Attempt当前缺pre-start candidate/manifest，worker fail closed | blocking；Controller需裁决recovery start/terminal owner |
| reactive accepted compact后exact hard无合法terminal owner | blocking；本artifact核心stop condition |
| dispatch仍有未收敛fixture、memory catch-up与reactive tests | resumed Slice 1 after adjudication |
| manifest v2 rejection/continuation/rollback/integration matrix未完整 | resumed Slice 1 after adjudication |
| full focused suite/full pyright/per-file coverage/static audits未完成 | resumed Slice 1 after adjudication |
| README稳定contract与测试入口未同步 | resumed Slice 1 completion audit |

除上述blocking owner question外，没有新增未分类risk。当前状态不是ready for dual code
review。
