# WU-OBS-00 Slice 2 Implementation

## 结论

- work unit：`WU-OBS-00`
- slice：`Slice 2`
- gate：`implementation`
- status：`complete`
- Controller implementation adjudication：`needs-fix` 已逐项修复并完成重新验证。
- accepted Slice 1：`126daa02afb87eb3ad91742198738476cc22481d`
- stop condition：未触发。Slice 2 所有规则均可从既有 typed Tool Trace、payload descriptor 与 Slice 1 trusted dataset 直接取证，不需要新增 producer/schema 字段。
- next entry point：Controller re-adjudication；本次实现不自行进入 review、commit、push、PR 或 Issue gate。

## 动机与语义 owner 核对

动机成立。Slice 1 已能把 hot SQLite、cold JSONL、payload descriptor 严格连接成可信分析数据集，但此前没有一个确定性投影把这些事实汇总为 operator 可消费的 Host/Tool/context/truncation/large-payload 诊断报告。因此问题不是 trace 数据缺失，也不是 producer/schema 能力不足，而是缺少 analyzer-owned 的规则、聚合与报告契约。

语义 owner 判定如下：

- 事件事实、调用参数、结果元数据与 Host 治理事实仍由既有 EventLog、ToolRuntime、Tool Trace producer 负责。
- hot/cold/payload 的严格解析、连接、完整性诊断与可用性判定仍由 Slice 1 trusted dataset/resolver 负责。
- Slice 2 Analyzer 只负责从可信 typed facts 计算 run/tool 聚合、finding、priority、recommendation、limitation、payload ranking 与确定性报告投影。
- Tool 名称复用 ToolRuntime 的 `FrameworkToolName` 公共契约；Analyzer 不复制框架工具名真源。
- cold JSONL 行大小只使用 Slice 1 提供的 `cold_jsonl_record_bytes`，不把它命名或解释成业务 payload 大小。

实现未从缺失字段推断业务事实，未从参数文本反推重复调用，未用 event timestamp 计算 tool latency，未引入 fallback、loose parsing、兼容 shim、producer/schema 扩张或下游补偿。

## Controller needs-fix 闭环

Controller 首次 implementation adjudication 判定为 `needs-fix`，本次仍停留在同一 Slice 2 implementation gate，完成以下 owner-boundary 修复：

- 更新 contracts 模块概览，准确说明该模块已经冻结 public source、policy 与 structured report contract。
- 扩充 contracts owner 的 `__all__`，精确包含所有 intended public report enums/dataclasses；Host root allowlist test 仍只负责 root public surface，没有扩大职责。
- 将规则内部未编号 finding 改为私有严格类型 `_FindingDraft`；规则排序并分配稳定 ID 后才构造 public `ToolTraceFinding`。
- public `ToolTraceFinding` 始终拒绝空 `finding_id`。
- `ToolTraceAnalysisInputSummary` 新增 owner-boundary validation，只校验自身可证明的 Path/mode/capabilities 类型及 hot/payload capability、hot watermark 关系，不重做 Source layout/discovery。
- `ToolTraceAnalysisReport` 新增 `summary.run_count == len(runs)` 及最终 finding ID 非空、唯一约束；未添加无法从 report 嵌套结构证明的推断性约束。
- 新增 owner-level tests，覆盖 contracts `__all__`、InputSummary invariant、public finding 空 ID、report 缺失/重复 ID 与 run count mismatch。

## 实现范围

### Production

- `dayu/host/tool_trace_analysis_contracts.py`
  - 定义最终结构化报告骨架及严格 typed contracts。
  - 冻结 layer、severity、priority、signal status、evidence kind、payload measurement source 等枚举。
  - 冻结 input、policy、summary、signal coverage、runs、payload rankings、vendor debugging、findings、limitations 顶层结构。
  - 使用 `__post_init__` 校验 owner-level 不变量，拒绝错误类型、负计数、无效 capability/watermark 关系、空/重复 finding ID 与 report summary mismatch。
  - 模块 owner `__all__` 精确导出冻结的 public contracts。
- `dayu/host/tool_trace_analysis_rules.py`
  - 实现 trusted dataset 到 deterministic report 的纯规则投影。
  - 实现 run/tool 聚合、integrity、Host、Tool、context、truncation/continuation、large-payload 规则。
  - 实现 direct evidence、优先级、建议与 limitation 的稳定生成和排序。
  - 使用私有 `_FindingDraft` 承担编号前 staging，最终 ID 分配后才构造 public finding。
  - `TOOL_AWAITING` / `RUN_WAITING` 仅进入汇总计数，不生成 finding。
  - `vendor_debugging` 在 Slice 2 固定为空列表，仅冻结最终 block shape。
- `dayu/host/tool_trace_analysis.py`
  - 编排 Slice 1 trusted dataset 构建和 Slice 2 报告生成。
  - 提供确定性 JSON 与固定章节 Markdown 渲染。
  - 输出只包含有界证据与度量，不输出 payload body。
- `dayu/host/__init__.py`
  - 导出 Slice 2 公共报告契约与 analyzer 入口。

### Tests

- `tests/host/test_tool_trace_analysis_rules.py`
  - owner-level rule matrix：input integrity、resolver limitation、Host duplicate governance、Tool repeated-identical request、failed/cancelled/policy-blocked、timing、truncation/continuation、context、compaction、payload ranking、waiting state、vendor block 与确定性排序。
- `tests/host/test_tool_trace_analysis.py`
  - orchestration、JSON/Markdown deterministic rendering、bounded evidence、无 payload body、owner exports、input/report/finding invariant 与严格契约测试。
- `tests/host/test_package_exports.py`
  - 仅更新 Host public export owner allowlist。
  - 这是 Controller 在实现过程中明确批准的唯一 test-only allowed-files 例外；没有借此扩大 production scope。

### 明确未实现

- provider/vendor-specific 诊断规则。
- native Anthropic / Claude gateway 专属归因。
- CLI、path discovery、命令参数或最终用户入口。
- producer/schema 新字段。
- payload body 输出或 exact/raw payload 复原。
- percentile-only 大 payload 告警。
- README 发布说明。

## 关键规则证据

### Trusted input 与 integrity

- hot/cold/payload 事实只消费 Slice 1 的严格连接结果。
- Slice 1 input diagnostics 投影为 Host integrity findings，并保留直接 typed evidence。
- resolver failure 不伪造 payload measurement，只产生依赖受限 limitation。
- hot-only 记录可参与有直接证据的规则；依赖 cold/payload 的规则按 capability coverage 明确受限。

### Host 与 Tool

- Host duplicate governance 与 Tool repeated-identical request 使用不同的事实 owner 与 rule identity，不相互替代。
- tool failed/cancelled 与 Host policy blocked 分开报告。
- latency 仅使用 `tool_result_meta` 的可信 duration；缺失或非法 duration 产生 limitation。
- 慢调用判断同时要求最小样本、median multiplier 与 absolute delta，避免仅凭单点或小样本误报。

### Truncation、continuation 与 context

- truncation 后的 continuation 只读取 typed `tool_request.arguments.cursor`。
- 明确区分 cursor match、没有 follow-up、错误 cursor 与 arguments unavailable。
- 框架 continuation tool 名称复用 `FrameworkToolName` owner；Analyzer 文件不复制对应字面量。
- context soft/hard limit、compaction failed 与 compaction attempt rejected 均来自直接事件事实。
- usage 只作为 post-call signal，不反推调用前 context 状态。

### Large payload

- 对 Slice 1 提供的全部 measurement category 生成排名，保留 measurement source。
- 阈值语义为 `>=`。
- cold 行度量明确标记为 `cold_jsonl_record_bytes`。
- 报告不携带 payload body，也不把 cold 行字节数解释成 payload 本体大小。

### Determinism

- findings 使用稳定 layer/rule/run/tool/evidence 排序与稳定 ID。
- report、JSON 与 Markdown 渲染在相同输入和 policy 下字节稳定。
- Markdown 只投影报告契约，不重新计算规则语义。

## 验证

所有命令均在 `source .venv/bin/activate` 后执行。

### Focused tests

命令：

```text
pytest -q tests/host/test_tool_trace_analysis_input.py tests/host/test_tool_trace_analysis_rules.py tests/host/test_tool_trace_analysis.py tests/host/test_package_exports.py::test_host_all_matches_current_public_contracts tests/host/test_import_boundary.py::test_fetch_more_token_stays_inside_toolruntime_owner_modules
```

结果：

```text
47 passed in 0.62s
```

### 相关 full Host tests

最终干净重跑：

```text
pytest -q tests/host
```

结果：

```text
2314 passed, 2 skipped, 6 deselected in 55.01s
```

首次 full Host 运行暴露三项：

- import-boundary owner token 检查：通过改为复用 `FrameworkToolName` 且移除 Analyzer 内对应字面量修复。
- Host package export owner allowlist：经 Controller 明确批准，仅修改 `tests/host/test_package_exports.py` 修复。
- 一个与本次 diff 无关的 runtime cancel-watchdog token 计数单次波动：与 import-boundary 测试隔离重跑为 `2 passed in 0.39s`，随后 full Host 干净重跑通过，未修改该 runtime 代码。

### Branch coverage

命令覆盖 focused owner tests，并启用 `--cov-branch`。修改 production 文件结果：

| 文件 | branch coverage |
|---|---:|
| `dayu/host/__init__.py` | `100%` |
| `dayu/host/tool_trace_analysis_contracts.py` | `85%` |
| `dayu/host/tool_trace_analysis_rules.py` | `89%` |
| `dayu/host/tool_trace_analysis.py` | `98%` |

全部修改 production 文件均达到 `>=80%`。

### Pyright

Targeted：

```text
python -m pyright dayu/host/tool_trace_analysis_contracts.py dayu/host/tool_trace_analysis_rules.py dayu/host/tool_trace_analysis.py dayu/host/__init__.py tests/host/test_tool_trace_analysis_rules.py tests/host/test_tool_trace_analysis.py tests/host/test_package_exports.py
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

Full：

```text
python -m pyright dayu/ tests/ utils/
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

### Workspace hygiene

- `git diff --check`：通过。
- 未 commit、未 push、未创建 PR、未修改 Issue。
- `docs/host/issues-implementation-control.md` 在开始实现前已由 Controller 修改并处于 dirty 状态；本次只读核验其 Slice 2 gate 状态，没有修改该文件。

## README 触发检查

本次修改触发了 `dayu/host/README.md` 与 `tests/README.md` 检查。两份 README 均已读取并核对：

- Slice 2 allowed files 不包含 README。
- accepted plan 把最终 CLI/用户入口与文档发布归属 Slice 4。
- 因此本次不机械修改 README；由 Slice 4 在其 owner scope 内根据最终稳定入口与操作契约统一更新。

## 风险与未覆盖项

- provider/vendor-specific rules：按 accepted plan 归属 Slice 3，不是 Slice 2 缺陷；当前报告保留最终 vendor block shape 且 `vendor_debugging=[]`。
- native Anthropic / Claude gateway 信号：仍由 Issue #64 owner 跟踪；Slice 2 不推断不存在的 adapter facts。
- CLI、真实 workspace 命令入口与用户文档：按 accepted plan 归属 Slice 4。
- file-only payload/iteration 的既有限制仍通过 limitation 显式呈现；本次未扩张 producer/schema。
- 首次 full Host 的单次 cancel-watchdog 测试波动已由隔离重跑和最终 full Host 干净通过闭环，没有证据指向 Slice 2 回归。

## 完成信号

Slice 2 requested scope、Controller needs-fix、owner-level tests、focused/full Host tests、targeted/full pyright、production branch coverage、README trigger audit 与 implementation artifact 均已完成。没有发现必须依赖 trace 缺失字段的规则，故状态为 `complete`，交回 Controller re-adjudication。
