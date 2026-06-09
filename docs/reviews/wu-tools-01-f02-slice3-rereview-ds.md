# WU-TOOLS-01-F02 Slice 3 再审查 — AgentDS

## 元数据

- Work unit: `WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- 当前 gate: Slice 3 re-review after fix
- 日期: 2026-06-09
- 审查人: AgentDS（再审查）
- 前置 artifact:
  - Controller adjudication: `docs/reviews/wu-tools-01-f02-slice3-code-review-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-tools-01-f02-slice3-fix-codex.md`
  - 首次 DS review: `docs/reviews/wu-tools-01-f02-slice3-code-review-ds.md`
- artifact path: `docs/reviews/wu-tools-01-f02-slice3-rereview-ds.md`

## Verdict: **pass**

所有已接受 finding 均已正确修复，所有已拒绝 finding 均未被改动，未发现新回归。

---

## 已接受 Finding 状态

| Finding | 决策 | 修复状态 | 验证 |
|---|---|---|---|
| MiMo F1: 未使用的 `socket` import | accepted | `import socket` 已从 `utils/diagnose_web_access.py` 删除 | 通过。diff 确认删除行，全文搜索 `socket.` 无命中。 |
| MiMo F3 / DS F1: comparison bucket 矩阵不穷尽 | accepted | `test_comparison_bucket_matrix` 从 6 个 case 扩展到 13 个 | 通过。7 个新 case 的预期 bucket 与 `_classify_diagnostic_bucket` 决策树逐条校验一致（见附录）。 |

---

## 已拒绝 Finding 误修检查

| Finding | 决策 | 检查结果 |
|---|---|---|
| MiMo F2: AST/import guard 测试缺失 | rejected-with-reason | **未修改。** `test_diagnose_web_access_does_not_import_old_web_or_ui_paths` (L521) 保持不变，AST 解析逻辑未动。 |
| DS F2: `requests_only_success` 的 `fetch_failed` 条件 | rejected-with-reason | **未修改。** `_classify_diagnostic_bucket:1833` 仍使用 `fetch_failed`（要求 `fetch_sampled and not fetch_ok`），未改为 `(not fetch_sampled or fetch_failed)`。 |

---

## 新回归扫描

| 检查项 | 结果 |
|---|---|
| OLD forbidden import（`dayu.engine.tool_registry` 等） | 无命中 — `utils/diagnose_web_access.py` 与测试文件均无 |
| 宽类型签名（`Any`/`object`） | 无命中 |
| live network / real browser 默认测试使用 | 无命中 — 全部通过 monkeypatch / tmp_path / synthetic payload |
| Host / Engine / ToolRuntime contract 变更 | 无 — `dayu/` 目录零 diff |
| 默认 CI workflow 变更 | 无 — `.github/` 无 diff |
| 仅预期文件被修改 | 是 — 仅 `utils/diagnose_web_access.py`（diff）与 `tests/tools/web/test_diagnose_web_access.py`（新增文件）有变更；`docs/host/issues-implementation-control.md` 为 Controller owned dirty 文件，不在审查范围内 |

---

## 新增测试用例正确性验证

对 `test_comparison_bucket_matrix` 新增 7 个 case 逐一 walk `_classify_diagnostic_bucket` 决策树，确认预期 bucket 与实现一致：

| 新增 case | payload 关键字段 | 预期 bucket | 决策路径 |
|---|---|---|---|
| `playwright_challenge_detected` | requests_ok, fetch_ok, playwright_ok=False, challenge=True | `playwright_challenge_detected` | all_success 条件 playwright_ok=False 不命中 → challenge 条件命中 |
| `requests_only_success` | requests_ok, fetch_sampled+failed, playwright 未采样 | `requests_only_success` | 前 6 条不命中 → 第 7 条 fetch_failed + (not playwright_sampled or playwright_failed) 命中 |
| `browser_only_success` | playwright_ok, requests_failed, fetch_failed | `browser_only_success` | 前 7 条不命中 → 第 8 条命中 |
| `requests_and_fetch_success_playwright_failed` | requests_ok, fetch_ok, playwright_failed | `requests_and_fetch_success_playwright_failed` | all_success playwright_ok=False 不命中 → challenge=False 不命中 → 第 9 条命中 |
| `fetch_only_failure` | requests_ok, fetch_failed, playwright_ok | `fetch_only_failure` | 前 9 条不命中 → 第 10 条 fetch_failed and (requests_ok or playwright_ok) 命中 |
| `all_failed` | requests_failed, fetch_failed, playwright_failed, all_sampled | `all_failed` | 前 10 条不命中 → 第 11 条 sampled_path_count>0 + 全路径失败条件命中 |
| `partial_sample` | playwright_only_sampled+ok, others unsampled | `partial_sample` | 前 11 条不命中 → sampled_path_count>0 → `partial_sample` |

全部 7 个新增 case 预期正确。

---

## 验证缺口与残余风险

1. **Deterministic tests 不覆盖真实网络/浏览器** — 已知设计决策，非遗漏。矩阵扩展不改变此约束。
2. **`ToolFailedOutcome` contract 边界** — 仍无法暴露 `http_status`/`internal_diagnostics`。本 Slice 已将边界显式化在 `diagnostics.note` 中，不构成功能缺陷。
3. **覆盖仍有缺口** — 矩阵覆盖 13/13 确定性分支，已穷尽；但 `partial_sample` 只测试了 playwright-only 组合，requests-only、fetch-only 的未采样组合未单独测试。不影响 gate 通过。

---

## 约束合规复查

| 约束 | 状态 |
|---|---|
| 禁止 OLD import | 通过 |
| 禁止 `Any`/`object` 宽类型 | 通过 |
| 禁止反向依赖 | 通过 |
| 不改 Host/Engine/ToolRuntime contract | 通过 |
| 不改 production Web behavior | 通过 |
| 不改默认 CI workflow | 通过 |
| 中文 docstring | 通过 |
