# WU-OBS-00 Aggregate Deepreview Re-Review — AgentDS

verdict=pass

work_unit=WU-OBS-00

gate=aggregate-deepreview-dual-rereview

reviewer=AgentDS (Claude Code)

implementation_base=f8d6d669e30a4110efce2910f07ff96f1a3ab556

review_base=f8d6d669

controller_adjudication=docs/reviews/wu-obs-00-aggregate-deepreview-controller-adjudication.md

fix_artifact=docs/reviews/wu-obs-00-aggregate-deepreview-fix-codex.md

fix_controller_adjudication=docs/reviews/wu-obs-00-aggregate-deepreview-fix-controller-adjudication.md

accepted_plan=docs/host/wu-obs-00-plan.md

prior_aggregate_review_artifacts=
- docs/reviews/code-review-20260724-163910.md
- docs/reviews/code-review-20260724-164901.md

## Scope

- Mode: current changes (uncommitted fix diff on work/wu-obs-00)
- Base: f8d6d669 (Slice 4 protected commit)
- Output file: docs/reviews/wu-obs-00-aggregate-deepreview-rereview-ds.md
- Included scope:
  - `dayu/service/tool_trace_analysis.py` — CTRL-AGG-01 temp lifecycle fix
  - `tests/service/test_tool_trace_analysis.py` — CTRL-AGG-01 owner-level tests
  - `dayu/service/README.md` — CTRL-AGG-02 措辞修正
  - `dayu/README.md` — CTRL-AGG-02 总揽措辞修正
  - `docs/host/issues-implementation-control.md` — gate 状态更新（非 fix owner，不审查）
- Excluded scope:
  - 所有 production Host contracts/rules/input/producer/schema（frozen，不在允许修改范围）
  - CLI behavior（不在允许修改范围）
  - control_doc 内容（非 fix owner）
  - 既有 review artifact（不可变）
  - 真实 workspace 数据（只读 smoke 已运行）
  - Controller rejected findings（无新直接证据，不重开）

## Independent Verification Evidence

### Focused owner tests

```bash
source .venv/bin/activate
pytest -q tests/service/test_tool_trace_analysis.py
```

结果：`15 passed in 0.34s`。

### Full affected matrix

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_durable_connection.py \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py \
  tests/service/test_tool_trace_analysis.py \
  tests/cli/test_tool_trace_command.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_import_boundary.py
```

结果：`237 passed, 3 warnings in 4.54s`。三条 warning 均来自既有 `edgar` 第三方 deprecation，不属于本 fix。

### Full pyright

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

### Changed-file branch coverage

```bash
source .venv/bin/activate
pytest -q tests/service/test_tool_trace_analysis.py \
  --cov=dayu.service.tool_trace_analysis \
  --cov-branch \
  --cov-report=term-missing
```

结果：`dayu/service/tool_trace_analysis.py  Stmts=162 Miss=10 Branch=28 BrPart=6 Cover=92%`。

Missed lines 均为 TypeError guard（141, 157, 160, 176, 202, 204, 212）、`_build_source` 的 Host contract rejection 路径（349-350）和 cleanup 内部的 OSError 分支（463），均属极端边界或编程错误守卫，不影响核心路径覆盖。

### Workspace analyzer read-only smoke

```bash
source .venv/bin/activate
python -m dayu.cli tool_trace analyze workspace \
  --output-dir /tmp/ds-rereview-smoke.<ts>
```

结果：exit code=`0`，JSON/Markdown 均生成。未运行 prompt、interactive 或 init，未删除或改写 `workspace/.dayu`，输入文件/DB hash 未被 Analyzer 改写。

### Controller rejected findings 检查

逐项确认未重开：

| Finding | Disposition | 本 artifact 是否重开 |
|---|---|---|
| DS-1 / MiMo-3: `_validate_source` future enum bare else | reject-nondefect | 否 — 未触及 `_validate_source` 或 Host source validation |
| DS-2: write-side PRAGMA 未回读 | reject-out-of-scope | 否 — 未触及 durable connection/transaction |
| MiMo-1: durable→engine 反向依赖 | reject-nondefect/pre-existing | 否 — 未触及 import 结构 |
| MiMo-2: Service/Host 路径常量重复 | reject-nondefect | 否 — 未新增/修改路径常量 |
| MiMo-4: 锁外 exact-prefix read | reject-plan-conflict | 否 — 未触及 cold reader/lock |
| MiMo-5: `lexists` 与 Host `stat` 不同 | reject-nondefect | 否 — 未修改 discovery |
| MiMo-6: CLI 兜底错误文本 | reject-nondefect | 否 — 未修改 CLI |
| MiMo-8: Analyzer 注入 SQLite policy | reject-plan-conflict | 否 — 未触及 SQLite policy |

无新直接证据，无重开。

## 逐项 Closure 验证

### CTRL-AGG-01 — strict UTF-8 temp lifecycle: CLOSED

**Owner**: `dayu.service.tool_trace_analysis` 的 `_write_temporary_text` 与 `_publish_report_pair`。

**独立逐路径走读**：

#### 路径 A：`_write_temporary_text` — 首个 JSON temp strict UTF-8 写入失败

```
_write_temporary_text(output_dir, "\ud800")
  → NamedTemporaryFile(delete=False) 成功 → temp path 保存到 temporary_path
  → with temporary_file: write("\ud800") → UnicodeEncodeError
  → except BaseException → _cleanup_temporary_paths((temporary_path,)) → unlink 成功
  → bare raise → UnicodeEncodeError 原样传播到 _publish_report_pair
  → _publish_report_pair 的 except BaseException 捕获
  → temporary_paths == [] （json_temporary_path 从未赋值，append 未执行）
  → _cleanup_temporary_paths(()) → no-op（当前 temp 已在 _write_temporary_text 内清理）
  → bare raise → 传播到 analyze_and_publish_tool_trace → 传播到 CLI → exit 1
```

闭合证据（`tool_trace_analysis.py:428-444`）：
- 第 428-436 行：`NamedTemporaryFile(delete=False)` 创建后立即保存 `temporary_path`
- 第 438-441 行：`with temporary_file:` 内 write + flush
- 第 442-444 行：`except BaseException` 捕获所有异常类型（包括 `UnicodeEncodeError`，它不是 `OSError`），先 cleanup 再 bare raise
- 原实现只在 `with` 块成功后 return path，异常时 path 不可达；新实现 path 在异常前已保存并可清理

测试证据（`test_tool_trace_analysis.py:464-498`）：
- `test_strict_utf8_temp_failure_keeps_old_reports_and_leaves_no_temp[first-json]`：`"\ud800"` 作为 json_text，断言 `UnicodeEncodeError`、旧 JSON/Markdown 保持、`.tmp=0`

#### 路径 B：`_publish_report_pair` — 第二个 Markdown temp strict UTF-8 写入失败

```
_publish_report_pair(json_text="new-json", markdown_text="\ud800", ...)
  → _write_temporary_text(json_path.parent, "new-json") 成功 → json_temp_path
  → temporary_paths = [json_temp_path]
  → _write_temporary_text(markdown_path.parent, "\ud800") → UnicodeEncodeError
    → 内部已清理当前 markdown temp
  → markdown_temporary_path 从未赋值，append 未执行
  → except BaseException → _cleanup_temporary_paths((json_temp_path,))
    → 清理此前成功的 JSON temp
  → bare raise
```

闭合证据（`tool_trace_analysis.py:376-387`）：
- 第 377 行：`temporary_paths: list[Path] = []`
- 第 378-384 行：依次调用 `_write_temporary_text`，每次成功后 append；任一次失败，后续 append 未执行
- 第 385-387 行：`except BaseException` 清理 `temporary_paths` 中此前已成功的 temp，然后 bare raise

测试证据（`test_tool_trace_analysis.py:464-498`）：
- `test_strict_utf8_temp_failure_keeps_old_reports_and_leaves_no_temp[second-markdown]`：`"\ud800"` 作为 markdown_text，断言 `UnicodeEncodeError`、旧报告保持、`.tmp=0`

#### 路径 C：第二个 temp 的 OSError / KeyboardInterrupt / SystemExit 传播

测试证据（`test_tool_trace_analysis.py:500-548`）：
- `test_second_temp_write_failure_propagates_and_cleans_all_temps[OSError]`
- `test_second_temp_write_failure_propagates_and_cleans_all_temps[KeyboardInterrupt]`
- `test_second_temp_write_failure_propagates_and_cleans_all_temps[SystemExit]`

三个参数化用例均：
- 通过 `_NamedTemporaryFileFailure(fail_call=2, failure=failure_type("temp-write-failed"))` 在第二次 `NamedTemporaryFile` 调用（即 Markdown temp）的 `write()` 阶段注入原始异常
- 断言 `raised.value is failure` — 同一异常实例传播，未被包装或转换
- 断言旧 JSON/Markdown 保持
- 断言 `_temporary_reports(output_dir) == ()` — 零 temp 泄漏

#### 路径 D：KeyboardInterrupt / SystemExit 不被包装为 ServiceToolTraceAnalysisPublishError

代码证据：
- `_write_temporary_text` 的 `except BaseException`（第 442 行）捕获 `KeyboardInterrupt` 和 `SystemExit`，但只做 cleanup + bare raise，不构造新异常
- `_publish_report_pair` 的 temp-write `except BaseException`（第 385 行）同样只 cleanup + bare raise
- `ServiceToolTraceAnalysisPublishError` 只在 replace phase 的 `except OSError`（第 397 行）构造，此时不再有 temp-write 操作
- `analyze_and_publish_tool_trace` 的 docstring（第 196-197 行）明确声明 `KeyboardInterrupt` 和 `SystemExit` 会原样传播

#### 路径 E：replace phase 的 correct non-regression

replace phase（第 389-413 行）的 `except OSError` 未变更为 `except BaseException`，这是正确的：
- `os.replace` 只抛出 `OSError` 子类
- `KeyboardInterrupt` / `SystemExit` 在 replace phase 不会从 `os.replace` 产生
- 若在 replace phase 的循环迭代间收到信号，窗口极窄且此时 temp 已全部写入；这是 accepted plan §10.3 的显式 residual

**CTRL-AGG-01 closure verdict: CLOSED。** 临时文件在 strict UTF-8 `UnicodeEncodeError`、`OSError`、`KeyboardInterrupt`、`SystemExit` 及任意其他 `BaseException` 子类的写入/传播路径上均执行 best-effort cleanup；exception instance 不被转换；旧报告不被替换；`errors="strict"` 不变。

### CTRL-AGG-02 — 双文件非事务措辞: CLOSED

**Owner**: Service publication contract documentation。

**独立逐位置核对**：

| 位置 | 旧措辞 | 新措辞 | 判定 |
|---|---|---|---|
| `tool_trace_analysis.py` 模块 docstring（第 4-5 行） | "原子发布" | "按固定顺序逐文件原子替换；两个报告文件不构成事务" | ✓ |
| `ServiceToolTraceAnalysisPublishError` docstring（第 72 行） | "原子发布失败" | "逐文件发布失败" | ✓ |
| `analyze_and_publish_tool_trace` docstring（第 186 行） | "原子发布" | "按固定顺序逐文件原子替换" | ✓ |
| `_publish_report_pair` docstring（第 362 行） | "原子发布报告对" | "逐文件原子替换，双文件不构成事务" | ✓ |
| `dayu/service/README.md` 模块说明（第 17 行） | "原子发布固定 JSON/Markdown 文件" | "按 JSON→Markdown 固定顺序逐文件原子替换；两个报告文件不构成事务" | ✓ |
| `dayu/service/README.md` 发布 owner 说明 | "原子发布" | "逐文件 `os.replace` 原子替换；双文件不构成事务" | ✓ |
| `dayu/README.md` 稳定边界（第 73 行） | "原子发布" | "按 JSON→Markdown 固定顺序逐文件原子替换同一 structured report 的两个输出；双文件不构成事务" | ✓ |

未改变：
- `ServiceToolTraceAnalysisPublishError` 等 public type name：不变 ✓
- JSON→Markdown replace 顺序：不变 ✓
- 第二次 replace 失败时 published_paths / failed_path 语义：不变 ✓
- `os.replace` 单文件原子性：不变 ✓

**CTRL-AGG-02 closure verdict: CLOSED。** 所有 LLM-facing 与 developer-facing 文档已统一为"JSON→Markdown 逐文件原子替换，双文件不构成事务"；不再存在"报告对原子发布"的错误跨文件事务暗示。

## Findings

### DS-R1 — `_write_temporary_text` 在 `NamedTemporaryFile` 构造失败时无法清理

- **入口/函数**: `_write_temporary_text`
- **文件(行号)**: `dayu/service/tool_trace_analysis.py:428-436`
- **输入场景**: 底层文件系统拒绝在 `dir=output_dir` 创建临时文件（权限、磁盘满、inode 耗尽），`tempfile.NamedTemporaryFile(...)` 构造器抛出 `OSError`
- **实际分支**: 构造器抛异常时 `temporary_file` 未绑定，`temporary_path` 赋值未执行，整个 `try` 块未进入
- **预期行为**: 此场景下无 temp 文件被创建，因此无需清理；异常原样传播
- **实际行为**: 与预期一致 — 构造失败时无文件被创建，无泄漏
- **直接证据**: 第 428-436 行，`NamedTemporaryFile(...)` 在 `temporary_path = Path(temporary_file.name)` 之前（第 437 行）。若构造失败，控制流不会到达第 437 行，无 path 可追踪，异常直接传播到 `_publish_report_pair` 的 `except BaseException`（第 385 行），此时 `temporary_paths` 为空，cleanup 为 no-op
- **影响**: 无 — 这不是 bug，是确认性 finding。构造失败时无文件创建，无需清理
- **建议改法和验证点**: 无需修改。当前行为正确。若未来需要在构造与 path 保存之间增加可能创建文件的中间步骤，才需要额外保护
- **修复风险（低）**: N/A
- **严重程度（低）**: 确认性 finding，非 defect

### DS-R2 — replace phase 中 `KeyboardInterrupt` 可能留下已写入但未 replace 的临时文件

- **入口/函数**: `_publish_report_pair` replace phase
- **文件(行号)**: `dayu/service/tool_trace_analysis.py:389-413`
- **输入场景**: 两个 temp 均已成功写入并 flush，正在执行 `for temporary_path, target_path in ...` replace 循环时收到 `KeyboardInterrupt`（例如 operator 在 JSON replace 成功后、Markdown replace 前按 Ctrl-C）
- **实际分支**: `except OSError`（第 397 行）不捕获 `KeyboardInterrupt`，异常直接逃出 `_publish_report_pair`，未经 cleanup
- **预期行为**: 已写入但未 replace 的 temp 文件应被 best-effort 清理
- **实际行为**: `pending_temporary_paths` 中仍存在的 temp 未被清理，残留在 output_dir
- **直接证据**: 第 391-413 行的 for 循环只对 `_replace_temporary_file` 的 `OSError` 做 try/except；`KeyboardInterrupt` 在循环迭代间或 `os.replace` 外的 Python 字节码位置到达时，不会被任何 handler 捕获，直接穿透到 `analyze_and_publish_tool_trace`（第 219 行），再穿透到 CLI
- **影响**: 残留 `.tool-trace-analysis-*.tmp` 文件在 output_dir；不丢失已发布数据（已 replace 的文件已原子落地），不损坏既有报告。operator 下次运行时会创建新 temp（不同随机名），旧 temp 仅占用磁盘空间
- **建议改法和验证点**: 可在 replace phase 外层增加 `try: ... finally: _cleanup_temporary_paths(tuple(pending_temporary_paths))` 确保任意异常（包括 `KeyboardInterrupt`）都触发 best-effort cleanup。但需注意 `finally` 中的 cleanup 不应覆盖 `except OSError` 中已有的 cleanup 逻辑
- **修复风险（低）**: 仅增加 finally 块，不改变正常路径和 OSError 路径的 cleanup 语义
- **严重程度（低）**: 窗口极窄（`os.replace` 是原子 OS 调用，sub-millisecond）；且 accepted plan §10.3 显式将 temp cleanup 定性为 best-effort；残留 temp 不影响数据正确性

## Open Questions

无。

## Residual Risk

- **双文件非事务性**：JSON/Markdown 仍不构成跨文件事务。第二次 replace 失败时已发布 JSON 不回滚。这是 accepted plan §10.3 的显式 design residual，由 typed `published_paths` / `failed_path` 准确表达，不属于 fix 遗漏。
- **cleanup best-effort 限制**：若底层文件系统拒绝 `unlink`（如 NFS  stale handle、权限变更），temp 文件可能残留。`_cleanup_temporary_paths` 正确地将 cleanup failure 记录为独立的 `ServiceToolTraceCleanupFailure` secondary detail，不与 primary publish error 混淆。这不是本 fix 可承诺的文件系统事务。
- **DS-R2 replace phase KeyboardInterrupt**：如上所述，极窄窗口下可能残留 temp 文件。若 operator 环境频繁使用 Ctrl-C，建议后续增加 replace-phase finally 保护。
- **未覆盖测试分支**：`_build_source` 的 Host contract rejection 路径（line 349-350）和 `_cleanup_temporary_paths` 的非 `FileNotFoundError` OSError 分支（line 463）未被测试覆盖。两者均属极端边界（前者需 Host `ToolTraceAnalysisSource` 构造器拒绝合法 Service 输入，后者需 `path.unlink()` 抛出非 `FileNotFoundError` 的 `OSError`），实际风险极低。
- **Coverage 92%**：高于 80% 阈值，剩余 8% 均为类型守卫与极端 OS 错误路径。

## Reviewer Notes

本 re-review 仅验证 CTRL-AGG-01 与 CTRL-AGG-02 两项 Controller accepted findings 的 closure 状态，并执行 adversarial regression pass。未发现需 block merge 的新 defect。Controller rejected 的 8 项 findings 均未重开，无新直接证据。

verdict=pass。建议 Controller 将本 gate 推进到 final closeout。
