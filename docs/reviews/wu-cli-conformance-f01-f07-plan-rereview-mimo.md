# WU-CLI-CONFORMANCE-F01-F07 Plan Re-review（MiMo）

## 0. Gate 元数据

- Gate：`plan re-review`（独立）
- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Reviewed plan：`docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`（fix 后版本）
- Fix artifact：`docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`
- Controller adjudication（真源）：`docs/reviews/wu-cli-conformance-f01-f07-plan-review-controller-adjudication.md`
- 前轮 reviewer 输入（仅作 finding provenance）：
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-review-ds.md`
- Review 方：MiMo（独立 re-review，不替代后续 controller 裁决）
- 编制日期：2026-08-02T18:24:02+08:00（Asia/Shanghai）
- Review 边界：只读 plan + 真源 + 代码事实；不编辑 plan、生产代码、测试、registry、PR 190

---

## 1. 冻结真源校验

| 真源 | Plan Gate 基线 SHA-256 | 实际 SHA-256 | 一致性 |
|---|---|---|---|
| `docs/cli_ci_oracles.json` | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` | ✓ |
| `docs/cli_ci_scenarios.json` | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` | ✓ |
| `observed-behavior-pr190-closeout.md` | `6aa8c8c7430e979b95f3bd8551f44ae34432e5e55172231c296d634932aa712f` | `6aa8c8c7430e979b95f3bd8551f44ae34432e5e55172231c296d634932aa712f` | ✓ |
| `compaction-invalid-response-audit-pr190.md` | `fed1a2ae29baf2b59b3d16d90460661c563ae18233f93530b241645ada38fb61` | `fed1a2ae29baf2b59b3d16d90460661c563ae18233f93530b241645ada38fb61` | ✓ |

所有冻结真源 SHA-256 与 Plan Gate 基线逐字节一致。

---

## 2. 总控 Accepted / Accepted-in-Part Finding 逐项状态

以 controller adjudication 为唯一 finding disposition 真源。每项标为：**已修复** / **部分修复** / **未修复** / **证据失效**。

### 2.1 MiMo findings（前轮 provenance）

| Finding | 裁决 | 状态 | 直接证据 |
|---|---|---|---|
| **M-F1** S1 `test_session_commands.py` 路径错误 | accepted | **已修复** | Plan §3.1 允许文件列表第 10 项已修为 `tests/cli/test_session_command.py`（单数）；§3.4 聚焦验证命令使用正确路径；`ls tests/cli/test_session_command.py` 确认文件存在。 |
| **M-F2** S4 `test_session_attachment.py` 路径错误 | accepted | **已修复** | Plan §6.1 允许文件列表第 3 项已修为 `tests/host/test_session_attachment_registry.py`；§6.4 聚焦验证命令使用正确路径；`ls tests/host/test_session_attachment_registry.py` 确认文件存在。 |
| **M-F3** v2 schema 命名映射不清 | accepted | **已修复** | Plan §9.2.1 增加了旧 active symbol/literal 到 fresh v2 symbol/literal 的完整机械映射表（8 行映射）；§9.8 聚焦验证命令包含 `rg` 扫描旧值零残留；传播闭包表覆盖 producer/persistence/reader/projection/tests/design 六环节。 |
| **M-F4** S7 原子范围缺少内部 checkpoints | accepted | **已修复** | Plan §9.8 列出四个内部 checkpoint（A—schema+source boundary、B—strict parser+accept、C—repair+operation、D—projection+multi-pass），每个有 focused tests/pyright；明确禁止 stash、新 branch、中间 commit。 |
| **M-F7** prompt_toolkit adapter seam | accepted/consolidated-into-DS-B3 | **已修复** | Plan §4.2 固定 public seam 决策：unset 调用 `Buffer.open_in_editor(validate_and_handle=False)`；显式命令使用 CLI-owned tempfile + public `run_in_terminal` + exact argv + public `Buffer.document`；不触碰 private API。 |
| **M-O1** provider blocked 后 next entry point | accepted | **已修复** | Plan §10.3 明确 `BLOCKED-ON-REAL-EVIDENCE` 状态、current/next gate 为 S8 real-evidence acquisition、恢复后新 run id；§14.2 删除了 implementation-time open question。 |
| **M-O2** Memory policy owner 位置 | accepted-as-plan-clarification | **已修复** | Plan §9.1 前置条件明确 `MemoryProjectionPolicy` 与 `estimate_memory_size_units()` 同在 `dayu/host/memory.py`；§9.4 直接复用同一 policy instance/estimator；§14.2 删除了 implementation-time 猜测。 |

### 2.2 DeepSeek findings（前轮 provenance）

| Finding | 裁决 | 状态 | 直接证据 |
|---|---|---|---|
| **DS-B1** Vt100Parser/thread bridge | accepted | **已修复** | Plan §5.2 固定 reader-thread 方案：parser 只在 reader thread 创建/调用；chunk `feed()` 与 named ESC ambiguity deadline/`flush()` 在同一线程；callback 只用 `loop.call_soon_threadsafe` 投递 typed action；完整序列不取消。代码验证：`Vt100Parser` 可导入，`run_in_terminal` 在 `prompt_toolkit.application`，`Buffer.document` 为 property。 |
| **DS-B2** registry 最终 disposition | accepted | **已修复** | Plan §13.2 固定 accepted plan commit 十条显式路径，包含两个 registry baseline 和 plan/review/fix/re-review/controller artifacts；stage 前后校验 working-tree 及 index SHA-256；此后 S1–S8 registry 必须 clean。 |
| **DS-B3** editor adapter seam 不可直接实施 | accepted | **已修复** | Plan §4.2 四分语义（missing/nonexec/OSError actionable、nonzero silent cancel、zero-only refill、unset public fallback）；显式路径使用 CLI-owned tempfile + public `run_in_terminal` + exact argv；不调用 private `_open_file_in_editor()`。代码验证：`Buffer.open_in_editor(validate_and_handle=False)` 签名确认、`run_in_terminal(func, render_cli_done, in_executor)` 签名确认。 |
| **DS-B4** closeout 现有消费者未映射 | accepted | **已修复** | Plan §5.2 增加机械映射表，逐点映射 `_PromptAcceptedRunState`、`_InteractiveAcceptedRunState`、`_cancel_prompt_turn_after_local_request`、`_start_interactive_turn`、`_request_interactive_cancel` 等到最小 shared coordinator；旧类型及兼容 wrapper 全部删除。代码验证：`session_execution.py:145,170` 两个旧 barrier 类存在，`publish_accepted` 尚未出现（待实现）。 |
| **DS-B5** S7 缺少实施缓解 | accepted-in-part | **已修复** | Plan §9.8 接受四个内部 checkpoint；明确禁止 stash、新 branch、wall-clock 预算、中间 stage/compatibility commit。 |
| **DS-B7** code-generation-ready 仍保留 open stop checks | accepted-in-part | **已修复** | Plan §14.2 editor seam 与 Memory owner 均已收口；仅 provider 可用性保留为 S8 operational stop，不再作为实现设计开放问题。 |

### 2.3 Controller 新增 findings

| Finding | 裁决 | 状态 | 直接证据 |
|---|---|---|---|
| **C1** S7 不得删除 reactive multi-pass | accepted-严重 | **已修复** | Plan §9.6 保留 `CompactPipelinePassQueuePlan` 与 `build_reactive_pass_queue_plan(...)`；每 pass 使用 immutable source boundary 和 whole-candidate repair；全部 required passes accepted 后 operation owner 重验 root coverage、duplicate、caps 及 budget，形成唯一 `CompactAcceptedTruthV2`；中间 pass 不写 canonical terminal/Memory/RunInput；失败只提交一个 `CONTEXT_COMPACTION_FAILED`。代码验证：`compact_pipeline.py:250,580` 两符号存在且被 `engine_ingest.py:108,2907` 消费。§9.8 聚焦验证命令包含 `rg` 扫描 reactive queue 存在性。 |
| **C2** F02 nonzero editor 取消语义 | accepted-严重 | **已修复** | Plan §4.2 四分语义明确：nonzero 为静默 cancel（无错误、原 draft/cursor、零 Run、REPL 继续）；missing/nonexec/OSError 为 actionable 错误；两者不再合并。§4.3 状态机图示 IDLE→EDITOR_PENDING→IDLE 三条独立路径。§4.4 测试断言 nonzero 路径 stderr 为空。 |
| **C3** S1 allowlist 未覆盖全部 construction sites | accepted-高 | **已修复** | Plan §3.2 增加 typed construction-site 映射表，覆盖 `test_entrypoint_runtime.py`、`test_entrypoint_runtime_prompt_path.py`、`test_transient_delivery_interruption_path.py`、`test_session_command.py`、`test_prompt_command.py`、`test_interactive_command.py`、`test_host_admin.py`、`test_entrypoint_runtime_interactive_path.py`。§3.4 `rg` inventory 命令覆盖 `dayu/cli dayu/service tests/cli tests/service`。代码验证：`rg` 输出确认所有 construction sites 均在上述文件中。 |
| **C4** Memory 必须消费 committed canonical event | accepted-高 | **已修复** | Plan §9.6 Memory 数据流图示固定为：Context Governance → terminal owner + commit permit → artifact + canonical CONTEXT_COMPACTED → commit → context_events strict semantic projection → Memory projector。§9.4 明确禁止 `context_governance.py` 直接传未提交对象给 `memory.py`；`memory.py` 只从 committed event projection 恢复。代码验证：`memory.py:23` 导入 `CONTEXT_COMPACTED`、`memory.py:993` 校验 `compacted_semantics`。 |
| **C5** 清理 stale plan metadata | accepted-中 | **已修复** | Plan §0 当前 Gate 状态为 `PLAN FIX COMPLETE — 待独立 Plan Re-review`；§16 明确 Plan Fix Gate 完成、下一入口为 plan re-review；旧阶段叙事已删除。 |

### 2.4 Rejected findings 保持拒绝

| Finding | 裁决 | 验证 |
|---|---|---|
| **M-F5** 需要旧 v1 durable data 兼容/迁移 | rejected-with-reason | Plan §2.2 非目标明确"不迁移旧 compact schema/旧 durable DB"；§9.2.1 删除旧 symbol、不允许 alias/兼容 re-export；旧 schema active input 由 strict parser 拒绝。**未复活。** |
| **M-F6** shared closeout 令 prompt 过度耦合 | rejected-with-reason | Plan §5.2 shared coordinator 只携带 turn identity、barrier、cancel intent；attachment/composer/pending mutation 留在 interactive owner。**未复活。** |
| **DS-B6** service README 判定未验证 | rejected-with-reason | 代码验证：`rg` 确认 `dayu/service/README.md` 不列 `EntrypointRuntimeRequest`、`ServiceHostAdminRequest`、`explicit_config_dir` 或 `config_overlay_dir`。**未复活。** |

---

## 3. Adversarial New-Finding Pass

### 3.1 Reactive bounded multi-pass 未被删除或形成中间 durable truth

**验证结论：通过。**

- `CompactPipelinePassQueuePlan` 存在于 `compact_pipeline.py:250`。
- `build_reactive_pass_queue_plan` 存在于 `compact_pipeline.py:580`，被 `engine_ingest.py:108,2907` 消费。
- Plan §9.6 明确保留 operation-level bounded reactive multi-pass；每 pass 使用 immutable source boundary；中间 pass truth 只在 operation 内存或受控 transient diagnostic artifact 中存在。
- Plan §9.8 聚焦验证命令包含 `rg -n 'CompactPipelinePassQueuePlan|build_reactive_pass_queue_plan'` 扫描，要求证明 reactive queue builder、operation consumer 与 owner tests 仍存在。
- 设计真源 `docs/host/design.md` 大量引用 reactive compaction（reactive_post_compact、reactive recovery 等），与 plan 保留 multi-pass 一致。
- **无中间 durable truth 泄漏风险**：§9.6 明确"中间 pass 不写 `CONTEXT_COMPACTED`、Memory 或 ordinary RunInput"。

### 3.2 Editor missing/nonexec/OSError/nonzero/zero/unset 四分与 public seam 可实现性

**验证结论：通过。**

四分语义已在 plan §4.2 固定：

1. **missing/nonexec/OSError**：actionable 错误、无 traceback、原 draft/cursor、零 Run、REPL 继续。
2. **nonzero**：静默 cancel、无错误、原 draft/cursor、零 Run、REPL 继续。
3. **zero**：读取编辑结果并通过 public `Buffer.document` 回填；后续显式 submit 才创建 Run。
4. **unset**：调用 public `Buffer.open_in_editor(validate_and_handle=False)`，允许 prompt_toolkit 系统 fallback。

Public seam 可实现性验证：
- `Buffer.open_in_editor(validate_and_handle=False)` — 签名确认，参数存在。
- `run_in_terminal(func, render_cli_done, in_executor)` — 位于 `prompt_toolkit.application`，签名确认。
- `Buffer.document` — property，可读写。
- 显式路径 CLI-owned tempfile + public `run_in_terminal` + exact argv 不触碰 private API。

**pyproject.toml 版本约束**：`prompt_toolkit>=3.0.0`，当前 venv 为 `3.0.52`。Plan §4.2 记录"当前锁定依赖是 prompt_toolkit==3.0.52"，但 pyproject.toml 实际约束为 `>=3.0.0`。三个 public API 在 3.x 系列稳定，editor seam 可实现性不受影响；该版本约束不一致作为 NEW-1/NF1 独立记录，待 controller 裁决。

### 3.3 Vt100Parser reader-thread/ESC deadline/typed bridge 可实现性

**验证结论：通过。**

- `Vt100Parser` 可导入（`from prompt_toolkit.input.vt100 import Vt100Parser` 成功）。
- 当前 `run_keys.py` 使用 `os.read(fd, 1)` + `running_key_action_from_bytes` + `asyncio.Queue`。
- Plan §5.2 固定 bridge 方案：reader thread 唯一创建 `Vt100Parser`；chunk read → `parser.feed(chunk)` → callback 分类 → `loop.call_soon_threadsafe(queue.put_nowait, action)`。
- ESC ambiguity：reader thread 设置 monotonic deadline，deadline 到期调用 `parser.flush()`。
- `Vt100Parser` 是同步增量状态机，无内部线程，reader thread 独占调用是线程安全的。
- 完整序列（CSI/Home/Delete/Alt/bracketed paste）由 parser 收齐后 callback 不满足 standalone ESC 条件，不投递 cancel。
- **可实现性成立**：public API 可用，线程模型兼容，typed bridge 清晰。

### 3.4 Accepted plan commit 精确纳入两个 registry 原字节

**验证结论：通过。**

Plan §13.2 固定：
- 十条显式路径包含 `docs/cli_ci_oracles.json` 和 `docs/cli_ci_scenarios.json`。
- Stage 前后四次 SHA-256 校验（working-tree × 2 + index blob × 2）。
- `git diff --cached --name-only` 必须与十路径集合完全相等。
- Commit 后 `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` 必须为空。
- 此后 S1–S8 不再携带 dirty registry。

当前实际 SHA-256 与 §0.1 基线一致（见 §1）。**Disposition 方案完整且可验证。**

### 3.5 S1/S4 路径、F06 机械传播、S7 checkpoints、committed event→Memory 链

**S1 路径**：§3.2 call path 固定为 argv → argparse（无 --config action）→ ParsedCliArgs（无 config_dir）→ CLI request → Service preparation → runtime location owner。代码验证：`arg_parsing.py` 中 `--config` 注册、`agent_entrypoint.py` 中 `resolve_explicit_config_dir`、`session.py` 中 `ServiceHostAdminRequest(config_overlay_dir=...)` 均存在且在 S1 删除范围内。✓

**S4 路径**：§6.2 两阶段确认（pending mutation → Host accepted/rejected → composer ack/preserve）。§6.3 状态机完整。Host owner test 路径 `tests/host/test_session_attachment_registry.py` 存在。✓

**F06 机械传播**：§8.2 两行机械映射（symbol + literal）；传播闭包覆盖 producer/persistence/reader/projection/tests/design。代码验证：旧 trigger `_RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED` 存在于 `run_input.py:338,6674,7979` 和 `_runner_call_manifest.py:157`；新值 `context_governance_resolved` 在代码中尚不存在（待实现）。§8.3 `rg` 扫描确保旧值零残留。✓

**S7 checkpoints**：§9.8 四个内部 checkpoint（A–D），每个有 focused tests/pyright 和明确的 implementation closure。✓

**Committed event→Memory 链**：§9.6 数据流图示固定为 terminal owner → artifact + canonical CONTEXT_COMPACTED → commit → context_events strict v2 semantic projection → Memory projector。代码验证：`memory.py:23` 导入 `CONTEXT_COMPACTED`、`memory.py:993` 校验 event type。禁止 `context_governance.py` 直接写 Memory。✓

### 3.6 无兼容/迁移/下游补偿、无越 scope

**验证结论：通过。**

- §2.2 非目标明确：不迁移旧 schema/DB、不提供 alias/re-export、不把 Host 语义下放到 CLI/Service/Engine。
- §9.2.1："旧 symbol 删除，不允许 alias、兼容 re-export、migration、fallback reader 或 dual-schema branch"。
- §8.2："不保留 alias/re-export"。
- §3.2："删除语法后不存在'部分入口接收、部分入口二次拒绝'的状态"。
- 各 slice 允许文件列表明确，不超出 scope。
- §14.3 no-overdesign rationale 逐项说明最小化理由。

### 3.7 所有"已有"路径真实存在

**验证结论：通过（附一个非阻塞观察）。**

Plan 声称"已有"的路径全部经代码验证存在：

| Plan 声称 | 实际存在 | 证据 |
|---|---|---|
| `_PromptAcceptedRunState` | ✓ | `session_execution.py:145` |
| `_InteractiveAcceptedRunState` | ✓ | `session_execution.py:170` |
| `_cancel_prompt_turn_after_local_request` | ✓ | `session_execution.py:1015` |
| `CompactPipelinePassQueuePlan` | ✓ | `compact_pipeline.py:250` |
| `build_reactive_pass_queue_plan` | ✓ | `compact_pipeline.py:580` |
| `MemoryProjectionPolicy` | ✓ | `memory.py:743` |
| `estimate_memory_size_units` | ✓ | `memory.py:1054` |
| `CONTEXT_COMPACTED` event type | ✓ | `context_events.py`（via `memory.py:23` import） |
| `_RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED` | ✓ | `run_input.py:338` |
| `EntrypointRuntimeRequest.explicit_config_dir` | ✓ | `entrypoint_runtime.py:449` |
| `ServiceHostAdminRequest.config_overlay_dir` | ✓ | `host_admin.py:31` |
| `resolve_explicit_config_dir` | ✓ | `agent_entrypoint.py:201` |
| `Buffer.open_in_editor(validate_and_handle=False)` | ✓ | prompt_toolkit 3.0.52 public API |
| `run_in_terminal` | ✓ | `prompt_toolkit.application` |
| `Buffer.document` property | ✓ | prompt_toolkit 3.0.52 |
| `Vt100Parser` | ✓ | `prompt_toolkit.input.vt100` |

**非阻塞观察**：S1 allowlist 未显式列出 `tests/service/test_host_assembly.py`，但该文件的 `config_overlay_dir` 引用全部是对 `RuntimeLocations` 对象属性的访问（`locations.config_overlay_dir`）或 `RuntimeLocations` 构造（`RuntimeLocations(config_overlay_dir=None, ...)`），不涉及 `ServiceHostAdminRequest` 或 `EntrypointRuntimeRequest` 的字段删除。因此 S1 的 `rg` verification 命令不会对该文件产生误报，allowlist 不需要扩展。**不构成 finding。**

---

## 4. New Findings

### NEW-1/NF1-未修复-低-pyproject.toml prompt_toolkit 版本约束为 >=3.0.0 而非锁定

- **位置**: Plan §4.2 "当前锁定依赖是 prompt_toolkit==3.0.52"
- **问题类型**: 契约缺失（轻微）
- **当前写法**: Plan 记录"当前锁定依赖是 prompt_toolkit==3.0.52"，但 pyproject.toml 声明 `prompt_toolkit>=3.0.0`。
- **反例/失败场景**: 若用户在不同环境安装，可能获得 3.0.0–3.0.51 的版本。Plan 使用的三个 public API（`open_in_editor`、`run_in_terminal`、`Buffer.document`）在 3.x 系列稳定，但未验证 3.0.0 下行为一致性。
- **为什么有问题**: Plan 将"3.0.52"作为实现依据，但实际约束允许更宽范围。风险低，因为 public API 稳定。
- **直接证据**: `pyproject.toml:44` 声明 `prompt_toolkit>=3.0.0`；`pip show` 确认当前 3.0.52。
- **影响**: 低。三个 public API 在 3.x 系列稳定；且 plan §14.1 已将 prompt_toolkit 行为列为 MEDIUM residual risk。
- **建议改法和验证点**: 由 controller 裁决是否需要 plan fix。若 accepted，plan 可在 §4.2 补充一句说明 pyproject.toml 约束为 `>=3.0.0`、当前 venv 为 3.0.52、三个 public API 在 3.x 系列稳定即可；若 rejected，保持现状作为 residual risk。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## 5. Residual Risks

| 风险 | 等级 | Plan 已有收敛 | Re-review 评估 |
|---|---|---|---|
| prompt_toolkit public API 行为随版本变化 | LOW | §4.2 版本记录 + §4.5 stop signal + §14.1 MEDIUM risk | 三个 public API 在 3.x 稳定；pyproject.toml 允许 >=3.0.0 但当前 venv 3.0.52 一致。**风险不升格。** |
| ESC ambiguity + SIGINT/terminal 同 batch 竞态 | MEDIUM | §5.2 Vt100Parser reader-thread + §5.3 状态机 + §5.5 PTY evidence | Vt100Parser 可导入、线程安全；typed bridge 方案清晰。**收敛充分。** |
| READ_ONLY 后 writer 退出时 fresh attach 竞争 | MEDIUM | §6.2 typed contract + §6.3 close-before-open + §6.5 real concurrent evidence | Host public typed mode 保证。**收敛充分。** |
| F07 fresh schema 影响面大 | HIGH | §9.1 原子边界 + §9.8 四个 checkpoint + §9.4 strict parser + §9.6 committed-event projection | v2 schema 名称尚不存在于代码中（待实现）；旧名称存在且需全量替换。原子边界 + checkpoint + strict scan 控制风险。**风险不升格。** |
| LLM 自然语言低质量但形式合法 | MEDIUM/ACCEPTED | §9.4 deterministic 最低信息 + coverage + §10.2 real evidence | 模型风险，不以 schema 伪装。**收敛充分。** |
| provider availability | MEDIUM/OPERATIONAL | §10.3 BLOCKED-ON-REAL-EVIDENCE + §12.2 Mimo-first/DeepSeek fallback | Operational risk，不阻塞 plan。**收敛充分。** |
| dirty registry 误 stage/覆盖 | HIGH/CONTROLLED | §13.2 四次 SHA-256 校验 + §11.1 每 slice guard | Registry SHA-256 当前一致；disposition 方案完整。**风险不升格。** |

**当前不存在未分类的 residual risk。**

---

## 6. Architecture / Overcoupling / Goal Drift / Non-goals 审查

### Architecture boundary

Plan §2.3 语义 owner 表（11 项）经代码验证与实际 owner 一致。各 slice 变更落在声明的 owner boundary 内。无跨层穿透。✓

### Overcoupling

S3 shared coordinator 只携带 turn identity + barrier + cancel intent，不携带 interactive-only 状态。S7 的 accepted truth 派生到 Memory/RunInput/artifact/trace 是单一真源多投影，不是耦合。S4 依赖 S3 的 barrier 是正常依赖顺序。✓

### Goal drift

逐 slice 验证：所有变更直接对应 frozen oracle 的 expected/forbidden predicate（F01–F07）。Plan 未将 implementation 风险升级为新目标或架构强化。✓

### Non-goals

§2.2 八项非目标逐项验证：不修改 frozen oracle/scenario、不迁移旧 schema、不下放 Host 语义、不改 Engine terminal、不重写 prompt_toolkit、不改 Fins preprocess、不用 LLM 做事实证明、不顺手清理。**全部遵守。** ✓

---

## 7. 结论

**Verdict: PASS**

Plan fix 已逐项落实总控裁决中全部 accepted/accepted-in-part findings（18/18 已修复：MiMo 7/7、DeepSeek 6/6、Controller 5/5；0 部分修复，0 未修复，0 证据失效）。Rejected findings（3 项）保持拒绝且未复活。Adversarial new-finding pass 发现一个低严重度非 blocking 新发现（NEW-1/NF1），待 controller 裁决。

关键验证点全部通过：
- Reactive bounded multi-pass 保留，无中间 durable truth 泄漏 ✓
- Editor 四分语义与 frozen evidence 一致，public seam 可实现 ✓
- Vt100Parser reader-thread bridge 可实现，线程安全 ✓
- Accepted plan commit 精确纳入两个 registry 原字节 ✓
- S1/S4 路径、F06 机械传播、S7 checkpoints、committed event→Memory 链完整 ✓
- 无兼容/迁移/下游补偿、无越 scope ✓
- 所有"已有"路径真实存在 ✓

**下一 gate 建议**：等待 controller adjudication 裁决本 re-review 结论及 NEW-1/NF1。若 controller accepted NEW-1，则需 plan fix + 独立 re-review；若 rejected，controller 确认全部 findings 已修复后方可执行 accepted plan commit（§13.2），随后进入 S1–S8 implementation gate。

---

*Review 方: MiMo | 日期: 2026-08-02T18:24:02+08:00 | 后续合法入口: controller adjudication（裁决 NEW-1/NF1 及全部 finding 状态）→ accepted plan commit 或 plan fix + re-review → S1 implementation*

---

# 第二轮 Re-review Addendum（MiMo）

## A. Gate 元数据

- Gate：`second plan re-review`（独立）
- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Reviewed plan：`docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`（第二次 fix 后版本）
- Second fix artifact：`docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`（§8 第二次 fix 记录）
- Controller adjudication（第二轮真源）：`docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md`
- Review 方：MiMo（第二轮独立 re-review）
- 编制日期：2026-08-02（Asia/Shanghai）
- Review 边界：只读 plan + fix + controller + 代码事实；不编辑 plan、生产代码、测试、registry、PR 190

---

## B. Controller R1 / R2 逐项验证

### R1 — prompt_toolkit 版本事实写错且影响 stop contract

**状态：已修复。**

直接验证：

| 验证点 | 结果 | 证据 |
|---|---|---|
| §4.2 区分环境事实与依赖声明 | ✓ | "当前开发/验证环境安装的是 `prompt_toolkit==3.0.52`，项目在 `pyproject.toml` 声明的依赖范围是 `prompt_toolkit>=3.0.0`；前者是本轮直接核验环境事实，不是版本 pin 或产品契约" |
| pyproject.toml 实际声明 | ✓ | `pyproject.toml:44` 声明 `prompt_toolkit>=3.0.0`；`.venv` 安装 3.0.52 |
| §4.2 CLI composer 作为 readback owner | ✓ | "CLI composer 作为 editor success behavior owner，按冻结规则最多移除一个末尾换行" — 产品语义归 CLI owner，不归依赖版本 |
| §4.5 stop signal 无 pin/private fallback | ✓ | "不得改用 private fallback、monkey patch、兼容层或擅自 pin 依赖；记录直接依赖证据并回到 plan gate" |
| §14.1 风险收敛无锁定版本措辞 | ✓ | "当前 resolved dependency 的 public seam contract tests、CLI-owned frozen readback规则、exact argv、无fallback真实PTY测试；seam不符即回plan" |
| 无残留 `锁定依赖`/`锁定版本`/`锁定 3.0.52` | ✓ | grep 确认 plan 中零命中；仅有的 `==3.0.52` 出现在环境事实描述且紧接"不是版本 pin"声明 |
| `_open_file_in_editor` 引用 | ✓ | 仅作为"禁止调用"的负面证据，不作为产品语义依据 |
| 未修改 pyproject.toml | ✓ | `git diff --cached --name-only` 为空，pyproject.toml 无变化 |

### R2 — accepted-plan staged set 引用了错误的 re-review artifact 名称

**状态：已修复。**

直接验证：

| 验证点 | 结果 | 证据 |
|---|---|---|
| §13.2 三条 re-review 路径正确 | ✓ | `plan-rereview-mimo.md`、`plan-rereview-ds.md`、`plan-rereview-controller-adjudication.md`（无连字符） |
| `git add --` 示例使用正确路径 | ✓ | 完整命令包含全部 10 条正确路径 |
| 无残留 `plan-re-review-*` 错误路径 | ✓ | grep `plan-re-review` 在 plan 和 fix artifact 中零命中 |
| 10 条路径全部存在 | ✓ | 逐项 `test -e` 全部 `EXISTS`，计数 = 10 |
| Registry SHA-256 不变 | ✓ | `f9972d943ac...` 与 `7f283b039dc...` 与 §0.1 基线逐字节一致 |
| fix artifact §8.3 列出完整 10 条路径 | ✓ | 逐条列出并标注"本轮没有另建或 rename 文件" |

---

## C. 原 18 项 Accepted Finding 回归扫描

确认第二次 plan fix 未导致原 18 项 finding 状态退化：

| 来源 | Finding | 首轮状态 | 第二轮状态 | 退化？ |
|---|---|---|---|---|
| MiMo | M-F1 | 已修复 | 已修复 | ✗ |
| MiMo | M-F2 | 已修复 | 已修复 | ✗ |
| MiMo | M-F3 | 已修复 | 已修复 | ✗ |
| MiMo | M-F4 | 已修复 | 已修复 | ✗ |
| MiMo | M-F7 | 已修复 | 已修复 | ✗ |
| MiMo | M-O1 | 已修复 | 已修复 | ✗ |
| MiMo | M-O2 | 已修复 | 已修复 | ✗ |
| DeepSeek | DS-B1 | 已修复 | 已修复 | ✗ |
| DeepSeek | DS-B2 | 已修复 | 已修复 | ✗ |
| DeepSeek | DS-B3 | 已修复 | 已修复 | ✗ |
| DeepSeek | DS-B4 | 已修复 | 已修复 | ✗ |
| DeepSeek | DS-B5 | 已修复 | 已修复 | ✗ |
| DeepSeek | DS-B7 | 已修复 | 已修复 | ✗ |
| Controller | C1 | 已修复 | 已修复 | ✗ |
| Controller | C2 | 已修复 | 已修复 | ✗ |
| Controller | C3 | 已修复 | 已修复 | ✗ |
| Controller | C4 | 已修复 | 已修复 | ✗ |
| Controller | C5 | 已修复 | 已修复 | ✗ |

**回归结论：18/18 已修复状态不变，0 退化。**

关键结构验证（确保 plan 核心 contract 未被 R1/R2 fix 破坏）：

| 维度 | 结果 | 证据 |
|---|---|---|
| Reactive bounded multi-pass 保留 | ✓ | §9.6 `CompactPipelinePassQueuePlan` + `build_reactive_pass_queue_plan` 完整保留；四分 root 重验不变 |
| Editor 四分语义完整 | ✓ | §4.2 四分（missing/nonexec/OSError、nonzero、zero、unset）未变 |
| Vt100Parser reader-thread model | ✓ | §5.2 thread ownership + ESC ambiguity deadline + typed bridge 不变 |
| S7 atomic closure + 4 checkpoints | ✓ | §9.1、§9.8 不变 |
| Committed event → Memory 链 | ✓ | §9.6 数据流图示不变；§9.4 禁止直连未提交对象 |
| Non-goals 8 项 | ✓ | §2.2 不变 |
| §13.2 accepted plan commit 精确路径 | ✓ | 修正为正确 10 条路径后，计数、存在性、registry hash 全部通过 |

---

## D. Gate Metadata 验证

| 验证点 | 结果 | 证据 |
|---|---|---|
| Gate 状态指向第二轮 re-review | ✓ | §0: `SECOND PLAN FIX COMPLETE — 待第二轮独立 Plan Re-review` |
| 下一合法入口仅为 re-review | ✓ | §0: "下一合法入口：仅为第二轮独立 **Plan Re-review Gate**" |
| §16 无 implementation 提前许可 | ✓ | "不得提前标记为 code-generation-ready"、"当前动作到此停止。下一合法动作仅是第二轮独立的 **Plan Re-review Gate**" |
| 禁止动作包含 implementation | ✓ | §0: "禁止动作：implementation、第二轮 plan re-review、code review、deepreview、stage、commit、push、PR 读取/写入/状态操作" |

---

## E. Adversarial New-Finding Pass

### 验证 §13.2 exact staged set = 10

10 条路径逐条验证：

1. `docs/cli_ci_oracles.json` — EXISTS
2. `docs/cli_ci_scenarios.json` — EXISTS
3. `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md` — EXISTS
4. `docs/reviews/wu-cli-conformance-f01-f07-plan-review-mimo.md` — EXISTS
5. `docs/reviews/wu-cli-conformance-f01-f07-plan-review-ds.md` — EXISTS
6. `docs/reviews/wu-cli-conformance-f01-f07-plan-review-controller-adjudication.md` — EXISTS
7. `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md` — EXISTS
8. `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-mimo.md` — EXISTS
9. `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-ds.md` — EXISTS
10. `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md` — EXISTS

**Exact set = 10，无遗漏、无多余。Registry hash 未变。**

### 无新 Finding

第二轮 fix 范围精确（R1 版本措辞、R2 路径修正），未触及 frozen oracle、design contract、slice 边界、non-goals 或 owner 决策。Adversarial pass 未发现新 material finding。

---

## F. 结论

**Verdict: PASS**

Controller R1/R2 均已修复：
- R1：§4.2/§4.5/§14.1 统一区分环境事实与依赖声明；readback owner 归 CLI composer；stop signal 禁止 pin/private fallback。
- R2：§13.2 三条 re-review 路径修正为真实 `plan-rereview-*`；`git add --` 示例完整；exact set = 10；registry hash 不变。

原 18 项 accepted/accepted-in-part finding 状态不变（18/18 已修复，0 退化）。Rejected findings（3 项）保持拒绝且未复活。Gate metadata 正确指向第二轮 re-review，无 implementation 提前许可。无新 finding。

**下一入口**：controller adjudication 确认本 re-review PASS 后，执行 accepted plan commit（§13.2 十条显式路径），随后进入 S1–S8 implementation gate。

---

*Review 方: MiMo | 日期: 2026-08-02 | 后续合法入口: controller adjudication 确认 PASS → accepted plan commit → S1 implementation*
