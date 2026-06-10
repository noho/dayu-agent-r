# WU-TOOLS-01-F03 Slice 4 Required Fix - Codex

## 修复点

- 在 `utils/smoke_web_ci.py` 新增 `_validate_external_url_file(path: Path) -> None`，并在 `_options_from_namespace()` 的参数构造阶段、文件存在性校验后调用。
- 校验逻辑复用 `_url_from_jsonl_line()` 解析 JSONL 对象/字符串行，跳过空行和注释行；纯文本 URL 行校验为 diagnostics 可处理的 HTTP/HTTPS URL。
- `_read_external_urls()` 继续只负责按 `--external-limit` 采样，不承担全文件 dry-run 校验，避免把 `limit=0` 与内容合法性耦合。
- 更新 `tests/tools/web/test_smoke_web_ci.py`：非法 JSONL 与非法 URL 文件均断言 `main()` 返回 exit code `2`，local fixture server 未启动，diagnostics runner 未调用，且不产生 output dir、summary 或 diagnostics artifacts；合法 JSONL 文件包含空行/注释时仍按 `--external-limit` 采样。

## 验证结果

- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` -> `36 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` -> `0 errors, 0 warnings, 0 informations`
- `git diff --check` -> passed

## accepted-low 未处理项

- 未处理 `_read_external_urls` / argparse help 对 `--external-limit=0` 的阅读歧义；controller 已裁决为 accepted-low，且当前行为保持不变：默认不运行外部诊断。
