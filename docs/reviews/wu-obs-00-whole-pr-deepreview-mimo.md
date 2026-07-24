# Code Review

## Scope

- Mode: PR (whole-PR deepreview)
- PR: 186
- Branch: work/wu-obs-00
- Base: main@9588ee7a
- Head: 9519b029
- Output file: docs/reviews/wu-obs-00-whole-pr-deepreview-mimo.md
- Review date/time: 2026-07-24T17:45:45
- Included scope: 全部 PR diff（38 production files, 12 test files, 2 docs files）
- Excluded scope: docs/reviews/ 下的历史 review artifacts（不属生产代码）
- Parallel review coverage: 无 subagent；主 reviewer 逐文件独立审查

## PR Facts

- Title: feat: add Tool Trace analyzer for Host/Engine/Tool diagnostics
- Author: noho
- URL: https://github.com/noho/dayu-agent-r/pull/186
- Base branch: main
- Head branch: work/wu-obs-00
- CI checks: 无配置

## Validation Summary

- Tests: 256 passed, 0 failed
- Pyright: 0 errors, 0 warnings
- Coverage: PR body 声明 publication owner 92%，changed production branch ≥80%

## Findings

未发现实质性问题。

以下为低严重度观察项，不构成 merge 阻断：

### 1-观察-[低]-open_host.py 导入 tool_trace.py 模块私有符号

- **入口/函数**: `dayu/host/open_host.py:142` → `_tool_trace_cold_lock_path`
- **文件(行号)**: `dayu/host/open_host.py:142`, `dayu/host/tool_trace.py:263`
- **输入场景**: N/A（静态导入关系）
- **实际分支**: `open_host.py` 从 `dayu.host.tool_trace` 导入 `_tool_trace_cold_lock_path`
- **预期行为**: 模块间依赖最小化，优先接口或协议
- **实际行为**: 导入了下划线前缀的模块私有 helper
- **直接证据**: `_tool_trace_cold_lock_path` 的 docstring 明确说明"producer 与 Analyzer reader 必须复用它；它不属于 Host package public surface"（`tool_trace.py:266-272`）
- **影响**: 无直接功能影响；若 `_tool_trace_cold_lock_path` 的签名变化，`open_host.py` 需同步修改
- **建议改法和验证点**: 当前可接受——两个模块同属 `dayu.host` 包，且 docstring 已明确复用契约。若后续 `_tool_trace_cold_lock_path` 的签名变得复杂，可考虑提升为 package-level public helper
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-观察-[低]-_capture_cold_prefix finally 可覆盖成功读取结果

- **入口/函数**: `_capture_cold_prefix` (`dayu/host/tool_trace_analysis_input.py:729`)
- **文件(行号)**: `dayu/host/tool_trace_analysis_input.py:808-817`
- **输入场景**: cold JSONL 文件在读取成功后 `handle.close()` 抛出 OSError
- **实际分支**: `finally` 块中 `handle.close()` 失败 → 抛出 `ToolTraceAnalysisInputError`
- **预期行为**: 数据已成功读入内存，close 失败不应丢弃结果
- **实际行为**: close 异常覆盖了已成功读取的 `content`，`return _CapturedColdPrefix(...)` 不执行
- **直接证据**: `tool_trace_analysis_input.py:808-817` 的 `finally` 块在 `handle.close()` 失败时抛出异常
- **影响**: 极低——只读文件 handle 的 `close()` 几乎不会失败；即使失败，OS 会在进程退出时清理
- **建议改法和验证点**: 当前行为从防御编程角度可接受——close 失败暗示文件系统异常，此时拒绝返回数据比返回可能不一致的数据更安全。无需修改
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-观察-[低]-Markdown section 索引依赖固定位置

- **入口/函数**: `render_tool_trace_analysis_markdown` (`dayu/host/tool_trace_analysis.py:102`)
- **文件(行号)**: `dayu/host/tool_trace_analysis.py:39-50, 118-125`
- **输入场景**: 向 `_MARKDOWN_SECTIONS` 元组头部插入新 section
- **实际分支**: `_MARKDOWN_SECTIONS[2]`、`[3]`、`[4]` 等硬编码索引
- **预期行为**: section 名与索引保持一致
- **实际行为**: 若在头部插入 section，所有后续索引会偏移
- **直接证据**: `tool_trace_analysis.py:118-125` 使用 `_MARKDOWN_SECTIONS[2]`、`_MARKDOWN_SECTIONS[3]`、`_MARKDOWN_SECTIONS[4]`
- **影响**: 维护性——后续修改者可能误插 section 导致标题错位
- **建议改法和验证点**: 当前 `_MARKDOWN_SECTIONS` 是模块私有常量，且渲染函数使用具名常量引用 section 标题（如 `_MARKDOWN_SECTIONS[2]` 对应 "Host findings"），风险可控。若 section 数量增长，可改为 dict 或具名常量
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

- **CI 缺失**: `gh pr checks 186` 显示无 CI checks 配置。所有验证（tests、pyright、coverage）均为本地执行。若后续有人 force push 或合并冲突，无自动回归保护。
- **Read-only store PRAGMA**: `open_host_durable_read_store` 使用 `PRAGMA query_only=ON` 物理只读，但 `run_read` 使用 `BEGIN` 而非 `BEGIN DEFERRED`。SQLite 默认 deferred transaction 在只读模式下不会获取写锁，行为正确，但显式 `BEGIN DEFERRED` 可提升意图清晰度。
- **Native Anthropic/Claude Code gateway correlation**: PR body 明确声明此 signal 在 #64 之前为 limited，Analyzer 已正确报告为 limitation 而非 finding。

## Architecture Assessment

### 分层与反向依赖

- CLI → Service → Host 分层严格遵守
- `dayu/cli/commands/tool_trace.py` 只 import `dayu.cli.arg_parsing` 和 `dayu.service.tool_trace_analysis`
- `dayu/service/tool_trace_analysis.py` 只 import `dayu.host` public exports
- 无反向 import

### Semantic Ownership

- Contracts 集中在 `tool_trace_analysis_contracts.py`，所有 public types 在此定义并校验不变量
- Input 读取与完整性校验由 `tool_trace_analysis_input.py` 拥有
- 行为规则与报告构造由 `tool_trace_analysis_rules.py` 拥有
- JSON/Markdown renderer 由 `tool_trace_analysis.py` 拥有，只消费 report 不重新读取输入
- Service 不解释 Tool Trace 业务语义

### Public Exports

- `dayu/host/__init__.py` 正确导出所有新 Tool Trace analysis types 和函数
- `__all__` 列表完整，无遗漏

### LLM-facing 文本

- Markdown renderer 使用 `_markdown_escape` 转义控制字符
- JSON renderer 使用 `ensure_ascii=False` + `sort_keys=True` 保证 deterministic 输出
- 证据 observed 字段使用白名单投影，不含 raw payload

### Read-Only / Lock / SQLite / Input Integrity

- Cold snapshot 使用 file_lock 保护 open/fstat，锁外从同一 handle 读取精确 prefix
- Hot snapshot 使用 `open_host_durable_read_store` 物理只读模式
- Cold JSONL parser 执行 strict schema validation、digest verification、ref consistency
- Hot/cold join 按 event id 主键与 ref/digest/sequence 二次校验

### Host/Engine/Tool 诊断规则

- Host findings: input integrity、duplicate governance、context pressure
- Engine findings: provider diagnostic、protocol error、partial tool-call、runner observation mismatch
- Tool findings: failure/cancelled、repeated identical request、latency outlier、truncation/continuation
- Vendor debugging: provider/client correlation grouping with conflict detection

### Provider Identity

- Vendor debugging blocks 按 provider_request_id → client_correlation_id → event identity 优先级分组
- 同 provider id 的 client/local identity 冲突会生成 conflict finding 和 limitation
- native Anthropic/Claude Code gateway signal 正确报告为 limitation（#64 待实现）

### CLI → Service → Host

- CLI `run_tool_trace_command` → Service `analyze_and_publish_tool_trace` → Host `analyze_tool_trace`
- CLI 只处理参数映射和 stdout/stderr 投影
- Service 负责输入发现、报告发布和临时文件清理
- Host 负责输入读取、规则分析和 report 构造

### Publication

- JSON 和 Markdown 按固定顺序逐文件原子替换（os.replace）
- 双文件不构成事务，typed partial-publication 路径报告已发布/失败状态
- 临时文件使用 NamedTemporaryFile + prefix/suffix，失败时 best-effort cleanup

## 结论

**Verdict: pass**

PR 实现了一个结构清晰、职责收敛的 Tool Trace Analyzer。生产代码严格遵守 CLI → Service → Host 分层架构，contracts 集中定义，语义所有权明确。Read-only 分析器不修改 Host durable state，cold snapshot 使用文件锁保护一致性，hot snapshot 使用物理只读 SQLite。测试 256 passed，pyright 0 errors。未发现 correctness、stability 或 architecture 层面的实质性问题。
