# WU-CLI-CONFORMANCE-F01-F07 Plan Re-review（DeepSeek）

## 0. Gate 元数据

- **Gate**: Plan Re-review（独立，不实施、不修改生产代码/测试/README/design/registry）
- **Work unit**: `WU-CLI-CONFORMANCE-F01-F07`
- **Reviewed plan**: `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`（fix 后版本）
- **Fix artifact**: `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`
- **裁决真源**: `docs/reviews/wu-cli-conformance-f01-f07-plan-review-controller-adjudication.md`
- **两路 review inputs**: `docs/reviews/wu-cli-conformance-f01-f07-plan-review-mimo.md`, `docs/reviews/wu-cli-conformance-f01-f07-plan-review-ds.md`
- **冻结真源**: `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/cli_ci.md`, `docs/host/design.md`, `docs/engine/design.md`, 两份 immutable evidence report
- **PR**: `190`
- **分支**: `codex/interactive-oracle`
- **编制日期**: 2026-08-02T18:25:38+08:00（Asia/Shanghai）

## 1. Re-review 范围与方法

本 re-review 只做两件事：

1. **逐 finding 验证修复**: 对总控裁决中全部 `accepted` / `accepted-in-part` finding，逐一在 fix 后的 plan 中寻找直接证据，标为 `已修复` / `部分修复` / `未修复` / `证据失效`。不得以两路 reviewer 一致代替证据，不得复活被总控 `rejected` 的 finding。
2. **Adversarial new-finding pass**: 按用户指定的检查项做增量发现，特别核对 reactive multi-pass、editor 四分语义与依赖范围、Vt100Parser 实现、registry 纳入、S1/S4 路径、F06 机械传播、S7 checkpoints、committed event→Memory 链、兼容/迁移/越 scope、以及所有"已有"路径真实性。

审查依据：fix 后的 plan（`plan-codex.md`）、plan-fix 记录（`plan-fix-codex.md`）、总控裁决、frozen oracle/scenario/design/evidence、以及直接代码事实。

## 2. Registry 与证据基线校验

| 校验项 | 值 | 结果 |
|---|---|---|
| `docs/cli_ci_oracles.json` SHA-256 | `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` | **PASS** — 与 plan §0.1 一致 |
| `docs/cli_ci_scenarios.json` SHA-256 | `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` | **PASS** — 与 plan §0.1 一致 |
| `python -m json.tool docs/cli_ci_oracles.json` | exit 0 | **PASS** |
| `python -m json.tool docs/cli_ci_scenarios.json` | exit 0 | **PASS** |
| Evidence `observed-behavior-pr190-closeout.md` | `/Users/leo/workspace/.dayu-cli-ci/pr190-closure-20260802TQgGLA1/evidence/interactive/observed-behavior-pr190-closeout.md` | **PASS** — 存在 |
| Evidence `compaction-invalid-response-audit-pr190.md` | `/Users/leo/workspace/.dayu-cli-ci/pr190-closure-20260802TQgGLA1/evidence/interactive/compaction-invalid-response-audit-pr190.md` | **PASS** — 存在 |

## 3. 环境与依赖事实

| 事实 | 值 | 对 plan 的影响 |
|---|---|---|
| prompt_toolkit installed | `3.0.52` | plan §4.2 以此为验证基线 |
| prompt_toolkit constraint | `>=3.0.0`（pyproject.toml:44） | 不是 `==3.0.52`；public seam 方案不依赖版本锁定 |
| `run_in_terminal` 可用性 | `prompt_toolkit.application.run_in_terminal(func, render_cli_done, in_executor)` — 可导入 | plan §4.2 的显式 editor launcher 依赖此 API；签名匹配 |
| `Buffer.open_in_editor(validate_and_handle)` | 可调用 | plan §4.2 unset 路径依赖此 API |
| `Buffer.document` (getter/setter) | 可读写 | plan §4.2 的 pre-freeze / post-refill 依赖此 API |
| `Vt100Parser` 可用性 | `prompt_toolkit.input.vt100.Vt100Parser(feed_key_callback)` — 可导入 | plan §5.2 prompt one-shot parser 依赖此 API |
| `Vt100Parser.feed(data: str) -> None` | 同步方法 | ✓ plan 的 reader-thread feed 方案匹配 |
| `Vt100Parser.flush() -> None` | 同步方法 | ✓ plan 的 ESC ambiguity deadline+flush 方案匹配 |
| `Vt100Parser` 线程安全 | 文档未声明 | plan 将 parser 生命周期限制在单一 reader thread 内 → 无跨线程调用 |
| `MemoryProjectionPolicy` owner | `dayu/host/memory.py:743` | ✓ 在 S7 allowlist 内 |
| `estimate_memory_size_units()` owner | `dayu/host/memory.py:1054` | ✓ 在 S7 allowlist 内 |
| `CompactPipelinePassQueuePlan` | `dayu/host/compact_pipeline.py:250` — 存在 | ✓ plan §9.6 保留此类型 |
| `build_reactive_pass_queue_plan` | `dayu/host/compact_pipeline.py:580` — 存在 | ✓ plan §9.6 保留此函数 |
| `design.md` reactive multi-pass | `docs/host/design.md:3835-3843` — 存在 | ✓ 与 controller C1 要求一致 |
| `_READ_SIZE_BYTES` | `dayu/cli/run_keys.py:24` = `1` | plan §5.2 切换到 chunk read + Vt100Parser |

## 4. 逐 Finding 修复状态

### 4.1 MiMo findings

| Finding | 裁决 | 状态 | 直接证据 |
|---|---|---|---|
| **M-F1** S1 `test_session_commands.py` 路径错误 | accepted | **已修复** | plan §3.1 allowlist 写为 `tests/cli/test_session_command.py`（单数）；`ls` 确认该文件存在；聚焦验证命令 `pytest tests/cli/test_session_command.py` 使用正确路径；construction-site 表也使用正确文件名 |
| **M-F2** S4 `test_session_attachment.py` 路径错误 | accepted | **已修复** | plan §6.1 allowlist 写为 `tests/host/test_session_attachment_registry.py`；`ls` 确认该文件存在；plan 明确"只增加 Host 已有 typed READ_ONLY owner contract 断言，不改 Host 生产代码"；聚焦验证命令使用正确文件名 |
| **M-F3** S7 v2 schema 命名映射不清 | accepted | **已修复** | plan §9.2.1 增加完整的旧 active symbol/literal → fresh v2 symbol/literal 机械映射表（10 行），以及 producer/persistence/reader/projection/tests/design 传播闭包表（8 行）；§9.8 聚焦验证的 `rg` 扫描确保旧值零残留；`§8.2`（F06）也给出同等二行机械映射 |
| **M-F4** S7 原子范围缺少内部 checkpoints | accepted | **已修复** | plan §9.8 列出 A-D 四个内部 checkpoint（schema/source-boundary → strict parser/accept → repair → projection+multi-pass），每个 checkpoint 有明确的 implementation closure、focused tests 和 pyright 范围；同时明确禁止 stash、新 branch、中间 stage/commit 或 compatibility 状态 |
| **M-F7** prompt_toolkit seam 风险 | accepted/consolidated-into-DS-B3 | **已修复** | 见 DS-B3 行 |
| **M-O1** provider blocked 后 next entry point 缺失 | accepted | **已修复** | plan §10.3 明确：provider blocked 时"状态固定为 BLOCKED-ON-REAL-EVIDENCE，不得 closeout pass；保留该次失败 bundle，current/next gate 都仍为 S8 real-evidence acquisition。provider 恢复后必须使用新 run id 重新执行" |
| **M-O2** Memory policy owner 位置待确认 | accepted-as-plan-clarification | **已修复** | plan §9.2 声明 "MemoryProjectionPolicy 与 estimate_memory_size_units() 的 owner 已由直接代码确认同在 dayu/host/memory.py"；§9.4 明确 "policy caps 直接接收 dayu/host/memory.py 已有 MemoryProjectionPolicy typed instance"；§14.2 删除了 implementation-time 猜测 |

### 4.2 DeepSeek findings

| Finding | 裁决 | 状态 | 直接证据 |
|---|---|---|---|
| **DS-B1** Vt100Parser/thread bridge 未指定 | accepted | **已修复** | plan §5.2 固定如下方案：(1) `_read_loop()` 在 reader thread 内创建唯一 Vt100Parser(callback)；(2) 同线程 chunk read → decode → feed；(3) ESC 后设置命名常量 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` monotonic deadline，后续 chunk 刷新 deadline；(4) `select` 无新字节且 deadline 到期时，同一 reader thread 调 `parser.flush()` 并清空 deadline；(5) parser callback 也在 reader thread，只分类 KeyPress → `RunningKeyAction`，并通过 `loop.call_soon_threadsafe(queue.put_nowait, action)` 投递；(6) 只有 `key is Keys.Escape` 且 `data == "\x1b"` 才投递 `CANCEL_RUN`；CSI/Home/Delete/SS3/Alt/bracketed paste 的完整序列不满足 standalone ESC 条件。已验证 `Vt100Parser.feed(data: str)` 和 `Vt100Parser.flush()` 为同步方法，与 reader-thread 方案兼容 |
| **DS-B2** registry 最终 disposition 缺失 | accepted | **已修复** | plan §13.2 定义 accepted plan commit 的十条显式路径（含两个 registry baseline 和完整 review loop）；stage 前后四次校验 working-tree + index SHA-256；commit 后 `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` 必须为空；此后 S1–S8 不再携带 dirty registry |
| **DS-B3** editor adapter seam 不可直接实施 | accepted | **已修复** | plan §4.2 固定决策：(a) missing/non-executable/OSError → actionable 错误、原 draft/cursor、零 Run、REPL 继续；(b) nonzero → 静默 cancel、原 draft/cursor、零 Run、REPL 继续；(c) zero → UTF-8 读取 → 通过 public `Buffer.document = Document(...)` 回填；(d) unset → 调用 public `Buffer.open_in_editor(validate_and_handle=False)`，允许 system fallback。显式路径使用 CLI-owned 安全 tempfile + public `run_in_terminal(..., in_executor=True)` + exact argv；不触碰 prompt_toolkit 私有 API，不 fallback。已验证 `run_in_terminal`（`prompt_toolkit.application.run_in_terminal`）可导入，签名 `(func, render_cli_done, in_executor)` 与 plan 兼容 |
| **DS-B4** closeout 现有消费者未映射 | accepted | **已修复** | plan §5.2 增加 7 个当前 site 到新最小 shared coordinator 的精确映射表：`_PromptAcceptedRunState.record`/`submit_entrypoint_turn_and_wait` → `publish_accepted`；`_cancel_prompt_turn_after_local_request` → `request_cancel(False)` + 跨 barrier 继续；`_InteractiveAcceptedRunState.record/wait_run_id` → `_AcceptedRunBarrier.publish_accepted/wait_run_id`；`_start_interactive_turn`/`_start_interactive_queued_followup`/`_promote_interactive_queued_followup` → 创建/携带同一 `_ActiveTurnCloseout`；`_InteractiveActiveTurn.cancel_reason/acceptance_task/cancel_task` → 收敛到 `_ActiveTurnCloseout`；`_request_interactive_cancel`/`_start_interactive_cancel_task` → 委托 `request_cancel`/`wait_accepted_then_cancel`；`_wait_interactive_batch_terminal_handling_sigint` → first/second Ctrl+C 分别委托；`_drive_interactive_tty_repl` → 同 batch typed intents 消费 + `observe_terminal`。已验证现有代码 `_PromptAcceptedRunState`（line 145）、`_InteractiveAcceptedRunState`（line 170）及其创建/消费点（lines 916, 1019, 1657, 1707, 1736）均被映射 |
| **DS-B5** S7 缺少实施缓解 | accepted-in-part | **已修复** | plan 接受四个内部 checkpoint（A-D）；明确拒绝 stash、新 branch、wall-clock 预算和中间 commit（与 controller 裁决"因为不是 correctness contract 且增加 dirty-baseline 风险"一致） |
| **DS-B7** code-generation-ready 仍保留 open stop checks | accepted-in-part | **已修复** | editor seam 已固定为 public-seam 方案（见 DS-B3）；Memory policy owner 已确认在 `dayu/host/memory.py`（见 M-O2）；仅 provider 可用性保留为 S8 operational stop（§10.3），不再作为实现设计开放问题 |

### 4.3 Controller 新增 findings

| Finding | 裁决 | 状态 | 直接证据 |
|---|---|---|---|
| **C1** S7 不得删除 reactive multi-pass | accepted-严重 | **已修复** | plan §9.6 明确保留 `CompactPipelinePassQueuePlan`、`build_reactive_pass_queue_plan(...)` 与 operation-level bounded multi-pass；每 pass 使用 immutable source boundary + whole-candidate repair；全部 required passes accepted 后，operation owner 按 frozen queue order 机械合并，再对 root `CompactInputV2` 重新执行 coverage partition/duplicate/caps/budget 四类重验，形成唯一 `CompactAcceptedTruthV2`；中间 pass truth 只在 operation 内存或受控 transient diagnostic artifact 中存在，不写 canonical terminal、Memory 或 ordinary RunInput；任一 pass exhaust 或 aggregate 无法在剩余 budget 内收口时，只写一个 canonical `CONTEXT_COMPACTION_FAILED`。§9.8 的 reactive multi-pass 测试覆盖 single-pass 与 multi-pass 的 cross-pass duplicate、aggregate cap、root budget 失败完整重产、以及 exhaust 后单 terminal。§11.2 contract scan 的第二个 `rg` 确认为保留而非残留："CompactPipelinePassQueuePlan、build_reactive_pass_queue_plan 与 operation-level bounded multi-pass 必须仍存在，并有 aggregate-root revalidation tests"。代码验证 `compact_pipeline.py:250`（class 定义）和 `compact_pipeline.py:580`（函数定义）当前存在 |
| **C2** F02 必须保持 nonzero editor 的冻结取消语义 | accepted-严重 | **已修复** | plan §4.2 的四分语义：(1) missing/non-executable/OSError → actionable 错误、无 traceback；(2) nonzero → 静默 cancel；(3) zero → 回填；(4) unset → public fallback。nonzero 不再与"配置不存在/不可执行/无法启动"合并。§4.3 状态机明确 EDITOR_PENDING + explicit return nonzero → IDLE（silent cancel，original draft/cursor）。§4.4 owner tests 覆盖"显式 /usr/bin/false（以及测试 launcher 返回任意非零）：exact argv 只启动一次；stderr 为空；draft/cursor/history 不变；零 Run；REPL 继续" |
| **C3** S1 allowlist 未覆盖 deleted request field 的全部 construction sites | accepted-高 | **已修复** | plan §3.2 增加 construction-site allowlist 表，逐项列出 `EntrypointRuntimeRequest(...)` 和 `ServiceHostAdminRequest(...)` 的全部 CLI/Service 生产与测试构造点（6 行 + 2 行），以及对应动作。实施前后运行的 `rg` inventory 命令覆盖 `dayu/cli dayu/service tests/cli tests/service`。已验证当前 `rg` 输出命中 plan 表的全部文件；`tests/service/test_host_assembly.py:3252` 的 `config_overlay_dir=None` 是构造 `RuntimeLocations`（运行时 location 结果类型），不是 `EntrypointRuntimeRequest` 或 `ServiceHostAdminRequest`，不在删除范围 |
| **C4** Memory 必须消费 committed canonical compact fact | accepted-高 | **已修复** | plan §9.6 明确数据流：Context Governance 产生 `CompactAcceptedTruthV2` → terminal owner + commit permit → compact artifact + canonical `CONTEXT_COMPACTED` strict v2 semantic payload → commit 成功 → `context_events.py` strict semantic projection → Memory projector 按 event sequence 更新 snapshot。明确禁止 `context_governance.py`、operation result 或 terminal helper 把未提交 `CompactAcceptedTruthV2` 直接传给 `memory.py`。失败 fallback 精确 outcome 由 `CONTEXT_COMPACTION_FAILED`、typed fallback input refs 和 fallback manifest 拥有；Memory 不得消费 rejected candidate |
| **C5** 清理 stale plan metadata | accepted-中 | **已修复** | plan §0 头："下一合法入口：仅为独立 **Plan Re-review Gate**；本次 fix 完成后必须停止"；§16："Plan Fix Gate 标记为 COMPLETE、non-blocked、**待独立 plan re-review**；尚未获得 code-generation 许可。当前动作到此停止。下一合法动作仅是独立的 **Plan Re-review Gate**"。旧 Phase B 叙事已全部移除 |

## 5. Adversarial New-Finding Pass

### 5.1 Reactive bounded multi-pass —— 未删除、无中间 durable truth

**结论：原 18 项已修复；此项无新增 finding。**

Plan §9.6 完整保留了 `CompactPipelinePassQueuePlan`、`build_reactive_pass_queue_plan` 及 operation-level bounded reactive multi-pass。关键不变量全部明确：

- 每 pass 对 immutable source boundary 做 whole-candidate repair；rejected pass candidate 不 materialize
- 全部 required passes accepted 后 operation owner 机械合并，并做 root coverage/duplicate/caps/budget 四类重验
- 中间 pass truth 只在 operation 内存或受控 transient diagnostic artifact 中存在
- 中间 pass 不写 `CONTEXT_COMPACTED`、Memory 或 ordinary RunInput
- 只有一个 canonical `CONTEXT_COMPACTED`（成功）或 `CONTEXT_COMPACTION_FAILED`（无法收口）

代码验证：`compact_pipeline.py:250` (class)、`compact_pipeline.py:580` (function) 和 `engine_ingest.py:108,2907` (consumer) 在 active code 中存在。`docs/host/design.md:3835-3843` 明确定义此要求。plan fix 已将删除 multi-pass 的反向表述完全替换。

### 5.2 Editor 四分语义与 public seam —— 可在声明的依赖范围实现

**结论：编辑器的 missing/non-executable/OSError/nonzero/zero/unset 四分语义与 public seam 在 pyproject.toml 声明的 `>=3.0.0` 公共接口边界可实现；此项产生 1 个新增 finding（NEW-1，低，未修复，非 blocking，等待 controller 裁决）。**

plan §4.2 的四分语义（missing/non-executable/OSError → actionable；nonzero → silent cancel；zero → refill；unset → public fallback）使用的 public seams 已验证：

- `run_in_terminal`：`prompt_toolkit.application.run_in_terminal(func, render_cli_done, in_executor)` — 可导入，in_executor=True 时在 thread pool executor 中执行
- `Buffer.open_in_editor(validate_and_handle=False)`：可调用，保留 prompt_toolkit 的标准 system fallback
- `Buffer.document`：可读写(getter/setter)，用于 pre-freeze 和 post-refill

这些 API 在 prompt_toolkit 3.0.x 全线存在，pyproject.toml 声明的约束 `>=3.0.0` 满足；不依赖当前 venv 的 3.0.52 特定版本。实施与验证应按 pyproject.toml 声明的 `>=3.0.0` 公共接口边界进行，不把偶然环境版本当锁。

**NEW-1（低，未修复）**: plan §4.2 开头写"当前锁定依赖是 prompt_toolkit==3.0.52"，但 pyproject.toml:44 实际约束为 `prompt_toolkit>=3.0.0`。plan 实际采用的 public-seam 方案不依赖版本锁定，但"锁定依赖"措辞与项目声明的依赖边界矛盾，可能误导 implementation agent 去依赖 3.0.52 特定行为。建议只修正事实措辞——将"当前锁定依赖是 prompt_toolkit==3.0.52"改为"当前开发环境安装 prompt_toolkit==3.0.52（pyproject.toml 约束为 >=3.0.0）；以下使用的 public API 在 >=3.0.0 均可用"——不修改依赖声明、不 pin 版本。

### 5.3 Vt100Parser reader-thread / ESC deadline / typed bridge / closeout consumer 映射 —— 可实现

**结论：原 18 项已修复；此项无新增 finding。**

已验证：
- `Vt100Parser(feed_key_callback)` 构造时传入 callback
- `feed(data: str) -> None` 和 `flush() -> None` 均为同步方法，适合在 reader thread 调用
- plan 将 parser 生命周期限制在单一 reader thread：创建、feed、flush 均在同一线程，无跨线程调用
- ESC ambiguity deadline 是 Dayu 侧命名常量（`_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS`），由 reader thread 管理 monotonic clock
- callback 只做 KeyPress → `RunningKeyAction` 分类，通过 `loop.call_soon_threadsafe` 投递到 asyncio queue
- 完整 CSI/Home/Delete/SS3/Alt/bracketed paste 序列由 Vt100Parser 内部累积，不会产生 `key is Keys.Escape and data == "\x1b"` 的 standalone ESC
- closeout consumer 映射表（§5.2 的 8 行 site→replacement 表）逐项覆盖当前代码中全部创建/消费点（lines 916, 1019, 1657, 1707, 1736）

### 5.4 Accepted plan commit 精确纳入两个 registry 原字节

**结论：原 18 项已修复；此项无新增 finding。**

plan §13.2 定义：
- 十条显式路径（含两个 registry 和完整 review loop，3 条 re-review artifact 标注"将由 plan re-review gate 新增"）
- stage 前校验 working-tree SHA-256
- `git add -- <十条路径>` 精确 staging
- stage 后校验 working-tree + index blob (`git show :path | shasum`)
- 四次 hash 必须与 §0.1 固定值一致
- commit 后 `git status --short` 显示 registry clean

### 5.5 S1/S4 路径、F06 机械传播、S7 checkpoints、committed event→Memory 链

**结论：原 18 项已修复；此项无新增 finding。**

- **S1 路径**: plan §3.2 的 construction-site 表 + `rg` inventory 覆盖全部 `EntrypointRuntimeRequest`/`ServiceHostAdminRequest` 构造点；`RuntimeLocations.config_overlay_dir`（runtime location 结果）区别于 request 字段，正确保留
- **S4 路径**: 修正后的 `tests/host/test_session_attachment_registry.py` 存在；plan §6.2-6.4 的 typed contract、状态机和 owner tests 完整
- **F06 机械传播**: plan §8.2 二行旧→新映射表 + 6 行 propagation closure 表（producer/persistence+strict reader/ingest reader/projection/owner tests/design）；§8.3 两个 `rg` 扫描覆盖 active code
- **S7 checkpoints**: plan §9.8 A-D 四个 checkpoint，每个有明确 implementation closure 和 focused tests/pyright；明确禁止 stash/branch/mid-commit
- **Committed event→Memory 链**: plan §9.6 完整数据流：accepted truth → terminal owner + commit permit → artifact + `CONTEXT_COMPACTED` payload → commit → `context_events` strict projection → Memory snapshot update。明确禁止未提交对象直传 Memory

### 5.6 无兼容/迁移/下游补偿、无越 scope

**结论：原 18 项已修复；此项无新增 finding。**

- Plan §2.2 非目标逐项明确：不迁移旧 compact schema/DB；不提供旧字段/trigger/`--config` 兼容读取/alias/re-export；不把 Host 语义下放到 CLI/Service/Engine；不改变 ordinary terminal outcome 枚举；不重写 prompt_toolkit 通用组件；不改变 Fins preprocess 独立能力；不用 LLM 做自然语言事实真伪证明；不顺手清理归档/无关 README/无关 pyright debt
- Plan §9.2.1 明确 v1 parser/alias/compat branch 全部删除
- Plan §8.2 明确"旧 literal 严格 unknown/fail closed"，不 alias/re-export
- Plan §3.2 明确"不保留旧名字 wrapper、常量 re-export 或 hidden environment compatibility"

### 5.7 所有"已有"路径真实存在

**结论：原 18 项已修复；此项无新增 finding。**

对 plan S1–S8 全部 allowlist 中 57 个"已有"文件路径（排除 3 条标注"将由 plan re-review gate 新增"的 artifact 路径）执行 `test -e` 检查：**57/57 存在，0 缺失**。

特别验证了 M-F1/M-F2 修正后的两条路径：
- `tests/cli/test_session_command.py`（单数）— 存在
- `tests/host/test_session_attachment_registry.py` — 存在

### 5.8 补充检查：S1 construction site inventory 完整性

**结论：原 18 项已修复；此项无新增 finding。**

运行 `rg -n 'EntrypointRuntimeRequest\(|ServiceHostAdminRequest\(|explicit_config_dir|config_overlay_dir' dayu/cli dayu/service tests/cli tests/service`，逐项验证：

- `tests/service/test_host_assembly.py` 中大量 `locations.config_overlay_dir` 引用 —— 消费的是 `RuntimeLocations` 结果，不是 `EntrypointRuntimeRequest` 或 `ServiceHostAdminRequest` 的字段。`RuntimeLocations.config_overlay_dir` 是独立的 runtime location API，不在本次删除范围
- `tests/service/test_host_assembly.py:3252` 的 `config_overlay_dir=None` —— 构造的是 `RuntimeLocations(...)`，不是被修改的 request 类型
- `dayu/service/host_assembly.py:309,332,1752` 的 `config_overlay_dir` —— 是 `HostAssembly` 内部参数，由 `entrypoint_runtime.py`/`host_admin.py` 传入（已在 S1 allowlist），`host_assembly.py` 本身不需要修改

## 6. New Findings 汇总

### NEW-1-未修复-低-plan §4.2 prompt_toolkit 版本措辞不够精确

- **位置**: §4.2 开头"当前锁定依赖是 prompt_toolkit==3.0.52"
- **问题类型**: 文档精度
- **当前写法**: "当前锁定依赖是 prompt_toolkit==3.0.52。直接代码证据已经确认：public Buffer.open_in_editor(validate_and_handle=False) 适合 unset 路径"
- **反例/失败场景**: pyproject.toml:44 实际约束为 `prompt_toolkit>=3.0.0`，不是 `==3.0.52`。若 implementation agent 理解为需要精确版本锁定，可能浪费精力在版本 pin 上。
- **为什么有问题**: plan 实际采用的 public-seam 方案（run_in_terminal、Buffer.open_in_editor、Buffer.document、Vt100Parser）不依赖特定 3.0.x 版本，措辞不应暗示需要版本锁定。
- **直接证据**: pyproject.toml:44 `"prompt_toolkit>=3.0.0"`；venv 中实际安装 3.0.52
- **影响**: 低 — public-seam 方案本身正确且不依赖版本锁定，仅措辞可能造成轻微误导
- **建议改法和验证点**: 将"当前锁定依赖是 prompt_toolkit==3.0.52"改为"当前开发环境安装 prompt_toolkit==3.0.52（pyproject.toml 约束为 >=3.0.0）；以下使用的 public API 在 3.0.x 全线可用"
- **修复风险**: 低
- **严重程度**: 低

## 7. Residual Risk 评估

| 风险 | 等级 | Plan 收敛方式 | Re-review 评估 |
|---|---|---|---|
| prompt_toolkit terminal suspend/resume + 显式 editor 子进程行为 | MEDIUM | Public seam contract test + 真实 PTY 测试 | 收敛充分 — public seam 方案消除了版本锁定和私有 API 依赖 |
| ESC ambiguity + SIGINT/terminal 同 batch 竞态 | MEDIUM | Vt100Parser chunk matrix、turn-bound state、确定性 scheduler + PTY evidence | 收敛充分 — reader-thread 方案消除了线程/async 桥接不确定性 |
| READ_ONLY 后 writer 退出时 fresh attach 竞争 | MEDIUM | Host public typed mode + close-before-open + stable pending identity + 真实双 CLI | 收敛充分 |
| F07 fresh schema + reactive aggregate 影响面大 | HIGH | S7 单一 outer 边界、四个内部 checkpoint、strict parser、root revalidation、committed-event projection、full suite | 收敛充分 — 但仍是最大 residual risk；S7 implementation 必须严格按 A→D checkpoint 推进 |
| LLM 自然语言低质量但形式合法 | MEDIUM/ACCEPTED | Deterministic 最低信息 + coverage；真实 provider evidence；不以 schema 伪装语义证明 | 接受为模型风险 |
| Mimo/DeepSeek/网络环境不可用 | MEDIUM/OPERATIONAL | Mimo-first + 明确 fallback + 新 bundle；环境失败不算产品 pass | 接受为 operational risk |
| dirty registry 误 stage/覆盖 | HIGH/CONTROLLED | Accepted plan commit 精确十路径、stage 前后 working-tree/index hash、之后 S1–S8 clean guard | 收敛充分 |

## 8. Open Questions

当前 **无未收敛的 plan design open questions**。所有在首轮 review 中提出的 open questions 已通过 plan fix 解决：

- 原 Q1（prompt_toolkit 版本/seam）：已通过 public-seam 方案解决
- 原 Q2（`_ActiveTurnCloseout` 消费者映射）：已通过 site→replacement 映射表解决
- 原 Q3（Memory policy cap 真源）：已确认 owner 在 `dayu/host/memory.py`
- 原 Q4（Mimo failure 处理）：已在 S8 规则中明确

## 9. Plan Review Conclusion

**Verdict: `pass`**

### 9.1 修复验证结论

总控裁决中的 **18 个 accepted/accepted-in-part finding 全部已修复**（18/18），没有发现部分修复、未修复或证据失效的情况：

- 7 个 MiMo findings（M-F1, M-F2, M-F3, M-F4, M-F7, M-O1, M-O2）：**全部已修复**
- 6 个 DeepSeek findings（DS-B1, DS-B2, DS-B3, DS-B4, DS-B5, DS-B7）：**全部已修复**（DS-B5/DS-B7 的 accepted-in-part 按裁决接受部分实施）
- 5 个 Controller 新增 findings（C1, C2, C3, C4, C5）：**全部已修复**

### 9.2 Adversarial pass 结论

所有用户指定的检查项均通过：
- ✓ reactive bounded multi-pass 保留且无中间 durable truth
- ✓ editor missing/nonexec/OSError/nonzero/zero/unset 四分语义在 `>=3.0.0` 依赖范围可实现
- ✓ Vt100Parser reader-thread/ESC deadline/typed bridge/closeout consumer 映射可实现
- ✓ accepted plan commit 精确纳入两个 registry 原字节
- ✓ S1/S4 路径、F06 机械传播、S7 checkpoints、committed event→Memory 链全部验证
- ✓ 无兼容/迁移/下游补偿、无越 scope
- ✓ 57/57 "已有"路径真实存在

新增 finding：仅有 NEW-1（低严重度、未修复、非 blocking），见 §6。**待 controller 裁决**——若 NEW-1 被 accepted，需在 plan 中修正措辞后重新 plan re-review；若被 rejected，可直接进入 implementation gate。

### 9.3 下一 gate 建议

**当前不直接进入 implementation gate；下一合法入口为 controller adjudication gate。**

Controller 需对 NEW-1 做出裁决：

- 若 **rejected**：plan 可直接进入 implementation gate（S1→S8 按序实施）。
- 若 **accepted**：需先执行 plan fix（修正 §4.2 版本措辞，不改变依赖声明、不 pin 版本），再经独立 plan re-review 确认后方可进入 implementation gate。

Plan 的设计层面已满足 code-generation-ready 条件：
- S1–S8 的 owner、call path、state machine、error handling、invariant、tests、completion/stop signal 均已明确
- 每个 slice 的 allowlist 精确，文件路径全部验证存在
- 所有 design open questions 已收敛
- Reactive multi-pass、committed-event→Memory、F02 四分语义 等关键 contract 已固定
- Staging/commit 边界、registry 保护、evidence 程序均已定义

S7 的 HIGH residual risk（32 文件原子变更）通过四个内部 checkpoint 和完整的 focused tests 收敛，implementation agent 必须严格按 A→D 顺序推进，不得跳过 checkpoint 验证。

S8 的 provider availability 是 operational risk；若 provider 不可用，S8 停留 `BLOCKED-ON-REAL-EVIDENCE`，不退回 S1–S7。

---

*Review 方: DeepSeek | 日期: 2026-08-02T18:25:38+08:00 | 下一合法入口: Controller Adjudication Gate（裁决 NEW-1 后决定是否需 plan fix → re-review 或直接进入 implementation）*

---

# 第二轮 Re-review（DeepSeek，独立 Plan Re-review Gate）

## R0. Gate 元数据

- **Gate**: 第二轮独立 Plan Re-review（PR 190，WU-CLI-CONFORMANCE-F01-F07）
- **Reviewed artifacts**:
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`（第二次 fix 后版本）
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-fix-codex.md`（含 §8 第二次 Plan Fix 记录）
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md`（R1/R2 裁决真源）
  - 本文件首轮 re-review 内容（保留不变）
- **编制日期**: 2026-08-02（Asia/Shanghai）
- **审查范围**: 仅验证 controller R1/R2 修复状态 + 原 18 项回归扫描 + 三项重点直接验证；不审实现、不修改 plan/其它文件、不 stage/commit/push/PR。
- **输出**: 本 durable addendum（追加于首轮 re-review 内容之后），不新建其它 artifact。

## R1. Controller R1 裁决逐项验证

Controller 要求（`rereview-controller-adjudication.md` §2 R1）：

| # | Controller 要求 | Plan 实际位置 | 验证结果 |
|---|---|---|---|
| 1 | 精确区分"当前验证环境安装 3.0.52"和"项目声明范围 >=3.0.0" | plan §4.2 L247: "当前开发/验证环境安装的是 `prompt_toolkit==3.0.52`，项目在 `pyproject.toml` 声明的依赖范围是 `prompt_toolkit>=3.0.0`；前者是本轮直接核验环境事实，不是版本 pin 或产品契约" | **已修复** — 两者明确区分，不含"锁定依赖""锁定版本""锁定 3.0.52"措辞 |
| 2 | 方案只依赖 prompt_toolkit public import/API，不依赖 3.0.52 私有实现 | plan §4.2 L247: "S2 只依赖 prompt_toolkit 的 public import/API：public `Buffer.open_in_editor(validate_and_handle=False)` 用于 unset 路径，public `run_in_terminal(...)` 与 public `Buffer.document` 用于 CLI-owned 最小 round trip"；private `_open_file_in_editor()` 行为仅作为"排除错误实现路径"的负面证据 | **已修复** — public seam 固定，不再有 implementation-time seam 选择 |
| 3 | "按锁定依赖去除末尾换行"改为 CLI owner frozen editor success behavior | plan §4.2 L261: "CLI composer 作为 editor success behavior owner，按冻结规则最多移除一个末尾换行" | **已修复** — readback 规则 owner 已从依赖版本转移至 CLI composer |
| 4 | Stop signal 改为 public seam 不符即回 plan；禁止 private fallback/monkey patch/pin | plan §4.5 L326: "当前 resolved dependency 的所需 public seam 与已核验证据不符。不得改用 private fallback、monkey patch、兼容层或擅自 pin 依赖"；plan §14.1 L1230: "CLI-owned frozen readback规则...seam不符即回plan" | **已修复** — stop signal 与 risk register 均使用正确措辞 |
| 5 | 不修改 pyproject.toml，不新增 dependency compatibility layer | plan fix §8.2 L194: "本轮未修改 `pyproject.toml`，未新增 dependency compatibility layer" | **已修复** — 无 pyproject.toml 修改、无兼容层 |

**R1 状态: 已修复**（5/5 子项均满足）

## R2. Controller R2 裁决逐项验证

Controller 要求（`rereview-controller-adjudication.md` §2 R2）：

| # | Controller 要求 | 验证方法与直接证据 | 验证结果 |
|---|---|---|---|
| 1 | 三条 re-review artifact 路径从 `plan-re-review-*` 改为 `plan-rereview-*` | `rg -n 'plan-re-review'` 对 plan-codex.md 与 plan-fix-codex.md 均为零命中；plan §13.2 十条路径及 `git add --` 示例全部使用 `plan-rereview-mimo.md`、`plan-rereview-ds.md`、`plan-rereview-controller-adjudication.md` | **已修复** — 无旧拼写残留 |
| 2 | 十条路径全部真实存在 | `test -e` 逐项验证：10/10 EXISTS，0 MISSING | **已修复** |
| 3 | Staged-set 计数仍为 10 | 路径集合精确含 10 条，plan §13.2 显式列出 10 条，plan fix §8.3 计数为 10 | **已修复** |
| 4 | 两个 registry working-tree/index digest 保持不变 | `shasum -a 256`: `f9972d94...` / `7f283b03...` 与 plan §0.1 完全一致；`git diff --cached --name-only` 输出为空（index 未被修改） | **已修复** |
| 5 | 当前 fix/re-review 阶段仍不 stage | `git diff --cached --name-only` 输出为空；plan §13.1 明确"不stage、不commit、不push" | **已修复** |

**R2 状态: 已修复**（5/5 子项均满足）

## R3. 原 18 项 Accepted Findings 回归扫描

逐项核对第二次 fix（R1/R2 措辞与路径修改）未导致原 18 项 finding 的修复证据退化：

| 来源 | Finding | 首轮状态 | 回归验证 | 回归结论 |
|---|---|---|---|---|
| MiMo | M-F1 | 已修复 | S1 allowlist 仍为 `tests/cli/test_session_command.py`（单数），construction-site 表完整 | **未退化** |
| MiMo | M-F2 | 已修复 | S4 owner test 仍为 `tests/host/test_session_attachment_registry.py` | **未退化** |
| MiMo | M-F3 | 已修复 | S6/S7 旧→新机械映射表与传播闭包完整 | **未退化** |
| MiMo | M-F4 | 已修复 | S7 四个内部 checkpoint A-D 仍列于 §9.8 | **未退化** |
| MiMo | M-F7 | 已修复 | S2 public seam 四分语义完整（已由 R1 增强而非削弱） | **未退化** |
| MiMo | M-O1 | 已修复 | S8 BLOCKED-ON-REAL-EVIDENCE 与新 run id 规则仍在 §10.3 | **未退化** |
| MiMo | M-O2 | 已修复 | Memory policy owner 仍为 `dayu/host/memory.py`，见于 §9.2/§9.4 | **未退化** |
| DeepSeek | DS-B1 | 已修复 | Vt100Parser reader-thread 方案仍完整在 §5.2 | **未退化** |
| DeepSeek | DS-B2 | 已修复 | Registry disposition 仍在 §13.2（且由 R2 修正路径而非削弱） | **未退化** |
| DeepSeek | DS-B3 | 已修复 | Editor 四分语义仍在 §4.2（已由 R1 增强） | **未退化** |
| DeepSeek | DS-B4 | 已修复 | Closeout consumer 映射表 7 行仍在 §5.2 | **未退化** |
| DeepSeek | DS-B5 | 已修复 | S7 checkpoints 禁止 stash/branch/mid-commit 仍在 §9.8 | **未退化** |
| DeepSeek | DS-B7 | 已修复 | Editor seam 与 Memory owner 已收口；仅 provider 为 operational stop | **未退化** |
| Controller | C1 | 已修复 | `CompactPipelinePassQueuePlan`/`build_reactive_pass_queue_plan` 保留 + root 重验仍在 §9.6 | **未退化** |
| Controller | C2 | 已修复 | F02 nonzero silent cancel 与四分语义仍在 §4.2/§4.3 | **未退化** |
| Controller | C3 | 已修复 | S1 construction-site allowlist 表与 `rg` inventory 仍在 §3.2 | **未退化** |
| Controller | C4 | 已修复 | Memory 只消费 committed event projection 数据流仍在 §9.6 | **未退化** |
| Controller | C5 | 已修复 | Stale Phase A/B 已删除；§0/§16 入口仅为 Plan Re-review | **未退化** |

被首轮总控 rejected 的 M-F5、M-F6、DS-B6 未被复活。

**回归结论: 原 18 项全部未退化。** 第二次 fix 仅触及 R1（§4.2/§4.5/§14.1 措辞）和 R2（§13.2 路径与 plan-fix §8 记录），不涉及其他 18 项的修复证据。

## R4. 三项重点直接验证

### R4.1 3.0.52 vs pyproject>=3.0.0 表述、CLI frozen readback owner、public seam stop/risk

- **版本表述**: plan §4.2 明确 "当前开发/验证环境安装的是 `prompt_toolkit==3.0.52`，项目在 `pyproject.toml` 声明的依赖范围是 `prompt_toolkit>=3.0.0`；前者是本轮直接核验环境事实，不是版本 pin 或产品契约"。✓
- **CLI frozen readback**: plan §4.2 "CLI composer 作为 editor success behavior owner，按冻结规则最多移除一个末尾换行"。✓
- **Public seam stop**: plan §4.5 "当前 resolved dependency 的所需 public seam 与已核验证据不符。不得改用 private fallback、monkey patch、兼容层或擅自 pin 依赖"。✓
- **Risk register**: plan §14.1 "当前 resolved dependency 的 public seam contract tests、CLI-owned frozen readback规则、exact argv、无fallback真实PTY测试；seam不符即回plan"。✓
- **无锁定/pin/private fallback**: plan §4.2 "S2 不再保留 implementation-time seam 选择"；显式路径禁止调用或 monkey-patch private `_open_file_in_editor()`。plan fix §8.2 "本轮未修改 `pyproject.toml`，未新增 dependency compatibility layer"。✓

### R4.2 三个 plan-rereview 路径与完整 git add 示例实际存在，exact set=10，registry hash 不变

- **三个 rereview 路径**:
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-mimo.md` → EXISTS ✓
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-ds.md` → EXISTS ✓
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-rereview-controller-adjudication.md` → EXISTS ✓
- **完整 git add 示例**: plan §13.2 L1191 使用 `git add --` 后跟十条精确路径，均使用 `plan-rereview-*` 拼写。✓
- **Exact set = 10**: 逐项计数为 10，与 plan §13.2 及 plan fix §8.3 一致。✓
- **Registry hash 不变**:
  - `docs/cli_ci_oracles.json`: `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` ✓
  - `docs/cli_ci_scenarios.json`: `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` ✓

### R4.3 Gate metadata 只指向第二轮 re-review，无 implementation 提前许可

- plan §0 L9: "Gate 状态：`SECOND PLAN FIX COMPLETE — 待第二轮独立 Plan Re-review`" ✓
- plan §0 L13: "下一合法入口：仅为第二轮独立 **Plan Re-review Gate**；本次 fix 完成后必须停止。" ✓
- plan §0 L12: "禁止动作：implementation、第二轮 plan re-review、code review、deepreview、stage、commit、push、PR 读取/写入/状态操作。" ✓
- plan §16 L1298: "Second Plan Fix Gate标记为 `COMPLETE`、non-blocked、**待第二轮独立plan re-review**；不得提前标记为code-generation-ready。" ✓
- plan §16 L1300: "当前动作到此停止。下一合法动作仅是第二轮独立的 **Plan Re-review Gate**；本次不得进入该gate，也不得实施、stage、commit、push或操作PR。" ✓
- plan fix §8.1 L182: "下一合法入口：仅为第二轮独立 `Plan Re-review Gate`；不得提前进入 implementation 或标记为 code-generation-ready。" ✓
- 全 plan 扫描无 "code-generation-ready" 声明、无 "Phase A"/"Phase B" 残留、无 "进入 implementation gate" 许可。✓

## R5. New Findings

本次第二轮 re-review 的 adversarial pass 未发现新的 material finding。R1/R2 修复完整，原 18 项未退化，三项重点验证全部通过。

## R6. 结论

| 项目 | 状态 |
|---|---|
| R1（prompt_toolkit 版本表述与 public seam） | **已修复** |
| R2（accepted-plan staged set 路径） | **已修复** |
| 原 18 项 accepted findings 回归 | **全部未退化**（18/18） |
| 三项重点直接验证 | **全部通过** |
| 新 finding | **无** |
| Gate metadata | **正确 — 仅指向第二轮 Plan Re-review，无 implementation 提前许可** |

**Re-review 结论: `pass`**

Plan 当前状态为 `SECOND PLAN FIX COMPLETE`，R1/R2 均已修复，原 18 项状态未因第二次 fix 退化，gate metadata 正确。当前仍处于 Plan Fix Gate 完成、等待第二轮独立 Plan Re-review 的状态。本 re-review 本身即为该第二轮独立 Plan Re-review。

**下一合法入口: Controller Adjudication Gate。** Controller 需对本轮 R1/R2 修复状态与回归结论做出最终裁决，并决定是否可进入 accepted plan commit（§13.2）及后续 implementation gate。

---

*第二轮 Re-review 方: DeepSeek | 日期: 2026-08-02 | 下一合法入口: Controller Adjudication Gate*
