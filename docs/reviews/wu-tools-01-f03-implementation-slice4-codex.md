# WU-TOOLS-01-F03 Slice 4 Implementation - AgentCodex

## 范围判断

- Slice 2/3 已经提供 external summary contract、external case 运行入口、`--external-limit` 采样上限和 diagnostic-only 分类，Slice 4 的动机真实存在但缺口较窄。
- 本轮没有修改 `dayu/tools/web`、Host 或 Engine；只修正 smoke 脚本自身的 gate/diagnostic 边界，并补 deterministic tests。

## 改动

- `utils/smoke_web_ci.py`
  - external diagnostics 子进程非零退出码现在优先分类为 `child_process_error` diagnostic-only，不再被 artifact missing/parse 状态掩盖，也不会贡献 local gate exit code。
  - local HTML/PDF gate 命令始终传 `--skip-playwright`。
  - `--include-playwright` 只影响 external diagnostic-only 命令；external 默认仍传 `--skip-playwright`。
  - 显式传入不存在的 `--external-url-file` 时，在参数阶段返回 operator input error exit code `2`。
- `tests/tools/web/test_smoke_web_ci.py`
  - 覆盖 external child returncode 非 0 不覆盖 local pass。
  - 覆盖 external artifact parse failure 与 artifact missing 不覆盖 local pass。
  - 覆盖 `--include-playwright` 只影响 external diagnostic-only，并保留 `playwright_challenge_detected` diagnostic-only bucket。
  - 覆盖不存在或非法 external URL 文件返回 exit code `2`。
  - 既有 `external-limit` 测试继续覆盖只取小样本，不默认跑全量 corpus。

## 验证结果

- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py -q`
  - 通过：`15 passed`
- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`
  - 通过：`35 passed`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：`0 errors, 0 warnings, 0 informations`
  - pyright 输出包含版本提示：`v1.1.409 -> v1.1.410`。
- `git diff --check`
  - 通过：无输出。

## README 判断

- 本次触及 `tests/`，已检查 `tests/README.md`。
- `tests/README.md` 已声明 `tests/tools/web/` 的 Web provider 测试必须保持 deterministic，通过 monkeypatch / fixture 替身控制，不做 live network 请求。
- 本轮只在既有 Web smoke 测试层内补 external diagnostic-only 场景，不新增测试层级、运行方式或 README 读者需要的新维护规则，因此不更新 README。

## 残余风险

- 本轮按 Slice 4 要求验证 deterministic tests、pyright 和 diff check；未运行真实外部 URL live diagnostics。
- external URL 的真实失败、anti-bot、Playwright challenge、网络波动和 provider/browser gap 仍只进入 `external_cases` / `diagnostic_only`，不作为 local gate regression。
- 默认 `--external-limit=0` 保持不运行外部样本；operator 若希望采样外部 URL，必须显式传 `--external-url-file` 和正数 `--external-limit`。
