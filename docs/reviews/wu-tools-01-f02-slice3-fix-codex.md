# WU-TOOLS-01-F02 Slice 3 Fix 记录 - Codex

## Fixed findings

- MiMo F1：已从 `utils/diagnose_web_access.py` 删除未使用的 `socket` import。
- MiMo F3 / DS F1：已扩展 `tests/tools/web/test_diagnose_web_access.py` 的 deterministic comparison bucket matrix，新增显式覆盖：
  - `playwright_challenge_detected`
  - `requests_only_success`
  - `browser_only_success`
  - `requests_and_fetch_success_playwright_failed`
  - `fetch_only_failure`
  - `all_failed`
  - `partial_sample`

## Rejected findings not touched

- MiMo import-guard missing finding：未修改。当前测试已存在 `test_diagnose_web_access_does_not_import_old_web_or_ui_paths()`。
- DS `requests_only_success` condition finding：未修改。未采样的 fetch 不是失败 fetch；本 fix 未改变分类器逻辑。

## Files changed

- `utils/diagnose_web_access.py`
- `tests/tools/web/test_diagnose_web_access.py`
- `docs/reviews/wu-tools-01-f02-slice3-fix-codex.md`

未修改 `docs/host/issues-implementation-control.md`。

## Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q`
  - 通过：`23 passed in 0.36s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：`0 errors, 0 warnings, 0 informations`
- `bash -n utils/diag_web.sh utils/diag_web_batch.sh`
  - 通过
- `git diff --check`
  - 通过
- Targeted forbidden import/type scan:
  - 严格扫描命令：`rg -n "^\s*(import|from)\s+(dayu\.engine\.tool_registry|dayu\.engine\.truncation_manager|dayu\.engine\.tools|dayu\.web|dayu\.ui)|\bAny\b|:\s*object\b|->\s*object\b|\bdict\[str,\s*object\]|\bMapping\[str,\s*object\]|\bSequence\[object\]" utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py`
  - 通过：无实际禁用 import 行，无 `Any` / `object` 宽类型签名命中。
  - literal scan 仅命中测试 guard 字面量与 tool schema `"object"` 字符串，未命中实际 forbidden imports。

## README decision

已检查 `tests/README.md`。本 fix 只在既有 `tests/tools/web/` deterministic 测试文件内补矩阵 case，没有新增测试层级、运行命令或维护约定；现有 README 已明确 Web provider tests 必须 deterministic、不做 live network 请求，因此无需更新。

## Residual risks

- 本 fix 只扩展 deterministic synthetic matrix，不证明真实网络、真实浏览器安装、真实 storage state、反爬挑战或 provider/API 可用性。
- 本 fix 未改变 comparison bucket classifier；如果后续 Slice/F03 需要改变未采样路径语义，应另行通过 plan/review 裁决。
