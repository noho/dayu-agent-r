# PR 190 F15 / F16 Plan Review Adjudication

## 结论

AgentMiMo 与 AgentDS 均给出 `pass-with-risks`。正确 owner 与 scope 仍清楚，不需要扩大 product public contract；先修正 plan 中的可实施性缺口，再双路 re-review。

## Findings 裁决

| Finding | 裁决 | Controller 依据与 plan fix |
|---|---|---|
| MiMo-01 / DS-R02 terminal reason source | `accepted-in-part` | 所有 Run terminal writer 都把 typed closeout `reason` 写为 canonical `reason_json={"reason": <non-empty str>}`；`FailUnstartedRunInput.reason` 的裸 `str` 是 writer 输入，不是 persisted `reason_json` shape。helper 只过滤 `HOST_RUN_TERMINAL_EVENT_TYPES`，严格读取该单一 object shape；不得 fallback 到 payload 建第二真源。增加 succeeded/failed/cancelled/lost producer contract tests；缺失、额外 key、空白、类型错误均 observation-invalid。|
| MiMo-02 EventLog connection | `accepted` | 明确使用 `open_host_durable_read_store(db_path, artifact_root, HostSQLiteStoragePolicy())` 与 `run_read`，在 Host transaction 内调用 `EventLogStore.read_events_after_matching`；不直接 SQL 复制 lifecycle/filter/payload 语义。|
| MiMo-03 / DS-R03 observation window/pagination | `accepted` | window 固定为 `(start_event_sequence, end_event_sequence]`，可选 exact `session_id`；end 在该次 snapshot transaction 前冻结。复用 filtered reader 的 `covered_event_sequence` / `max_event_sequence`，keyset 推进到 end；no-progress、越界或遗漏 accepted/terminal 均 invalid，禁止 OFFSET。|
| MiMo-04 accepted ordinal / mapping | `accepted` | `accepted_ordinal` 是 helper 按 window 内 `RUN_ACCEPTED.event_sequence` 升序分配的一基序号，并同时保留真实 accepted sequence；跨 segment chain 使用累计 absolute ordinal，但事实 identity 始终是 run_id/event id/sequence。terminal class 由 `HostRunEventType` 机械映射，不新增状态枚举。|
| MiMo-05 existing tests boundary | `accepted` | 既有 strict mismatch/recovery tests 保留；新增 regression 证明旧实现先失败、修复后通过，并补 exact reload/freeze。不得把 strict mismatch test 改成 loose acceptance。|
| DS-R01 / R04 empty normalized text / label holes | `rejected-with-reason` | `CompactAcceptedReplacementV4` typed constructors 与 strict persisted parser 对每个必填文本执行 `strip() != ""`；合法 accepted replacement 不可能含全空白 title/detail/text。canonical normalizer 对这种合法前置不会产出空值。静默 skip 会改写 accepted replacement/coverage 语义，明确禁止。补 owner test 锁定 whitespace-only candidate/persisted payload 在 accept/read boundary 已拒绝；pair projector继续 fail closed，不增加 skip/renumber。|
| DS-R05 dependency schema | `accepted` | `PtyAction` 增加显式 nullable `required_success_accepted_ordinal`，而不是解析 magic trigger。每个 dependent prompt只依赖其声明的直接 upstream；跨 segment 先执行 segment-level gate。非 succeeded 时不发送该 action及同链后续 action，写 stopped identity/reason并只做 cleanup。|
| DS-R06 duplicate terminal definition | `accepted` | duplicate 仅指同一 run_id 出现两个或更多 `HOST_RUN_TERMINAL_EVENT_TYPES` canonical facts；`RUN_CANCELLING`、Attempt terminal与其它 lifecycle event不参与。不同/相同 terminal type的第二条都 invalid。|
| DS-R07 reload fidelity | `accepted` | deterministic test从 canonical accepted event/artifact关闭 store后重新物理只读打开，重建 pair并比较 typed JSON、block text/digest/size；不假设内存对象。|
| MiMo/DS README findings | `accepted` | F15 明确 Host stable pair renderer truth，更新 `docs/host/design.md` 与 `dayu/host/README.md`；新增 CLI CI helper测试/命令，更新 `tests/README.md`。`docs/engine/design.md`只核对 Host ownership，无 Engine 变更则记录不更新理由。|
| DS run-terminals writer owner | `accepted` | tracked helper只返回 typed projection/JSON value；temporary harness负责写文件与 descriptor/digest。|

## Additional Controller correction

- F15 canonical projection 必须覆盖 summary/fact/anchor/intent/reference 全部文本叶子；格式矩阵重点为 answer anchor，但不得局部特例。
- `normalized_material_text` 仍是唯一文本规则。计划中的 low-level canonical block builder 必须用 private typed wrapper 表达“已规范化”，不能用 bool/string trust 绕过 owner validation。
- fresh evidence index 用 `process_outcome`、`run_terminal_summary/records`、`dependency_gate` 和 `evidence_status` 分栏；删除含混的 scenario success 字段，不保留兼容 alias。
- independent mandatory observation 可以继续；依赖已失败成功结果的 rolling chain 必须停止。正式 Oracle/registry继续 `unadjudicated`。
