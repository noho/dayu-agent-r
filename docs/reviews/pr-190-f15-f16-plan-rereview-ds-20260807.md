# PR190 F15/F16 Plan Re-Review — AgentDS Adversarial

- **Review target**: `docs/gateflow/pr-190-f15-f16-plan-20260807.md` + `docs/gateflow/pr-190-f15-f16-plan-review-adjudication-20260807.md`
- **Original DS review**: `docs/reviews/pr-190-f15-f16-plan-review-ds-20260807.md`
- **Reviewer**: AgentDS (adversarial, independent re-review)
- **Timestamp**: 2026-08-07T09:09:24
- **Task**: 核对所有 accepted findings 是否精确关闭，rejected whitespace/payload fallback findings 是否有直接代码依据且没有兼容/第二真源

---

## Accepted Findings Closure Verification

逐项核对 adjudication 中的 accepted/accepted-in-part 裁决，确认每个 finding 已通过直接代码证据精确关闭：

| # | Finding | Adjudication | 直接代码证据 | 关闭状态 |
|---|---------|-------------|-------------|---------|
| MiMo-02 | EventLog connection | 使用 `open_host_durable_read_store(db_path, artifact_root, HostSQLiteStoragePolicy())` + `run_read` + `EventLogStore.read_events_after_matching` | `read_events_after_matching` 存在于 `dayu/host/durable/event_log.py:748`；`open_host_durable_read_store` 存在于 `dayu/host/durable/connection.py`（已由 prompt_observe_calibration.py:33 import 确认） | **精确关闭** |
| MiMo-03 / DS-R03 | observation window/pagination | window=`(start_event_sequence, end_event_sequence]`，keyset 推进，no OFFSET，no-progress/越界 fail closed | `read_events_after_matching` 使用 `covered_event_sequence`/`max_event_sequence` keyset（event_log.py:748+） | **精确关闭** |
| MiMo-04 | accepted ordinal/mapping | `accepted_ordinal` 为 window 内 `RUN_ACCEPTED.event_sequence` 升序一基序号；terminal class 由 `HostRunEventType` 机械映射 | `HOST_RUN_TERMINAL_EVENT_TYPES` 在 `lifecycle_events.py:133-138` 定义完整集合；`_run_terminal_event_type()` 在 `run_transition.py` 提供映射 | **精确关闭** |
| MiMo-05 | existing tests boundary | 保留 strict mismatch/recovery tests；新增 regression 证明旧实现先失败、修复后通过 | 不涉及新代码事实，属测试策略决策 | **精确关闭** |
| DS-R05 | dependency schema | `PtyAction.required_success_accepted_ordinal: int\|None`，不解析 magic trigger，每 dependent prompt 只依赖直接 upstream | `PtyAction` 位于 `prompt_observe_calibration.py:73-119`，现有 trigger 字段为 `str`；新增独立 `int\|None` 字段不破坏既有 trigger 语义 | **精确关闭** |
| DS-R06 | duplicate terminal definition | duplicate=同一 run_id 有 2+ `HOST_RUN_TERMINAL_EVENT_TYPES` canonical facts；lifecycle events 不参与；不同/相同 terminal type 的第二条都 invalid | `HOST_RUN_TERMINAL_EVENT_TYPES` 包含 `RUN_SUCCEEDED/RUN_FAILED/RUN_CANCELLED/RUN_LOST`（lifecycle_events.py:133-138）；`RUN_CANCELLING` 属于 `HOST_RUN_LIFECYCLE_EVENT_TYPES`（lifecycle_events.py:33）而非 terminal | **精确关闭** |
| DS-R07 | reload fidelity | deterministic test 从 canonical accepted event/artifact 关闭 store 后重新物理只读打开，重建 pair 并比较 typed JSON、block text/digest/size | 不涉及新代码事实，属测试设计决策；`CompactAcceptedReplacementV4.to_json()` 提供完整 JSON 序列化（compaction.py:1608-1631） | **精确关闭** |
| MiMo/DS README | README 更新 | F15 更新 `docs/host/design.md` + `dayu/host/README.md`；F16 新增 CLI CI helper 测试更新 `tests/README.md`；`docs/engine/design.md` 无变更则记录不更新理由 | `AGENTS.md:113-116` 触发规则覆盖这三个 target | **精确关闭** |
| DS run-terminals writer | writer owner | tracked helper 只返回 typed projection/JSON value；temporary harness 负责写文件与 descriptor/digest | 符合 `cli_ci.md` evidence bundle contract；helper 在 `utils/` 下不写文件是正确分层 | **精确关闭** |

---

## Rejected Findings Code Evidence Verification

### DS-R01 / R04 rejected-with-reason：whitespace-only text 不会通过 accepted replacement boundary

**Adjudication 断言**："`CompactAcceptedReplacementV4` typed constructors 与 strict persisted parser 对每个必填文本执行 `strip() != ""`；合法 accepted replacement 不可能含全空白 title/detail/text。"

**逐层代码证据**：

1. **`_require_non_empty` 定义** — `dayu/host/_public_validation.py`：
   ```python
   def require_non_empty(value: str, *, field_name: str) -> None:
       if value.strip() == "":       # ← 拒绝纯空白
           raise ValueError(f"{field_name} must be non-empty")
   ```
   直接证据：`value.strip() == ""`，意味着 `"  "`, `"\n\n"`, `"\t"` 全部被拒绝。

2. **各 text 字段均使用此校验**：
   - `CompactSessionSummaryV4.text` → `_require_non_empty(self.text, ...)`（compaction.py:1240）
   - `CompactAnswerAnchorV4.title` → `_require_non_empty(self.title, ...)`（compaction.py:1322）
   - `CompactAnswerAnchorV4.detail` → `_require_non_empty(self.detail, ...)`（compaction.py:1323）
   - `CompactEvidenceFactV4.claim` → `_require_non_empty(self.claim, ...)`（compaction.py:1278）
   - `CompactForwardIntentV4.text` → `_require_non_empty(self.text, ...)`（compaction.py:1368）
   - `CompactReferenceContinuityV4.text` → `_require_non_empty(self.text, ...)`（compaction.py:1409）

3. **结论**：DS-R01 的反例场景（"compactor 合法地为 answer_anchor 产出一个只有空白行的 detail"）在 `CompactAcceptedReplacementV4` 的构造边界就被 `ValueError` 拒绝。该 accepted replacement 不可能被持久化，因此 canonical projection 不会遇到此输入。

**兼容/第二真源检查**：
- 无兼容 fallback：adjudication 明确禁止 skip/renumber，"静默 skip 会改写 accepted replacement/coverage 语义"
- 无第二真源：`_require_non_empty` 是唯一 text validity 校验入口，不存在另一套宽松校验可以绕过
- pair projector 继续 fail closed：从未引入 loose compare

**R04 的 cascading effect**：R04 是 R01 的推论——如果 R01 的空 section 不存在，则 recovery label 映射错位也不存在。R01 被正确拒绝后，R04 自动失效。

**验证结论**：DS-R01/R04 的 rejection 有直接、完整、逐层的代码证据支持。没有引入兼容路径或第二真源。

---

### DS-R02 accepted-in-part：`reason_json` 单一 shape + 禁止 payload fallback

**Adjudication 断言**："所有 Run terminal writer 都把 typed closeout reason 写为 canonical `reason_json={"reason": <non-empty str>}`；helper 严格读取该单一 object shape；不得 fallback 到 payload 建第二真源。"

**逐层代码证据**：

1. **`_run_terminal_event_request`**（run_transition.py:4432）：`reason={"reason": request.reason}`
2. **`_attempt_terminal_event_request`**（run_transition.py:4389）：`reason={"reason": request.reason}`
3. **`_run_failed_event_request`（无 attempt 路径）**（run_transition.py:3900）：`reason={"reason": request.reason}`
4. **`_run_cancelled_event_request`**（run_transition.py:4333）：`reason={"reason": request.reason}`
5. **`_startup_recovering_lost_event_request`（RUN_LOST）**（run_transition.py:3784）：`reason={"reason": request.reason}`

五个 terminal writer 覆盖全部 4 种 terminal type（`RUN_SUCCEEDED` 通过 `_run_terminal_event_request` 的 `request.run_terminal_status` 路由，line 4425）。全部使用相同的 `{"reason": <str>}` shape。

**兼容/第二真源检查**：
- 无 payload fallback：adjudication 明确"不得 fallback 到 payload 建第二真源"
- No second `reason` source：`reason_json` 列是唯一 canonical reason 存储；`payload_json` 中的 `reason` 字段是 payload 内部字段，不应作为 helper 的 reason 来源
- `_optional_canonical_json(None)` → `None`（SQL NULL）→ helper fail closed：如果某类事件（非 terminal）的 `reason_json` 为 NULL，helper 在过滤到 terminal events 后不会遇到此情况

**验证结论**：DS-R02 的裁决有完整的代码证据支持。`{"reason": <str>}` 是统一且唯一的 canonical shape。禁止 payload fallback 的约束正确。

---

## Controller Corrections 新增约束验证

Adjudication 末尾的 "Additional Controller correction" 包含 4 条约束。逐条验证无新风险：

| # | Correction | 代码一致性 | 风险评估 |
|---|-----------|-----------|---------|
| 1 | canonical projection 覆盖全部 section，不只 answer anchor | 与 plan §4.1 "覆盖全部 previous-view 文本 section" 一致 | 无新风险 |
| 2 | low-level builder 必须用 private typed wrapper 表达"已规范化" | 阻止 `bool` flag / string trust 绕过 owner validation；与 AGENTS.md "禁止魔法字符串" 一致 | 无新风险 — 是 implementation 规范强化 |
| 3 | fresh evidence index 删除含混 scenario success 字段，不保留兼容 alias | 与 plan §2.4 non-goals "不把 harness 变成第二套业务 verdict/oracle" 一致 | 无新风险 |
| 4 | independent mandatory observation 继续；依赖链 stop | 与 plan §5.4 一致 | 无新风险 |

---

## Remaining Open Items

| Item | 来源 | 状态 |
|------|------|------|
| R01/R04 whitespace boundary | 原 DS review | **已关闭** — 代码证明 whitespace-only text 在 accepted replacement boundary 被拒绝 |
| R02 terminal reason source | 原 DS review | **已关闭** — 所有 terminal writer 统一 `{"reason": <str>}` shape |
| R03 pagination | 原 DS review | **已关闭** — `read_events_after_matching` + keyset 机制明确 |
| R05 dependency schema | 原 DS review | **已关闭** — `PtyAction.required_success_accepted_ordinal` 显式 typed field |
| R06 duplicate definition | 原 DS review | **已关闭** — `HOST_RUN_TERMINAL_EVENT_TYPES` 过滤 + lifecycle exclusion |
| R07 reload fidelity | 原 DS review | **已关闭** — store close/reopen + typed comparison test |
| R08 README | 原 DS review | **已关闭** — 明确 target README 列表 |
| Open Q1 (R01 关联) | 原 DS review | **已关闭** — compactor schema 在 accept boundary 保证非空 |
| Open Q2 (observation window) | 原 DS review | **已关闭** — `(start_event_sequence, end_event_sequence]` |
| Open Q3 (writer owner) | 原 DS review | **已关闭** — tracked helper 返回 projection；harness 负责文件写入 |

---

## Final Re-Review Conclusion: **pass**

全部 accepted findings 已精确关闭。DS-R01/R04 rejected finding 的代码依据逐层验证通过：

- 所有 `CompactAcceptedReplacementV4` 子类型的文本字段在构造时经 `_require_non_empty`（`value.strip() == ""`）校验
- 所有 Run terminal writer（5 个）统一使用 `reason={"reason": <non-empty str>}` 写入 `reason_json`
- 无兼容路径、无第二真源、无 payload fallback

无新 findings。Plan + adjudication 已 code-generation-ready。

---

## Appendix: Evidence Trace

### Whitespace rejection chain
```
_public_validation.py: require_non_empty(value.strip() == "")
    ↑
compaction.py: CompactSessionSummaryV4.__post_init__ → _require_non_empty(text)
compaction.py: CompactAnswerAnchorV4.__post_init__ → _require_non_empty(title)
compaction.py: CompactAnswerAnchorV4.__post_init__ → _require_non_empty(detail)
compaction.py: CompactEvidenceFactV4.__post_init__ → _require_non_empty(claim)
compaction.py: CompactForwardIntentV4.__post_init__ → _require_non_empty(text)
compaction.py: CompactReferenceContinuityV4.__post_init__ → _require_non_empty(text)
```

### Terminal reason_json unified shape
```
run_transition.py:4432: reason={"reason": request.reason}  ← _run_terminal_event_request (SUCCEEDED/FAILED/CANCELLED/LOST)
run_transition.py:4389: reason={"reason": request.reason}  ← _attempt_terminal_event_request
run_transition.py:3900: reason={"reason": request.reason}  ← _run_failed_event_request (attempt-free FAILED)
run_transition.py:4333: reason={"reason": request.reason}  ← _run_cancelled_event_request
run_transition.py:3784: reason={"reason": request.reason}  ← _startup_recovering_lost_event_request (LOST)
```
