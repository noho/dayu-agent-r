# WU-CLI-SESSION-01 Plan Re-Review

## Review Target

`docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md`（plan fix 后版本）

## Scope

Focused re-review：只复核 controller adjudication 中 accepted findings 是否关闭。

## Artifacts Reviewed

- Updated plan: `docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md`
- Original MiMo review: `docs/reviews/plan-review-wu-cli-session-01-mimo-20260616.md`
- DS review: `docs/reviews/plan-review-wu-cli-session-01-ds-20260616.md`
- Controller adjudication: `docs/reviews/plan-review-wu-cli-session-01-adjudication-20260616.md`
- Plan fix report: `docs/reviews/wu-cli-session-01-plan-fix-codex-20260616.md`

## Code Facts Verified for Re-Review

- `dayu/host/read_api.py` line 1065: `__all__ = ["get_run", "get_session"]` — confirmed, plan 要求同步增加 `list_sessions`。
- `dayu/host/durable/codec.py` 中 `parse_utc_timestamp(...)` 已存在并在 `read_api.py` 中导入使用。
- `dayu/cli/host_context.py` line 359-380: `__all__` 包含 `interactive_process_slot_key`，确认需要清理。

## Finding Closure Table

| Adjudication Finding | 来源 | 状态 | 验证 |
|---|---|---|---|
| DS F-01 timestamp conversion gap | DS review | **已修复** | Section 6 新增完整的"时间戳转换规则"段：指定 `parse_utc_timestamp(...)`、malformed → `HostDurableError`、不得静默降级。Section 9 S1 和 Section 10 同步增加实现和测试要求。 |
| DS F-02 SessionListItem / SessionSnapshot asymmetry | DS review | **已修复** | Section 6 新增显式裁决段："`created_at` / `closed_at` 只作为 list-summary fields 加入 `SessionListItem`，本 WU 不扩展 `SessionSnapshot`"。Section 10 增加断言。 |
| DS F-03 / MiMo F05 resume execution core underspecified | DS + MiMo review | **已修复** | Section 9 S5 定义了完整的两阶段拆分：`_resolve_existing_session_id(host, selector) -> str` 在 session.py，`_execute_prompt_on_existing_session(args, session_id, invocation) -> int` 在 prompt.py，`_execute_interactive_on_existing_session(args, session_id, input_reader, invocation) -> int` 在 interactive.py。每个函数指定了参数、返回值、异常传播、行为约束和 stop condition。 |
| DS F-04 / MiMo F03 label reverse mapping underspecified | DS + MiMo review | **已修复** | Section 7 新增 KIND/LABEL 反解四条固定规则，包括 `slot is None` → anonymous、`cli.prompt` / `cli.interactive` scope 匹配、其它 → other。明确"label 允许包含点号；反解时只移除固定前缀，不按 `.` split"。Section 9 S3 引用该规则。 |
| DS F-05 purge-by-label TOCTOU | DS review | **已修复** | Section 7 新增"并发语义"段：明确 TOCTOU 窗口由 Host durable transaction precondition 兜底；CLI 错误必须同时包含用户原始 selector 和 Host error context。Section 9 S4/S5 增加 TOCTOU 测试期望。 |
| MiMo F01 Host Protocol / API export omissions | MiMo review | **已修复** | Section 6 新增显式枚举：`dayu/host/api.py` Host Protocol + `api.__all__`、`dayu/host/read_api.py` + `read_api.__all__`、`_PublicHostHandle`、`dayu/host/__init__.py`、`tests/host/test_package_exports.py`。Section 9 S1 和 Section 10 重复。 |
| MiMo F04 purge tombstone output format | MiMo review | **已修复** | Section 7 固定成功输出为 `Purged session <session_id> (tombstone: <tombstone_ref_prefix>...)`，prefix 为 ref 去掉空白后前 12 个字符。Section 9 S4 和 Section 10 增加稳定断言。 |
| DS F-08 list vs concurrent purge snapshot isolation | DS review | **已修复** | Section 6 durable helper 段新增："上述'已 purge 不出现'指 read transaction 开始时的 durable snapshot。若并发 purge 在本次 read transaction 开始后提交，本次 `list_sessions` 可以仍看到旧 snapshot；后续 `get_session` / `submit_followup` / `purge_session` 等 Host command 仍是最终 truth。" Section 8 Purged Session 重复。 |
| DS F-09 `interactive_process_slot_key` export cleanup | DS review | **已修复** | Section 9 S2 精确变更："若 `interactive_process_slot_key(...)` 无其它用途，删除该 helper、测试引用，并同步从 `host_context.__all__` 中移除。" |

## Rejected / Deferred Findings（确认 plan fix 处理）

| Finding | Adjudication Decision | Plan Fix 处理 |
|---|---|---|
| DS F-06 list query amplification | deferred-with-owner | Section 12 新增 "List query amplification" 条目记录为后续性能风险。 |
| DS F-07 no ListSessionsRequest | rejected-with-reason | Section 12 新增 "No ListSessionsRequest" 条目。 |
| MiMo F02 resume-by-label full scan | rejected-with-reason | Section 12 保留 "Resume by label uses list_sessions" 条目。 |

## New Issues Found During Re-Review

无新增 blocker。Plan fix 覆盖了所有 accepted findings，未引入新问题。

## Residual Risks

与原 review 一致，无新增：

- `list_sessions` 无 pagination（已接受的有意边界）。
- resume-by-label 全量扫描（已接受的不过度设计权衡）。
- S5 实现复杂度——plan 现已定义最小可接受拆分和 stop conditions。

## Conclusion

**PASS**

所有 9 个 accepted findings 均已修复。Plan 现在对 implementation agent 足够具体：

1. Host public API/export 变更清单完整覆盖 Protocol、`api.__all__`、`read_api.__all__`、`_PublicHostHandle`、`__init__`、`test_package_exports.py`。
2. Timestamp conversion 规则明确使用 `parse_utc_timestamp(...)`，malformed → `HostDurableError`。
3. `SessionListItem` 与 `SessionSnapshot` 不对称是有意设计并已记录。
4. S5 resume 两阶段拆分有具体函数签名、参数、返回值、异常和 stop conditions。
5. Label reverse mapping 有四条固定规则，覆盖 dots in labels。
6. Purge/resume TOCTOU 由 Host precondition 兜底，CLI 错误包含原始 selector。
7. Purge 输出格式冻结为 `Purged session <id> (tombstone: <prefix>...)`。
8. Snapshot isolation 行为已记录。
9. `interactive_process_slot_key` 清理已纳入 S2。

Plan 可安全交给 implementation agent。
