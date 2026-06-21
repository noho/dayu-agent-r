# WU-CLI-SESSION-01 CLI Session 管理计划

## 1. 目标 / 动机 / 成功信号

### 目标

为 `dayu-cli` 正式补齐显式 Session 管理能力：

- 删除 `dayu-cli interactive --new-session`。
- 保持 `dayu-cli prompt` / `dayu-cli interactive` 在不带 `--label` 时每次创建 fresh anonymous Session。
- 保持 `--label <name>` 的 ensure-by-label 语义：第一次创建，后续复用。
- 增加基于 Host durable truth 的 CLI Session `list` / `resume` / `purge` 能力。
- 正式增加 Host public list sessions API，CLI 不读取 Host durable internals。

### 动机

当前用户可通过 `--label` 隐式复用 Session，但缺少显式的“我有哪些 Session / 继续哪个 Session / 删除哪个 Session”命令面。`interactive --new-session` 仍保留过时分支，且它创建的是带进程临时 slot 的新 Session；这会让用户误以为 Session 管理仍靠 interactive 命令的局部 flag，而不是 Host 统一真源。

第一性原理判断：问题真实存在，严重性中等偏高。Session 生命周期是 Host 治理真源，CLI 是 UI adapter。没有 Host public list API 时，CLI 若实现 list/resume/purge 只能绕过 Host 读 durable store，违反分层；而 resume 如果被误解为 Host wait-resume 或恢复旧 Agent/Runner，会破坏 Engine 一次执行边界。因此本 WU 应先补 Host public read contract，再在 CLI 层实现用户心智模型。

### 成功信号

- `interactive --new-session` 不再出现在 argparse help，也不能解析成功。
- 不带 `--label` 的 `prompt` / `interactive` 仍调用 `create_session(bind_slot=False)`。
- 带 `--label` 的 `prompt` / `interactive` 仍调用 `ensure_session(scope=cli.prompt|cli.interactive, slot_key=cli.<command>.<label>)`。
- 新 Host public `list_sessions` 可通过 `open_host(...).list_sessions(...)` 与函数式 `dayu.host.list_sessions(...)` 读取 Session 列表。
- CLI `session list` 的输出来自 Host public list API。
- CLI `session resume` 根据 `session_id` 或 label 选择已有 OPEN Session，继续提交新的 prompt / interactive turn；不恢复旧 Agent、Runner、Attempt。
- CLI `session purge` 调用 Host public `purge_session`，并对未 close / 非终态 Run 的前置条件失败给出清楚错误。
- 受影响 pytest 与 pyright 通过，无新增类型错误。

## 2. 非目标 / 范围边界

- 不修改 Engine 运行语义；不增加 Engine Session 概念；不恢复旧 Agent / Runner / Attempt。
- 不把 CLI resume 设计为 Host `resolve_wait(...)` 的等待恢复入口。
- 不新增 workflow、后台 job、跨重启 CLI process owner、客户端 ownership 真源。
- 不让 CLI 直接读取 `dayu.host.durable.*` 或 SQLite。
- 不把 `purge` 等同于 `close` / `cancel` / archive / UI hide。
- 不实现旧库兼容读取或 schema migration；本 WU 的 Host list sessions 应基于现有 `host_sessions` / `host_session_slots` / `host_runs` 表。
- 不修改 `docs/host/issues-implementation-control.md`。
- 不做 PR / commit / push。

## 3. 设计文档对齐

### Host

`docs/host/design.md` 已明确：

- Host 是 Session / Run / Attempt / EventLog / admission / cancel / resume / retry / replay / memory / tool governance 的治理真源。
- Engine 不拥有 Session / Run 生命周期。
- `ensure_session`、`create_session`、`get_session`、`close_session`、`purge_session`、`get_run`、`watch_session_events` 等是普通 Service-facing 稳定公共能力。
- `purge_session` 是 destructive retention exception，必须先满足 Session closed 且所有 Run 终态等前置条件。

本 WU 应在该设计基础上正式增加 `list_sessions` 为 Host public read API。它是 `get_session` 的集合读取 sibling：只读 durable truth，不写 EventLog，不启动 dispatch，不依赖 projection。

### Engine

`docs/engine/design.md` 已明确 Engine 是 run-scoped 一次性 Agent / Runner 模型，不保存跨 run 状态，也不拥有 Session 生命周期。CLI resume 只是在已有 Host Session 上提交新的 follow-up Run；它不改 Engine。

## 4. 直接代码证据

- `dayu/cli/arg_parsing.py` 当前 `ParsedCliArgs` 有 `new_session: bool`，`_new_default_namespace()` 设为 `False`；`_register_interactive_command()` 在 mutually exclusive group 中注册 `--label` 和 `--new-session`。这是 obsolete CLI surface 的直接证据。
- `dayu/cli/commands/prompt.py::_ensure_prompt_session()` 在 `args.label is None` 时调用 `ensure_or_create_entrypoint_session(create_new=True, bind_slot=False, scope=None, slot_key=None)`；带 label 时使用 `prompt_slot_key(args.label)` 和 `PROMPT_SESSION_SCOPE` 调用 `ensure_session`。这证明 prompt 默认已经 fresh anonymous，label 已 ensure-by-label。
- `dayu/cli/commands/interactive.py::_ensure_interactive_session()` 带 label 时使用 `interactive_slot_key(args.label)` 和 `INTERACTIVE_SESSION_SCOPE` 调用 `ensure_session`；无 label 且无 `new_session` 时创建 `bind_slot=False` 的 fresh anonymous Session；但 `args.new_session` 分支仍创建 `bind_slot=True`、slot 为 `interactive_process_slot_key(invocation)` 的进程临时 Session。该分支应删除。
- `dayu/cli/host_context.py` 已定义 `PROMPT_SESSION_SCOPE = "cli.prompt"`、`INTERACTIVE_SESSION_SCOPE = "cli.interactive"` 与 label 到 slot key 的映射，后续 resume-by-label 应复用这套模型。
- `dayu/host/api.py::Host` 目前只有 `ensure_session`、`create_session`、`get_session`、`get_run`、outbox、submit、retry、replay、resolve、cancel、close、purge、maintenance 等方法，没有 `list_sessions`。
- `dayu/host/open_host.py::_PublicHostHandle` 已把 async handle 方法逐一转发到 command/read facade；新增 list API 应跟随 `get_session` / `get_run` 模式。
- `dayu/host/read_api.py` 当前 `get_session()` 使用 `_GetSessionOperation` 读取 durable session row 与 slot row，再通过 `session_snapshot_from_rows(...)` 生成 public snapshot；list sessions 应放在同一 read facade，不应进入 command path。
- `dayu/host/durable/state.py` 已有 `read_session_by_id(...)`、`read_session_slot_by_session_id(...)`、`session_snapshot_from_rows(...)`，并且 `host_sessions` row 已包含 `created_at` / `closed_at`。list 不需要 schema migration。
- `dayu/host/command.py::purge_session()` 已把未关闭或非终态 Run 前置条件映射为 `HostApiErrorCode.INVALID_STATE`，message 为 `purge_session requires a closed Session with terminal Runs`。CLI purge 应保留这个 Host truth，并给用户可理解错误。
- `tests/cli/test_arg_parsing.py` 当前 help expectation 包含 interactive `--new-session`，后续必须更新。
- `tests/cli/test_interactive_command.py` 当前有 `test_interactive_new_session_creates_bound_process_session`，后续必须删除或改为断言 `--new-session` 用法错误。
- `tests/host/test_public_session_api.py` 当前覆盖 ensure/create/get/close/purge，但没有 list sessions API。
- `tests/host/test_package_exports.py` 锁定 `dayu.host` 包根导出与 `dayu.host.api.__all__`，新增 public dataclass / facade 必须同步测试。

## 5. 受影响文件 / 模块

### Host public API

- `dayu/host/api.py`
- `dayu/host/read_api.py`
- `dayu/host/open_host.py`
- `dayu/host/durable/state.py`
- `dayu/host/__init__.py`

### CLI

- `dayu/cli/arg_parsing.py`
- `dayu/cli/main.py`
- `dayu/cli/host_context.py`
- `dayu/cli/output.py`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- 新增 `dayu/cli/commands/session.py`
- 可选新增 `dayu/cli/session_identity.py` 或 `dayu/cli/session_selection.py`，仅放 CLI 层，承载 label/session-id 解析与展示 helper。

### 测试

- `tests/host/test_public_session_api.py`
- `tests/host/test_package_exports.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- 新增 `tests/cli/test_session_command.py`
- `tests/README.md`

### 文档

- `docs/host/design.md`
- `dayu/host/README.md`
- `dayu/README.md`
- `tests/README.md`

## 6. 公共契约 / Schema / 状态机变更

### Host API dataclass

在 `dayu/host/api.py` 增加：

```text
@dataclass(frozen=True, slots=True)
class SessionListItem:
  session_id: str
  status: SessionStatus
  slot: SessionSlotRef | None
  active_run_id: str | None
  queued_run_ids: tuple[str, ...]
  timeline_cursor: HostStreamCursor
  created_at: datetime
  closed_at: datetime | None

@dataclass(frozen=True, slots=True)
class ListSessionsResult:
  sessions: tuple[SessionListItem, ...]
```

不要新增开放 filter/profile/query callback。第一版 `list_sessions()` 无 request 参数，返回全部当前未 purge 的 Session，按 `created_at DESC, session_id ASC` 稳定排序。这个接口满足 CLI list/resume/purge 的真实需求，避免过早设计分页、搜索 DSL 或 operator report。

字段说明：

- `session_id` 是 Host Session identity。
- `status` 是 `OPEN` / `CLOSED`。
- `slot` 为 `None` 表示 anonymous Session；非空时表达 Host slot binding。
- `active_run_id` / `queued_run_ids` 是 Host admission truth 的当前摘要。
- `timeline_cursor` 复用 `SessionSnapshot` 的全局 EventLog cursor 语义。
- `created_at` / `closed_at` 来自 durable Session row，使用 timezone-aware UTC `datetime`。

时间戳转换规则：

- durable `SessionRow.created_at` / `closed_at` 是固定 UTC timestamp 字符串，不是 public `datetime`。
- `read_api.list_sessions` 在 `SessionRow -> SessionListItem` 转换时必须复用 `dayu.host.durable.codec.parse_utc_timestamp(...)`，不得自行使用宽松 ISO parser。
- `created_at` 必须解析成功；`closed_at is None` 时 public 字段保持 `None`，非空时必须解析成功。
- `parse_utc_timestamp(...)` 返回 timezone-aware UTC `datetime`，这就是 public contract。
- durable row 中 timestamp 格式非法、日期非法或非固定 UTC `Z` 格式时，转换 helper 必须把底层 `ValueError` 包装为 `HostDurableError`，错误信息说明 `session row timestamp is invalid` 或同等语义；不得静默降级、返回 `None` 或暴露 raw string。

`SessionListItem` 与 `SessionSnapshot` 的不对称是本 WU 的有意设计：`created_at` / `closed_at` 只作为 list-summary fields 加入 `SessionListItem`，本 WU 不扩展 `SessionSnapshot`。理由是当前需求只要求 CLI list 展示和选择摘要；`get_session(session_id)` 的既有契约不为本 WU 承担时间戳扩展。除非 implementation agent 发现直接代码证据证明 `SessionSnapshot` 不扩展会导致 `list_sessions` 无法同源实现，否则不得顺手扩大 `SessionSnapshot` public surface。

### Host Protocol / Opener / Read API

- `Host` Protocol 增加 `async def list_sessions(self) -> ListSessionsResult`。
- `_PublicHostHandle` 增加 `list_sessions()`，先 `_raise_if_closed()`，再调用 `dayu.host.read_api.list_sessions(...)`。
- `dayu.host.read_api` 增加 `list_sessions(host: HostCommandHandle) -> ListSessionsResult`。
- `dayu/host/api.py` 的 `Host` Protocol 增加 `list_sessions` 方法；`dayu.host.api.__all__` 增加 `SessionListItem`、`ListSessionsResult`，并保持 `Host` Protocol 是 public handle 真源。
- `dayu/host/read_api.py` 增加 `list_sessions(...)`，并同步 `read_api.__all__`。
- `dayu/host/open_host.py` 的 `_PublicHostHandle` 增加 async `list_sessions()`，闭包检查与 `get_session` / `get_run` 一致。
- `dayu/host/__init__.py` 包根导入并导出 `SessionListItem`、`ListSessionsResult`、`list_sessions`。
- `tests/host/test_package_exports.py` 同步 expected exports；断言 public exports 包含新 symbols，且不导出 durable helper。

### Durable 读取 helper

在 `dayu/host/durable/state.py` 增加只读 helper，例如：

```text
@dataclass(frozen=True, slots=True)
class SessionWithSlotRows:
  session: SessionRow
  slot: SessionSlotRow | None

def read_all_sessions_with_slots(transaction: HostTransaction) -> tuple[SessionWithSlotRows, ...]
```

该 helper：

- 从 `host_sessions` left join 当前 `host_session_slots`。
- 不读取 purge tombstone；已 purge Session 已从 `host_sessions` 删除，因此自然不会出现在结果中。
- 上述“已 purge 不出现”指 read transaction 开始时的 durable snapshot。若并发 purge 在本次 read transaction 开始后提交，本次 `list_sessions` 可以仍看到旧 snapshot；后续 `get_session` / `submit_followup` / `purge_session` 等 Host command 仍是最终 truth。
- 不做 projection catch-up。
- 不返回裸 `HostRow`、dict、tuple bag 或 `Any`。
- 排序固定为 `created_at DESC, session_id ASC`。

`read_api.list_sessions` 在 read transaction 中把每行转成 `SessionListItem`。可复用 `session_snapshot_from_rows(...)` 以保持 active / queued / cursor 语义同源，但要注意不要为每个 item 引入不必要的重复代码；若需要专门转换 helper，也应在 `state.py` 或 `read_api.py` 内部私有化。

### Schema

不需要 durable schema migration。现有 `host_sessions`、`host_session_slots`、`host_runs` 已能支持第一版 list。若实现中发现必须新增索引，只能按项目 schema 规则以 fresh schema 起库处理，不写旧库兼容读取方案。

### 状态机

- `list_sessions` 是只读 API，不改变 Session / Run / Attempt / EventLog / projection / outbox / memory 状态。
- `resume` 不是新的 Host lifecycle transition；它等价于对已有 OPEN Session 调用 `submit_followup(behavior=QUEUE)`。
- `purge` 继续使用现有 `purge_session` 状态机；CLI 不绕过 `close_session` 前置条件，也不自动 cancel / close。

## 7. CLI 命令面设计

### 命令命名空间

新增 top-level namespace：

```text
dayu-cli session list
dayu-cli session resume ...
dayu-cli session purge ...
```

建议使用 singular `session`，避免把旧 `sessions` 排除项直接复活为含糊兼容命令。`EXCLUDED_COMMAND_NAMES` 可保留 `"sessions"`，新增 `COMMAND_SESSION = "session"`。

### `session list`

命令：

```text
dayu-cli session list [--show-closed]
```

第一版默认显示所有未 purge Session。`--show-closed` 如果保留，应只是显示策略；若默认已显示 open + closed，则不要加该参数。为避免无必要分支，推荐第一版无参数，全部显示。

输出 text table，列：

- `SESSION_ID`
- `STATUS`
- `KIND`：`prompt` / `interactive` / `anonymous` / `other`
- `LABEL`：从 `cli.prompt.<label>` 或 `cli.interactive.<label>` 反解；anonymous 显示 `-`
- `ACTIVE_RUN`
- `QUEUED`
- `CREATED_AT`
- `CLOSED_AT`

KIND / LABEL 反解必须只使用 Host slot truth，规则固定为：

- `slot is None` -> `KIND=anonymous`，`LABEL=-`。
- `slot.scope == "cli.prompt"` 且 `slot.slot_key` 以 `"cli.prompt."` 开头并带非空后缀 -> `KIND=prompt`，`LABEL=slot.slot_key[len("cli.prompt."):]`。
- `slot.scope == "cli.interactive"` 且 `slot.slot_key` 以 `"cli.interactive."` 开头并带非空后缀 -> `KIND=interactive`，`LABEL=slot.slot_key[len("cli.interactive."):]`。
- 其它 Host slot，包括非 CLI scope、CLI scope 但 slot_key 前缀不匹配或后缀为空 -> `KIND=other`，`LABEL=<slot.slot_key>`。

label 允许包含点号；反解时只移除固定前缀，不按 `.` split。例如 `slot_key="cli.prompt.proj.v1"` 必须显示 `LABEL=proj.v1`。

错误语义：

- Host open / list 失败：stderr `dayu-cli session list: <message>`，exit `1`。
- 无 Session：stdout 输出可读空状态，例如 `No sessions.`，exit `0`。

不要在 list 输出中展示 tool_call_id、Attempt id、execution id、payload digest、projection cursor 等内部治理信息。

### `session resume`

命令：

```text
dayu-cli session resume --session-id <session_id> --mode prompt "<prompt>"
dayu-cli session resume --session-id <session_id> --mode interactive
dayu-cli session resume --label <label> --kind prompt --mode prompt "<prompt>"
dayu-cli session resume --label <label> --kind interactive --mode interactive
```

参数：

- 必须二选一：`--session-id <id>` 或 `--label <name>`。
- 使用 `--label` 时必须提供 `--kind prompt|interactive`，因为同一个 label 在 `cli.prompt` 与 `cli.interactive` 是不同 Host slot namespace。
- `--mode prompt|interactive` 表示 resume 后使用 one-shot prompt 还是 REPL。
- `--mode prompt` 必须提供 positional prompt。
- `--mode interactive` 不接受 positional prompt。
- 支持与 `prompt` / `interactive` 相同的 Agent execution options：`--ticker`、`--model-name`、`--thinking`、`--web-provider`、`--temperature`、tool timeout、fallback、limits 等。不要把这些 option 放入 extra payload。

Session 选择：

- `--session-id`：调用 `host.get_session(session_id)` 或 `list_sessions` 后匹配，缺失为 usage/lookup error。
- `--label + --kind`：通过 Host `list_sessions()` 在 slot truth 中查找对应 `cli.prompt.<label>` 或 `cli.interactive.<label>`；找不到时失败，不创建新 Session。
- 如果目标 Session status 是 `CLOSED`，CLI 在 submit 前失败，提示需要新建 Session 或选择 open Session；exit `2` 或 `1` 均可，但推荐 `2` 表示用户选择了不可用目标。最终实现必须测试并固定。
- 如果 Session 在 preflight 后被并发关闭，`submit_followup` 的 HostApiError 直接映射为 stderr 与失败退出码；Host 是最终 truth。

执行语义：

- prompt resume：复用 prompt scene / context / Service runtime assembly / SIGINT cancel 语义，在选中的 Session 上提交新 prompt。
- interactive resume：复用 interactive scene / REPL / 每轮 watcher / SIGINT cancel 语义，在选中的 Session 上提交后续用户输入。
- resume 不绑定 slot，不修改 label，不创建新 Session。

### `session purge`

命令：

```text
dayu-cli session purge --session-id <session_id> --yes [--reason <text>]
dayu-cli session purge --label <label> --kind prompt --yes [--reason <text>]
```

参数：

- 必须二选一：`--session-id` 或 `--label + --kind`。
- 必须提供 `--yes`。这是 destructive 操作，非交互确认更适合 CI 和测试；第一版不做 stdin prompt。
- `--reason` 可选；默认 `cli_session_purge`。

错误语义：

- 缺少 `--yes`：usage error，exit `2`。
- 目标不存在：stderr 明确 `Session not found` 或 `No session found for label ...`，exit `2`。
- Host 返回 `INVALID_STATE`：stderr 说明 purge 需要 closed Session 且所有 Run 已终态，不自动 close/cancel；exit `1`。
- Host 返回 `CONFLICT`：说明已被其它请求 purge；exit `1`。
- Host 返回 `IDEMPOTENCY_CONFLICT`：说明同一 client_request_id 语义冲突；exit `1`。
- 成功输出固定为一行：`Purged session <session_id> (tombstone: <tombstone_ref_prefix>...)`，exit `0`。`<tombstone_ref_prefix>` 为 tombstone ref 去掉空白后的前 12 个字符；若 ref 短于 12 个字符则使用完整 ref，仍保留结尾 `...`。测试只断言该固定格式，不解析完整 tombstone。

并发语义：

- `purge --label` 先通过 `list_sessions()` 把用户 selector 解析为 `session_id`，再调用 Host `purge_session`。这两个步骤之间存在 TOCTOU 窗口，CLI 不做锁或 CAS。
- 若解析后目标被其它进程 close/purge，Host `purge_session` 的 durable transaction precondition 是最终 truth；CLI 必须把 HostApiError 原样归类，并在 stderr 同时包含用户原始 selector（例如 `--label foo --kind prompt`）和 Host error context（至少包含 resolved `session_id`、Host error code/message）。
- 同样，`resume --label` 解析后若 Session 被并发 close，`submit_followup` 的 Host precondition 是最终 truth；CLI 错误也必须包含用户原始 selector 与 Host error context。

CLI purge 不应自动调用 `close_session`，因为 close 是独立用户意图。若后续需要 `session close`，应另立 work unit。

## 8. Session 身份模型

### Anonymous Session

- 由 `prompt` / `interactive` 无 `--label` 创建。
- Host `SessionSnapshot.slot is None`。
- 每次命令启动都是新的 Session。
- 可通过 `session list` 看到 `KIND=anonymous`。
- 可通过 `session resume --session-id ...` 继续使用；不能通过 label 恢复。

### Labeled Session

- 由 `prompt --label <name>` 或 `interactive --label <name>` 创建或复用。
- Prompt label 映射为 `scope=cli.prompt`、`slot_key=cli.prompt.<name>`。
- Interactive label 映射为 `scope=cli.interactive`、`slot_key=cli.interactive.<name>`。
- 同一个 `<name>` 在 prompt 与 interactive 下是两个不同 label namespace。
- `session list` 从 Host slot truth 展示 label，不从 CLI 本地缓存推断。

### Resumed Session

- 由 `session resume` 明确选中已有 Session。
- 使用 `--session-id` 时不关心该 Session 是否有 label。
- 使用 `--label + --kind` 时必须命中现有 Host slot；找不到不创建。
- resume 只提交新的 prompt / interactive turn；不恢复旧 Agent / Runner / Attempt，不触碰 Host wait-resume。

### Purged Session

- 成功 purge 后不再出现在之后新开的 `list_sessions()` read transaction 中。
- 正在运行的 `list_sessions()` 看到的是 read transaction snapshot；并发 purge 可能对该 snapshot 不可见，这是可接受的一致性边界。
- `get_session(session_id)` 继续返回 `NOT_FOUND`。
- purge tombstone 只用于审计 / 幂等，不参与 resume、retry、replay、memory 或 RunInputBuilder。

## 9. 实现切片

### Slice S1 - Host public list sessions API

**目标**：增加只读 Host public `list_sessions` API，并基于 durable truth 返回 typed list result。

**允许修改文件 / 模块**：

- `dayu/host/api.py`
- `dayu/host/read_api.py`
- `dayu/host/open_host.py`
- `dayu/host/durable/state.py`
- `dayu/host/__init__.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_package_exports.py`

**精确变更**：

- 新增 `SessionListItem`、`ListSessionsResult` dataclass，字段与第 6 节一致，中文 docstring 完整说明参数、返回值、异常。
- `Host` Protocol 增加 `list_sessions`；`dayu.host.api.__all__` 增加新的 public dataclass。
- `_PublicHostHandle` 增加 async `list_sessions`。
- `read_api.list_sessions(...)` 增加 read transaction operation；`read_api.__all__` 增加 `list_sessions`。
- `state.py` 增加 typed durable read helper，不返回裸 row bag。
- 包根 `dayu/host/__init__.py` 导出与 export 测试同步。
- `SessionRow.created_at` / `closed_at` 转 public datetime 时使用 `parse_utc_timestamp(...)`；malformed durable timestamp 包装为 `HostDurableError`。

**非目标**：

- 不加 pagination/filter DSL。
- 不加 schema migration。
- 不加 CLI。

**测试 / 验证**：

- `test_list_sessions_returns_open_closed_and_anonymous_labeled_sessions`
- `test_list_sessions_excludes_purged_session`
- `test_list_sessions_rejects_malformed_session_timestamp`
- `test_list_sessions_closed_handle_errors_through_open_host` 或复用 opener 测试风格。
- `test_package_exports` 同步新增 symbols。

**完成信号**：

- Host public list API 可从 command facade 与 async `open_host` handle 调用。

**停止条件**：

- 如果需要新增表或改变已有 row shape，停止并回到设计；按 fresh schema 起库规划，不做兼容读取。

### Slice S2 - 删除过时的 `interactive --new-session`

**目标**：删除过时 CLI surface，保持 interactive 默认 fresh anonymous 行为不变。

**允许修改文件 / 模块**：

- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/host_context.py`，仅当删除 `interactive_process_slot_key` 后无引用时清理
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_interactive_command.py`
- `tests/README.md`

**精确变更**：

- `ParsedCliArgs` 删除 `new_session` 字段；默认 namespace 删除对应赋值。
- `_register_interactive_command()` 删除 mutually exclusive group，直接注册 `--label`。
- `_ensure_interactive_session()` 删除 `args.new_session` 分支。
- 若 `interactive_process_slot_key(...)` 无其它用途，删除该 helper、测试引用，并同步从 `host_context.__all__` 中移除。
- 更新 help expectation，不再包含 `--new-session`。
- 将 `test_interactive_new_session_creates_bound_process_session` 改为解析 `--new-session` 返回 usage error，或直接删除该旧语义测试并增加 parser negative test。

**非目标**：

- 不改变 label 行为。
- 不改变默认 anonymous Session。
- 不新增 resume/list/purge。

**测试 / 验证**：

- `pytest tests/cli/test_arg_parsing.py tests/cli/test_interactive_command.py -q`

**完成信号**：

- `dayu-cli interactive --help` 不含 `--new-session`。
- `parse_cli_args(("interactive", "--new-session"))` 失败。

**停止条件**：

- 如果删除 `new_session` 迫使旧兼容 wrapper 出现，停止；不要保留兼容 flag。

### Slice S3 - CLI Session 选择 / 输出 helper

**目标**：为 `session` 命令建立 CLI-local identity 解析和展示，不让 command handler 直接拼散落逻辑。

**允许修改文件 / 模块**：

- 新增 `dayu/cli/session_identity.py` 或 `dayu/cli/session_selection.py`
- `dayu/cli/host_context.py`
- `dayu/cli/output.py`
- `tests/cli/test_session_command.py`

**精确变更**：

- 增加 label kind enum 或受限字符串常量：`prompt` / `interactive`。
- 增加 label -> slot ref helper，复用 `prompt_slot_key` / `interactive_slot_key` 与 scope 常量。
- 增加从 `SessionListItem.slot` 反解 CLI display kind/label 的 helper，精确规则必须与第 7 节 KIND / LABEL 反解一致：anonymous、prompt、interactive、other 四类固定，不按点号拆 label。
- 增加 `render_session_list(...)`、`render_session_purge_result(...)` 等输出 helper。
- 所有 helper 使用严格类型；禁止 `Any`、`object`、裸 dict/list 签名。

**非目标**：

- 不调用 Host。
- 不读取 durable internals。

**测试 / 验证**：

- label 反解覆盖 anonymous / prompt / interactive / other slot；必须包含 label 含点号的用例，例如 `proj.v1`。
- 输出不展示 Attempt / execution / payload ref / digest。

**完成信号**：

- CLI session command 可以复用统一 selector/output helper。

**停止条件**：

- 如果 helper 开始承载 Host 状态机判断，停止并拆回 command handler 或 Host public API。

### Slice S4 - CLI `session list` 与 `session purge`

**目标**：增加显式 Session 管理命令中的只读 list 与 destructive purge。

**允许修改文件 / 模块**：

- `dayu/cli/arg_parsing.py`
- `dayu/cli/main.py`
- 新增 `dayu/cli/commands/session.py`
- `dayu/cli/output.py`
- `dayu/cli/host_context.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_session_command.py`

**精确变更**：

- `CLI_COMMAND_NAMES` 增加 `COMMAND_SESSION = "session"`。
- 注册 `session` 子命令，并在其下注册 `list` / `resume` / `purge` subcommand。S4 只实现 list/purge；resume 可以先返回 not implemented 也可以在 S5 同时落地，但 parser shape 需一次固定。
- `COMMAND_RUNNERS[COMMAND_SESSION] = run_session_command`。
- `run_session_command` 使用 `prepare_entrypoint_runtime(...)` + `open_host(...)`，只通过 Host public API list/purge。
- purge 构造 `PurgeSessionRequest`，`client_request_id` 使用本次 CLI invocation id 派生；同一次命令内稳定即可，不需要跨进程固定。
- purge 必须要求 `--yes`。
- HostApiError 映射为用户可读 stderr 与固定 exit code。

**非目标**：

- 不自动 close/cancel。
- 不实现 JSON output，除非 implementation agent 证明已有 CLI 输出模式需要。

**测试 / 验证**：

- Parser help 包含 `session list/resume/purge`。
- list 调用 fake Host `list_sessions`，输出 anonymous/labeled/open/closed。
- purge 缺 `--yes` 返回 usage error。
- purge by `session_id` 调用 Host `purge_session`。
- purge by label 先用 `list_sessions` resolve slot，再调用 Host `purge_session`。
- Host `INVALID_STATE` 输出清楚错误，不调用 close/cancel。
- purge by label 的 TOCTOU 测试：fake Host `list_sessions` 返回匹配 label 的 session A，随后 `purge_session(A)` 抛出 `CONFLICT` 或 `NOT_FOUND`；stderr 必须同时包含原始 selector（label + kind）与 Host error context（session A + code/message）。
- purge 成功输出严格断言 `Purged session <session_id> (tombstone: <prefix>...)`。

**完成信号**：

- `session list` 和 `session purge` 完成端到端 mocked Host 测试。

**停止条件**：

- 如果需要用户交互式确认，先固定 `--yes` 策略；不要实现 stdin prompt。

### Slice S5 - CLI `session resume`

**目标**：在选定 Host Session 上继续 prompt 或 interactive 输入。

**允许修改文件 / 模块**：

- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/session.py`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/host_context.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`

**精确变更**：

- 明确拆成两段：`session.py` 只负责 selector resolution；`prompt.py` / `interactive.py` 只负责 execute on existing Session。二者不得互相复制职责。
- 在 `session.py` 增加私有解析边界，例如 `_resolve_existing_session_id(host: Host, selector: CliSessionSelector) -> str`：
  - 参数：Host public handle；用户 selector，包含原始命令面（`session_id` 或 `label + kind`）以及用于错误展示的原始 selector 文本。
  - 返回值：已存在且在解析时为 `SessionStatus.OPEN` 的 `session_id`。
  - 行为：`session_id` selector 调用 `get_session`；`label + kind` selector 调用 `list_sessions()` 并用第 7 节 slot 规则精确匹配；找不到不创建。
  - 异常：找不到或解析到 CLOSED Session 时抛 CLI usage error；HostApiError / HostDurableError 不吞掉，交给 session command 顶层映射为 stderr。
  - stop condition：解析函数不得调用 `create_session`、`ensure_session`、`submit_followup`、prompt / interactive 执行 helper。
- 在 `prompt.py` 抽出窄入口，例如 `_execute_prompt_on_existing_session(...) -> int`：
  - 参数：`ParsedCliArgs`、已选定 `session_id: str`、`CliInvocation` 或创建 invocation 所需的 command/scenario 输入；必要时注入 `CliSigintMonitor` 以保持测试可控。
  - 返回值：CLI exit code，语义与 `run_prompt_command` 当前返回一致。
  - 行为：复用 prompt scene/runtime assembly、`service_run_overrides_from_args`、`_submit_prompt_turn_handling_sigint(...)` 与 `render_prompt_terminal_result(...)`；不得调用 `_ensure_prompt_session`、`create_session` 或 `ensure_session`。
  - 异常：参数用法错误继续抛 `CliCommandUsageError`；Host submit/watch/cancel 错误向上透传，由调用方按现有 CLI 顶层规则渲染。
- 在 `interactive.py` 抽出窄入口，例如 `_execute_interactive_on_existing_session(...) -> int`：
  - 参数：`ParsedCliArgs`、已选定 `session_id: str`、`input_reader: Callable[[str], str]`、`CliInvocation` 或创建 invocation 所需输入；必要时注入 `sigint_monitor_factory`。
  - 返回值：CLI exit code，语义与 `run_interactive_command` 当前返回一致。
  - 行为：复用 interactive scene/runtime assembly、`service_run_overrides_from_args`、`_run_interactive_repl(...)`、每轮 watcher 与 SIGINT cancel；不得调用 `_ensure_interactive_session`、`create_session` 或 `ensure_session`。
  - 异常：参数用法错误继续抛 `CliInteractiveUsageError`；Host submit/watch/cancel 错误向上透传。
- `session resume --session-id ... --mode prompt "<prompt>"`：resolve session -> 校验 OPEN -> 调用 prompt execute-on-existing-session。
- `session resume --session-id ... --mode interactive`：resolve session -> 校验 OPEN -> 调用 interactive execute-on-existing-session。
- `session resume --label ... --kind ...`：通过 `list_sessions()` 找现有 slot；找不到不创建。
- 复用 `build_prompt_host_context` / `build_interactive_host_context`；operation 可使用 `resume_session` 或 `submit_followup`，但 LLM-facing prompt 不暴露 Host 内部治理术语。
- 若 selector resolution 后、submit 前 Session 被并发关闭或 purge，`submit_entrypoint_turn_and_wait` / Host command precondition 是最终 truth；session command stderr 必须包含原始 selector 与 Host error context。

**非目标**：

- 不新增 Host API `get_session_by_label`。
- 不改变 prompt / interactive 默认入口行为。
- 不把 resume 做成 steer；使用 `FollowupBehavior.QUEUE`。

**测试 / 验证**：

- resume prompt by session id 调用 fake Host `get_session` + `submit_followup`，不调用 `create_session` / `ensure_session`。
- resume interactive by label 调用 `list_sessions` resolve 后连续两轮同 Session。
- closed Session resume 返回用户错误，不 submit。
- missing label 返回用户错误，不 create。
- resume by label 的 TOCTOU 测试：fake Host `list_sessions` 返回匹配 label 的 session A，随后 submit 抛出 `INVALID_STATE`；stderr 包含原始 selector、session A 与 Host code/message。
- prompt / interactive 原有 tests 仍通过。

**完成信号**：

- 用户可明确选择历史 Session 并继续 prompt 或 interactive turn。

**停止条件**：

- 如果为了复用 prompt/interactive core 需要把大量私有状态跨模块导入，先在原模块内拆出上述 execute-on-existing-session 窄入口；不要复制 submit/watch/cancel 业务路径。
- 如果抽取会迫使 `session.py` 直接组装 Service runtime 或 Host submit request，停止并回到 plan review；`session.py` 只能编排 selector、mode 与已有 command 执行入口。

### Slice S6 - 文档同步

**目标**：代码落地后同步设计真源与开发手册。

**允许修改文件 / 模块**：

- `docs/host/design.md`
- `dayu/host/README.md`
- `dayu/README.md`
- `tests/README.md`

**精确变更**：

- `docs/host/design.md`：在 Host public API 列表中加入 `list_sessions`，说明它是 durable read truth、不是 projection，不触发执行；补充 CLI resume 与 Host wait-resume 的术语区分。
- `dayu/host/README.md`：先遵守其 Agent 更新约束，只写已实现能力；在接口列表、公共契约与 read truth 章节加入 `list_sessions`。
- `dayu/README.md`：仅在 Host public contract 总览中补充 `list_sessions`，不写 CLI 用户手册。
- `tests/README.md`：更新 CLI 测试覆盖描述，删除 `interactive --new-session`，加入 session list/resume/purge；更新 Host 公共 API测试描述。

**非目标**：

- 不写 work unit 过程状态。
- 不把 CLI 使用手册塞进 Host README。

**测试 / 验证**：

- 文档无需单独测试，但最终 `pyright` 和相关 pytest 必须通过。

**完成信号**：

- 文档与已实现 public contract 一致。

**停止条件**：

- 如果发现 `docs/host/design.md` 需要先改才能让 scope 成立，先完成设计文档 slice，再继续实现；本 plan 不直接改设计真源。

## 10. 测试 / 验证命令与预期断言

### 受影响 pytest

```bash
source .venv/bin/activate
pytest tests/host/test_public_session_api.py tests/host/test_package_exports.py -q
pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py -q
```

预期断言：

- Host list API 返回 open/closed、anonymous/labeled Session，排序稳定。
- 已 purge 的 Session 不出现在 list 中。
- `list_sessions` 把 durable timestamp string 解析为 timezone-aware UTC `datetime`；malformed durable timestamp 抛 `HostDurableError`，不静默降级。
- `SessionListItem` 包含 `created_at` / `closed_at`；`SessionSnapshot` 在本 WU 不新增这两个字段。
- `dayu.host` 包导出包含新的 public list 符号，且不泄漏 durable helper。
- `dayu.host.api.__all__`、`dayu.host.read_api.__all__`、`dayu.host.__init__.__all__` 与 `tests/host/test_package_exports.py` 同步。
- `interactive --new-session` 已移除。
- 既有 prompt/interactive 默认与 label Session 测试继续通过。
- Session list/resume/purge 命令测试使用 mocked Host public API，不使用真实 Host durable internals。
- label 反解稳定覆盖 anonymous、prompt、interactive、other，且 label 包含点号时只剥离固定前缀。
- purge 成功输出格式固定为 `Purged session <session_id> (tombstone: <prefix>...)`。
- purge/resume by label 的 resolve-then-command TOCTOU 场景下，stderr 包含用户原始 selector 与 Host error context。

### 更宽的定向 pytest

```bash
source .venv/bin/activate
pytest tests/cli tests/host/test_public_session_api.py tests/host/test_package_exports.py -q
```

### 类型检查

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

预期断言：

- pyright 0 errors。
- 无新增 weak typing guard 违规：触及代码不得新增 `Any` / `object` / 无类型签名 / 裸容器注解。

### 覆盖率

新增 `dayu/cli/commands/session.py` 与任何新 CLI helper 模块的单文件覆盖率目标为 >= 80%。如果仓库当前没有方便的单文件覆盖率命令，implementation agent 至少要确保分支测试覆盖：

- list 空 / 非空。
- 按 session id / label resume。
- purge 成功 / 缺少 `--yes` / invalid state。
- label kind 消歧。

## 11. 文档决策

- `docs/host/design.md` 必须更新，因为 Host public API 发生变化。
- `dayu/host/README.md` 必须检查，且代码落地后大概率需要更新，因为 Host public handle 与包导出发生变化。其 Agent 更新约束禁止写未来计划，所以只能在实现真实存在后更新。
- `dayu/README.md` 必须检查，且大概率需要更新，因为跨包 Host public contract 发生变化。
- `tests/README.md` 必须更新，因为 CLI 与 Host 测试范围变化。
- Engine 语义不变，因此不需要更新 Engine README。
- 除非 implementation 触及 `dayu/config/`，否则不需要更新 config README。

## 12. 风险 / 开放问题

- **CLI 命令命名空间**：本 plan 推荐 `dayu-cli session ...`。如果产品侧坚持 `sessions ...`，implementation 必须同步更新 `EXCLUDED_COMMAND_NAMES`，且不要增加兼容 alias。
- **Closed Session resume exit code**：推荐对用户选择 closed Session 返回 usage error `2`。如果 implementation 将所有 HostApiError 都映射为 `1`，测试必须显式冻结该选择。
- **List 规模**：第一版不做 pagination 是有意的最小设计。如果真实 workspace 可能有大量 Session，应另开 follow-up issue 设计 pagination，而不是在本 WU 过度设计。
- **List query amplification**：本 WU 可使用 straightforward read 实现；若真实 Session 规模导致性能压力，future list pagination / performance hardening follow-up 负责。当前 plan 不因此扩大 Host contract。
- **Purge 确认**：本 plan 使用强制 `--yes`，不做 stdin prompt。这是为了 deterministic CLI tests 与 CI 使用。
- **Session 时间戳**：Public `SessionListItem.created_at/closed_at` 会在 Host API 中引入 datetime 字段。如果 reviewer 认为该 contract surface 过大，fallback 是从 public dataclass 与 CLI list 中移除时间戳；但 list UX 会变弱。不要暴露 raw durable timestamp string。
- **Resume by label uses list_sessions**：本 plan 不新增 `get_session_by_label` API，以免在真实非 CLI 调用方需要前扩大 Host surface。
- **No ListSessionsRequest**：`list_sessions()` 沿用 `get_session` / `get_run` 的只读零参数模式；本 WU 不添加 request envelope、filter、profile、query 或 callback。
- **Rejected/deferred findings 不改变方案**：DS F-06 仅记录为后续性能风险；DS F-07 不添加 `ListSessionsRequest`；MiMo F02 不添加 `get_session_by_label`；本 WU 不添加 pagination。

## 13. 为什么该方案没有过度设计

- 只新增 Issue 要求的一个 Host public read API；不引入 query language、owner model、pagination、archive state 或 client registry。
- 复用现有 Host `purge_session`，不增加 CLI 专属 destructive 语义。
- 复用现有 prompt/interactive Service runtime path，不创建第二套 CLI 执行栈。
- anonymous/labeled/resumed 只是 CLI 用户心智模型，底层仍是现有 Host Session/slot truth；不增加 Host 状态机状态。
- Engine 保持不变，继续维护 run-scoped Agent/Runner 边界。
- destructive purge 使用显式 `--yes`，不引入交互式确认机制。

## 14. 完成报告格式

后续 implementation agent 完成后按以下格式汇报：

1. Plan artifact path：`docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md`
2. Scope summary：简述 Host list API、CLI `session list/resume/purge`、`--new-session` 删除、文档同步。
3. Proposed slices：标记 S1-S6 完成情况；若有合并或拆分，说明原因。
4. Validation plan：列出实际运行的 pytest / pyright 命令与结果。
5. Blocking open questions or residual risks：如无阻塞，明确剩余风险，例如未跑全量测试或 list 无 pagination。
