# WU-OBS-00 Aggregate Deepreview Re-Review (AgentMiMo)

status=complete

work_unit=WU-OBS-00

gate=aggregate-deepreview-dual-rereview

verdict=pass

reviewer=AgentMiMo

implementation_base=f8d6d669e30a4110efce2910f07ff96f1a3ab556

controller_adjudication=docs/reviews/wu-obs-00-aggregate-deepreview-controller-adjudication.md

fix_artifact=docs/reviews/wu-obs-00-aggregate-deepreview-fix-codex.md

fix_controller_adjudication=docs/reviews/wu-obs-00-aggregate-deepreview-fix-controller-adjudication.md

## Scope

- Mode: current changes (re-review of aggregate fix)
- Branch: work/wu-obs-00
- Base: f8d6d669
- Output file: docs/reviews/wu-obs-00-aggregate-deepreview-rereview-mimo.md
- Included scope: uncommitted fix diff for `dayu/service/tool_trace_analysis.py`, `tests/service/test_tool_trace_analysis.py`, `dayu/service/README.md`, `dayu/README.md`, `docs/host/issues-implementation-control.md`
- Excluded scope: frozen Host contracts/rules/schema, control_doc,既有 review artifacts, workspace/.dayu 数据
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## CTRL-AGG-01 Closure — strict UTF-8 temp lifecycle

**verdict=closed**

独立验证路径：

1. `_write_temporary_text` (line 416-445): `NamedTemporaryFile(delete=False)` 成功后立即保存 `temporary_path = Path(temporary_file.name)`，在 `try`/`except BaseException` 块内执行 write+flush，异常时对当前 temp 调用 `_cleanup_temporary_paths((temporary_path,))` 后 bare `raise`。

2. `_publish_report_pair` (line 376-387): temp-write phase 捕获 `BaseException`（覆盖 `UnicodeEncodeError`、`OSError`、`KeyboardInterrupt`、`SystemExit`），对 `temporary_paths` 列表中此前已成功写入的 temp 执行 best-effort cleanup 后 bare `raise`。

3. `_cleanup_temporary_paths` (line 448-473): 对每个 path 尝试 `_unlink_temporary_file`，捕获 `FileNotFoundError`（已清理）和 `OSError`（记录 secondary detail），不抛出。

直接证据：

- `first-json` parametrized test (line 464-502): `json_text="\ud800"` 触发 `UnicodeEncodeError`，断言旧 JSON/Markdown 保持、`.tmp=0`。
- `second-markdown` parametrized test: `markdown_text="\ud800"` 同理。
- `OSError`/`KeyboardInterrupt`/`SystemExit` injection test (line 505-551): 通过 `_NamedTemporaryFileFailure` monkeypatch 在第二个 temp write 注入异常，断言同一异常实例传播（`raised.value is failure`）、旧报告保持、`.tmp=0`。

代码走读确认：异常未被转换为 `ServiceToolTraceAnalysisPublishError` 或其他类型；`KeyboardInterrupt`/`SystemExit` 不被 `except BaseException` 转为普通 failure，cleanup 后原样传播。temp path 在 `NamedTemporaryFile` 构造后立即取得，write 失败时路径可用于 cleanup。无 loose encoding、replacement character 或 `errors="ignore"`。

## CTRL-AGG-02 Closure — dual file non-transaction wording

**verdict=closed**

独立验证路径：

逐处核对措辞统一性：

| 位置 | 修改前 | 修改后 |
|---|---|---|
| module docstring (line 1-5) | "原子发布" | "按固定顺序逐文件原子替换；两个报告文件不构成事务" |
| `ServiceToolTraceAnalysisPublishError` docstring (line 72) | "原子发布失败" | "逐文件发布失败" |
| `analyze_and_publish_tool_trace` docstring (line 185-196) | "原子发布" | "逐文件原子替换" |
| `_publish_report_pair` docstring (line 362-373) | "原子发布报告对" | "逐文件原子替换，双文件不构成事务" |
| `dayu/service/README.md` (line 17, 43-46) | "原子发布" | "逐文件原子替换；双文件不构成事务" |
| `dayu/README.md` (line 73, 90) | "原子发布" | "逐文件原子替换...双文件不构成事务" |

所有措辞统一为：JSON→Markdown 固定顺序、同目录 temp + `os.replace` 单文件原子替换、双文件不构成事务。public type name `ServiceToolTraceAnalysisPublishError` 未改名。replace 顺序和第二次 replace 失败时的 partial-publication behavior 未改变。

## Adversarial Regression Pass

逐项检查：

1. **BaseException catch 安全性**: `_write_temporary_text` 和 `_publish_report_pair` 的 `except BaseException` 在 cleanup 后 bare `raise`，不转换异常类型。`_cleanup_temporary_paths` 自身不会抛出（内部捕获 `FileNotFoundError` 和 `OSError`），因此不会掩盖原始异常。

2. **temp path 可用性**: `temporary_path = Path(temporary_file.name)` 在 `NamedTemporaryFile` 构造后立即执行，早于 `write`/`flush`，因此 write 失败时路径已可用。

3. **context manager + delete=False**: `NamedTemporaryFile(delete=False)` 的 context manager exit 只关闭文件句柄，不删除文件，因此 cleanup 路径正确。

4. **KeyboardInterrupt/SystemExit 传播**: `except BaseException` 捕获后 cleanup 再 bare `raise`，保持原始异常实例和 traceback。测试以 `raised.value is failure` 断言 identity。

5. **无 loose encoding 修复**: 未引入 `errors="ignore"`/`"replace"`/`"backslashreplace"`，strict UTF-8 保持不变。

6. **Host/CLI semantic owner 无漂移**: 修复仅在 Service publication boundary 内，未修改 Host report schema/renderer、Analyzer rules/input、CLI behavior 或 public type name。

7. **issues-implementation-control.md**: 仅更新 gate status 和 next entry point，不涉及 production 语义。

8. **Controller rejected findings 未重开**: DS-1/DS-2/MiMo-1~6/MiMo-8 均未被重新引入或修改。

## Verification Commands 与结果

```bash
# Focused owner tests
source .venv/bin/activate
pytest -q tests/service/test_tool_trace_analysis.py
# 结果: 15 passed in 0.33s

# Full affected test matrix
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
# 结果: 237 passed, 3 warnings in 4.56s

# Full pyright
python -m pyright dayu/ tests/ utils/
# 结果: 0 errors, 0 warnings, 0 informations

# Workspace analyzer read-only smoke
python -m dayu.cli tool_trace analyze workspace --output-dir $(mktemp -d)
# 结果: exit 0, JSON/Markdown 非空

# Cold-file analyzer read-only smoke
python -m dayu.cli tool_trace analyze workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl --output-dir $(mktemp -d)
# 结果: exit 0, JSON/Markdown 非空
```

## Residual Risk

- JSON/Markdown 双文件不具备跨文件事务性：accepted plan 显式 residual，由 typed partial-publication truth 与文档准确表达。
- cleanup 是 best-effort：底层文件系统拒绝 unlink 时可能留下 temp。不改变 primary failure，且不是本修复可承诺的文件系统事务。
- aggregate 初审中被 Controller 驳回的 findings 保持驳回。

## Open Questions

无。
