# Aggregate Deep Review: WU-CLI-SESSION-01

## Scope

- Mode: current branch aggregate review
- Branch: `wu-cli-session-01`
- Base: `653c9966` (accepted plan commit)
- Output file: `docs/reviews/deepreview-wu-cli-session-01-aggregate-mimo-20260616.md`
- Included scope: S1-S6 all production code, tests, docs, and review artifacts
- Excluded scope: `docs/host/issues-implementation-control.md`（controller bookkeeping，只检查事实矛盾）
- Parallel review coverage: 无
- Review date: 2026-06-16

## Findings

未发现实质性问题。

## Aggregate Verification

### 1. Host list_sessions API 全闭环

| 层 | 文件 | 证据 |
|---|---|---|
| Public dataclass | `dayu/host/api.py:2267-2352` | `SessionListItem`、`ListSessionsResult` frozen dataclass，完整 `__post_init__` 校验 |
| Host Protocol | `dayu/host/api.py:3242-3250` | `async def list_sessions(self) -> ListSessionsResult` |
| Read API | `dayu/host/read_api.py:105-113` | `list_sessions(host)` → `host._run_read(_ListSessionsOperation())` |
| Read transaction | `dayu/host/read_api.py:284-300` | `_ListSessionsOperation.__call__` → `read_all_sessions_with_slots` → `_session_list_item_from_rows` |
| Timestamp parsing | `dayu/host/read_api.py:334-364` | `_parse_session_row_timestamp` / `_parse_optional_session_row_timestamp` 使用 `parse_utc_timestamp`，malformed 包装为 `HostDurableError` |
| Durable helper | `dayu/host/durable/state.py:1283-1331` | `read_all_sessions_with_slots` SQL left join + `_session_with_slot_rows_from_host_row` |
| Slot decode | `dayu/host/durable/state.py:969-1026` | `_slot_row_from_session_list_host_row` 使用 `_decode_optional_text` / `_decode_optional_int`，缺列抛 `HostRowDecodeError` |
| Open host handle | `dayu/host/open_host.py:369-377` | `_PublicHostHandle.list_sessions` → `_raise_if_closed` → `_list_sessions` |
| Package export | `dayu/host/__init__.py:50,77,101,168,198,218` | `ListSessionsResult`、`SessionListItem`、`list_sessions` 均在 `__all__` |
| Tests | `tests/host/test_public_session_api.py` | 空库边界、open/closed/anonymous/labeled/purged/malformed/closed handle |
| Export test | `tests/host/test_package_exports.py` | 锁定 `__all__` 同步 |
| Design doc | `docs/host/design.md` | behavior matrix + 接口分层 + CLI resume 术语区分 |
| README | `dayu/host/README.md`, `dayu/README.md` | handle 方法、包根 facade、Host 专属契约、稳定边界 |

**结论**：全闭环，无缺口。

### 2. CLI `interactive --new-session` 彻底删除

| 检查点 | 证据 |
|---|---|
| `ParsedCliArgs` 无 `new_session` 字段 | `arg_parsing.py` diff 确认删除 |
| `_new_default_namespace` 无 `new_session=False` | diff 确认删除 |
| `_register_interactive_command` 无 mutually exclusive group | diff 确认改为直接 `--label` |
| `_ensure_interactive_session` 无 `args.new_session` 分支 | diff 确认删除 |
| `interactive_process_slot_key` 函数删除 | `host_context.py` diff 确认 |
| `host_context.__all__` 无该符号 | diff 确认 |
| 全仓无 dangling reference | grep 确认零结果（仅测试中的 negative test 引用） |
| 默认 anonymous 行为保持 | `test_interactive_two_turns_use_same_session_and_independent_watchers` 断言 `bind_slot=False, scope=None, slot_key=None` |
| `--label` ensure-by-label 保持 | `test_interactive_label_reuses_host_slot_and_fills_context_slots` 存在且通过 |
| `--new-session` parser 拒绝 | `test_interactive_new_session_flag_exits_with_usage_error` 验证 `EXIT_USAGE_ERROR` |

**结论**：彻底删除，默认 anonymous / label 行为保持。

### 3. CLI `session list / resume / purge` 全部已实现

| 命令 | 实现文件 | 测试覆盖 |
|---|---|---|
| `session list` | `session.py:222-232` 调用 `host.list_sessions()` + `render_session_list` | parser help、open/closed 输出、empty state |
| `session resume` | `session.py:235-289` selector resolution → prompt/interactive narrow entry | by session-id、by label、CLOSED fail fast、missing label fail fast、TOCTOU |
| `session purge` | `session.py:292-329` selector → `host.purge_session` + `render_session_purge_result` | --yes 门禁、by session-id、by label、INVALID_STATE、TOCTOU、成功输出 |
| resume ≠ wait-resume | `session.py:258,279` 使用 `FollowupBehavior.QUEUE`，不使用 `STEER` | `test_prompt_existing_session_execution_does_not_create_or_ensure` 断言 `behavior is FollowupBehavior.QUEUE` |
| purge 不自动 close/cancel | `session.py` 不调用 `close_session` / `cancel_session_runs` | `host.close_cancel_calls == 0` 断言 |

**结论**：全部已实现，resume 不是 wait-resume，purge 不自动 close/cancel。

### 4. 分层边界保持

| 检查点 | 证据 |
|---|---|
| CLI 不读 durable internals | `grep -rn "durable" dayu/cli/` 返回零结果 |
| CLI 不反向 import Host 内部 | session.py 只导入 `dayu.host.api`（public DTO）和 `dayu.host.open_host`（public opener） |
| Host list_sessions 不膨胀 API | `ListSessionsResult` 是纯只读 DTO，无 filter/callback/pagination 参数 |
| Host Protocol 是 stable contract | `Host` Protocol 定义在 `api.py`，`_PublicHostHandle` 实现它 |
| Engine 未修改 | `docs/engine/design.md` 无变更，Engine run-scoped 边界不冲突 |
| `dayu.runtime` 未被穿透 | 无新增 `dayu.runtime` → `dayu.host` / `dayu.cli` 依赖 |

**结论**：UI/CLI → Service → Host → Engine 分层边界保持。

### 5. LLM-facing 语义约束

| 检查点 | 证据 |
|---|---|
| 输出不泄漏 Attempt/execution/payload ref/digest/cursor | `test_render_session_list_uses_public_summary_without_internal_fields` 断言 `attempt-hidden`、`execution-hidden`、`payload-ref-hidden`、`digest-hidden`、`HostStreamCursor` 均不在输出中 |
| purge 输出不泄漏 digest | `test_render_session_purge_result_hides_digest` 断言 `sha256`、`digest-hidden` 不在输出中 |
| 错误消息不暴露 raw durable timestamp | `test_list_sessions_malformed_timestamp_returns_public_internal_error` 断言 `"not-a-fixed-utc-timestamp"` 不在错误消息中 |
| Host DTO 只包含业务语义字段 | `SessionListItem` 字段：session_id、status、slot、active_run_id、queued_run_ids、timeline_cursor、created_at、closed_at |

**结论**：无 Host 内部治理字段伪装为业务事实。

### 6. Tests / README / docs 与代码事实一致

| 文档 | 检查结果 |
|---|---|
| `tests/README.md` | CLI 段覆盖 interactive --new-session 删除、session list/resume/purge、existing-session 入口；Host 段覆盖 list_sessions、空库边界、slot row decode fail-closed |
| `docs/host/design.md` | list_sessions 在 function list、behavior matrix、接口分层；CLI resume 与 Host wait-resume 术语区分 |
| `dayu/host/README.md` | handle 方法、包根 facade、Host 专属契约、稳定边界均含 list_sessions |
| `dayu/README.md` | Host public contract 类型列表含 Session 列表读取结果；读取入口语义正确 |
| `docs/engine/design.md` | 未修改，Engine 边界不冲突 |

**结论**：文档与代码事实一致。

## Residual Risk（非阻断）

| 风险 | 性质 | 阻断 closeout |
|---|---|---|
| `list_sessions` 无 pagination | plan 已接受的第一版设计；后续可独立扩展 | 否 |
| N+1 查询（每个 Session 额外 2 条 Run 查询） | plan 已记录；当前 Session 规模可接受 | 否 |
| tab 输出无终端宽度裁剪 | 后续 CLI UX 可调 | 否 |
| `session purge --label` 的 TOCTOU | plan 已记录；Host purge precondition 是最终 truth | 否 |
| session.py 导入 prompt.py / interactive.py 的 `_` 前缀私有函数 | plan 已接受的 stop condition 范围内耦合 | 否 |

## Open Questions

无。

## Conclusion

**PASS**。WU-CLI-SESSION-01 S1-S6 全部实现，行为一致，分层边界保持，文档同步完整。无阻断 closeout 的 finding。
