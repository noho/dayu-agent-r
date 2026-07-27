# WU-OBS-00 Aggregate Deepreview Second Re-Review — AgentDS

## Scope

- Mode: current changes (aggregate fix re-review)
- Branch: `work/wu-obs-00`
- Base: `f8d6d669` (implementation base, HEAD)
- Reviewer: AgentDS (Claude Code reviewer, independent of AgentMiMo)
- Output file: `docs/reviews/wu-obs-00-aggregate-deepreview-second-rereview-ds.md`
- Included scope:
  - `dayu/service/tool_trace_analysis.py` — complete uncommitted diff
  - `tests/service/test_tool_trace_analysis.py` — complete uncommitted diff
  - Controller adjudication chain: `rereview-controller-adjudication → rereview-fix-codex → second-fix-controller-adjudication`
  - Accepted plan §10.3 (output publication and exit codes)
- Excluded scope:
  - `dayu/README.md`, `dayu/service/README.md` — pre-existing dirty, not part of this fix
  - `docs/host/issues-implementation-control.md` — pre-existing dirty, not part of this fix
  - All other review artifacts — read-only reference, not in review scope
- Parallel review coverage: 无（本 Agent 独立走读全部相关路径）

## Verdict

**verdict=pass**

CTRL-AGG-01（strict UTF-8 temp-write）、CTRL-AGG-02（双文件非事务措辞）、CTRL-RR-01（replace phase 中断泄漏 pending temp）三项全部关闭，无回归，无新 actionable finding。

## 三项 Closure 独立确认

### CTRL-AGG-01 — strict UTF-8 temp-write path

`_write_temporary_text`（`tool_trace_analysis.py:420-449`）使用 `NamedTemporaryFile(encoding="utf-8", errors="strict")` 创建临时文件，`except BaseException` handler（line 446）在任意异常逃逸前调用 `_cleanup_temporary_paths((temporary_path,))` 清理当前 temp，随后 bare `raise` 原样传播。`test_strict_utf8_temp_failure_keeps_old_reports_and_leaks_no_temp` 覆盖了 first/second position 的 `UnicodeEncodeError` 路径，断言旧报告不变且 `.tmp=0`。

**状态：closed，无回归。**

### CTRL-AGG-02 — 双文件非事务措辞

`_publish_report_pair` docstring（line 362）写明"按 JSON 后 Markdown 顺序逐文件原子替换，双文件不构成事务"。`analyze_and_publish_tool_trace` docstring（line 188）写明"按固定顺序逐文件原子替换同源 JSON/Markdown"。`ServiceToolTraceAnalysisPublishError` docstring（line 72-85）的 `published_paths` 与 `failed_path` 字段说明准确反映双文件非事务语义。没有在任何 public docstring、异常消息或 LLM-facing text 中将双文件描述为事务。

**状态：closed，无回归。**

### CTRL-RR-01 — replace phase 中断泄漏 pending temp

这是本 gate 的核心 closure，按以下维度逐项确认：

#### replace phase try 边界（lines 391-417）

```python
target_path = json_path
try:
    for temporary_path, target_path in (
        (json_temporary_path, json_path),
        (markdown_temporary_path, markdown_path),
    ):
        _replace_temporary_file(temporary_path, target_path)
        pending_temporary_paths.remove(temporary_path)
        published_paths.append(target_path)
except OSError as exc:
    cleanup_error = _cleanup_temporary_paths(tuple(pending_temporary_paths))
    ...
    raise ServiceToolTraceAnalysisPublishError(...) from exc
except BaseException:
    _cleanup_temporary_paths(tuple(pending_temporary_paths))
    raise
```

- 完整 JSON→Markdown 逐文件 replace 循环及两次 replace 之间的 Python 控制流均在同一个 `try` 内。
- `except OSError`（line 400）保留 typed `published_paths` / `failed_path` / `primary_publish_error` / `cleanup_error` / `temporary_paths_cleaned` 完整 primary/secondary truth。
- `except BaseException`（line 415）只调用 `_cleanup_temporary_paths(tuple(pending_temporary_paths))` 后 bare `raise`，不转换异常类型、不丢弃 traceback、不覆盖已发布的报告文件。

#### 第一次 replace 中断（first replace 前）

`test_first_replace_interruption_keeps_old_reports_and_cleans_all_temps`（test file lines 635-674）参数化 `KeyboardInterrupt` / `SystemExit`：

- `raised.value is failure` — 异常 identity 原样传播 ✅
- `json_path == "old-json"` — 旧 JSON 未改写 ✅
- `markdown_path == "old-markdown"` — 旧 Markdown 未改写 ✅
- `_temporary_reports(output_dir) == ()` — 两个 pending temp 均被清理 ✅

#### 第二次 replace 中断（Markdown replace 前）

`test_second_replace_interruption_keeps_new_json_and_old_markdown`（test file lines 677-716）参数化 `KeyboardInterrupt` / `SystemExit`：

- `raised.value is failure` — 异常 identity 原样传播 ✅
- `json_path == "new-json"` — 新 JSON 已成功发布且未回滚 ✅
- `markdown_path == "old-markdown"` — 旧 Markdown 保持 ✅
- `_temporary_reports(output_dir) == ()` — 只清理 pending Markdown temp（JSON temp 在第一次 replace 成功后已从 pending 移除）✅

#### OSError typed primary/secondary truth 非回归

- `except OSError` 仍在 `except BaseException` 之前（line 400 vs 415），不会被 `BaseException` 拦截。
- `test_first_replace_failure_keeps_old_reports_and_publishes_nothing` — first replace OSError：`published_paths=()` / `failed_path=json_path` / `cleanup_error=None` ✅
- `test_second_replace_failure_keeps_new_json_and_existing_markdown_state` — second replace OSError：`published_paths=(json_path,)` / `failed_path=markdown_path` / `cleanup_error=None` ✅
- `test_cleanup_secondary_failure_does_not_change_primary_publication_truth` — cleanup secondary failure 不覆盖 primary target 与 published_paths ✅

#### temp-write phase 已有保护（前轮 CTRL-AGG-01 范畴，确认无回归）

- `_write_temporary_text` 内部 `except BaseException` + bare `raise`（lines 446-448）仍覆盖单文件 temp write 中断。
- `_publish_report_pair` temp-write phase handler（lines 385-387）覆盖双文件 temp write 阶段的 pending 聚合清理。
- `test_second_temp_write_failure_propagates_and_cleans_all_temps` 参数化 `OSError` / `KeyboardInterrupt` / `SystemExit`，覆盖 second temp write 失败时的全部 temp 清理 + 异常 identity。

**状态：closed，无回归。**

## Findings

未发现实质性问题。

## Adversarial Failure Pass

对以下场景做独立走读，未发现新 defect：

| 场景 | 处置 | 结论 |
|------|------|------|
| `KeyboardInterrupt` 在 `os.replace` syscall 期间到达 | Python 在 syscall 返回后检查信号；`os.replace` 在 POSIX 上为原子操作，完成或失败后才返回 Python 控制流 | 无 defect |
| `KeyboardInterrupt` 在 `pending_temporary_paths.remove()` 与 `published_paths.append()` 之间到达 | 两个操作之间仅一条 bytecode；异常由 `except BaseException` 捕获并清理剩余 pending temp，已替换的 temp 不再是临时文件故无需清理 | 无 defect |
| 中断发生在 `_cleanup_temporary_paths` 内部的 `_unlink_temporary_file` | `_cleanup_temporary_paths` 只捕获 `FileNotFoundError` 与 `OSError`；`KeyboardInterrupt` 会逃逸，中断 cleanup 但保留原始异常 identity | 已知 accepted 行为；Controller 在前轮已确认这是 acceptable residual risk |
| 执行 cleanup 时 `str(exc)` 本身抛出异常 | `_bounded_error_summary` 在 cleanup 路径中被调用；若 `str(exc)` 失败会掩盖原始异常。但 Python 内置异常的 `__str__` 极端可靠，且 `_bounded_error_summary` 有 `.replace` 防御空字符串 | 理论风险极低，无 evidence 需 report |
| `NamedTemporaryFile` 构造成功但 `Path(temporary_file.name)` 失败 | `temporary_file.name` 是构造器设置的 `str` 属性，`Path()` 构造不涉及 I/O | 不可行 |
| 空 `json_text` / `markdown_text` | 写入空文件后 `os.replace` 到最终路径 → 空报告覆盖旧报告 | 行为正确；空报告仍为有效报告 |
| 输出目录路径含 symlink 或特殊字符 | `_absolute_normalized_path` 使用 `os.path.normpath` + `os.path.abspath` 归一化；`NamedTemporaryFile(dir=output_dir)` 使用已解析路径 | 行为正确 |
| 磁盘满（ENOSPC）在 temp write 或 `os.replace` 期间 | `OSError` → temp-write phase handler 清理 / replace phase `except OSError` 产生 typed publication error | 行为正确 |
| temp-write phase handler 与 `_write_temporary_text` 内部 handler 对同一 temp 的双重清理 | `_cleanup_temporary_paths` 在 `FileNotFoundError` 上 `continue`（line 466-467），第二次 unlink 为 no-op | 无 defect |
| `except BaseException` 捕获 `MemoryError` / `RecursionError` 等非正常异常 | cleanup 仍为 best-effort，bare `raise` 保留原始异常语义 | 行为正确；不转换 catastrophic 异常类型 |

## Open Questions

无。

## Residual Risk

- 两个报告文件不构成跨文件事务；第二次 replace 前中断保留新 JSON 与旧 Markdown。此为 accepted plan §10.3 明确保留的行为，不是未修复 defect。
- cleanup 为 best-effort；若 `_cleanup_temporary_paths` 执行期间收到第二个 `KeyboardInterrupt`，部分 pending temp 可能残留。Controller 在前轮已裁决这是 acceptable residual risk — 优先保留原始异常 identity。
- `_bounded_error_summary` 行 467（`except FileNotFoundError: continue`）未被 branch coverage 覆盖；该分支仅在 `_write_temporary_text` 内部 handler 与 `_publish_report_pair` temp-write handler 双重清理同一 temp 时触发。这是 edge-case 路径，不构成 behavior gap。
- 未执行真实 OS 信号投递（SIGINT）、磁盘满或权限故障等破坏性环境测试；owner-level deterministic failure injection 覆盖了要求的控制流、文件内容与 temp lifecycle contract。

## Verification Results

- **focused tests**: `19 passed in 0.35s` ✅
- **affected matrix** (10 files): `241 passed, 3 warnings in 4.84s` ✅（3 warnings 均为 edgar 第三方 deprecation）
- **targeted pyright**: `0 errors, 0 warnings, 0 informations` ✅
- **full pyright** (`dayu/ tests/ utils/`): `0 errors, 0 warnings, 0 informations` ✅
- **branch coverage** (`tool_trace_analysis.py`): `92%` (Stmts=166, Miss=10, Branch=28, BrPart=6) ✅（高于 80% 目标）
- **git diff --check**: pass ✅
- **HEAD**: `f8d6d669`，无 commit ✅
