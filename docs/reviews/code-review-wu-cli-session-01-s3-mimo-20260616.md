# Code Review: WU-CLI-SESSION-01 S3

## Scope

- Mode: current changes
- Branch: `wu-cli-session-01`
- Base: `653c9966` (accepted plan commit)
- Output file: `docs/reviews/code-review-wu-cli-session-01-s3-mimo-20260616.md`
- Included scope:
  - `dayu/cli/session_identity.py`（新增）
  - `dayu/cli/output.py`
  - `tests/cli/test_session_command.py`（新增）
  - `tests/README.md`
  - `docs/reviews/wu-cli-session-01-s3-implementation-codex.md`
- Excluded scope: `docs/host/issues-implementation-control.md`（controller bookkeeping）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Review Detail

### 1. label kind / display kind 是否严格受限且类型安全

- `CliSessionLabelKind` 和 `CliSessionDisplayKind` 均为 `StrEnum`（`session_identity.py:25-38`），成员固定为 `prompt`/`interactive` 和 `anonymous`/`prompt`/`interactive`/`other`。
- `slot_ref_for_cli_label` 对非法 `kind` 抛 `TypeError`（`session_identity.py:73`）。
- `CliSessionDisplayIdentity` 为 `frozen=True, slots=True` dataclass（`session_identity.py:41`）。
- **结论**：类型安全，枚举受限。

### 2. label -> SessionSlotRef 是否复用既有 scope / slot_key helper

- `slot_ref_for_cli_label` 对 `PROMPT` 调用 `prompt_slot_key(label)` + `PROMPT_SESSION_SCOPE`，对 `INTERACTIVE` 调用 `interactive_slot_key(label)` + `INTERACTIVE_SESSION_SCOPE`（`session_identity.py:63-72`）。
- `prompt_slot_key` / `interactive_slot_key` 来自 `dayu.cli.host_context`，是既有 CLI slot key 构造 helper。
- **结论**：正确复用。

### 3. slot -> KIND/LABEL 反解是否符合 plan 第 7 节

- `display_identity_from_slot` 实现固定分支链（`session_identity.py:76-116`）：
  - `slot is None` -> `ANONYMOUS` + `"-"` ✅
  - `scope == "cli.prompt"` 且 `slot_key` 以 `"cli.prompt."` 开头且后缀非空 -> `PROMPT` + 后缀 ✅
  - `scope == "cli.interactive"` 且 `slot_key` 以 `"cli.interactive."` 开头且后缀非空 -> `INTERACTIVE` + 后缀 ✅
  - 其它 -> `OTHER` + `slot.slot_key` ✅
- `_label_suffix` 只做 `slot_key[len(expected_prefix):]` 切片，不按 `.` split（`session_identity.py:140`）。
- 空后缀返回 `None`，落入 `OTHER`（`session_identity.py:141-142`）。
- 测试覆盖：`test_display_identity_from_slot_covers_cli_and_other_slots` 断言 `proj.v1` 含点号不拆分、`cli.prompt.` 空后缀归 OTHER、非 CLI scope 归 OTHER、prefix 不匹配归 OTHER（`test_session_command.py:48-86`）。
- **结论**：完全符合 plan 第 7 节。

### 4. render 函数是否只消费 Host public DTO，不泄漏内部治理字段

- `render_session_list` 消费 `ListSessionsResult`，行渲染只取 `session_id`、`status.value`、`kind.value`、`label`、`active_run_id`、`len(queued_run_ids)`、`created_at`、`closed_at`（`output.py:317-337`）。
- `render_session_purge_result` 消费 `PurgeSessionResult`，只输出 `session_id` 和 tombstone 前缀，不输出 `deleted_counts_digest`（`output.py:170-189`）。
- 测试 `test_render_session_list_uses_public_summary_without_internal_fields` 断言 `attempt-hidden`、`execution-hidden`、`payload-ref-hidden`、`digest-hidden`、`HostStreamCursor` 均不出现在输出中（`test_session_command.py:135-139`）。
- 测试 `test_render_session_purge_result_hides_digest` 断言 `sha256`、`digest-hidden`、`payload`、`attempt`、`execution` 均不出现在输出中（`test_session_command.py:177-181`）。
- **结论**：不泄漏内部治理字段。

### 5. S3 是否越界调用 Host / 读 durable / 注册 concrete session 命令

- `session_identity.py` 只导入 `SessionSlotRef` 类型和 CLI scope/prefix 常量，不导入 Host handle 或 durable helper。
- `output.py` 只导入 `ListSessionsResult`、`PurgeSessionResult`、`SessionListItem` 类型，不调用 Host。
- `tests/cli/test_session_command.py` 直接构造 public DTO 测试 helper，不创建 Host 或 durable store。
- 未注册 `session` 命令、未实现 `session list`/`resume`/`purge`。
- **结论**：未越界。

### 6. tests/README 更新是否只记录当前测试事实

- README 补充句为："Session command helper 测试覆盖 CLI label kind 到 Host public slot ref 的映射、anonymous / prompt / interactive / other slot 展示身份反解、含点号 label 不拆分、Session list 空 / 非空输出和 purge 输出不展示删除计数 digest 或内部治理字段。"
- 与 `test_session_command.py` 中 5 个测试的实际覆盖一致。
- 未宣称 concrete session 命令已实现。
- **结论**：符合 tests/README 边界。

### 7. docstring / 类型签名 / AGENTS 约束

- 所有新增函数和类均有完整中文 docstring，含 `:param`、`:returns`、`:raises`。
- 无 `Any`、`object`、无类型参数或无类型返回值。
- `session_identity.py` 模块 docstring 说明"不调用 Host、不读取 durable store"（`session_identity.py:1-5`）。
- `PROMPT_SLOT_KEY_PREFIX` / `INTERACTIVE_SLOT_KEY_PREFIX` 未在 `host_context.__all__` 中导出，但 `session_identity.py` 通过直接 import 使用——这是合理的，因为前缀常量是 CLI 内部实现细节，`session_identity.py` 作为 CLI 内部模块需要它们做反解。
- **结论**：符合 AGENTS 约束。

## Open Questions

无。

## Residual Risk

- `render_session_list` 使用 tab 分隔文本表，无终端宽度裁剪。implementation report 已记录为后续 UX 需求。
- 仅运行 S3 指定测试（5 passed）与全项目 pyright（0 errors），未运行全量 pytest。
