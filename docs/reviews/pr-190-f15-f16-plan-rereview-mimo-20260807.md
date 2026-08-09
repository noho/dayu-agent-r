# PR 190 F15/F16 Plan Re-Review — AgentMiMo (2026-08-07)

## Reviewed Target

- Plan: `docs/gateflow/pr-190-f15-f16-plan-20260807.md` (updated)
- Adjudication: `docs/gateflow/pr-190-f15-f16-plan-review-adjudication-20260807.md`

## Scope

Re-review：核对所有 accepted findings 是否精确关闭，rejected findings 是否有直接代码依据且未引入
fallback/skip/第二真源。

## Accepted Findings 逐项核对

### MiMo-01 / DS-R02 terminal reason source → `accepted-in-part`

**Adjudication 要求**: 所有 terminal writer 写 `reason_json={"reason": <non-empty str>}`；
helper 严格读该单一 object shape；不得 fallback 到 payload。

**Plan 关闭证据**:
- §5.1 #3: "terminal reason 的唯一 persisted 真源是 terminal event row 的 `reason_json`，
  其唯一合法 shape 是 exact JSON object `{"reason": <non-empty str>}`"
- "missing/null、额外 key、空字符串/纯空白、非字符串、非 object 或 malformed JSON 均 observation-invalid"
- "**禁止 fallback 到 `payload_json`、diagnostic event、日志文本或 `host_runs` 建第二真源。**"
- §7.2: 新增 `test_each_run_terminal_producer_persists_exact_reason_object`、
  `test_terminal_reason_rejects_missing_extra_blank_or_wrong_typed_object`、
  `test_terminal_reason_never_falls_back_to_payload_json`

**判定**: ✅ 精确关闭。单一 shape 定义、fail-closed 语义、禁止 fallback、producer/reader 双向 tests 均已写入。

### MiMo-02 EventLog connection → `accepted`

**Adjudication 要求**: 使用 `open_host_durable_read_store` + `run_read`，在 Host transaction 内调用
`EventLogStore.read_events_after_matching`。

**Plan 关闭证据**:
- §5.1: "调用 `open_host_durable_read_store(db_path, artifact_root, HostSQLiteStoragePolicy())` 打开
  Host **只读** durable store"
- "通过 store 的 `run_read` 在 Host read transaction 内构造/调用 `EventLogStore.read_events_after_matching`"
- "不直接 SQL 复制 lifecycle/filter/payload 语义，也不读取 `host_runs.status` 作为替代真源"

**判定**: ✅ 精确关闭。数据访问路径、API 调用方式、禁止直接 SQL 均已明确。

### MiMo-03 / DS-R03 observation window/pagination → `accepted`

**Adjudication 要求**: window `(start_event_sequence, end_event_sequence]`，可选 session_id；
end 在 snapshot transaction 前冻结；keyset 推进到 end；禁止 OFFSET。

**Plan 关闭证据**:
- §5.1: "observation window 是不可变的 `(start_event_sequence, end_event_sequence]`，并可附加 exact `session_id`"
- "start 在发送本次 observation 第一条业务 action 前取得；end 在进程/segment observation 完成后、
  该次 snapshot read transaction 开始时冻结"
- "使用 filtered reader 返回的 `covered_event_sequence` / `max_event_sequence` 做 event-sequence keyset 推进，
  直到覆盖 frozen end；禁止 OFFSET"
- "covered sequence 不前进、倒退、越过 end，或 window 内 accepted/terminal 无法完整归属，均 observation-invalid"

**判定**: ✅ 精确关闭。window 参数、冻结时机、keyset 推进、fail-closed 语义均已写入。

### MiMo-04 accepted ordinal / mapping → `accepted`

**Adjudication 要求**: `accepted_ordinal` 是 window 内 `RUN_ACCEPTED.event_sequence` 升序一基序号；
保留真实 sequence；terminal class 由 `HostRunEventType` 机械映射。

**Plan 关闭证据**:
- §5.1 #1: "按 window 内 `RUN_ACCEPTED.event_sequence` 升序分配一基 `accepted_ordinal`，
  同时保留真实 accepted event id/sequence"
- §5.1 #2: "terminal class 由 `HostRunEventType` 机械映射，不新建第二套 lifecycle 枚举"

**判定**: ✅ 精确关闭。

### MiMo-05 existing tests boundary → `accepted`

**Adjudication 要求**: 保留既有 strict mismatch/recovery tests；新增 regression 证明旧实现先失败、
修复后通过；不得改成 loose acceptance。

**Plan 关闭证据**:
- §6.1: "保留既有 strict mismatch/recovery rejection tests，不把它们改成 loose acceptance"
- §6.1: "whitespace-only candidate 与 persisted replacement 分别在 typed accept/read boundary 被拒绝，
  projector 不 skip/renumber"
- §7.1: 新增 `test_whitespace_only_replacement_candidate_is_rejected_at_accept_boundary`、
  `test_whitespace_only_persisted_replacement_is_rejected_at_read_boundary`

**判定**: ✅ 精确关闭。既有 tests 保留、新增 regression tests、不改 loose acceptance。

### DS-R05 dependency schema → `accepted`

**Adjudication 要求**: `PtyAction` 增加显式 nullable `required_success_accepted_ordinal`，
不解析 magic trigger。

**Plan 关闭证据**:
- §5.4: "`PtyAction` 增加显式 nullable typed 字段 `required_success_accepted_ordinal: int | None`，
  禁止解析 magic trigger 字符串表达 dependency"

**判定**: ✅ 精确关闭。

### DS-R06 duplicate terminal definition → `accepted`

**Adjudication 要求**: duplicate 仅指同一 run_id 出现两个或更多 `HOST_RUN_TERMINAL_EVENT_TYPES` canonical facts。

**Plan 关闭证据**:
- §5.1 #4: "duplicate terminal 精确定义为：同一 `run_id` 出现两个或更多属于 `HOST_RUN_TERMINAL_EVENT_TYPES`
  的 canonical facts；无论第二条 terminal type 与第一条相同还是不同都 invalid。
  `RUN_CANCELLING`、Attempt terminal及其他 lifecycle/diagnostic events 不参与 duplicate 判断。"

**判定**: ✅ 精确关闭。

### DS-R07 reload fidelity → `accepted`

**Adjudication 要求**: deterministic test 从 canonical accepted event/artifact 关闭 store 后重新物理只读打开，
比较 typed JSON、block text/digest/size；不假设内存对象。

**Plan 关闭证据**:
- §4.3: "reload fidelity test 必须从 canonical accepted event/artifact 建库，关闭 store 后通过物理只读 reopen
  重建；比较完整 typed JSON、block text、digest 与 size，不复用任何首次构建的内存对象。"

**判定**: ✅ 精确关闭。

### MiMo/DS README findings → `accepted`

**Adjudication 要求**: F15 更新 `docs/host/design.md` 与 `dayu/host/README.md`；
新增 CLI CI helper 测试更新 `tests/README.md`。

**Plan 关闭证据**:
- §6.1: "**必须更新** `docs/host/design.md` 与 `dayu/host/README.md`"
- §6.1 docs/host/design.md: "在 accepted replacement/previous compacted pair owner contract 中明确"
- §6.1 dayu/host/README.md: "更新 Host stable pair renderer truth"
- §6.2: "**必须更新** `tests/README.md`"
- §6.1: "`docs/engine/design.md` 只用于核对 Engine 不拥有该 projection；没有 Engine contract/code 变化，
  必须在 completion report 记录'不更新'的 owner 理由"

**判定**: ✅ 精确关闭。三份文档更新/不更新决策均已明确。

### DS run-terminals writer owner → `accepted`

**Adjudication 要求**: tracked helper 只返回 typed projection/JSON value；temporary harness 负责写文件。

**Plan 关闭证据**:
- §5.3: "tracked helper 只返回 typed projection/JSON value，不负责文件 I/O、descriptor 或 digest；
  每个 scenario/segment 的 temporary harness 负责把该 value 写成独立 `run-terminals.json` 并生成 descriptor/digest"

**判定**: ✅ 精确关闭。

## Rejected Findings 核对

### DS-R01 / R04 empty normalized text / label holes → `rejected-with-reason`

**Adjudication 理由**: `CompactAcceptedReplacementV4` typed constructors 与 strict persisted parser
对每个必填文本执行 `strip() != ""`；合法 accepted replacement 不可能含全空白 title/detail/text。
canonical normalizer 对合法前置不会产出空值。静默 skip 会改写 accepted replacement/coverage 语义。

**直接代码验证**:
- `_public_validation.py:19`: `if value.strip() == "": raise ValueError(f"{field_name} must be non-empty")`
  — 这是 `_require_non_empty` 的实现，校验 `strip() == ""`
- `compaction.py:1322-1323`: `CompactAnswerAnchorV4.__post_init__` 调用
  `_require_non_empty(self.title, ...)` 和 `_require_non_empty(self.detail, ...)`
- `compact_material.py:3396,3413,3443`: `_required_host_row_text` / `_optional_host_row_text` /
  `_required_json_text` 均校验 `value.strip() != ""`

**Plan 处理**:
- §4.1: "whitespace-only candidate 必须在 accept boundary 被拒绝，whitespace-only persisted payload
  必须在 read boundary 被拒绝；pair projector 遇到任何违约值继续 fail closed"
- "严禁静默 skip、补默认文本、重新编号或保留 label 空洞来掩盖 invalid durable truth"
- §4.3: 新增 invariant "whitespace-only accepted value 在 accept/read owner boundary 拒绝；
  projector 不 skip、不 renumber"
- §6.1: "whitespace-only candidate 与 persisted replacement 分别在 typed accept/read boundary 被拒绝"
- §7.1: 新增 `test_whitespace_only_replacement_candidate_is_rejected_at_accept_boundary`、
  `test_whitespace_only_persisted_replacement_is_rejected_at_read_boundary`

**判定**: ✅ rejected 有直接代码依据。`_require_non_empty` 在 `_public_validation.py:19` 确认
`strip() == ""` 校验。Plan 未引入 fallback/skip/第二真源；projector 继续 fail closed。

## Controller Corrections 核对

1. **F15 canonical projection 覆盖全部文本叶子**: ✅ §4.1 列出 summary/fact/anchor/intent/reference
2. **`normalized_material_text` 仍是唯一文本规则**: ✅ §4.2 #1 引入 `_CanonicalMaterialText` typed wrapper，
   #2 专用 low-level builder
3. **fresh evidence index 分栏**: ✅ §5.5 使用 `process_outcome`/`run_terminal_summary/records`/
   `dependency_gate`/`evidence_status` 分栏，无含混 scenario success 字段
4. **independent mandatory observation 继续**: ✅ §5.4 列出 independent mandatory work 不因 Run 失败短路

## New Findings

无新 findings。所有 accepted findings 精确关闭，rejected findings 有直接代码依据且未引入
fallback/skip/第二真源。

## Re-Review Conclusion

**pass**

Plan 已按 adjudication 要求精确修正。所有 11 项 accepted findings 均在 plan 对应位置写入了
具体关闭措施；1 项 rejected finding 有 `_public_validation.py:19` 和 `compaction.py:1322-1323`
的直接代码证据支持，且 plan 的处理方式（fail-closed、不 skip/renumber）符合约束。
可以进入 implementation gate。
