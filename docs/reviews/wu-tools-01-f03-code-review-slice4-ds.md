# Code Review

## Scope

- Mode: current changes
- Branch: wu-tools-01-f03-web-ci-smoke
- Base: main
- Output file: docs/reviews/wu-tools-01-f03-code-review-slice4-ds.md
- Included scope:
  - `utils/smoke_web_ci.py` — Slice 4 改动：external child returncode 非零优先分类、`--skip-playwright` 硬编码 local gate、`--include-playwright` 只影响 external、非法 external URL 文件返回 exit code 2、Docling blocker 停止 external
  - `tests/tools/web/test_smoke_web_ci.py` — Slice 4 新增 deterministc tests
  - `docs/reviews/wu-tools-01-f03-implementation-slice4-codex.md` — implementation artifact
- Excluded scope:
  - `dayu/tools/web/`、Host、Engine — Slice 4 未修改
  - `utils/web_ci_urls.jsonl` — Slice 4 未修改
  - `utils/diagnose_web_access.py` — Slice 4 未修改
  - `tests/README.md` — 未修改，已检查
- Sources of truth consulted:
  - `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md` Slice 4
  - `docs/host/issues-implementation-control.md` WU-TOOLS-01-F03 章节
  - `docs/host/design.md` 分层边界
  - `docs/engine/design.md` 分层边界
- Parallel review coverage: 无

## Verification Results

- `pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`
  - **35 passed** in 0.34s
- `python -m pyright dayu/ tests/ utils/`
  - **0 errors, 0 warnings, 0 informations**
- `git diff --check`
  - 无输出（无 whitespace 错误）

## Findings

### DS4-001-未修复-低-external URL 文件内容非法时校验晚于 local case 执行

- **入口/函数**: `main()` → `_execute_smoke()` → `_run_external_cases()` → `_read_external_urls()`
- **文件(行号)**: `utils/smoke_web_ci.py:1646`-`1674`（`_read_external_urls` 校验），`utils/smoke_web_ci.py:1830`-`1832`（调用点），`utils/smoke_web_ci.py:2033`-`2066`（`main` 异常捕获）
- **输入场景**: operator 显式传 `--external-url-file <path>`，文件存在但 JSONL 内容非法（例如 `{not-json`）或 URL 字段为空字符串
- **实际分支**: 参数阶段 `_options_from_namespace`（line 2018-2019）仅校验文件是否存在，不校验内容合法性。`_execute_smoke` 先调用 `_run_local_cases`（line 1938）运行 local diagnostics 子进程并生成 artifacts，然后调用 `_run_external_cases`（line 1947），后者调用 `_read_external_urls`（line 1832），此时才因 JSONL 非法抛出 `ValueError`。异常由 `main()` 的 `except (OSError, ValueError)` 捕获（line 2062），返回 exit code 2
- **预期行为**: 所有 operator input error 应在任何业务执行（包括 local diagnostics 子进程启动）之前被检测并拒绝
- **实际行为**: local HTML/PDF diagnostics 子进程已运行，local artifacts 已写入 `output_dir/diagnostics/local/`，但 `_write_summary` 从未执行，`output_dir/summary.json` 不存在。operator 需要在修复输入后重新运行，local diagnostics 会再次执行
- **直接证据**: 
  - `_options_from_namespace` line 2018-2019 只做 `is_file()` 检查，不解析 JSONL 内容
  - `_execute_smoke` line 1938 的 `_run_local_cases` 在 line 1947 的 `_run_external_cases`（内含 `_read_external_urls`）之前执行
  - 测试 `test_invalid_external_file_returns_operator_input_error`（test_smoke_web_ci.py:768-827）证明此行为：fake_runner 能处理 local URL，但最终 `assert not (output_dir / "summary.json").exists()` 确认无 summary
- **影响**: 局部 artifacts 残留但不产生错误的系统状态；operator 需要重新运行；实际用户感知为输入参数校验时序瑕疵
- **建议改法和验证点**: 在 `_options_from_namespace` 中，当 `external_url_file is not None` 且 `is_file()` 通过后，对 JSONL 文件调用 `_read_external_urls` 做 dry-run 内容校验（或新增轻量 `_validate_external_url_file` 函数，仅做格式校验不返回 URL 列表）。注意：如果内容校验放在 `_options_from_namespace`，需要处理 `_read_external_urls` 的 `limit=options.external_limit` 依赖——方案可以是先以 `limit=1` 校验第一行格式，或抽象一个纯格式校验函数不依赖 limit。验证点：测试传入非法 JSONL 文件时，确认 local cases 未运行、无 artifacts 生成、exit code 2
- **修复风险（低）**: 变更仅影响参数校验的调用时序，不改变分类逻辑或 exit code 语义；需确保 dry-run 校验不产生副作用（如创建输出目录）
- **严重程度（低）**: exit code 2 语义正确，无数据损坏或错误状态传播；仅 UX 瑕疵——operator 看到一条 error message 但磁盘上已有部分 artifacts

## Open Questions

- 无。

## Residual Risk

- Slice 4 没有运行真实外部 URL live diagnostics，所有 external 路径仅通过 synthetic payload 测试。真实站点的 anti-bot challenge、网络波动、provider/browser gap 行为仍只进入 `diagnostic_only`，符合 plan 预期。
- `_classify_loaded_artifact` 中的 external + child_returncode != 0 检查（line 1088-1089）在 `_classify_child_result` 的正常调用路径下为防御性死代码，当前不产生行为错误，但若未来 `_classify_loaded_artifact` 被独立调用，需确认该路径有对应测试。
- `utils/web_ci_urls.jsonl` 未修改（`git diff` 确认无变更）。合理：Slice 4 不要求给 URL 添加 metadata，external 采样只通过 `--external-url-file` + `--external-limit` 控制。

## Conclusion

**pass-with-fixes**：一个低严重度 finding（DS4-001）建议修正——将非法 JSONL 内容校验提前到参数阶段，避免执行 local cases 后才报告 operator input error。其余 5 项挑战全部通过：外部默认不运行、`--include-playwright` 只影响 external diagnostic-only、external 所有失败路径不覆盖 local pass、不存在文件返回 exit code 2、测试 deterministic 无真实网络、类型签名无 Any/object、无魔法数字扩散。pyright 0 errors，35 tests passed，`git diff --check` clean。
