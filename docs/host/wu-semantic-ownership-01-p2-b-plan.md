# WU-SEMANTIC-OWNERSHIP-01 P2-B Plan

## 1. Goal / Motivation / Success Signal

Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-B Host memory/test contract hardening`.

目标：修正 Host memory 与测试契约中仍存在的三类语义所有权漂移：

- memory durable projection adapter 在 projection time 把 terminal artifact 中的 assistant final answer hydrate 回 EventLog payload view。
- Host import-boundary AST helper 只检查绝对 `from x import y`，漏掉相对 import。
- memory snapshot 测试夹具仍在多处手写 `ConversationMemorySnapshotVNext(...)` 和 `"pending"` digest sentinel，缺少同源 fixture factory 与 cross-path equivalence 测试。

第一性原理判断：P2-B 动机成立，但严重性应保持 P2，不应上升为 Conversation Memory 或 compact 架构重做。当前直接证据显示问题集中在 projection / RunInputBuilder 消费契约和测试边界硬化；除 MiMo 08 需要同步设计真源对 terminal answer continuity 的描述外，不需要 durable schema migration、Conversation Memory redesign、compaction schema redesign、retention redesign 或 tool evidence 重做。

成功信号：

- `RUN_SUCCEEDED` 的 assistant final-answer continuity 不再通过 memory projection adapter 或 RunInputBuilder adapter 修改 EventLog payload mapping 来投影；消费者改为读取同一个 typed final-answer continuity source。
- direct memory consumer、durable memory projection、ordinary RunInputBuilder 对 descriptor-backed terminal final answer 的可见语义有明确等价 / 非等价测试：纯 memory event consumer 不跟随 descriptor，durable/read-input adapter 通过同一 helper 取得 answer text，且不把 descriptor/ref/digest 作为 LLM-facing 文本。
- `tests/host/test_import_boundary.py` 的 import scanner 覆盖相对 import，并能把 `from .service import x` / `from ..fins import y` 解析到可匹配的绝对模块名或明确报出无法解析的 package-relative owner。
- memory snapshot 测试夹具集中到一个测试 helper/factory，`snapshot_digest="pending"` sentinel 不再散落在 `test_compact_material.py` / `test_run_input_builder.py` 的业务测试体中。
- 受影响 Host memory / compact material / run input / import-boundary tests、pyright、`git diff --check` 通过。

## 2. Direct Evidence And Current Finding Judgment

控制文档证据：

- `docs/host/issues-implementation-control.md:174` 记录 next entry point 为 P2-B plan in progress，并限定 scope 为 memory final-answer artifact hydration、import-boundary relative import gaps、scattered memory snapshot fixture/sentinel patterns。
- `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md:148-162` 接受 P2 Host memory/test contract hardening，并给出期望修复形态：final-answer text resolution 进入 ingest-time committed facts 或 shared typed resolver、import-boundary AST scan 覆盖 relative imports、shared memory snapshot fixture factories 与 cross-path equivalence tests。

设计真源证据：

- `docs/host/design.md:43` 固定 projection、timeline、audit、usage、tool trace、outbox、memory snapshot 不能反向成为 EventLog 真源。
- `docs/host/design.md:51-56` 固定 EngineEvent Ingest、RunInputBuilder、Conversation Memory、Projection 的 owner boundary。
- `docs/host/design.md:2778-2784` 固定 Conversation Memory 是 EventLog / payload descriptor / artifact 之上的 read model，不是事实真源。
- `docs/host/design.md:3069-3071` 固定 awaiting / wait-resolution memory 语义必须从 canonical request atom、accepted evidence envelope 与 raw outcome 派生，不能从治理事件反推 LLM-facing 业务语义。
- `docs/host/design.md:3078` 固定 snapshot 与 projection checkpoint 同事务提交；RunInputBuilder 消费 snapshot 时必须记录 cursor。
- `docs/host/design.md:3082` 固定 Trace Memory 来源包括 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED.final_answer` 与用户可见 Run 状态。
- `docs/host/design.md:3140` 固定 ordinary RunInput 只能输出业务可读内容，不暴露 EventLog id、payload ref、artifact ref、digest、cursor、policy ref 或 Host 内部治理术语。
- `docs/engine/design.md:3-7` 固定 Engine 是一次性 run 执行器，不拥有 Host durable truth；`docs/engine/design.md:483` 固定 EngineEvent stream 没有 Host durable cursor，调用方必须在 Engine 外 ingest durable facts。

### MiMo 08: accepted / design-truth-dependent

当前仍成立，但应把修复边界缩小为 terminal answer continuity projection contract，不扩大为 durable schema migration。

直接代码证据：

- `dayu/host/durable/memory.py:373-419` 的 `_memory_projection_payload_view(...)` 在 `RUN_SUCCEEDED` payload 缺少可读 `final_answer` 时调用 `assistant_final_answer_continuity_text(...)`，随后 `merged[_PAYLOAD_FIELD_FINAL_ANSWER] = final_answer`，把 descriptor-backed terminal artifact content 合并成 transient payload。
- `dayu/host/run_input.py:3199-3229` 的 `_payload_with_assistant_final_answer(...)` 使用同一模式为 RunInputBuilder 构造 transient payload。
- `tests/host/test_memory_projection.py:1063-1138` 明确覆盖 durable projection adapter hydrate terminal content 后进入 selected recent window。
- `tests/host/test_memory_projection.py:1143-1175` 同时断言 direct memory consumer 不跟随 terminal descriptor，说明当前已有双路径差异，但差异靠 adapter payload mutation 表达。
- `dayu/host/_terminal_answer.py:1-16` 的模块说明当前仍写明 durable projection / run-input adapter 可以把 descriptor-backed terminal artifact content hydrate 成 transient `final_answer`，因此 code-only 修复会和设计/模块契约冲突。

Root cause：assistant final-answer continuity 的 source-of-truth 已有 shared resolver，但 memory / RunInputBuilder adapter 通过“修改 EventLog payload view”把 resolver 输出塞回 `final_answer` 字段，导致 read model 消费者看起来像读到了原始 canonical payload。正确边界应是：Host terminal fact owner 在 ingest/terminal payload boundary 产生或引用 final answer continuity；projection/read-input 消费一个显式 typed answer text projection，不修改 EventLog payload mapping，也不让 descriptor/ref/digest 成为 LLM-facing 文本。

Design decision：implementation 前必须先更新 `docs/host/design.md` 和 `_terminal_answer.py` 的职责说明，明确 `RUN_SUCCEEDED` hot payload、terminal payload descriptor 与 assistant final-answer continuity resolver 的关系；本 P2-B 不做旧库兼容读取、不迁移 durable schema、不要求把完整 answer 文本复制进 EventLog hot payload。若实施中发现必须新增 EventLog schema 字段或改变 terminal closeout canonical payload contract，必须停止并升级为独立 design gate。

### MiMo 09: accepted

当前仍成立。

直接代码证据：

- `tests/host/test_import_boundary.py:180-197` 的 `_imported_module_names(...)` 只把 `ast.ImportFrom` 中 `node.module is not None and node.level == 0` 的绝对 import 加入结果。
- 同一 helper 被 Host、runtime、projection、memory、purge、wait callback、Engine 等 import-boundary tests 复用，例如 `tests/host/test_import_boundary.py:216-233`、`:368-390`、`:417-430`。

Root cause：import-boundary test helper 是扫描语义 owner；它当前只处理绝对 import，导致 `from .x import y` / `from ..x import y` 这种实际依赖路径不参与禁止前缀匹配。生产代码 owner 不应为测试漏扫背锅，修复应落在 AST helper，不能在每个 boundary test 中写局部特判。

### MiMo 12: accepted with narrowed evidence

当前仍成立，但 `"pending"` sentinel 的直接证据已从 `tests/host/test_memory_projection.py` 转移到 compact/run-input 相关测试，不能机械声称 memory projection 测试仍大量散落 sentinel。

直接代码证据：

- `tests/host/test_compact_material.py:2990-3045` 的 `_empty_snapshot(...)` 先构造 `ConversationMemorySnapshotVNext(..., snapshot_digest="pending")`，再用 `calculate_memory_snapshot_digest(...)` 回填 digest。
- `tests/host/test_compact_material.py:639`、`:1031`、`:3038`、`:3100`、`:3180` 仍出现 `snapshot_digest="pending"`。
- `tests/host/test_run_input_builder.py:4010`、`:4177`、`:4245` 直接手写 `ConversationMemorySnapshotVNext(...)`；`:4101`、`:4216`、`:4281` 仍出现 `snapshot_digest="pending"`。
- `tests/host/test_memory_projection.py:1737`、`:2777` 使用 `write_memory_snapshot_with_checkpoint(...)`；`:2431` 使用 public empty snapshot builder。memory projection 测试本身没有当前直接证据显示 `"pending"` sentinel 大量散落。
- 当前缺少一个 cross-path equivalence test，断言同一个 EventLog / terminal descriptor source 在 durable memory projection 与 ordinary RunInputBuilder 的 LLM-facing selected recent assistant answer 中同源一致，并且 direct memory event consumer 保持 descriptor-blind。

Root cause：memory snapshot construction 的测试真源不集中。compact material、RunInputBuilder 和 memory projection tests 分别构造 snapshot / cursor / digest，导致同一 snapshot invariant 由多个测试各自重建，也让 `"pending"` sentinel 这种中间态实现细节泄漏到业务测试体。

## 3. Owner Boundary

| 语义 | 首次产生 | 校验 | 持久化 / 真源 | 投影 / 用户或 LLM 可见 | P2-B 修复边界 |
|---|---|---|---|---|---|
| Engine final answer | Engine `final_answer` EngineEvent | Host EngineEvent Ingest 验证 non-empty final answer 与 terminal plan | Host EventLog `RUN_SUCCEEDED` / terminal payload descriptor / payload digest | Host read API、Outbox、Conversation Memory、RunInputBuilder | 不改 Engine；Host terminal answer continuity helper 是唯一 resolver；memory/run-input 不修改 payload view |
| Conversation Memory selected recent assistant item | committed EventLog / accepted compact projection | memory projection policy 与 snapshot digest/integrity | memory snapshot tables + projection checkpoint | RunInputBuilder LLM-facing messages / memory inspection | read model 只消费 typed projection material，不反向补写 EventLog payload semantics |
| Import-boundary dependency scan | test helper 读取 Python AST | `_matches_prefix(...)` 和 package-relative resolution | 测试断言，无 production durable state | pytest failure | 修复 `tests/host/test_import_boundary.py` helper；不改生产 import |
| Memory snapshot fixtures | tests fixture factory | public constructors + `calculate_memory_snapshot_digest(...)` | 测试数据，不是 production state | compact / run-input / memory tests | 新增/复用同一个 tests helper；禁止各测试重建 digest sentinel 模式 |

为什么不做过度设计：

- MiMo 08 的最小正确修复是消除 projection payload mutation，并同步设计/模块契约；不需要改 Conversation Memory 五类模型、compact candidate schema、retention、tool evidence 或 Run lifecycle。
- MiMo 09 是 test scanner owner 缺口，不需要新增通用 import linter 或跨仓库工具。
- MiMo 12 是测试 fixture owner 缺口，不需要生产 fixture API，也不需要把 tests helper 提升到 `dayu.host` public contract。

## 4. Non-goals / Scope Boundary

- 不实施本 plan；当前任务只产出 plan 与 delivery artifacts。
- 不修改生产代码、测试或 README 于本 planning gate。
- 不重设 Conversation Memory 五类语义模型。
- 不修改 compact proposal schema、compactor prompt、retention/purge、tool evidence envelope、wait-resolution schema 或 durable migration 策略。
- 不改 Engine final_answer contract。
- 不把完整 final answer 强制复制进 EventLog hot payload，除非 implementation 直接证明 shared resolver 方案不足；若发生，必须停止并重新设计 durable terminal payload contract。
- 不做旧库兼容读取；schema 相关实现按全新 schema/contract 起库处理。
- 不通过下游测试夹具特判来掩盖 production owner boundary。

Stop conditions：

- 实施发现消除 payload mutation 必须新增或迁移 durable EventLog schema 字段。
- 实施发现 `_terminal_answer.py` 与 `docs/host/design.md` 对 terminal answer continuity 的 truth 不能在不改变 Host public terminal contract 的情况下对齐。
- 相对 import 解析需要跨 package root 推断且无法从文件路径和 package root 得到确定模块名。
- shared memory snapshot fixture 需要生产代码新增仅供测试的 constructor 或绕过 snapshot digest invariant。
- cross-path equivalence test 暴露现有 RunInputBuilder 与 memory projection 对 LLM-facing final answer 的真实语义冲突，且不能归入 P2-B 最小 hardening。

## 5. Implementation Slices

本 work unit 建议 2 个 implementation slices。

拆分理由：MiMo 09 / MiMo 12 是独立 test-boundary hardening，不依赖 MiMo 08 的 terminal answer continuity design sync。MiMo 08 有低概率触发 Host terminal payload design gate；若放在同一个不可分割 slice 中，会不必要地阻塞 import-boundary 和 fixture hardening。两片仍然保持低 gate 成本，并按依赖关系让 S1 的 snapshot fixture 供 S2 的 cross-path equivalence test 复用。

### S1. Import Boundary And Memory Snapshot Test Fixture Hardening

Objective：先关闭 MiMo 09 和 MiMo 12 的独立 test-boundary 缺口，不触碰 production memory semantics。

Allowed files/modules：

- `tests/host/test_import_boundary.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_memory_projection.py`，仅用于把新增/既有 memory projection 测试接入 shared snapshot factory 或 source scan。
- `tests/host/memory_snapshot_factories.py` 或 `tests/host/_memory_snapshot_factories.py`
- `tests/README.md`，仅在 README 约束判定测试职责说明需要更新时修改。

Exact allowed changes：

- 在 `tests/host/test_import_boundary.py` 修改 `_imported_module_names(...)` 或新增同源 helper，使 `ast.ImportFrom` 的 `node.level > 0` 能解析为绝对模块名。
- 相对 import 解析算法必须是确定性的：
  1. 调用方向 helper 传入被扫描文件路径和 package root。
  2. 从文件路径相对 package root 计算当前模块 package path；文件本身的 stem 不是 package prefix，当前 package 是其 parent package。
  3. `node.level == 1` 表示当前 package；`node.level == 2` 表示当前 package 的 parent，依此类推。
  4. 回溯后的 package prefix 与 `node.module` 拼接为绝对模块名；`node.module is None` 时只返回回溯后的 package prefix。
  5. 若文件不在 package root 下、回溯超出 package root、或无法得到确定 package prefix，helper 必须返回明确解析错误并使对应测试失败；不得静默跳过。
- 测试必须覆盖 absolute import、同包相对 import、父包相对 import、`node.module is None` 的相对 import，以及无法解析的 synthetic case。
- 新增 tests-only memory snapshot factory。factory 必须使用 public memory dataclasses / builders 和 `calculate_memory_snapshot_digest(...)`，统一生成 empty/rich snapshot、cursor、policy_digest。
- factory 内部可以使用一个私有 sentinel 常量或空 digest 占位来完成 digest 计算，但业务测试体不得直接写 `snapshot_digest="pending"`。
- 迁移 `test_compact_material.py` 与 `test_run_input_builder.py` 中手写 `ConversationMemorySnapshotVNext(...)` 和 `snapshot_digest="pending"` 的业务测试到 shared factory。
- `tests/host/test_memory_projection.py` 中新增或迁移的测试也必须使用 shared factory 或 public builder，不得新增 `"pending"` sentinel。
- 保留专门 digest invariant test 时，必须集中在 factory 测试或明确命名的 digest invariant test 中，并解释为什么不能使用 shared factory。

Tests / assertions：

- import-boundary helper unit 覆盖 absolute / relative same-package / relative parent-package / relative no-module / unresolvable cases。
- source scan 断言 `tests/host/test_compact_material.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_memory_projection.py` 的业务测试体不再出现 `snapshot_digest="pending"`。
- source scan 断言 `ConversationMemorySnapshotVNext(` 在 `test_compact_material.py` 与 `test_run_input_builder.py` 中只出现在 shared factory、factory test、或明确 digest invariant test 允许位置。

Validation：

```bash
source .venv/bin/activate && pytest tests/host/test_import_boundary.py
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_memory_projection.py
source .venv/bin/activate && pyright
git diff --check
```

Rollback / verification point：

- `rg -n "snapshot_digest=\"pending\"" tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py` 不应显示业务测试体散落 sentinel。
- `rg -n "node\\.level == 0" tests/host/test_import_boundary.py` 不应再是 relative import 漏扫条件。

### S2. Terminal Answer Continuity Projection Contract

Objective：关闭 MiMo 08，消除 memory projection / RunInputBuilder 通过 payload mutation 暗示 canonical `RUN_SUCCEEDED.final_answer` 的问题，并补齐真实 artifact cross-path equivalence。

Allowed files/modules：

- `docs/host/design.md`
- `dayu/host/_terminal_answer.py`
- `dayu/host/terminal_payload.py`，仅在 terminal answer continuity resolver contract 需要同步 helper 返回类型或 typed material 时修改。
- `dayu/host/durable/memory.py`
- `dayu/host/run_input.py`
- `dayu/host/memory.py`，仅当需要扩展 `MemoryProjectionEvent` 或 projection helper typed 字段。
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_compact_material.py`，仅当需要复用 S1 fixture 或更新 cross-path source scan。
- `tests/README.md`，仅在 README 约束判定测试职责说明需要更新时修改。

Exact allowed changes：

- 先更新 `docs/host/design.md` 中 Conversation Memory / RunInputBuilder terminal answer continuity 描述，明确：
  - EventLog / payload descriptor / artifact 是 terminal fact 真源。
  - terminal answer continuity resolver 可以从 committed terminal fact refs 读取 assistant final-answer text。
  - projection / RunInputBuilder 不得通过修改 EventLog payload mapping 来让下游误以为 `final_answer` 来自 hot payload。
  - LLM-facing projection 只能输出 answer text，不输出 `terminal_summary_ref`、`terminal_summary_digest`、payload ref、artifact ref、event id 或 digest。
- 更新 `dayu/host/_terminal_answer.py` 模块说明，替换旧契约文本：resolver 输出是 typed continuity material 或 answer text material；consumer 不通过 payload mutation 消费。
- 在 production code 中移除 `_memory_projection_payload_view(...)` 和 `_payload_with_assistant_final_answer(...)` 对 `RUN_SUCCEEDED` payload 的 mutation。
- 若选择显式 typed field，该 field 的落点优先是 projection-internal view，例如 `_MemoryProjectionPayloadView` 或 RunInputBuilder internal event view；这不是 EventLog durable schema migration。
- 只有在确有必要时，才可扩展 `MemoryProjectionEvent` 这类 Host public read-model input type；这必须同步 `docs/host/design.md`。
- 禁止把 field 加到 `ConversationMemorySnapshotVNext`、`SelectedRecentWindowItem` 或其它 durable snapshot schema，只为消除 payload mutation。
- `_memory_projection_payload_view(...)` / `_payload_with_assistant_final_answer(...)` 中 `TOOL_RESULT_ACCEPTED` 的 accepted evidence projection 分支必须保持当前 owner boundary，不得借 MiMo 08 重写 tool evidence。
- 保持 direct `build_conversation_memory_snapshot_from_events(...)` consumer descriptor-blind：没有 inline final_answer 或显式 typed answer material 时，不跟随 descriptor。
- `tests/host/test_memory_projection.py` 保留 direct consumer descriptor-blind 测试；把 durable projection descriptor-backed final answer 测试改为断言 typed answer material，不再断言 adapter hydrate payload。
- 增加 cross-path equivalence test，至少包含一个真实 durable store case：
  - 写入 `RUN_SUCCEEDED` event，inline `final_answer` 为空；
  - `terminal_summary_ref` / `terminal_summary_digest` 指向真实 terminal artifact payload；
  - durable memory projection 和 ordinary RunInputBuilder 分别消费同一个 committed terminal source；
  - 两条路径产出的 LLM-facing assistant answer text 字符串必须完全相同；
  - 产出文本不得包含 `terminal_summary_ref`、`terminal_summary_digest`、payload ref、artifact ref、event id、digest、cursor 或 Host governance label。

Tests / assertions：

- memory projection 测试断言 descriptor-backed final answer 的 LLM-facing text 来自 resolver typed material，不来自 payload mutation。
- direct consumer 测试断言没有 typed answer material 时 descriptor-only `RUN_SUCCEEDED` 不进入 selected recent assistant window。
- RunInputBuilder / memory projection cross-path equivalence 测试断言真实 terminal artifact descriptor case 的 answer text 完全一致，refs/digests 不泄漏。
- source scan 覆盖 `tests/host/test_memory_projection.py`，防止新增 equivalence test 重新引入 `"pending"` sentinel。

Validation:

```bash
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compact_material.py
source .venv/bin/activate && pyright
git diff --check
```

Broader optional validation for implementation reviewer:

```bash
source .venv/bin/activate && pytest tests/host
```

Rollback / verification point：

- `rg -n "merged\\[_PAYLOAD_FIELD_FINAL_ANSWER\\]|transient ``final_answer``" dayu/host docs/host/design.md` 不应显示 production payload mutation 或旧契约文本。
- `rg -n "terminal_summary_ref|terminal_summary_digest|payload_ref|payload_digest|artifact_ref|event_id|cursor" tests/host/test_memory_projection.py tests/host/test_run_input_builder.py` 的命中必须来自测试输入 / negative assertion，不得来自 expected LLM-facing output。

## 6. Propagation Audit Expectations

Implementation completion report 必须列出并确认以下路径语义一致：

1. Engine 产出 `final_answer` EngineEvent。
2. Host EngineEvent Ingest 写入 terminal payload descriptor 与 `RUN_SUCCEEDED` canonical terminal fact。
3. Terminal answer continuity resolver 从 committed terminal fact refs 读取 answer text，并校验 descriptor/digest。
4. Durable memory projection 消费 resolver typed material，生成 selected recent assistant item；不修改 EventLog payload view。
5. Ordinary RunInputBuilder 消费同源 resolver typed material或同源 memory snapshot，构造 LLM-facing assistant continuity；不输出 refs/digests/internal governance text。
6. Direct memory event consumer 在没有 typed material 时保持 descriptor-blind，不从 descriptor 反推 final answer。
7. Tests 中 compact material、RunInputBuilder、memory projection 使用同一个 snapshot fixture factory 或同一个 public builder/digest invariant。
8. Import-boundary tests 对 absolute 和 relative imports 使用同一个 source-of-truth scanner。

## 7. README Trigger Judgment

当前 planning gate 只新增 plan 和 review artifact，不需要 README 更新。

后续 implementation 的 README 判断：

- 修改 `dayu/host/` 生产代码时，必须先读取 `dayu/host/README.md` 的 Agent 更新约束，并判断 terminal answer continuity、Conversation Memory、RunInputBuilder 或 import boundary 是否属于该 README 读者职责。
- 修改 `tests/host/` 或新增 tests helper 时，必须先读取 `tests/README.md` 的 Agent 更新约束，并判断是否需要记录 shared memory snapshot fixture / import-boundary test responsibility。
- 修改 `docs/host/design.md` 是 design truth sync，不自动触发根 README；只有用户可见 CLI/Web/WeChat 工作流、安装、命令参数、默认输出、日志定位或 workspace 文件位置变化时才检查根 `README.md`。
- 若 implementation 发现需要改变 `UI -> Service -> Host -> Engine` 分层关系或 Host/Engine public contract，必须停止并先同步 `dayu/README.md` / `docs/engine/design.md`，不能在 P2-B 内顺手修改。

## 8. Completion Report Format

Implementation agent 最终报告必须包含：

- 改了哪些文件，按 design truth、production code、tests、README decision 分组。
- 三个 finding 的最终状态：accepted fixed / rejected with reason / deferred with owner。
- Propagation audit 结果。
- 实际运行的验证命令及结果。
- 未覆盖风险和 owner；不得留下 unclassified residual risk。
