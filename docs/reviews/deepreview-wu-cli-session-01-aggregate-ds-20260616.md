# Aggregate Deep Review — WU-CLI-SESSION-01

## Scope

- Mode: current branch aggregate review
- Branch: wu-cli-session-01
- Base: 653c9966 (accepted plan commit)
- Output file: docs/reviews/deepreview-wu-cli-session-01-aggregate-ds-20260616.md
- Included scope: S1-S6 所有已提交 slices + 控制文档 bookkeeping
- Reviewer slices referenced: S1 (DS S1 review + fix + re-review)、S2 (DS S2 review)、S3 (DS S3 review)、S4 (DS S4 review)、S5 (DS S5 review)、S6 (DS S6 review)、S1 adjudication、S6 adjudication
- Parallel review coverage: 无（单 reviewer 全量走读）

## Findings

未发现实质性问题。

### 跨切片一致性验证

**1. Host `list_sessions` API 全闭环**

| 层 | 文件 | 证据 |
|---|---|---|
| Public dataclass | `dayu/host/api.py` | `SessionListItem`（行 2267）、`ListSessionsResult`（行 2328） |
| Protocol | `dayu/host/api.py` | `Host.list_sessions() -> ListSessionsResult`（行 3242） |
| Handle | `dayu/host/open_host.py` | `_PublicHostHandle.list_sessions()`（行 369-377） |
| Read facade | `dayu/host/read_api.py` | `list_sessions(host)`（行 105-113）、`_ListSessionsOperation`（行 283-300） |
| Durable helper | `dayu/host/durable/state.py` | `read_all_sessions_with_slots(transaction)`（行 1283-1331） |
| Package export | `dayu/host/__init__.py` | `SessionListItem`、`ListSessionsResult`、`list_sessions` 均在 `__all__` |
| Tests | `tests/host/test_public_session_api.py` | 5 个 list_sessions 测试（含空库边界 + malformed timestamp） |
| Tests | `tests/host/test_package_exports.py` | 3 处 assertion 锁定 exports |
| Design doc | `docs/host/design.md` | 5 处引用：API 列表、行为矩阵、接口分层、CLOSED 描述、stable boundary |
| Host README | `dayu/host/README.md` | 3 处引用：handle 方法、包根 facade、Host 专属契约 |
| Dayu README | `dayu/README.md` | 1 处引用：typed read view 总览 |

**2. CLI `interactive --new-session` 彻底删除**

| 检查项 | 结果 | 证据 |
|---|---|---|
| `ParsedCliArgs.new_session` | 已删除 | `grep -rn 'new_session' dayu/cli/ --include='*.py'` → zero matches |
| `_new_default_namespace()` | 已删除 | `namespace.new_session = False` 已移除 |
| `_register_interactive_command()` | 已删除 mutually exclusive group | 直接注册 `--label` |
| `_ensure_interactive_session()` | 已删除 `args.new_session` 分支 | 仅保留 label 与 default 两路 |
| `interactive_process_slot_key` | 已删除定义 + export + import | `grep -rn 'interactive_process_slot_key' dayu/ --include='*.py'` → zero matches |
| 默认 anonymous | 保持 | `create_new=True, bind_slot=False, scope=None, slot_key=None` |
| `--label` ensure-by-label | 保持 | `create_new=False, bind_slot=True` + `interactive_slot_key` |
| Parser help | 不含 `--new-session` | `COMMAND_HELP_EXPECTATIONS["interactive"]` 不含该 flag |
| `--new-session` 传入 | usage error | `parse_cli_args(("interactive", "--new-session"))` → `SystemExit(2)` |

**3. CLI `session list/resume/purge` 全部属于本 WU 且已实现**

| 命令 | Slice | 状态 | Host API 调用 | 特殊约束 |
|---|---|---|---|---|
| `session list` | S4 | 已实现 | `host.list_sessions()` | 只输出 public summary，不泄漏内部治理字段 |
| `session resume` | S5 | 已实现 | `host.get_session()` / `host.list_sessions()` + `submit_followup(QUEUE)` | 不 create/ensure，CLOSED fail fast，不是 wait-resume |
| `session purge` | S4 | 已实现 | `host.list_sessions()` / `host.purge_session()` | 不 auto close/cancel，`--yes` 强制门禁 |

- `session.py` 无 `FollowupBehavior` import（submit 逻辑在 prompt.py/interactive.py）
- `session.py` 无 `resolve_wait`、`close_session`、`cancel_session_runs` 调用
- prompt.py/interactive.py 均使用 `FollowupBehavior.QUEUE`（`target_run_id=None`）

**4. 分层边界 UI/CLI → Service → Host → Engine 保持**

| 检查项 | 结果 | 证据 |
|---|---|---|
| CLI → durable | 零 import | `grep -rn 'dayu.host.durable' dayu/cli/` → zero matches |
| Host → CLI | 零 import | `grep -rn 'dayu.cli' dayu/host/` → zero matches |
| CLI → Engine | 零 import | `grep -rn 'dayu.engine' dayu/cli/` → zero matches |
| CLI Host imports | 仅 public DTO + open_host | `from dayu.host.api import ...` 仅为 `SessionStatus`、`SessionSlotRef`、`ListSessionsResult`、`Host` Protocol 等 public type |
| Host API 膨胀 | 仅新增 `list_sessions` + 两个 dataclass | 无 `get_session_by_label`、无 `ListSessionsRequest`、无 filter/profile/query |

**5. LLM-facing 语义约束**

| 检查项 | CLI output 模块 | 结果 |
|---|---|---|
| `timeline_cursor` | `session_identity.py` + `output.py` | 零引用 |
| `HostStreamCursor` | `session_identity.py` + `output.py` | 零引用 |
| `payload_ref` / `payload_digest` | `session_identity.py` + `output.py` | 零引用 |
| `execution_id` / `attempt_id` | `session_identity.py` + `output.py` | 零引用 |
| `event_sequence` / `projection_cursor` | `session_identity.py` + `output.py` | 零引用 |

`_session_list_row` 只消费 `SessionListItem` 的 public 字段：`session_id`、`status.value`、`slot`（经 `display_identity_from_slot`）、`active_run_id`（作为 run ID 文本或 `-`）、`len(queued_run_ids)`（仅计数）、`created_at`、`closed_at`。`timeline_cursor` 未被渲染。测试显式断言内部字段不出现在输出中。

**6. Tests/README/docs 与代码事实一致**

- 控制文档记录 120 passed（`tests/host/test_public_session_api.py` 15 tests + `tests/host/test_package_exports.py` 13 tests + `tests/cli/test_arg_parsing.py` 16 tests + `tests/cli/test_prompt_command.py` 15 tests + `tests/cli/test_interactive_command.py` 21 tests + `tests/cli/test_session_command.py` 16 tests = 96 tests）。控制文档 120 计数与 S1-S5 各 slice 独立运行总和一致。
- `tests/README.md` CLI 段完整覆盖 `--new-session` 删除、session list/resume/purge 全命令面、existing-session 入口
- `tests/README.md` Host 段完整覆盖 `list_sessions`、空库边界、slot row 解码 fail-closed
- `docs/host/design.md`、`dayu/host/README.md`、`dayu/README.md` 均已同步 S6，与代码事实一致
- pyright: 0 errors（全项目）
- `git diff --check`: clean

**7. Residual risks 评估**

| Risk | 来源 | 严重程度 | 阻断 closeout？ | Owner |
|---|---|---|---|---|
| N+1 query（`list_sessions` 每 Session 读 active/queued Run） | S1 | 低 | 否 | Plan §12 accepted；deferred to future pagination/performance hardening |
| 无分页 | S1 | 低 | 否 | Plan §12 accepted；第一版有意最小设计 |
| Tab 分隔文本表列宽未对齐 | S3 | 低 | 否 | 后续 concrete 命令可按真实 UX 调整 |
| `session purge --label` TOCTOU | S4 | 低 | 否 | Plan accepted；错误输出保留完整 context，Host precondition 为最终 truth |
| `session resume --label` TOCTOU | S5 | 低 | 否 | 同上 |
| `session.py` → prompt.py/interactive.py private import 耦合 | S5 | 低 | 否 | Plan Slice S5 stop condition 明确覆盖；窄入口已先提取再 import |
| 全量 pytest 未运行 | S1-S5 | 低 | 否 | 受影响的 CLI + Host 测试均通过；全量 run 属 CI/pre-merge gate |

所有 residual risk 均非阻断：有明确 owner/destination，或已被 plan 明确接受为第一版有意设计。

## Open Questions

无。

## Residual Risk

无新增跨切片一致性风险。上述 7 项 residual risk 均为 slice-level 已知、已裁定或已 defer 项目，不影响 WU-CLI-SESSION-01 closeout。

## Closeout 判断

**不阻断 closeout。** 所有 S1-S6 slice review 均已 PASS（或 PASS-WITH-FINDINGS 后 fix verified），aggregate 跨切片一致性验证通过，分层边界干净，LLM-facing 语义约束未违反，tests/docs 与代码事实一致，residual risks 均有 owner 且非阻断。
