# Code Review

## Scope

- Mode: current changes
- Branch: `wu-cli-debug-stream-01`
- Base: `main` (implied, uncommitted diff only)
- Output file: `docs/reviews/code-review-wu-cli-debug-stream-01-slice4-ds-20260620.md`
- Included scope: uncommitted changes to `README.md`, `tests/README.md`, `docs/host/issues-implementation-control.md`；untracked artifact `docs/reviews/implementation-wu-cli-debug-stream-01-slice4-20260620.md`
- Excluded scope: production code、test code (Slice 1-3 已提交)；未跟踪的 `MEMORY.md` 类文件
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Open Questions

### OQ-1: README `write` 命令参数表未列出 `--debug-stream`

`write` 命令参数表（`README.md:722`）当前写 `--debug / --verbose`，未包含 `--debug-stream`。而 `prompt` 和 `interactive` 两节的参数表均已同步加上 `--debug-stream`。

- **不构成 defect**：`--debug-stream` 是全局参数，全局参数表已声明"全部主命令"适用。`write` 的参数表在 Slice 4 前也只列 `--debug / --verbose`，Slice 4 没有改变这一模式。
- **建议**：未来若统一整理各命令参数表，可考虑在 `write` 参数表也补上 `--debug-stream`，或全区统一去掉命令级参数表中的冗余全局参数列。

### OQ-2: `--detail` 共享参数表适用命令列为仅 `prompt`，但 `interactive` 也支持

`README.md:303` 共享参数表写 `--detail / --no-detail` 适用 `prompt`，但 `interactive` 命令也实际支持 activity view 切换（Ctrl+T）。这是 Slice 4 前已有问题，Slice 4 未触及该行。不构成 Slice 4 defect。

### OQ-3: 实现 artifact 的验证命令未列出实际 pytest 运行

实现 artifact 称"Slice 4 只更新文档，不重新运行 pytest"（diff check 与 pyright 已跑）。该声明与 Slice 4 scope（纯文档）一致——前序 Slice 1-3 已由 pytest 验证 `--debug-stream` 行为。但控制文档 `issues-implementation-control.md` 的验证要求未强制 docs-only slice 需重跑 pytest。此问题是流程级判断，不构成实现 defect。

## Residual Risk

- `README.md:290` 的 `--log-level` choices 仍含 `critical`，而 `dayu/cli/arg_parsing.py:17-23` 的 `LOG_LEVEL_CHOICES` 不含 `critical`。此为 Slice 4 前既有不一致，实现 artifact 已在残余风险中显式标出。不影响 `--debug-stream` 的正确性或可用性。
- `git diff --check` 与 `pyright dayu/ tests/ utils/` 均通过，0 errors。
- 未修改 `dayu/host/README.md`、`dayu/engine/README.md` 的理由成立：本 Slice 未新增 Host/Engine public contract、状态机、EventLog 语义或 package-level 开发接口。`STREAM_DEBUG_LOG_LEVEL` 位于 `dayu.runtime.log_levels`（层中立基础设施），Host/Engine 内部日志级别重分类不改变其公共契约。

## 逐项审查结论

### 1. README.md 是否符合自身 Agent更新约束

**PASS。** Slice 4 新增内容严格遵循"最终用户使用手册"边界：
- 只写 `--debug-stream` 的 CLI 参数、含义、与 `--debug` / `--detail` / `--log-file` 的关系和命令行示例。
- 不写 Host/Engine 内部实现、work-unit 状态、EventLog contract、测试清单或开发者迁移计划。
- `--debug-stream` 行内描述语言（"stream delta"、"SSE 完成标记"、"逐 delta ingest"、"stream idle heartbeat"）是对诊断日志中用户可见内容的描述，不是内部治理术语的暴露。

### 2. --debug / --debug-stream / --detail / --log-file 关系是否准确

**PASS。** 
- `--debug`：普通诊断（Host open、命令提交、调度、Runner HTTP、终态收口），默认不输出逐 delta stream 诊断。——准确，STREAM_DEBUG(9) < DEBUG(10)，普通 DEBUG 阈值抑制 stream 记录。
- `--debug-stream`：包含普通 DEBUG 加 stream delta / stream idle heartbeat / SSE done-token / Host 逐 delta ingest。——准确，STREAM_DEBUG(9) 阈值同时放出 stream 和 debug 记录。
- `--detail`：终端 activity stream，与 `--debug`/`--debug-stream` 诊断日志分离，不写入 `--log-file`。——准确，activity stream 走 stderr，诊断日志走 Python logging。
- 日志示例新增 `--debug-stream --log-file` 组合命令。——准确可用。

### 3. tests/README.md 是否只记录当前已落地测试事实

**PASS。**
- CLI 覆盖（第 91 行）：`--debug` / `--debug-stream` 加入 CLI main 参数装配覆盖描述——实际测试 `test_arg_parsing.py` 有 `debug_stream` 参数化测试。
- CLI interactive（第 97 行）：`--debug-stream` 不进入旧 Agent 执行参数——实际测试 `test_interactive_command.py:1359` 有对应断言。
- CLI prompt：`--debug`/`--debug-stream`/`--verbose` 诊断不污染 stdout——实际测试 `test_prompt_command.py:820` 有参数化覆盖。
- runtime logging（第 123 行）：STREAM_DEBUG 阈值契约——实际测试 `test_log.py` 有 `test_debug_suppresses_stream_debug_records_but_stream_debug_emits_both` 等。
- Host logging（第 196 行新增）：delta ingest 使用 stream-debug 级别，受 DEBUG 抑制——实际测试 `test_logging.py:180` 有对应断言。
- Engine runner diagnostics（第 241 行新增）：stream idle heartbeat 与 SSE done-token 的 stream-debug gating——实际测试 `test_runner_diagnostics.py:288` 有对应断言。

所有 claims 均有对应测试文件与测试函数直接支撑，未发现无测试支撑的过度声明。

### 4. 未修改 dayu/host/README.md、dayu/engine/README.md 的理由是否成立

**PASS。**
- `dayu/host/README.md`：Host 开发手册只写 public contract、状态机、EventLog 语义、package-level 接口。本 Slice 的 Host `engine_ingest.py` 改动是把 delta ingest 日志级别从 `logging.DEBUG` 改为 `STREAM_DEBUG_LOG_LEVEL`，属于内部实现细节调整，不改变 Host public API、状态迁移或契约。
- `dayu/engine/README.md`：Engine 开发手册只写 public entry、RunnerSpec、EngineEvent/RunnerEvent contract。本 Slice 的 Engine runner/sse_parser 改动是把 stream idle heartbeat 和 SSE done-token 诊断级别从 `logging.DEBUG` 改为 `STREAM_DEBUG_LOG_LEVEL`，属于内部诊断级别调整，不改变 Engine public API 或事件契约。
- `STREAM_DEBUG_LOG_LEVEL` 定义在 `dayu.runtime.log_levels`（层中立基础设施），不属于 Host 或 Engine 的 package-level 接口。

### 5. memory_repair.catch_up.budget_exhausted 处理

**PASS。** 控制文档已有明确裁决：`budget_exhausted` stop reason 已从当前代码删除，`MemoryProjectionRepairStopReason` 只保留 `IDLE`/`TARGET_REACHED`/`FAILURE`。Slice 4 实现 artifact 正确地将此标为"已修复 bug，不做回归以外处理"。代码核对（通过前序 Slice 验证）确认无回归。

### 6. 文档是否存在误导、过度承诺、过长难维护、术语错误或 README 触发规则遗漏

**PASS。**
- 无误导：`--debug-stream` 的行为描述与 STREAM_DEBUG(9) < DEBUG(10) 的日志级别语义一致。
- 无过度承诺：不声称 `--debug-stream` 会输出逐 chunk 内容或 body text。
- 无过长难维护：新增内容为 1 行参数表 + 2 行说明 + 少量示例，控制在 README 现有密度内。
- 无术语错误：stream delta / SSE done-token / 逐 delta ingest 等术语与设计真源一致。
- README 触发规则：`README.md` 因 CLI 参数和用户可见诊断行为变化触发更新——已更新。`tests/README.md` 因测试覆盖职责描述变化触发更新——已更新。`dayu/host/README.md` 与 `dayu/engine/README.md` 检查后判定无需更新——触发规则不要求机械更新。

## 结论

**PASS。**

WU-CLI-DEBUG-STREAM-01 Slice 4 的文档变更准确、一致、合规：
- 根 README 对 `--debug-stream` 的用户可见行为描述与实际实现语义一致。
- tests/README.md 的 CLI/runtime/Host/Engine logging 覆盖摘要与已落地测试事实一致。
- 未修改 Host/Engine README 的理由成立。
- 无新增实质缺陷、误导、过度承诺或术语错误。
- 既有 `--log-level critical` 不一致已在实现 artifact 残余风险中显式记录。
