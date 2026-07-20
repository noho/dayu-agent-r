# WU-SEMANTIC-OWNERSHIP-01 P3-B S1 Implementation Artifact

## Gate 与范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 P3-B`
- Gate：implementation S1
- Accepted plan：`docs/host/wu-semantic-ownership-01-p3-b-terminal-final-answer-outbox-plan.md`
- Accepted plan commit：`77c15e159b706afac315706be6751a81cc38d262`
- Decision：`complete`
- Scope：只实现 terminal-answer resolver / HostEvent / Outbox / durable-public invariant / retry-idempotency / tests / Host README；未进入 code review、其它 gate 或 P3-C。

第一性原理判断保持成立：生产 `RUN_SUCCEEDED` 是 descriptor-only，而原 Outbox 只读 inline `final_answer`，会把已提交的核心回答事实投影为 `succeeded + final_answer=None`。修复落在 final-answer source-selection owner、Outbox projection transaction 与 durable/public validation boundary，没有在 Service/UI 或纯 memory consumer 增加第二套 parser。

## Changed files

Production：

- `dayu/host/_terminal_answer.py`
- `dayu/host/read_api.py`
- `dayu/host/outbox.py`
- `dayu/host/api.py`
- `dayu/host/durable/outbox.py`

Tests：

- `tests/host/test_terminal_payload.py`
- `tests/host/test_read_api_terminal_policy.py`
- `tests/host/test_outbox_projection.py`
- `tests/host/test_outbox_durable.py`
- `tests/host/test_public_open_host_options.py`
- `tests/host/test_public_outbox_api.py`
- `tests/host/test_public_offline_outbox_smoke.py`

Docs：

- `dayu/host/README.md`
- `docs/reviews/wu-semantic-ownership-01-p3-b-s1-implementation-codex.md`

未修改 `dayu/host/terminal_payload.py`；现有 policy helper 已足够，required/optional consumer 语义由 owner module 自足说明。现有 engine ingest、memory projection、compact material 与 run-input descriptor assertions 足够，因此未修改 plan 中标注为“仅缺口时修改”的四个 propagation test 文件。未触碰并发 CLI-CI 文件或其它非 P3-B 文件。

## What changed

### Resolver required / optional policy

- `dayu.host._terminal_answer` 新增 non-nullable `required_assistant_final_answer_continuity_text(...) -> str`。
- required 与 optional public helper 共用一个模块级私有 resolution core；source precedence 只定义一次：非空 inline `final_answer` 优先，否则读取 digest-checked terminal descriptor 顶层 `content`。
- descriptor ref/digest 双缺失、单边损坏、descriptor missing、digest mismatch、SQLite row missing、JSON invalid、JSON top-level non-object、content missing / blank / non-text 均按 plan taxonomy fail closed 或在 optional contract 中有界省略。
- lenient 只影响 inline 字段；descriptor pair、descriptor/digest、SQLite/JSON integrity 与 descriptor content 类型不被 lenient 吞掉。

### HostEvent / Outbox source convergence

- `read_api._succeeded_host_event` 改用 required resolver；删除 read API 私有 terminal descriptor / SQLite parser。
- succeeded final answer `content` 来自 resolver；`filtered`、`degraded`、`finish_reason` 继续只来自 canonical `RUN_SUCCEEDED`，不随 content source 切换。
- `build_outbox_terminal_item_row` 迁移为显式 `HostTransaction` 参数；Outbox consumer 在 ProjectionRunner 提供的同一 transaction 中解析回答并写 row。
- Outbox 删除私有 inline final-answer source ownership。succeeded 调 required resolver；failed / cancelled 不调用 resolver并始终写 `final_answer_json=None`；lost 继续显式 skip。
- Outbox identity、terminal event set、pagination、drain state、EventLog 与 Run/Attempt truth 未改变。

### Durable / public invariants

- `HostFinalAnswerView.content` 拒绝空白文本。
- `OutboxTerminalItem` 要求 succeeded 必有 final answer，failed / cancelled / lost 禁止 final answer。
- durable Outbox write 与 raw read boundary 共用同一 row validator：succeeded 要求 `final_answer_json`，非成功禁止；没有修改 DDL、schema version 或 migration。

### Retry / idempotency closure

- 测试用 production closeout 形状写入 descriptor-only success，保存 descriptor 全部 durable columns，仅删除 descriptor row。
- 第一次 catch-up 证明 resolver failure 回滚 item/checkpoint，并由独立 transaction 留下 `HostDurableError` failure row。
- test-only 原样恢复同一 ref/digest/sqlite payload id/全部 columns 后重试，证明 item + checkpoint 同事务提交、failure 清除。
- 把同一 typed event 再交给 consumer 返回 `DUPLICATE`；按 terminal event id 与 item id 计数均为 1。没有新增 production repair API、callback seam、overload 或 compatibility wrapper。

## Validation

### Focused behavior tests

```text
pytest tests/host/test_terminal_payload.py \
  tests/host/test_read_api_terminal_policy.py \
  tests/host/test_outbox_projection.py \
  tests/host/test_outbox_durable.py \
  tests/host/test_public_open_host_options.py \
  tests/host/test_public_outbox_api.py \
  tests/host/test_public_offline_outbox_smoke.py -q
-> 71 passed
```

覆盖 inline / descriptor-only / precedence、完整 descriptor taxonomy、HostEvent 正负向投影、Outbox metadata、failed/cancelled/lost negative、durable/public invariant、raw row corruption、projection rollback/retry/duplicate 和 `FinalAnswerWorkerFactory` production smoke。

### Propagation regression

```text
pytest tests/host/test_engine_ingest_mapping.py \
  tests/host/test_memory_projection.py \
  tests/host/test_compact_material.py \
  tests/host/test_run_input_builder.py -q
-> 290 passed

pytest tests/host/test_projection_runner.py -q
-> 15 passed
```

### Coverage / affected Host regression

```text
pytest tests/host --ignore=tests/host/test_toolruntime_executor.py \
  --cov=dayu.host._terminal_answer \
  --cov=dayu.host.outbox \
  --cov=dayu.host.durable.outbox \
  --cov=dayu.host.read_api \
  --cov=dayu.host.api --cov-report=term -q
-> 1651 passed, 1 skipped, 5 deselected
-> _terminal_answer.py 96%
-> api.py 93%
-> durable/outbox.py 90%
-> outbox.py 96%
-> read_api.py 90%
-> total 92%
```

全量 Host + coverage 首次执行得到 `1697 passed, 1 skipped, 5 deselected, 15 failed`；15 个失败全部位于未触及的 `test_toolruntime_executor.py`，错误是 coverage 进程插桩下 `multiprocessing.connection.rebuild_connection` identity 不一致。该文件无 coverage 单独复跑 `61 passed`，因此这是 coverage + spawn 的验证环境限制，不是 S1 product regression。

### Type / source / whitespace

```text
pyright
-> 0 errors, 0 warnings, 0 informations

git diff --check
-> pass

git diff --no-index --check /dev/null \
  docs/reviews/wu-semantic-ownership-01-p3-b-s1-implementation-codex.md
-> pass（无 whitespace diagnostic；exit 1 仅表示新 artifact 有内容）

rg "assistant_final_answer_continuity_text|required_assistant_final_answer_continuity_text|_PAYLOAD_FIELD_FINAL_ANSWER|_terminal_payload_object" dayu/host
-> descriptor-aware answer source selection 只在 _terminal_answer.py
-> read_api 无私有 terminal descriptor parser
-> outbox 无私有 _PAYLOAD_FIELD_FINAL_ANSWER reader
-> durable memory / compact material / run input 继续调用 optional owner

rg "payload_resolution|durable\.transaction|_terminal_answer" dayu/host/memory.py
-> no matches；纯 memory consumer 未新增 transaction/artifact 反向依赖
```

## Propagation audit

1. `FinalAnswerData.content -> engine_ingest._final_answer_plan -> _write_terminal_payload -> descriptor/SQLite row -> terminal_closeout_in_transaction -> descriptor-only RUN_SUCCEEDED`：pass。production smoke 断言 canonical success 无 `final_answer` key，ref/digest 非空并能 join 到同 digest SQLite descriptor payload；terminal payload 顶层 `content == final:1:<run_id>`。
2. `RUN_SUCCEEDED -> required resolver -> read_api._succeeded_host_event -> live HostEvent`：pass。inline 与 descriptor-only 均得到非空 `HostFinalAnswerView`；metadata 从 canonical payload 读取；descriptor/content 损坏 fail closed。
3. `RUN_SUCCEEDED -> required resolver -> Outbox row -> public read/drain`：pass。production smoke 中 live/read/drain content 和 metadata 等值，terminal event id / dedupe key 同一，read/drain 不新增 EventLog row。
4. `RUN_SUCCEEDED -> optional resolver -> durable memory / compact material / run input`：pass。既有 descriptor-backed typed material tests 290 项回归通过；没有新增 parser，descriptor/ref/digest 未进入 LLM-facing answer text。
5. `RUN_FAILED / RUN_CANCELLED / RUN_LOST` negative：pass。HostEvent 三类均 `final_answer is None`；failed/cancelled durable row 为 NULL；lost skip；伪造 inline/content/descriptor 不被提升。
6. `resolver failure -> transaction rollback -> failure diagnostic -> same descriptor restore -> retry -> duplicate replay`：pass。failure 不改变 Run truth，item/checkpoint 原子回滚，恢复后同 identity 只保留一个 item。

## README decision

- `dayu/host/README.md`：updated。记录已实现且稳定的 succeeded final answer required contract、共同 resolver、canonical metadata、非成功禁止和 Outbox transaction/retry 语义。
- `tests/README.md`：not updated。没有新增测试层、运行入口或维护规则，现有 Host projection/public smoke 分层不变。
- 根 `README.md` / `dayu/README.md` / design docs：not updated。用户工作流、分层、装配和既有 design truth 未改变。

## Finding status

- Finding 01：fixed。descriptor-only production success 现可生成完整 Outbox final answer。
- DS-2：fixed（按 accepted current-code scope）。Outbox 与 read API 回到同一 resolver；既有 typed memory/compact/run-input 路径保持单向。
- DS-4：fixed（按 accepted corrected scope）。Outbox 不再拥有 final-answer source parsing；其 result/summary refs、identity 与 diagnostics owner 保持不变。
- Controller P3-B：fixed。required/optional policy、descriptor taxonomy、public/durable invariant、production smoke 与 retry/idempotency closure 已落地。

## Residual risks / owner

- `covered by later approved slice`：Outbox DDL 尚无 conditional CHECK；producer、write/read validator 与 public validator 已覆盖当前边界，数据库级 closed-set / DDL hardening owner 仍是 P3-J。
- `requiring new issue or explicit user decision`：descriptor 外部损坏后的自动 repair 不在 P3-B；当前只保证 failure 可诊断及同 descriptor 外部恢复后安全 retry。若需要自动 repair，应新立 storage repair work unit。
- `requiring new issue or explicit user decision`：optional material consumer 当前允许完整缺失 source 时省略 material；若未来改为 fatal，需先修改 design truth，不能在 consumer 局部收紧。
- `requiring new issue or explicit user decision`：metadata 与 descriptor payload 当前由同一 closeout plan 产生，本 slice 不新增跨副本一致性 digest；只有出现直接漂移证据时再建立独立 owner/schema work unit。

没有未分类 residual risk。plan stop condition 均未触发。

## Completion status

Implementation S1：`complete`。

Artifact path：`docs/reviews/wu-semantic-ownership-01-p3-b-s1-implementation-codex.md`。

Next entry point：`code review S1`。遵照本次用户要求，本轮停止在 implementation gate；不执行 review，不 commit/push/PR，不进入 P3-C 或其它 gate。
