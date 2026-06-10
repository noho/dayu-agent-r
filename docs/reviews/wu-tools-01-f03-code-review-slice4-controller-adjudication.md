# WU-TOOLS-01-F03 Slice 4 Code Review Controller Adjudication

## 输入

- Implementation artifact: `docs/reviews/wu-tools-01-f03-implementation-slice4-codex.md`
- MiMo review: `docs/reviews/wu-tools-01-f03-code-review-slice4-mimo.md`
- DS review: `docs/reviews/wu-tools-01-f03-code-review-slice4-ds.md`
- Controller validation:
  - `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` -> 35 passed
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` -> 0 errors
  - `git diff --check` -> passed

## 总体裁决

结论：`pass-with-fixes`。

Slice 4 主要目标已经满足：默认不运行外部 URL，`--external-url-file` 与 `--external-limit` 控制小样本，external child failure / artifact gap / parse failure / Playwright challenge 均保持 diagnostic-only，不产生 exit code 1，也不覆盖 local gate。

但 DS4-001 成立：外部 JSONL 文件内容非法时，当前校验发生在 `_run_external_cases()` 内，晚于 local HTML/PDF diagnostics。operator input error 应在任何 live diagnostics 执行前失败，避免留下无 summary 的部分 local artifacts。

## Required Fix

1. 将 external URL 文件内容校验提前到参数阶段。
   - 来源：DS4-001。
   - 要求：
     - 当 `--external-url-file` 指向存在但内容非法的 JSONL / URL 文件时，`main()` 应在启动 local fixture / local diagnostics 前返回 exit code `2`。
     - 对应测试应证明 runner 未被调用，并且不产生 local diagnostics artifacts / summary。
     - 不改变外部 diagnostic-only 分类逻辑；合法文件仍按 `--external-limit` 采样。
   - 推荐实现：
     - 新增私有 helper，例如 `_validate_external_url_file(path: Path) -> None`，复用 `_url_from_jsonl_line()` 的 JSONL 行校验语义，跳过空行与注释行。
     - `_options_from_namespace()` 在文件存在性校验后调用该 helper。
     - `_read_external_urls()` 仍负责按 `limit` 返回样本，避免把 `limit=0` 与内容校验耦合。

## Accepted / Deferred

- 外部文件不存在时 fail-fast 且不写 summary：accepted。它是 operator input error，不需要 local smoke 可见性。
- `_read_external_urls` / argparse help 对 `--external-limit=0` 的阅读歧义：accepted-low。当前行为正确：默认不运行外部诊断。
- 未修改 `utils/web_ci_urls.jsonl`：accepted。Slice 4 不需要为 URL corpus 添加 metadata。

## Fix Gate 验证要求

- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `git diff --check`

