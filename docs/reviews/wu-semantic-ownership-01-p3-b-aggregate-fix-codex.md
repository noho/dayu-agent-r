# WU-SEMANTIC-OWNERSHIP-01 P3-B aggregate fix — AgentCodex

## Gate / scope

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-B`。
- Gate：aggregate fix only。
- Timestamp：`2026-07-10T15:38:48+08:00`。
- Accepted finding 真源：`docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-deepreview-controller-adjudication.md`。
- Fix scope：只处理 `P3-B-AGG-F01`。
- Allowed production：`dayu/host/read_api.py`。
- Test scope：现有最小 P3-B public Outbox 文件 `tests/host/test_public_outbox_api.py`。
- Non-goals：不修改 control doc、既有 review artifact、CLI-CI 文件、schema、public dataclass 或其它 production 文件；不 commit、push、创建 PR 或进入 aggregate re-review。
- Decision：`P3-B-AGG-F01` 已修复；next entry point 是 controller 安排的 aggregate re-review，本 gate 未进入该步骤。

## 第一性原理与 owner boundary

动机成立，且 Low 严重性判断合理。正常 producer 已通过 `optional_payload_text` 拒绝非空白约束不满足的 canonical `finish_reason`，`HostFinalAnswerView` 也保留独立 public validation；但 raw SQLite Outbox row 可能绕过 producer。`_final_answer_from_outbox_json` 是 durable Outbox JSON 首次投影为 public typed view 的读取 owner，它原先只拒绝非文本 `finish_reason`，把空串或纯空白继续交给 public dataclass，导致损坏 durable row 抛出裸 `ValueError`，破坏既定的 `HostDurableError -> HostApiError(INTERNAL_ERROR)` public 错误链。

修复必须落在该 raw durable projection boundary，而不是下游 Service/UI、测试 fixture 或 `HostFinalAnswerView`。本次在 parser 中对非 `None` 文本显式执行非空白校验；不 trim、不替换、不填默认值，也不捕获或转换 `HostFinalAnswerView` 的独立校验。该方案只补齐与既有 `content` 相同的 field-specific durable diagnostic，不需要新增 helper、registry、wrapper 或 schema。

语义 owner 划分：

| 阶段 | Owner | 本次结论 |
|---|---|---|
| 事实产生 | Engine / Host terminal closeout 产生 canonical `finish_reason` | 不改；正常路径继续产出原值或 `None` |
| producer 校验 | Outbox `_final_answer_json` 通过 `optional_payload_text` 校验可选非空文本 | 不改；正常写入路径已有约束 |
| durable 持久化 | `host_outbox_terminal_items.final_answer_json` | 不改 schema / DDL；raw corruption 仍需 reader fail closed |
| public read 校验 | `read_api._final_answer_from_outbox_json` | 修复落点；空串与纯空白抛 field-specific `HostDurableError` |
| public typed contract | `HostFinalAnswerView.__post_init__` | 保留独立校验，不转换、不兼容 |
| public error 投影 | `HostCommandHandle._run_read` / `_host_api_error_from_durable_error` | 保持 `HostApiErrorCode.INTERNAL_ERROR`，cause 为原 `HostDurableError` |

## Changed files

- `dayu/host/read_api.py`
  - `_final_answer_from_outbox_json` 在类型检查之后拒绝 `finish_reason == ""` 与纯空白文本。
  - 抛出 `HostDurableError("Outbox final answer field finish_reason must be non-empty text")`，诊断显式包含 `Outbox`、`finish_reason` 与 `non-empty` 语义。
  - `None` 仍表示未知 finish reason；合法非空文本原样传入 `HostFinalAnswerView`。
- `tests/host/test_public_outbox_api.py`
  - 新增参数化 public 行为测试，使用 production Host 先生成真实 Outbox item，再直接更新 raw SQLite `final_answer_json`，分别注入空串与纯空白 `finish_reason`。
  - 断言 public read 抛 `HostApiError(INTERNAL_ERROR)`，其直接 cause 是 `HostDurableError`，且诊断保留字段级非空语义。
- `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-fix-codex.md`
  - 本 fix gate durable artifact。

## Propagation audit

### 正常路径

```text
canonical RUN_SUCCEEDED.finish_reason
  -> outbox._final_answer_json
  -> optional_payload_text（None 或非空文本）
  -> canonical final_answer_json
  -> durable Outbox row
  -> read_api._final_answer_from_outbox_json
  -> HostFinalAnswerView 独立 public validation
  -> public Outbox read / drain consumer
```

结果：正常值不被 trim、转换或重建；producer、durable projection parser 与 public dataclass 对 `None | non-empty str` 的语义一致。

### raw durable corruption 路径

```text
raw SQLite final_answer_json.finish_reason = "" 或纯空白
  -> read_api._final_answer_from_outbox_json
  -> HostDurableError（Outbox / finish_reason / non-empty）
  -> HostCommandHandle._run_read 保留 cause
  -> HostApiError(INTERNAL_ERROR)
```

结果：损坏 durable row 不再以 `ValueError` 越过 durable/public 错误分类，也不会生成 public view、Service/UI 输出或 LLM-facing material。Outbox row 本身不被兼容性改写，trace、memory、compact、audit 与 EventLog truth 均未发生变化。

### 独立 public validation

`HostFinalAnswerView.__post_init__` 仍调用 `_require_optional_non_empty` 校验 `finish_reason`。本次没有删除、捕获、转换或弱化该校验；直接构造 public contract 与 raw durable read 各自在自己的 owner boundary fail closed。

## Validation

### Targeted new behavior

```text
source .venv/bin/activate
pytest tests/host/test_public_outbox_api.py::test_public_outbox_read_rejects_raw_blank_finish_reason -q
```

结果：`2 passed in 0.34s`。

### Focused P3-B behavior

```text
source .venv/bin/activate
pytest tests/host/test_terminal_payload.py \
  tests/host/test_read_api_terminal_policy.py \
  tests/host/test_outbox_projection.py \
  tests/host/test_outbox_durable.py \
  tests/host/test_public_open_host_options.py \
  tests/host/test_public_outbox_api.py \
  tests/host/test_public_offline_outbox_smoke.py -q
```

结果：`77 passed in 1.00s`，即原 focused 75 项加新增 2 个 raw blank `finish_reason` case。

### Propagation regression

```text
source .venv/bin/activate
pytest tests/host/test_engine_ingest_mapping.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_projection_runner.py -q
```

结果：`305 passed in 2.10s`。

### Type / diff / scope

```text
source .venv/bin/activate
pyright
```

结果：`0 errors, 0 warnings, 0 informations`。仅有 pyright `1.1.409 -> 1.1.411` 可用的版本提示，不是类型错误。

```text
git diff --check
```

结果：pass，无 whitespace diagnostic。

Preflight 与最终 status 对照确认：本 gate 只新增 `read_api.py`、最小 public Outbox 测试文件和本 artifact 的变更；进入 gate 前已存在的 `docs/host/issues-implementation-control.md` dirty change、CLI-CI 未跟踪文件及既有 aggregate review 未跟踪文件保持原状态，本 gate 未修改它们。

## README decision

- `dayu/host/README.md`：不更新。该 README 已记录 succeeded final answer、Outbox public contract 与 durable projection fail-closed 的稳定边界；本次只是对称补齐 raw corruption 的内部字段诊断，不改变公共接口、状态机、主要执行路径或开发者稳定契约。
- `tests/README.md`：不更新。没有新增测试层级、运行方式或维护规则，只在既有 public Outbox 行为文件补充一个 corruption case。
- 根 `README.md` / `dayu/README.md`：不更新。用户工作流、安装/CLI、分层与装配均未改变。

## Finding final status

| Finding | Final status | Evidence |
|---|---|---|
| `P3-B-AGG-F01` blank Outbox `finish_reason` diagnostic boundary | **已修复** | parser 显式拒绝空串/纯空白并抛 field-specific `HostDurableError`；2 个 raw SQLite -> public read case 证明 `HostApiError(INTERNAL_ERROR)` 与 durable cause |

Blocking open question：无。aggregate fix gate completion：pass。

## Residual risks / owners

| Residual | 分类 / owner | 本次状态 |
|---|---|---|
| Outbox DDL conditional `CHECK` | assigned to later work unit：P3-J | 不在 P3-B 修改 schema；producer、durable validator 与 public read 继续 fail closed |
| descriptor automatic repair | assigned to later work unit：P3-J / storage hardening（出现直接产品需求时） | 本 gate 不新增 repair API 或兼容路径 |
| optional-material strictness | assigned to later work unit：P3-C / design adjudication | 本 gate 不改变 optional resolver policy |
| writer/reader field constants | controller 已裁决为 private projection detail | 行为测试足以保护，不新增共享 registry |

没有未分类 residual risk；没有触发新的 issue 或用户决策需求。

Artifact path：`docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-fix-codex.md`。
