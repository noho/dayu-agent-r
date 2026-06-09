# WU-TOOLS-01-F02 Aggregate Deepreview Re-Review (AgentDS)

## 元数据

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Review type：aggregate deepreview re-review (after fix)
- Reviewer：AgentDS
- Date：2026-06-09
- Fix artifact：`docs/reviews/wu-tools-01-f02-aggregate-deepreview-fix-codex.md`
- Controller adjudication：`docs/reviews/wu-tools-01-f02-aggregate-deepreview-controller-adjudication.md`
- Prior DS review：`docs/reviews/wu-tools-01-f02-aggregate-deepreview-ds.md`
- Prior MiMo review：`docs/reviews/wu-tools-01-f02-aggregate-deepreview-mimo.md`
- Review scope：verify accepted fixes only; verify rejected/deferred findings not accidentally changed; detect new regressions or scope creep.

## Verdict

**pass**

Fix 干净、聚焦、无副作用。所有 accepted findings 得到正确修复，所有 rejected/deferred findings 未触碰，无新回归或范围蔓延。

---

## 1. Accepted Finding Status

| Finding | Verdict | 证据 |
|---|---|---|
| DS F1: CLI 缺少 `--url` / `--url-file` 显式互斥校验 | ✅ 已修复 | `_validate_cli_mode()` 新增，`main()` 分流前调用；test 覆盖冲突与缺失两种路径，退出码 2，错误消息业务可读 |
| MiMo F2 / DS F3: URL 安全与 header 脱敏缺少直接 deterministic tests | ✅ 已修复 | 新增 4 个 deterministic test：URL 规范化、URL 安全策略（含 IPv4-mapped IPv6）、header 脱敏、CLI 模式选择 |

### 1.1 DS F1 详细验证

**生产代码变更** (`utils/diagnose_web_access.py`)：

- `_validate_cli_mode(options: CliOptions) -> None`（line 776–794）：同时提供 `--url` 与 `--url-file` 时 raise `ValueError("--url 与 --url-file 不能同时提供；请只选择单 URL 模式或批量 URL 文件模式。")`；两者都缺失时 raise `ValueError("必须提供 --url 或 --url-file 其中一个，以选择单 URL 模式或批量 URL 文件模式。")`
- `main()` 中 `_parse_options` 后、分流前调用（line 2539）：`_validate_cli_mode(options)`
- ValueError 被已有 `except Exception` handler（line 2543-2545）捕获，返回退出码 2，stderr 输出业务可读错误

**测试覆盖** (`test_cli_requires_exactly_one_url_mode`)：
- 同时传入 `--url` 和 `--url-file` → 退出码 2，stderr 含 "`--url 与 --url-file 不能同时提供`"
- 两者均不传 → 退出码 2，stderr 含 "`必须提供 --url 或 --url-file 其中一个`"

**评估**：实现精确、错误消息业务可读、测试覆盖两种错误路径。合法单 URL 与批量模式语义未改变。

### 1.2 MiMo F2 / DS F3 详细验证

**新增测试** (`tests/tools/web/test_diagnose_web_access.py`)：

| 测试 | 覆盖范围 | 关键边界 |
|---|---|---|
| `test_url_normalization_requires_http_url` | `_normalize_url_for_http` | scheme 补全（`example.com/report` → `https://...`）、空白输入拒绝、ftp scheme 拒绝、缺失 host 拒绝 |
| `test_url_safety_rejects_private_and_local_hosts_by_default` | `_validate_url_safety` + `_is_private_or_local_host` | localhost、`.localhost`、`.local`、`0.0.0.0`、IPv4 loopback/private（127.0.0.1, 10.0.0.1, 172.16.0.1, 192.168.1.1）、IPv6 loopback/link-local（`::1`, `fe80::1`）、IPv4-mapped IPv6 私网（`::ffff:10.0.0.1`）；`--allow-private-network-url` 显式放行 |
| `test_header_redaction_masks_sensitive_header_values` | `_redact_headers` | 5 个敏感关键词（authorization, cookie, token, secret, key）全部脱敏为 `<redacted>`；非敏感 header（User-Agent, Cache-Control）保留原值 |
| `test_cli_requires_exactly_one_url_mode` | CLI 模式互斥 | 见 1.1 |

**评估**：覆盖全面，所有测试均为 deterministic（无 live network），无生产代码修改（这些 helper 在测试下表现正确，未暴露真实 bug）。此次满足 controller 裁决的 "add focused deterministic tests" 和 "IPv4-mapped IPv6 evidence" 要求。

---

## 2. Rejected / Deferred Mis-Fix Check

| 原 Finding | 决策 | 验证结果 | 证据 |
|---|---|---|---|
| MiMo F1: `requests_and_fetch_success_playwright_failed` 对未采样 Playwright 返回 `partial_sample` | rejected | ✅ 未触碰 | `_classify_diagnostic_bucket` 函数未被 diff 触及；`test_comparison_bucket_matrix` 中 `all_success_before_challenge` case 依然存在 |
| MiMo F3: `detect_bot_challenge` import | rejected | ✅ 未触碰 | `from dayu.tools.web.web_challenge_detection import detect_bot_challenge` 仍在 line 44；两处调用（line 1109, 1674）未变 |
| MiMo F4: shell wrapper headed/manual-wait 默认值 | rejected | ✅ 未触碰 | `diag_web.sh` line 17 `--headed`、line 19 `--manual-wait-seconds 30` 未变 |
| MiMo F5: `all_success` 优先于 `playwright_challenge_detected` | rejected | ✅ 未触碰 | `_classify_diagnostic_bucket` decision tree 顺序未变；`test_comparison_bucket_matrix` 中 `all_success_before_challenge` case 依然存在 |
| MiMo F6: 批量子进程环境变量继承 | rejected | ✅ 未触碰 | `_run_batch_diagnose` 中 `subprocess.run(...)` 仍未传入 `env` 参数 |
| DS F2: 批量模式无并发控制 | deferred | ✅ 未触碰 | grep `concurrent\|ThreadPool\|ProcessPool\|max_workers\|max_parallel` 无匹配 |

---

## 3. 非目标逐项核对

| 非目标 | 状态 | 证据 |
|---|---|---|
| 不修改 Web smoke gate | ✅ | 无 pass/fail/skip gate 逻辑变更 |
| 不关闭 WU-TOOLS-01-S5-R2 | ✅ | 未修改 control doc |
| 不把 live diagnostics 放入默认 CI | ✅ | 无 CI workflow 变更 |
| 不修改默认 CI workflow | ✅ | 未修改 `.github/` 下任何文件 |
| 不恢复 OLD imports | ✅ | AST import guard 依然通过；生产文件中 forbidden import scan clean |
| 不修改 production Web tools | ✅ | `dayu/tools/web/` 未在 diff 中 |
| 不修改 Host/Engine/ToolRuntime contract | ✅ | `dayu/host/`、`dayu/engine/` 未在 diff 中 |
| 不增加 batch concurrency | ✅ | grep clean（见 2 节 DS F2） |

---

## 4. 范围蔓延检查

**修改文件清单**：

| 文件 | 变更量 | 角色 |
|---|---|---|
| `utils/diagnose_web_access.py` | +22 lines | Fix target：新增 `_validate_cli_mode` + `main()` 中调用 |
| `tests/tools/web/test_diagnose_web_access.py` | +89 lines | Fix target：4 个新 test function |
| `docs/host/issues-implementation-control.md` | ±4 lines | Controller-owned dirty；按 review scope 忽略 |

**生产代码变更**：仅新增 1 个校验函数和 1 行调用。无函数签名变更、无 import 变更、无已有逻辑修改。

**测试代码变更**：仅新增 4 个独立 test function。无已有 test 被修改或删除。test helper `_payload`、fixture monkeypatch、已有 10 个 test 均未变。

无新文件创建。无 scope creep。

---

## 5. 独立验证结果

Controller 报告的结果已独立复现：

| 验证项 | Controller 报告 | 独立复现 |
|---|---|---|
| `pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q` | 27 passed | 27 passed（复现一致） |
| `python -m pyright dayu/ tests/ utils/` | 0 errors | 0 errors, 0 warnings |
| `bash -n utils/diag_web.sh utils/diag_web_batch.sh` | passed | passed |
| `git diff --check` | passed | clean |
| forbidden import scan | no matches | production file clean（test file 中匹配项为 AST guard test constants） |
| wide-type scan | no matches | clean |

---

## 6. New Findings

无新 finding。本轮修复是纯粹的点状修正，未引入任何新问题。

**轻微观察项**（不构成 finding）：
- `_run_single_diagnose` 内部 line 1887 仍保留 `raise ValueError("单 URL 模式必须提供 --url。")` 校验。该路径经 `main()` 的 `_validate_cli_mode` 后已不可达，属于防御性残留，不造成功能问题。

---

## 7. Residual Risks

本轮修复未改变运行时行为（仅新增 CLI 前置校验，新增 tests 不变更生产逻辑），因此残余风险与原 DS aggregate review 相同：

| ID | 严重性 | 描述 | Owner / Destination |
|---|---|---|---|
| F02-R1 | — | DS F1 已修复，原风险消除 | — |
| F02-R3 | Medium | Web smoke pass/fail 标准与 evidence 消费方式待 F03 裁决 | WU-TOOLS-01-F03 / Issue #120 |
| F02-R4 | Medium | diagnostic JSON schema 的 F03 消费子集超出 F02 最小稳定子集时的兼容策略 | WU-TOOLS-01-F03 / Issue #120 |
| F02-R5 | Low | `_is_private_or_local_host` 不处理 IPv4-mapped IPv6 scope ID；test 已覆盖 `::ffff:10.0.0.1` 正常判定为 private | 后续维护 |
| F02-R6 | Low | Playwright 安装与 browser channel 因环境不同而异 | Environment / operator |
| F02-R7 | Low | `fetch_web_page` 内部实现变化可能导致 current adapter 行为改变 | WU-TOOLS-01 future changes |

---

## 8. 下一 gate 建议

**推荐：draft PR gate**

理由：
1. 两个 accepted finding 均已正确修复。
2. 全部 rejected/deferred finding 均未被意外触碰。
3. 无新回归、无范围蔓延。
4. 独立验证结果与 Controller 报告一致。
5. 残余风险均有明确 owner/destination，均不阻断 draft PR。
