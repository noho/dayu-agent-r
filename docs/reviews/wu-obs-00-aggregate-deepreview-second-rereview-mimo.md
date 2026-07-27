# WU-OBS-00 Aggregate Deepreview Second Re-Review (AgentMiMo)

status=complete

work_unit=WU-OBS-00

gate=aggregate-deepreview-second-dual-rereview

verdict=pass

reviewer=AgentMiMo

implementation_base=f8d6d669e30a4110efce2910f07ff96f1a3ab556

controller_adjudication=docs/reviews/wu-obs-00-aggregate-deepreview-rereview-controller-adjudication.md

fix_artifact=docs/reviews/wu-obs-00-aggregate-deepreview-rereview-fix-codex.md

fix_controller_adjudication=docs/reviews/wu-obs-00-aggregate-deepreview-second-fix-controller-adjudication.md

## Scope

- Mode: current changes (second re-review of aggregate fix)
- Branch: work/wu-obs-00
- Base: f8d6d669
- Output file: docs/reviews/wu-obs-00-aggregate-deepreview-second-rereview-mimo.md
- Included scope: uncommitted fix diff for `dayu/service/tool_trace_analysis.py`, `tests/service/test_tool_trace_analysis.py`, `dayu/service/README.md`, `dayu/README.md`, `docs/host/issues-implementation-control.md`
- Excluded scope: frozen Host contracts/rules/schema, control_doc, 既有 review artifacts, workspace/.dayu 数据
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## CTRL-AGG-01 Closure — strict UTF-8 temp lifecycle

**verdict=closed**

独立验证路径：

1. `_write_temporary_text` (line 432-449): `NamedTemporaryFile(delete=False)` 成功后立即保存 `temporary_path = Path(temporary_file.name)` (line 441)，在 `try`/`except BaseException` 块内执行 write+flush (line 442-448)，异常时调用 `_cleanup_temporary_paths((temporary_path,))` 后 bare `raise`。

2. `_publish_report_pair` (line 376-387): temp-write phase 捕获 `BaseException`（覆盖 `UnicodeEncodeError`、`OSError`、`KeyboardInterrupt`、`SystemExit`），对已成功写入的 temp 执行 best-effort cleanup 后 bare `raise`。

3. `_cleanup_temporary_paths` (line 452-477): 对每个 path 尝试 `_unlink_temporary_file`，捕获 `FileNotFoundError`（已清理）和 `OSError`（记录 secondary detail），不抛出。

直接证据：

- `first-json` test (line 505-543): `json_text="\ud800"` 触发 `UnicodeEncodeError`，断言旧 JSON/Markdown 保持、`.tmp=0`。
- `second-markdown` test: `markdown_text="\ud800"` 同理。
- `OSError`/`KeyboardInterrupt`/`SystemExit` temp-write injection test (line 546-592): 通过 `_NamedTemporaryFileFailure` monkeypatch，断言 `raised.value is failure`、旧报告保持、`.tmp=0`。

代码走读确认：异常未被转换；`KeyboardInterrupt`/`SystemExit` 在 cleanup 后原样传播。temp path 在 `NamedTemporaryFile` 构造后立即取得，write 失败时路径可用。无 loose encoding。

与前轮 rereview-mimo 一致，无回归。

## CTRL-AGG-02 Closure — dual file non-transaction wording

**verdict=closed**

独立验证路径：

逐处核对措辞统一性：

| 位置 | 当前措辞 |
|---|---|
| module docstring (line 1-6) | "按固定顺序逐文件原子替换；两个报告文件不构成事务" |
| `ServiceToolTraceAnalysisPublishError` docstring (line 72) | "逐文件发布失败" |
| `analyze_and_publish_tool_trace` docstring (line 186) | "逐文件原子替换" |
| `_publish_report_pair` docstring (line 362) | "逐文件原子替换，双文件不构成事务" |
| `dayu/service/README.md` (line 17) | "逐文件原子替换；两个报告文件不构成事务" |
| `dayu/service/README.md` (line 43-44) | "逐文件 `os.replace` 原子替换；双文件不构成事务" |
| `dayu/README.md` (line 73) | "逐文件原子替换同一 structured report 的两个输出；双文件不构成事务" |
| `dayu/README.md` (line 90) | "逐文件原子替换；双文件不构成事务" |

所有措辞统一。public type name `ServiceToolTraceAnalysisPublishError` 未改名。replace 顺序和 partial-publication behavior 未改变。

## CTRL-RR-01 Closure — replace phase interrupt cleanup

**verdict=closed**

独立验证路径：

### Replace phase code structure (line 389-417)

```python
published_paths: list[Path] = []
pending_temporary_paths = list(temporary_paths)
target_path = json_path                    # defensive initialization
try:
    for temporary_path, target_path in (
        (json_temporary_path, json_path),
        (markdown_temporary_path, markdown_path),
    ):
        _replace_temporary_file(temporary_path, target_path)
        pending_temporary_paths.remove(temporary_path)
        published_paths.append(target_path)
except OSError as exc:                     # ① specific typed truth
    cleanup_error = _cleanup_temporary_paths(tuple(pending_temporary_paths))
    ... raise ServiceToolTraceAnalysisPublishError(...) from exc
except BaseException:                      # ② generic interrupt cleanup
    _cleanup_temporary_paths(tuple(pending_temporary_paths))
    raise
```

关键事实：

1. **完整 replace phase 在同一个 `try` 内** (line 392-399): JSON replace → pending remove → Markdown replace → pending remove。两次 replace 调用之间的 Python 控制流均被覆盖。

2. **`except OSError` 保持 typed primary/secondary truth** (line 400-414): `published_paths`、`failed_path`、`primary_publish_error`、`cleanup_error`、`temporary_paths_cleaned` 全部从同一执行路径派生。`target_path` 在循环内更新，OSError 时指向实际失败目标。

3. **`except BaseException` 只清理 pending 后 bare raise** (line 415-417): 不转换异常类型，不创建 typed error，保持原始 identity 和 traceback。

4. **第一次 replace 中断**: pending 包含两个 temp（JSON temp + Markdown temp）。旧 JSON/Markdown 均保持。

5. **第二次 replace 中断**: JSON 已 replace 并从 pending 移除，pending 仅含 Markdown temp。新 JSON 保持，旧 Markdown 保持。

直接证据：

- `test_first_replace_interruption_keeps_old_reports_and_cleans_all_temps` (line 636-674): `_ReplaceInterruption(fail_call=1)` 注入 `KeyboardInterrupt`/`SystemExit`，断言 `raised.value is failure`、旧 JSON=`old-json`、旧 Markdown=`old-markdown`、`.tmp=0`。

- `test_second_replace_interruption_keeps_new_json_and_old_markdown` (line 677-716): `_ReplaceInterruption(fail_call=2)` 注入中断，断言 `raised.value is failure`、新 JSON=`new-json`（已发布未回滚）、旧 Markdown=`old-markdown`、`.tmp=0`。

### OSError typed truth non-regression

- `test_first_replace_failure_keeps_old_reports_and_publishes_nothing` (line 595-632): 第一次 replace `OSError` → `published_paths=()`、`failed_path=json_path`、`cleanup_error=None`、`temporary_paths_cleaned=True`。
- `test_second_replace_failure_keeps_new_json_and_existing_markdown_state` (line 719-762): 第二次 replace `OSError` → `published_paths=(json_path,)`、`failed_path=markdown_path`。
- `test_cleanup_secondary_failure_does_not_change_primary_publication_truth` (line 765-821): cleanup 失败时 primary/secondary truth 不漂移。

所有既有和新增 owner tests 在 focused suite 中通过（19 passed）。

## Adversarial Failure Pass

逐项检查：

1. **BaseException catch 安全性**: `_write_temporary_text` 和 `_publish_report_pair` 的 `except BaseException` 在 cleanup 后 bare `raise`，不转换异常类型。`_cleanup_temporary_paths` 内部捕获 `FileNotFoundError` 和 `OSError`，对 `KeyboardInterrupt`/`SystemExit` 不捕获（它们不从 `OSError` 派生），因此 cleanup 期间极端罕见的中断会传播但不掩盖 primary typed error 路径——该路径仅通过 `except OSError` 进入。

2. **temp path 可用性**: `temporary_path = Path(temporary_file.name)` 在 `NamedTemporaryFile` 构造后立即执行（line 441），早于 `write`/`flush`（line 444-445），因此 write 失败时路径已可用。

3. **context manager + delete=False**: `NamedTemporaryFile(delete=False)` 的 context manager exit 只关闭文件句柄，不删除文件，因此 `except BaseException` 的 cleanup 路径正确。

4. **KeyboardInterrupt/SystemExit 传播**: `except BaseException` 捕获后 cleanup 再 bare `raise`，保持原始异常实例和 traceback。测试以 `raised.value is failure` 断言 identity。

5. **无 loose encoding 修复**: 未引入 `errors="ignore"`/`"replace"`/`"backslashreplace"`，`errors="strict"` 保持不变。

6. **Host/CLI semantic owner 无漂移**: 修复仅在 Service publication boundary 内，未修改 Host report schema/renderer、Analyzer rules/input、CLI behavior 或 public type name。

7. **target_path 防御初始化**: `target_path = json_path` (line 391) 在 try 外初始化，确保 OSError handler 中 `target_path` 总是有定义（即使 for 循环首次迭代的 `_replace_temporary_file` 调用前就失败——但实际上 `target_path` 在循环赋值前不会被使用，因为 `_replace_temporary_file` 必须先执行才可能失败）。

8. **Controller rejected findings 未重开**: 无新直接证据支持重开前轮被驳回 findings。

## Verification Commands 与结果

```bash
# Focused owner tests
source .venv/bin/activate
pytest -q tests/service/test_tool_trace_analysis.py
# 结果: 19 passed in 0.34s

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
# 结果: 241 passed, 3 warnings in 4.91s

# Targeted pyright
python -m pyright dayu/service/tool_trace_analysis.py tests/service/test_tool_trace_analysis.py
# 结果: 0 errors, 0 warnings, 0 informations

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

## Three-Item Closure Summary

| Item | Status | Evidence |
|---|---|---|
| CTRL-AGG-01 | closed | temp-write phase `except BaseException` + strict UTF-8; 前轮一致，无回归 |
| CTRL-AGG-02 | closed | 8 处措辞统一为 "逐文件原子替换" + "双文件不构成事务" |
| CTRL-RR-01 | closed | replace phase `except BaseException` 覆盖完整 try 块; 4 新 owner tests 断言 identity/final files/.tmp=0 |

## Residual Risk

- JSON/Markdown 双文件不具备跨文件事务性：accepted plan 显式 residual，由 typed partial-publication truth 与文档准确表达。
- cleanup 是 best-effort：底层文件系统拒绝 unlink 时可能留下 temp。不改变 primary failure。
- aggregate 初审中被 Controller 驳回的 findings 保持驳回。
- cleanup 期间极端罕见的 `KeyboardInterrupt` 可能传播，不进入 typed error carrier——对 best-effort cleanup 可接受。

## Open Questions

无。
