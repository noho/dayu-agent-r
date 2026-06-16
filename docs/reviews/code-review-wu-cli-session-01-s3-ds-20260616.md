# Code Review — WU-CLI-SESSION-01 S3

## Scope

- Mode: current changes
- Branch: wu-cli-session-01
- Base: 653c9966 (accepted plan commit)
- Output file: docs/reviews/code-review-wu-cli-session-01-s3-ds-20260616.md
- Included scope:
  - `dayu/cli/session_identity.py`（新文件）— `CliSessionLabelKind`、`CliSessionDisplayKind`、`CliSessionDisplayIdentity`、`slot_ref_for_cli_label`、`display_identity_from_slot`、`_label_suffix`
  - `dayu/cli/output.py` — `render_session_list`、`render_session_purge_result` 与私有 helper
  - `tests/cli/test_session_command.py`（新文件）— 5 个 helper 测试
  - `tests/README.md` — Session helper 测试覆盖描述补充
  - `docs/reviews/wu-cli-session-01-s3-implementation-codex.md`
- Excluded scope:
  - `docs/host/issues-implementation-control.md`（controller bookkeeping，仅校验无事实矛盾）
  - `dayu/cli/arg_parsing.py`、`dayu/cli/commands/session.py`（S3 未修改）
  - S1/S2/S4/S5/S6 slice 文件（不在 S3 scope）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 逐项确认

**1. label kind / display kind 严格受限且类型安全**

- `CliSessionLabelKind` 为 `StrEnum`，仅含 `PROMPT` / `INTERACTIVE`（`session_identity.py:25-29`）
- `CliSessionDisplayKind` 为 `StrEnum`，仅含 `ANONYMOUS` / `PROMPT` / `INTERACTIVE` / `OTHER`（`session_identity.py:32-38`）
- `slot_ref_for_cli_label(kind: CliSessionLabelKind, ...)` 参数类型为 enum 而非 raw string（`session_identity.py:53`）
- 非法 kind 通过 `is` identity check 落入 `raise TypeError` 分支（`session_identity.py:73`）

**2. label → SessionSlotRef 复用正确 scope 与 slot key**

- `CliSessionLabelKind.PROMPT` → `SessionSlotRef(scope=PROMPT_SESSION_SCOPE, slot_key=prompt_slot_key(label))`（`session_identity.py:63-67`）
- `CliSessionLabelKind.INTERACTIVE` → `SessionSlotRef(scope=INTERACTIVE_SESSION_SCOPE, slot_key=interactive_slot_key(label))`（`session_identity.py:68-72`）
- `PROMPT_SESSION_SCOPE` / `INTERACTIVE_SESSION_SCOPE` 与 `prompt_slot_key` / `interactive_slot_key` 均从 `dayu.cli.host_context` 导入（`session_identity.py:12-19`）
- 测试断言含空白 label `" proj.v1 "` 经 `prompt_slot_key` strip 后正确映射（`test_session_command.py:32-44`）

**3. slot → KIND/LABEL 反解完全符合 plan 第 7 节**

`display_identity_from_slot` 的四个分支与 plan 规则一一对应（`session_identity.py:76-116`）：

| 输入 | plan 规则 | 实现分支 | 证据 |
|---|---|---|---|
| `slot is None` | KIND=anonymous, LABEL=- | `session_identity.py:86-90` → `ANONYMOUS`, `"-"` | 测试行 55-56, 75-76 |
| `scope=cli.prompt`, `slot_key=cli.prompt.<suffix>` (suffix非空) | KIND=prompt, LABEL=suffix | `session_identity.py:91-101` → `PROMPT`, suffix | 测试行 56-58, 77-78 |
| `scope=cli.interactive`, `slot_key=cli.interactive.<suffix>` (suffix非空) | KIND=interactive, LABEL=suffix | `session_identity.py:102-112` → `INTERACTIVE`, suffix | 测试行 59-63, 79-80 |
| 其它（非CLI scope / 前缀不匹配 / 后缀为空） | KIND=other, LABEL=slot_key | `session_identity.py:113-116` → `OTHER`, `slot.slot_key` | 测试行 65-86 |

`_label_suffix` 只做固定前缀剥离（`slot_key[len(expected_prefix):]`，`session_identity.py:140`），不按 `.` split。测试覆盖含点号 label `"proj.v1"`（`test_session_command.py:78`）、前缀不匹配（行 83-84）、空后缀（行 85-86）。

**4. render 函数只消费 Host public DTO，不泄漏内部治理字段**

`render_session_list`（`output.py:154-172`）:
- 入参 `ListSessionsResult` 是 Host public DTO
- `_session_list_row` 只读取 `SessionListItem` 的 public 字段：`session_id`、`status.value`、`slot`（经 `display_identity_from_slot` 转义）、`active_run_id`、`len(queued_run_ids)`（仅计数）、`created_at`、`closed_at`
- 未渲染 `timeline_cursor`、`HostStreamCursor`
- 测试显式断言 `"attempt-hidden" not in rendered`、`"execution-hidden" not in rendered`、`"payload-ref-hidden" not in rendered`、`"digest-hidden" not in rendered`、`"HostStreamCursor" not in rendered`（`test_session_command.py:135-139`）

`render_session_purge_result`（`output.py:177-196`）:
- 入参 `PurgeSessionResult` 是 Host public DTO
- 仅展示 `session_id` 与 tombstone 前 12 字符前缀
- 测试断言 `"sha256" not in rendered`、`"digest-hidden" not in rendered`、`"payload" not in rendered`、`"attempt" not in rendered`、`"execution" not in rendered`（`test_session_command.py:177-181`）

**5. S3 未越界调用 Host / 读 durable / 注册命令**

- `session_identity.py` 的 Host 导入仅限于 `SessionSlotRef`（public DTO），无 `open_host`、`list_sessions`、`purge_session`、`get_session` 调用（`session_identity.py:20`）
- `output.py` 的 Host 导入仅限于 `ListSessionsResult`、`PurgeSessionResult`、`SessionListItem`（均为 public DTO），无任何 Host 函数调用（`output.py:28-32`）
- 未修改 `arg_parsing.py`，未注册 `session` 命令，未新增 `dayu/cli/commands/session.py`
- 未 import `dayu.host.durable.*`

**6. tests/README 更新只记录当前测试事实**

`tests/README.md:95` 新增一句："Session command helper 测试覆盖 CLI label kind 到 Host public slot ref 的映射、anonymous / prompt / interactive / other slot 展示身份反解、含点号 label 不拆分、Session list 空 / 非空输出和 purge 输出不展示删除计数 digest 或内部治理字段。" — 与 5 个实际测试覆盖一一对应，未宣称 concrete session 命令已实现。

**7. control doc 无事实矛盾**

`docs/host/issues-implementation-control.md` 记录 S3 `gate: code review`、implementation status 为 "S3 implementation completed"、validation 为 "5 passed"（`issues-implementation-control.md:146-150`），与 implementation report 一致。

**8. docstring / 类型签名 / AGENTS**

- 所有新增函数与类均有中文 docstring
- 无 `Any`、`object`、无类型参数
- 无反向依赖（CLI 层不向上依赖 Service/Host/Engine 实现）
- 无兼容 wrapper
- pyright: 0 errors（implementation report 记录）

## Open Questions

无。

## Residual Risk

- `render_session_list` 使用 tab 分隔文本表，列宽未对齐；当 `session_id` 或 label 较长时可能视觉错位。后续 concrete `session list` 命令可按真实 UX 需求调整格式。
- 仅运行了 S3 指定测试（`tests/cli/test_session_command.py` 5 passed）与全项目 pyright；未运行全量 pytest。
