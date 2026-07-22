# WU-CTX-04 Slice 2 Final Acceptance（Controller）

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`2/3`
- accepted baseline：`eda1d70eb2c2252570807e1fcdb1cd234a5aae7a`
- implementation artifact：`docs/reviews/wu-ctx-04-slice-2-implementation-codex.md`
- initial review adjudication：
  `docs/reviews/wu-ctx-04-slice-2-code-review-controller-adjudication.md`
- review-fix artifact：`docs/reviews/wu-ctx-04-slice-2-review-fix-codex.md`
  （SHA-1 `8c4ddb7e4f004e490b58d75c830bcb3206c27c9b`）
- AgentMiMo re-review：`docs/reviews/wu-ctx-04-slice-2-re-review-mimo.md`
  （SHA-1 `3446cd76293b41699703fcfbe81f5ed852002a4e`）
- AgentDS re-review：`docs/reviews/wu-ctx-04-slice-2-re-review-ds.md`
  （SHA-1 `8d4093d89f7d1e0a71385bb9514e2cd5937662f7`）
- Controller decision：`pass`
- blocking open questions：None

## Acceptance judgment

Slice 2 已完成 public Session attachment、target-only attachment recovery、scheduler-before-
unlock lifecycle barrier、periodic owned-session reconciliation、proactive durable
single-operation/crash resume、reactive required-range机械适配、PayloadStore manifest owner收敛
与旧 proactive count config删除的联合 checkpoint。

初次 code review 后，Controller 以直接控制流证明 zero-proactive-request early return 会把
orphan/unknown durable state错误转换为`ABSENT -> CREATE_NEW`，因此接受
`CTRL-S2-001`为High/blocking finding。AgentCodex已在 durable projection owner修复，
两路独立re-review和Controller复读均确认：malformed state fail closed，合法reactive-only
history保持隔离，unsafe operation identity不再借用reactive id，dispatcher无安全id时只通过
既有governance failure收口Run且没有compaction/provider/Attempt副作用。

当前没有剩余blocking/should-fix finding；Slice 2 可以形成受保护accepted commit并作为
Slice 3 implementation baseline。

## Accepted finding closure

### CTRL-S2-001 — fixed

- `_project_state(...)` 不再在zero proactive request时提前返回；所有相关非-request rows
  都经过strict payload/manifest、known owner、sequence与identity验证。
- 只有严格验证属于reactive request owner的rows，以及明确非compactor runner-call rows，
  才从proactive projection隔离。
- orphan rejection/failed terminal/compactor manifest、reactive+unknown row与malformed request
  均投影为`INVALID`；合法reactive-only仍为`ABSENT`。
- INVALID fallback id只来自复用同一strict request parser验证通过的proactive request；
  malformed/reactive request不提供id。
- dispatcher无安全id时调用`_fail_unstarted_in_transaction(...)`；Run=`FAILED`，provider、
  Attempt、新request、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED`均为0增量。

### F-DS-01 — fixed

Protocol/registry docstring现准确描述production真实路径：ACTIVE RW直接取lease；RECOVERING
RW只在root recovery lease存续时允许target-recovery wake产生的嵌套work lease。直接owner
test覆盖`RECOVERING+0 -> reject`、root存续时nested success、root释放后再次reject。

### MIMO-REVIEW-001 — accepted portion fixed

`_close_owned_resources` docstring已澄清mandatory失败立即阻断后续owner close，只有mandatory
阶段完整成功后才进入best-effort owner cleanup。Controller拒绝了原reviewer提出的
`release_host_close()`失败后继续关闭actor/store的行为修改；本fix没有改变close控制流或
`mark_closed()`条件。

### F-DS-02 — retracted / closed

projection read与prepare write位于同一个`run_write(_operation)` transaction；不存在原finding
声称的跨transaction TOCTOU。

## New observation adjudication

### N-DS-01 — rejected，evidence-invalid

DS声称非-request row缺少顶层`session_id/run_id`校验。实际`_project_state`第一遍循环在判断
`row.event_type`之前，对**每一行**执行：

```python
if row.session_id != session_id or row.run_id != run_id:
    raise HostDurableError(...)
```

因此request与非-request rows均已直接验证；不增加重复第二遍检查。

### N-DS-02 — rejected，no actionable gap

`invalid_reason`保存稳定异常类别而非durable原文，不参与dispatcher业务决策，也没有public/
LLM-facing consumer。把它扩展为新的细粒度enum会新增未被design/plan要求的诊断contract；
当前typed phase/decision与raw terminal evidence已完整满足fail-closed语义。

### MiMo observations — closed

- “mandatory步骤从try/except移出是本fix行为变化”的时间归因错误：该结构属于Slice 2初始
  implementation；本次review-fix只改docstring。用accepted Slice 1 baseline比较无法隔离fix。
- safe-id helper未来可能新增异常类型、orphan manifest集成测试依赖真实scheduler等均为
  speculative/test-maintenance observation，不是当前correctness或ownership finding。

## Validation evidence

### Implementation gate

- plan §8.2 matrix：`639 passed, 1 skipped, 6 deselected`
- plan §8.3 matrix：`579 passed, 1 skipped`
- affected surface `tests/host tests/runtime tests/service tests/cli`：
  `3520 passed, 8 skipped, 6 deselected`
- full pyright：`0 errors, 0 warnings, 0 informations`
- touched production per-file coverage：全部`>=80%`（最低CLI 81%）
- stale proactive count/startup recovery/global non-terminal query checks：预期归零；
  `read_cancelling_runs`仅保留accepted Slice 3 owner路径
- repository ruff baseline未新增/扩散；`git diff --check`通过

### Review-fix / re-review gate

- Controller focused复验：`153 passed`
- AgentCodex full Host：`2133 passed, 1 skipped, 6 deselected`
- AgentMiMo focused：`138 passed`；full Host：
  `2133 passed, 1 skipped, 6 deselected`；full pyright=`0 errors`；ruff/diff check通过
- AgentDS focused：`138 passed`；full Host：
  `2133 passed, 1 skipped, 6 deselected`；full pyright=`0 errors`
- final `git diff --check`：pass

## Scope / ownership audit

- 三次scope amendment均有直接baseline消费者/owner证据，限定为机械迁移或已存在owner缺陷；
  没有改变design、public contract、schema、state machine或Slice 3 boundary。
- `dayu.runtime`新增strict-native primitive保持layer-neutral，无Host/Engine/Service/UI/Fins反向依赖。
- attachment access truth只由registry产生；scheduler只消费窄port/lease，不从mutex文件、origin、
  event顺序或fallback推断资格。
- proactive operation truth只由context event contract与`proactive_compaction` projection产生；
  dispatcher不解析raw rows。
- manifest storage owner收敛为PayloadStore；没有artifact双写或reader fallback。
- 未引入兼容alias/default/wrapper、`hasattr/getattr`补偿或测试私有production seam。
- README同步按accepted plan继续由Slice 3统一处理；当前fix不改变用户可见API/工作流。

## Residual risk classification

- workspace-wide `read_cancelling_runs` periodic path：`covered-by-later-approved-slice`，唯一owner
  为WU-CTX-04 Slice 3 execution-owner cancel reconcile；Slice 3验收必须归零。
- provider process crash不承诺外部side effect exactly-once：accepted non-goal；durable prepared
  manifest保守消耗attempt并从下一schedule stage恢复，不在本WU引入distributed transaction。
- Windows strict-native mutex：实现与unit contract已覆盖，当前执行环境只完成POSIX验证；属于
  cross-platform environment residual，不改变Slice 2 acceptance。
- consumer task exception observation：pre-existing baseline且未证明形成Slice 2 correctness
  regression；不把未裁决的未来改造扩入WU-CTX-04。
- unclassified residual risk：None。

## Gate decision

`pass`。Slice 2 implementation、review-fix与双路re-review全部闭环；允许创建
`gateflow: accept WU-CTX-04 slice 2`受保护本地commit。commit后进入Slice 3
execution-owner cancel reconcile、README/product integration与final verification。
