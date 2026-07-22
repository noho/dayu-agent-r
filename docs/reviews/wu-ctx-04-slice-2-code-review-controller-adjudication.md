# WU-CTX-04 Slice 2 Code Review Controller Adjudication

## Gate metadata

- work unit：`WU-CTX-04`
- slice：`2/3`
- accepted baseline：`eda1d70eb2c2252570807e1fcdb1cd234a5aae7a`
- reviewed range：accepted Slice 1 至当前未提交 Slice 2 working tree
- implementation artifact：`docs/reviews/wu-ctx-04-slice-2-implementation-codex.md`
  （SHA-1 `2a65981a5450866c5bde8a39fd22617b03c25d4f`）
- scope amendment：`docs/reviews/wu-ctx-04-slice-2-scope-amendment-controller.md`
  （SHA-1 `8b0aca765f9b9b266ea8989cb83e397233a14d91`）
- AgentMiMo review：`docs/reviews/code-review-20260722-161504-mimo.md`
  （SHA-1 `be242cecc515e2c97e2b1588f4ce236083a84234`）
- AgentDS review：`docs/reviews/code-review-20260723-000000-ds.md`
  （SHA-1 `6a8fe8b6eab0f05845834536aa912774b8bc5217`）
- Controller decision：`needs-fix`
- blocking open questions：None

## First-principles judgment

Slice 2 的主体实现已经形成 attachment、target recovery 与 proactive durable
single-operation 的联合闭环；两路 reviewer 的测试与类型检查证据也确认主体路径稳定。
但是当前 proactive projection 在没有已验证 proactive request 时提前返回
`ABSENT`，会跳过同 Run 其它 compaction rows 的 owner/identity/schema 校验。
这不是可忽略的诊断问题：`ABSENT -> CREATE_NEW` 会授权写入 request，并可能触发
provider 外部副作用。因此 durable corruption/mismatch 被错误转成新的 side effect，
违反 accepted plan 的 fail-closed 状态机；Slice 2 不能直接接受。

正确 semantic owner 是 `dayu.host.proactive_compaction` 的 durable projection。
dispatcher 只应消费 projection 的 typed decision；不得在 dispatcher 用 raw row、
默认 operation id 或兼容分支重新解释损坏历史。

## Findings adjudication

### CTRL-S2-001 — accepted，High / blocking

**问题**：`_project_state(...)` 第一遍只扫描 request rows，随后在
`len(requested_rows) == 0` 时直接返回 `_absent_state()`。第二遍对 compactor
manifest、rejection、`CONTEXT_COMPACTED`、`CONTEXT_COMPACTION_FAILED` 的 strict
owner/sequence/payload 校验完全未执行。

**可执行后果**：

1. 无 request 但存在孤立 compactor manifest/rejection/terminal 时，被投影为
   `ABSENT`，下一次 governance 可创建新 proactive request并调用 provider。
2. 只有合法 reactive request、但另有 unknown-operation row 时，同样被投影为
   `ABSENT`；unknown row 被静默吞掉。
3. request 校验失败时，`_earliest_requested_event_id(...)` 不区分 trigger owner。
   如果最早 request 是 reactive，INVALID state 会错误携带 reactive operation id；
   dispatcher 随后可能向 reactive operation 追加 proactive failed terminal。
4. INVALID state 没有可安全识别的 proactive operation id 时，dispatcher 当前抛
   `RuntimeError`，没有按 accepted plan 使用既有 governance failure 收口 Run。

**裁决**：接受为 blocking finding。AgentDS 将孤立 durable row 解释为“没有 operation，
所以 CREATE_NEW 正确”，但 EventLog row 本身就是状态机证据；proactive projection 的职责
正是验证它能否归属已验证 owner。accepted plan 明确要求 malformed/mismatched state
fail closed、provider 0 调用，并在无法安全构造 fallback 时通过 governance failure
终结 Run。只有完全验证为 reactive owner 的 rows 才能从 proactive projection 隔离；
unknown/orphan row 不能获得同等待遇。

**修复边界**：

- projection 即使没有 proactive request，也必须验证所有相关非-request rows；只忽略
  已通过 strict request/identity/sequence 校验并确认属于 reactive operation 的 rows，
  以及明确不是 compactor proposal 的 runner-call rows。
- 合法 reactive-only request/history 仍投影为 `ABSENT`。
- orphan/unknown/malformed/mismatched row 投影为 `INVALID`，不得创建 request、不得调用
  provider。
- INVALID fallback 只能使用可安全识别的 proactive operation id；不得使用 reactive id。
  没有安全 proactive id 时，不追加 compaction terminal，直接由既有 governance failure
  owner终结 Run。

### F-DS-01 — accepted，Low / should-fix

`SessionNewWorkAccessPort.try_acquire_new_work_lease` 与 registry implementation 的
docstring 声称只允许 `ACTIVE RW`，但 production target-recovery 的 committed-batch
wake 会在 root recovery lease 仍持有时调用 scheduler wake，继而在
`RECOVERING + new_work_lease_count > 0` 下取得嵌套 work lease。该行为符合 accepted
plan“只有本次 target recovery 产生的 scheduler reconciliation 可消费 lease”的
设计，问题是 owner contract 文本与 direct owner test 缺口，不是行为错误。

修复限定为：同步 Protocol/implementation 中文 docstring，并增加 registry owner test，
证明 `RECOVERING + 0 lease` 拒绝、持有 root recovery lease 时允许嵌套 lease，释放后恢复拒绝。

### MIMO-REVIEW-001 — partially accepted as documentation correction；behavioral fix rejected

MiMo 正确指出 `_close_owned_resources` 的 docstring“首个错误在全部 owner cleanup 尝试后
传播”过宽；但建议把 `release_host_close()` 包入 best-effort 后继续关闭 store/actor 等
后续 owner，与 accepted plan 的固定 mandatory 顺序冲突。

`release_host_close()` 是 scheduler lifecycle 成功后的 mandatory attachment-release
阶段；它自己已继续尝试全部 record release并保留首错。该阶段失败时 registry 仍保留
未完成 record，Host 必须保持 `CLOSING`，不能进入依赖 mandatory 阶段完成的后续 owner
shutdown/`close_done`/`mark_closed()`。否则重复 close 会在 actor/store 已关闭后重跑前置
阶段，破坏既定 retry contract。

裁决为：只修正 `_close_owned_resources` docstring，明确 mandatory 阶段错误立即阻断后续
owner close；进入 best-effort owner 阶段后才是“全部安全 cleanup 尝试后传播首错”。
不得改变当前控制流和 `mark_closed()` 条件。

### F-DS-02 — rejected / retracted

AgentDS 已撤回。`read_proactive_compaction_projection(...)` 与
`_prepare_compact_before_dispatch(...)` 位于同一个 `_operation(transaction)` closure，
由单次 `run_write(_operation)` 执行，不存在 reviewer 原称的跨 transaction TOCTOU。

### AgentDS counterexample recheck — rejected

四项“非反例”结论不接受：

- “没有 request 就没有需要校验的 operation”混淆了 owner 缺失与 row 可忽略；孤立 row
  正是 malformed durable state。
- “unknown row 可留给独立 integrity checker”违反本 work unit 的 strict projection
  owner边界，并会让当前 dispatcher实际产生 provider side effect。
- “malformed request 仅 durable corruption 可达”不能解除 fail-closed 要求；strict
  reader与 INVALID phase就是 corruption/mismatch 的生产防线。
- “proactive 正常顺序总早于 reactive”不能证明 `_earliest_requested_event_id` 在损坏
  request下拥有 trigger truth；不能把偶然顺序当 semantic owner。

### Residual risks

- `read_cancelling_runs` workspace-wide periodic path：保持 deferred-to-Slice-3，由
  execution-owner cancel reconcile 精确关闭。
- consumer task exception observation：pre-existing，未证明由 Slice 2 引入；不扩大
  当前 review-fix scope。

## Required review fix

AgentCodex 必须只实施以下修复：

1. 在 proactive projection owner关闭 CTRL-S2-001 的四个分支，不增加兼容 parser、
   fallback operation id或第二套 integrity owner。
2. dispatcher 在 INVALID 且无安全 proactive operation id 时，以既有
   `_fail_unstarted_in_transaction(...)` governance failure收口；provider/request/
   compaction terminal均为0增量。
3. owner tests至少覆盖：
   - 无 request + orphan rejection/terminal/compactor manifest；
   - 合法 reactive-only request/history；
   - 合法 reactive request + unknown-operation row；
   - malformed request不能把 reactive id当 proactive id；
   - dispatcher无安全 operation id时Run fail closed、provider 0、无新 request/terminal。
4. 修正 recovery nested work-lease 的 Protocol/implementation docstring与直接状态机测试。
5. 只澄清 `_close_owned_resources` mandatory/best-effort docstring，不改变 close顺序。
6. 运行 focused pytest、受影响 Host suite、全量 pyright、`git diff --check`，并形成唯一
   Slice 2 review-fix artifact。

允许的现有边界文件：

- `dayu/host/proactive_compaction.py`
- `dayu/host/dispatch.py`
- `dayu/host/session_attachment.py`
- `dayu/host/open_host.py`（仅 docstring）
- `tests/host/test_proactive_compaction_operation.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_session_attachment_registry.py`
- `docs/reviews/wu-ctx-04-slice-2-review-fix-codex.md`（new）

## Gate decision

`needs-fix`。Slice 2 进入 `review-fix-in-flight`；修复完成后必须由 AgentMiMo 与
AgentDS 对 accepted findings 和新增 diff 做双路独立 re-review，Controller 再裁决，
不得直接接受或提交 Slice 2。
