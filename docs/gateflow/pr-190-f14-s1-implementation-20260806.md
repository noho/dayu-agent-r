# PR 190 F14 S1 implementation record

## Gate metadata

- gate: `implementation`
- work unit / slice: F14 / S1 Host accepted coverage frontier
- accepted plan commit / implementation base: `b222b8b064f096d899a9de708e45cd1fb6e732e6`
- branch: `codex/interactive-oracle`
- implementer: AgentCodex
- Controller ownership: scope owner、finding adjudication 与 gate transition 均保留给 Controller
- status: code review accepted findings fix complete，待原 reviewers窄re-review与Controller裁决
- commit / push: 未执行
- artifact path: `docs/gateflow/pr-190-f14-s1-implementation-20260806.md`

## First-principles verdict and owner

F14 动机成立。accepted terminal 的 EventLog sequence 只证明 accepted fact 的提交位置，不证明其之前所有 raw material 都已进入 immutable source boundary。消费语义的唯一真源是每条 strict `ContextCompactedSemanticPayload.compacted_source_refs`，即 represented / omitted exact partition 覆盖的 source refs；`current_input_ref`、protected / unselected raw groups 不属于本次消费。

修复 owner 明确为 `dayu.host.compact_material` 的 EventLog-backed material projector。未修改 downstream renderer、Memory rule、Engine、provider、prompt、UI、Oracle 或 scenario；未新增 durable cursor、schema 或 public contract。

## Red evidence before production change

先只新增 `tests/host/test_compact_material.py::test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix`。fixture 使用真实 canonical user / answer event refs，以及与 producer EventLog id 不同的 opaque accepted evidence id。

命令：

```text
source .venv/bin/activate && pytest -q tests/host/test_compact_material.py::test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix
```

旧实现结果：`1 failed`。直接失败值：

```text
assert view.post_compact_delta_start_sequence == protected_start_sequence
AssertionError: assert 11 == 5
```

`11` 是 accepted terminal sequence `10` 的 `+1`；`5` 是未进入 accepted boundary 的 protected Run group 最早 canonical material sequence。这直接证明旧 `_post_compact_delta_start_sequence` 把 ledger terminal 位置误作 consumption frontier。

同一测试在 production owner 实现后结果为 `1 passed`，并增加关闭/reopen durable store 后 view exact 相等断言，覆盖 restart。

## Code review fix iteration

执行依据：`docs/gateflow/pr-190-f14-code-review-adjudication-20260806.md`。本轮只修复accepted findings C1 / M1 / M2 / M3 / D2 / D3；明确不采纳rejected AgentDS F1，未把`group[0].event_sequence`改成重复的`min()`计算，也未新增schema、cursor、fallback或public contract。

### C1 — `run_id=None` metadata proof

先只新增`test_pre_dispatch_consumed_user_without_run_id_cannot_prove_atomic_group`，构造真实canonical `USER_INPUT_ACCEPTED` row，其ref已进入accepted `compacted_source_refs`但`run_id=None`。旧实现单测直接失败：

```text
source .venv/bin/activate && pytest -q tests/host/test_compact_material.py::test_pre_dispatch_consumed_user_without_run_id_cannot_prove_atomic_group
```

结果：`1 failed`，直接证据为`Failed: DID NOT RAISE <class 'dayu.host.durable.errors.HostDurableError'>`。这证明metadata fast path把缺失Run identity的user ref命中静默升级成whole-group proof，绕开typed projection与`_atomic_material_units` fail-closed。

production修复只收紧`_conservative_unconsumed_row_start_sequence`：`group_consumed`现在同时要求非空`run_id`、唯一user anchor及anchor ref已消费；`run_id=None`保守进入typed projector，随后由既有atomic owner拒绝缺失turn group identity。修复后C1、partial atomic与protected suffix组合验证`3 passed`；最终逐finding focused为`5 passed`。

### M1 — 三轮 frontier owner proof

将原“两轮terminal、只观察最终view”fixture改成三轮逐阶段owner test。每轮都追加真实user / answer / accepted evidence atomic group与accepted terminal，不固定sequence常量，而是从实际append row取得期望frontier；每阶段显式断言：

- 三个frontier严格单调递增；
- raw suffix按`(event_sequence, event_sub_index)`保持canonical order；
- cumulative consumed refs与raw suffix refs互斥，二者并集精确覆盖该阶段全部eligible material refs；
- 每个集合内部无duplicate，计数相加等于eligible refs总数，因而exact-once、no-gap、no-duplicate。

单测`test_pre_dispatch_cumulative_accepted_chain_advances_only_complete_groups`结果：`1 passed`。

### M2 — correction aging / second replacement / reconnect

新增最小Host integration `test_correction_ages_into_second_accepted_replacement_and_reconnects_from_memory`，只复用production accepted evidence envelope、material selector、Context Governance acceptance、strict terminal parser、Conversation Memory projection、durable store与ordinary RunInput builder：

1. 旧口径与correction group分别写入真实`TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED`，两条result都携带production `AcceptedEvidenceEnvelope`；旧ref为`evidence:event-aging-old-evidence`，新ref为`evidence:event-aging-correction-evidence`，二者不相等。
2. 首轮production selector在`selected_recent_window_turn_floor=2`下选择完整旧口径user / answer / evidence group，并把bridge / correction两组完整标记为`protected_recent_raw_floor`。首次accepted replacement产生`Old revenue was 100.` EvidenceFact且只绑定旧ref；strict terminal与Memory fact都记录首terminal provenance。correction user / answer / evidence仍在selected recent window。
3. 追加四轮更新后，同一production selector选择bridge / correction及较早两组newer groups，同时只把最新两组标记`protected_recent_raw_floor`，证明correction完整离开floor与bounded recent window。第二条正式accepted terminal exact消费该prefix并产生`Corrected revenue was 120.` EvidenceFact；proposal的`retained_previous_evidence_fact_labels`为空，新fact只绑定新ref，明确不retain、不借用旧ref。
4. 第二terminal提交后重新从EventLog strict读取首terminal，typed semantics与提交前完全相等，旧fact仍绑定旧ref；第二terminal、Memory snapshot的new fact与provenance都绑定第二terminal / 新ref，旧ref没有被重写到new fact。
5. 新ordinary durable Run的material view不再包含correction raw group，但保留最新两组protected raw frontier；关闭并重开SQLite/artifact store后，durable Memory仍只含new fact+新ref+第二terminal provenance，ordinary RunInput只出现正式correction claim / summary一次，不呈现old fact或raw correction user / answer / evidence。

Controller evidence audit指出初版summary-only fixture不足后，先加入真实evidence atom与raw evidence absence断言；仅aging两轮时测试直接失败于`assert all(correction_evidence_text not in content for content in contents)`，证明correction evidence仍在bounded recent window。最终fixture不是删除断言或修改UI/Memory fallback，而是按production policy追加四轮真实newer groups，使correction真正退出recent window，再由第二accepted replacement接管，结果`1 passed`。

测试没有调用UI fallback、没有伪装production CLI/scenario，也没有用fixture默认ref重建语义。`_material_view_run_for_input_event`只为真实EventLog input row提供只读material owner边界；最终ordinary Run / Attempt及RunInput均由durable production owner创建、重开并读取。21.7%无证据约束继续复用既有owner test，本fixture不伪造无证据EvidenceFact。

### M3 / D2 / D3 — 时序、ownership cross-reference与docstring

- M3：`docs/host/design.md`改为“build期间”分阶段proof：accepted chain读取时由`_accepted_compact_chain_before_current_input` / `_validate_accepted_compact_entry_references`校验exact refs；material projection时由`_conservative_unconsumed_row_start_sequence` / `_unconsumed_atomic_material_blocks`校验frontier与atomic prefix。
- D2：metadata helper中文docstring与行内注释明确whole-group selector proof owner为`turn_group_memberships_for_material_blocks`，本helper只做metadata-first保守裁剪，最终all-or-none / prefix proof必须复用`_atomic_material_units`；Host design / README同步明确`run_id=None`不能跳过。
- D3：删除纯转换helper `_accepted_compacted_source_refs`中宽泛且错误的`:raises Exception: 不主动抛出异常。`。

`tests/README.md`未更新：本轮没有改变测试层级、运行方式或维护规则。`docs/engine/design.md`再次truth check，无需修改；F14仍不改变Engine边界。

## Implementation decisions

1. 在同一 read transaction 中读取当前 input 前、当前 Session 全部 canonical `CONTEXT_COMPACTED`，按 sequence 升序逐条 resolve + strict parse 一次，形成私有 typed chain entry。
2. latest replacement 与 latest accepted evidence aggregate 只从最后一条 typed entry 投影；cumulative consumption 只按 accepted terminal / boundary order累积每条 `compacted_source_refs`。
3. 每条 accepted terminal 的 `current_input_ref` 必须 exact 指向同 Session、更早的 canonical `USER_INPUT_ACCEPTED`。任一 `PREVIOUS_*` boundary source ref 必须 exact 指向同 Session、更早的 canonical `CONTEXT_COMPACTED`；missing、wrong type/class/session、self 或 forward ref fail closed。
4. raw side先读取当前 input 前全部 relevant canonical row metadata，仅包含 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`。以每个完整 `run_id` group 唯一 user anchor 是否在 cumulative consumed refs 中证明可跳过的已消费prefix；无anchor、重复anchor或 `run_id=None` 不能在metadata阶段跳过。
5. 只对保守suffix运行typed payload/evidence projector。删除 latest represented evidence early filter，避免在atomic proof前隐藏已消费evidence block。
6. 对suffix复用 `_sorted_material_blocks` + `_atomic_material_units`：block refs必须all-in或none-in，unit blocks必须同一消费状态，units必须为consumed prefix + unconsumed suffix；partial/mixed/non-prefix均抛 `HostDurableError`。
7. 对外 `post_compact_delta_start_sequence` 从最终保留的第一条material block派生；无保留block时等于current input sequence。latest terminal id/sequence继续只表示provenance。

## Changed files

- `dayu/host/compact_material.py`
  - strict accepted chain、current/previous exact back-reference validation；
  - cumulative accepted consumption；
  - metadata-first conservative raw frontier；
  - suffix atomic exact proof；
  - 删除 latest represented evidence early filter。
- `tests/host/test_compact_material.py`
  - F14 red→green regression、cumulative accepted chain、共享reactive current anchor、partial atomic corruption、non-accepted events、restart、opaque evidence id、current/previous invalid refs与合法previous rolling provenance；
  - coverage fixture显式接收真实current input ref与per-label source refs。
- `tests/host/test_run_input_builder.py`
  - coverage-sensitive compact fixtures改用真实canonical current/source refs；
  - M2用两条真实accepted evidence atom证明旧/new EvidenceFact ref与terminal provenance同源，并覆盖aging、第二replacement、reopen Memory / ordinary RunInput。
- `tests/host/test_dispatch_scheduler.py`
  - previous accepted compact fixture改用真实user/answer/evidence/current refs；复用既有repair、failure、fallback、stale/late状态机测试。
- `docs/host/design.md`
  - 区分terminal provenance、accepted consumption与derived material frontier；说明protected raw生命周期、previous/current exact refs及early-filter禁令。
- `dayu/host/README.md`
  - 按Host开发者读者边界更新accepted coverage frontier实现概览。
- 本 artifact。

未修改 `docs/engine/design.md`。truth check确认其现有设计明确声明Engine不知道compact schema、五类Memory、coverage、repair、artifact或Host cursor，F14未改变该边界。

未修改 `tests/README.md`：测试分层、命令与维护规则未变化。未修改根README或`dayu/README.md`：无用户入口、CLI参数或分层装配变化。

## Validation

### Focused red→green and owner tests

- 强制red：上述单测旧实现 `1 failed`，直接值 `11 != 5`。
- 首次green：同一单测 `1 passed`。
- final owner file：`tests/host/test_compact_material.py` 随受影响union通过；覆盖accepted chain、non-accepted diagnostics、restart、opaque evidence id、partial corruption、current / previous strict refs。

### Affected union

```text
source .venv/bin/activate && pytest -q \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_compaction_cancellation_scope.py
```

结果：`341 passed in 3.79s`。

该union复用既有scheduler/operation/cancellation owner tests，覆盖initial accepted、repair accepted、tier 1–3 accepted、attempt rejected、repair exhausted、failed fallback、cancel、stale/late与recovery路径；没有复制状态机到material单测。

### Changed-file coverage

```text
source .venv/bin/activate && pytest -q \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  --cov=dayu.host.compact_material --cov-report=term-missing
```

结果：`188 passed`，`dayu/host/compact_material.py` line coverage `85%`，达到单文件 `>=80%` 目标。

### Types and static checks

- focused pyright：`0 errors, 0 warnings, 0 informations`。
- full `pyright`：`0 errors, 0 warnings, 0 informations`。
- focused Ruff（全部changed Python files）：`All checks passed!`。
- full Ruff：失败，报告89项既有错误，全部位于本轮未修改文件；changed files无Ruff错误，未越权清理范围外基线。
- `python -m compileall -q dayu tests utils`：通过。
- 全仓 `*.json` 逐文件 `python -m json.tool` parse scan：通过。
- `git diff --check`：通过。
- `git diff --exit-code -- dayu/config config tests/cli/test_smoke_cli_init_provider_matrix.py`：通过，证明本轮未修改prompt/config/frozen publication Oracle相关文件。

### Full pytest

结果：`6764 passed, 10 skipped, 6 deselected, 4 failed, 3 warnings in 235.22s`。

4个failure均来自 `tests/cli/test_smoke_cli_init_provider_matrix.py` 的checked-in frozen publication manifest与当前 `config/prompts/**` digest不匹配。失败路径与本轮changed files无交集，且上述explicit diff check确认本轮未修改config/prompt/manifest/Oracle；因此分类为范围外既有publication baseline inconsistency，不通过更新Oracle或放宽断言补救。

### Fix iteration final validation

逐finding focused：

```text
source .venv/bin/activate && pytest -q \
  tests/host/test_compact_material.py::test_pre_dispatch_consumed_user_without_run_id_cannot_prove_atomic_group \
  tests/host/test_compact_material.py::test_pre_dispatch_cumulative_accepted_chain_advances_only_complete_groups \
  tests/host/test_compact_material.py::test_pre_dispatch_partial_atomic_coverage_fails_closed \
  tests/host/test_compact_material.py::test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix \
  tests/host/test_run_input_builder.py::test_correction_ages_into_second_accepted_replacement_and_reconnects_from_memory
```

结果：`5 passed in 0.47s`。

受影响union：

```text
source .venv/bin/activate && pytest -q \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_compaction_cancellation_scope.py
```

结果：`343 passed in 4.92s`。该union继续复用既有accepted / repair / non-accepted / failure / cancel / stale-late / recovery状态机tests，没有复制状态机到M2 fixture。

changed-file coverage：

```text
source .venv/bin/activate && pytest -q \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  --cov=dayu.host.compact_material --cov-report=term-missing
```

结果：`190 passed in 2.15s`；`dayu/host/compact_material.py`为`1080 statements / 160 missed / 85%`。

focused static / diff checks：

```text
source .venv/bin/activate && pyright \
  dayu/host/compact_material.py \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_dispatch_scheduler.py
```

结果：`0 errors, 0 warnings, 0 informations`。

```text
source .venv/bin/activate && ruff check \
  dayu/host/compact_material.py \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_dispatch_scheduler.py
```

结果：`All checks passed!`。

`git diff --check`通过；`git diff --exit-code -- dayu/engine docs/engine dayu/config config dayu/service dayu/ui dayu/fins tests/cli/test_smoke_cli_init_provider_matrix.py`通过，证明未修改Engine、Oracle、scenario、provider、UI、config/prompt或Fins。最终HEAD仍为`b222b8b064f096d899a9de708e45cd1fb6e732e6`，未commit、未push。

## Schema, public contract and LLM-facing impact

- schema / DB migration：无。
- public contract / public export：无。
- durable cursor / second truth：无。
- compatibility / fallback / loose parser：无。
- LLM-facing schema、prompt或文本：无修改。
- latest `represented_evidence_refs` 语义不变，仍只表示latest replacement逐fact evidence refs union；未改作cumulative consumption。

## Residual risks and uncovered areas

- accepted chain strict parse成本随Session accepted terminals数量增长；分类：accepted plan明确接受的当前slice权衡。raw payload解析已由metadata prefix proof收窄；不得用第二cursor或terminal估算替代。
- real production CLI / provider observation未在本implementation gate运行；分类：交给Controller后续formal observation / adjudication流程。deterministic owner与integration tests已证明frontier，不把provider非确定性混入owner correctness。
- 全仓frozen publication manifest 4项失败；分类：范围外既有baseline inconsistency，owner为publication/config work unit，不得在F14修改Oracle。
- 全仓Ruff 89项既有错误；分类：范围外baseline，changed files focused Ruff通过。
- formal scenario / accepted Oracle状态：本slice未修改，仍由Controller / Oracle owner裁决。

没有未分类residual risk，也没有需要扩张accepted owner、schema或public contract的blocking question。

## Completion and next entry point

S1 implementation完成，worktree保持未提交、未push。下一入口由Controller执行scope audit并进入Gateflow `code review`；AgentCodex不自行裁决gate、不创建commit、不修改PR状态。
