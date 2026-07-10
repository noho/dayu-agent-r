# WU-SEMANTIC-OWNERSHIP-01 P3-B S1 code-review fix

## Gate 与范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-B`。
- Gate：S1 code-review fix。
- Controller 真源：`docs/reviews/wu-semantic-ownership-01-p3-b-s1-code-review-controller-adjudication.md`。
- Accepted findings：`P3-B-S1-CR-F01`、`P3-B-S1-CR-F02`。
- Decision：`complete`。
- 本轮未进入 re-review，未 commit / push / 创建 PR，未重开 rejected / deferred concerns。

## 第一性原理与 owner boundary

两项 accepted finding 均成立，严重度保持 Low。

- `content` 事实由 terminal-answer owner 产生并在 Outbox projection 中 materialize；durable Outbox row 中的 `final_answer_json` 由 Outbox JSON read boundary 负责解析与字段语义校验，`HostFinalAnswerView` 继续负责 public contract 校验。损坏 raw row 不应绕过 Outbox boundary，也不应把 durable 诊断委托给 public dataclass 的 `ValueError`。
- `finish_reason` 由 canonical `RUN_SUCCEEDED` 拥有。Outbox projection 与 succeeded HostEvent read 只严格投影该字段；非文本值必须 fail closed，不转换、不兼容、不从 descriptor 或下游重建。

修复落在事实的直接解析/投影边界，没有修改 terminal-answer source selection、Outbox transaction、durable schema、public exception mapping 或任何下游 UI / Service 消费者。

## Changed files

Production：

- `dayu/host/read_api.py`：`_final_answer_from_outbox_json` 在构造 `HostFinalAnswerView` 前显式拒绝 `content == ""` 与纯空白文本，抛出包含 `Outbox` / `field` / `content` 语义的 `HostDurableError`。保留 `HostFinalAnswerView` 的独立 public 校验。

Tests：

- `tests/host/test_public_outbox_api.py`：先通过 production Host 路径 materialize Outbox item，再直接污染真实 SQLite raw row 的 `final_answer_json.content`，最后调用 public `Host.read_outbox_terminal_items`。空串与纯空白两种输入均证明 public facade 保持既有 `HostApiError(INTERNAL_ERROR)` 契约，且 cause 是带 Outbox field 诊断的 `HostDurableError`；测试没有只直接调用 private parser。
- `tests/host/test_outbox_projection.py`：在 canonical success metadata behavior matrix 增加非文本 `finish_reason=123`，断言 Outbox 不写半成品 item、记录 `HostDurableError` projection failure，诊断包含 `finish_reason`。
- `tests/host/test_read_api_terminal_policy.py`：增加 succeeded HostEvent read 行为测试，canonical 非文本 `finish_reason=123` 抛 `HostDurableError`，诊断包含 `finish_reason`。

## Validation

直接受影响测试：

```text
pytest tests/host/test_public_outbox_api.py \
  tests/host/test_outbox_projection.py \
  tests/host/test_read_api_terminal_policy.py -q
-> 32 passed
```

P3-B focused（原 71 + 新增 4 个 pytest case）：

```text
pytest tests/host/test_terminal_payload.py \
  tests/host/test_read_api_terminal_policy.py \
  tests/host/test_outbox_projection.py \
  tests/host/test_outbox_durable.py \
  tests/host/test_public_open_host_options.py \
  tests/host/test_public_outbox_api.py \
  tests/host/test_public_offline_outbox_smoke.py -q
-> 75 passed
```

传播回归：

```text
pytest tests/host/test_engine_ingest_mapping.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_projection_runner.py -q
-> 305 passed
```

类型与 whitespace：

```text
pyright
-> 0 errors, 0 warnings, 0 informations

git diff --check
-> pass
```

## Propagation audit

1. 正常成功路径：`FinalAnswerData.content -> terminal descriptor / canonical RUN_SUCCEEDED -> required terminal-answer resolver -> Outbox final_answer_json -> durable row read -> public Outbox item`。focused 与 production public smoke 通过，新检查不改变正常非空回答。
2. Outbox raw-row 损坏路径：`raw final_answer_json.content empty/blank -> durable row decode -> _final_answer_from_outbox_json -> HostDurableError -> public HostApiError cause`。两种空白输入均 fail closed，诊断同时指明 Outbox、field 与 content；不再泄漏 `HostFinalAnswerView` 的 `ValueError`。
3. Outbox canonical metadata 路径：`RUN_SUCCEEDED.finish_reason(non-text) -> Outbox projection optional text validation -> apply transaction rollback -> projection failure row`。断言 item 不存在、failure code 为 `HostDurableError`、diagnostic 含 `finish_reason`；没有转换或兼容。
4. HostEvent canonical metadata 路径：`RUN_SUCCEEDED.finish_reason(non-text) -> succeeded HostEvent read -> HostDurableError`。诊断含 `finish_reason`，content resolver 和 descriptor metadata 不会覆盖 canonical 非法值。
5. 其它消费者：`RUN_SUCCEEDED -> optional resolver -> memory / compact / run input`与 ProjectionRunner retry/idempotency 回归共 305 项通过。本轮未修改事实产生、持久化、audit/trace/memory 或 LLM-facing 投影，不存在第二套 source-of-truth。
6. 非成功路径：failed / cancelled / lost 仍不提升 forged final answer；focused 回归通过，本轮未触及该边界。

## README decision

- `dayu/host/README.md`：not updated by this fix。稳定的 succeeded final-answer / Outbox 契约已在现有 P3-B 改动中记录；本轮只改善损坏 raw row 的边界诊断，不改 public contract。
- `tests/README.md`：not updated。没有新增测试层级、运行入口或维护规则。
- 根 `README.md` / `dayu/README.md`：not updated。用户工作流、分层与装配未变。

## Finding final status

- `P3-B-S1-CR-F01`：已修复。Outbox JSON parsing boundary 显式拒绝 content 空串/纯空白，抛出带 Outbox field 语义的 `HostDurableError`；真实 raw durable row -> public read 测试已锁定。`HostFinalAnswerView` 校验保留。
- `P3-B-S1-CR-F02`：已修复。Outbox projection failure 与 succeeded HostEvent read 两条行为测试均锁定 non-text `finish_reason` fail closed 与稳定字段诊断；无转换/兼容实现。
- Rejected / deferred concerns：状态不变，本轮未重开。

## Residual risks / completion

- `assigned to later work unit`：P3-J DDL conditional CHECK 仍由原 owner 负责，本轮无 schema 变更。
- `requiring new issue or explicit user decision`：descriptor 自动 repair 和 optional-material policy tightening 仍是原非目标，本轮无新证据要求扩大范围。
- 没有未分类 residual risk，没有 blocking open question。

Completion status：S1 code-review fix `complete`。Artifact path：`docs/reviews/wu-semantic-ownership-01-p3-b-s1-fix-codex.md`。按 controller 的下一 entry point 是 parallel code re-review；遵照本次用户限制，本轮停在 fix gate，不进入 re-review。
