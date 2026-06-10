# WU-TOOLS-01-F02 Aggregate Deepreview Re-Review — MiMo

## 元数据

- Work unit: `WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Gate: aggregate deepreview re-review after fix
- 日期: 2026-06-09
- 输入裁决: `docs/reviews/wu-tools-01-f02-aggregate-deepreview-controller-adjudication.md`
- 输入修复: `docs/reviews/wu-tools-01-f02-aggregate-deepreview-fix-codex.md`
- 修复提交: `89604aa0` (gateflow: accept WU-TOOLS-01-F02 slice3)

## Verdict

**pass**

所有 accepted findings 修复正确，rejected/deferred findings 未被意外修改，无新增回归或 scope creep。

## Accepted Finding 验证状态

| Finding | 要求 | 验证结果 | 状态 |
|---|---|---|---|
| DS F1: `--url` / `--url-file` 互斥校验 | 分流前显式校验，业务可读错误，deterministic test | `_validate_cli_mode(options)` 在 `main()` 分流前调用（`diagnose_web_access.py:2539`）；同时提供时 `raise ValueError("--url 与 --url-file 不能同时提供…")`，同时缺失时 `raise ValueError("必须提供 --url 或 --url-file 其中一个…")`；`main()` catch Exception 输出到 stderr 并返回退出码 2；`test_cli_requires_exactly_one_url_mode`（`test_diagnose_web_access.py:511-528`）覆盖两种错误路径。 | ✅ 通过 |
| MiMo F2: URL 规范化/安全/脱敏 deterministic tests | 聚焦 helper 测试，含 local/private hosts 和 IPv4-mapped IPv6，不加 live network 测试 | `test_url_normalization_requires_http_url`（:112-123）覆盖裸 host 补 https、空值、非 HTTP scheme、缺失 host；`test_url_safety_rejects_private_and_local_hosts_by_default`（:126-154）覆盖 localhost、.localhost、.local、0.0.0.0、127.0.0.1、10.x、172.16.x、192.168.x、::1、fe80::、::ffff:10.0.0.1，以及 `allow_private_network_url=True` 放行；`test_header_redaction_masks_sensitive_header_values`（:157-178）覆盖 Authorization、Cookie、X-Api-Key、X-Access-Token、Client-Secret 脱敏和非敏感 header 保留。 | ✅ 通过 |
| DS F3: IPv4-mapped IPv6 test-only | 测试锁定证据，不改 classifier/URL safety 逻辑 | `_is_private_or_local_host("::ffff:10.0.0.1")` 在 `test_url_safety_rejects_private_and_local_hosts_by_default` 中断言为 `True`（:147）；`_validate_url_safety` 对 `::ffff:10.0.0.1` 在 `allow_private_network_url=True` 时放行（:148-151）。生产代码中 `_is_private_or_local_host` 未被修改。 | ✅ 通过 |

## Rejected/Deferred Finding 误修检查

| Finding | Decision | 检查结果 |
|---|---|---|
| MiMo F1: partial_sample bucket 语义 | rejected | `git diff` 未触及 `_compute_comparison_bucket` 或相关逻辑。 |
| MiMo F3: `detect_bot_challenge` import | rejected | `git diff` 未触及 import 语句或 challenge 检测逻辑。 |
| MiMo F4/F5/F6: wrapper 默认值 / all_success 优先级 / 子进程环境 | rejected | `git diff` 未触及 wrapper、bucket 排序或 subprocess 环境继承。 |
| DS F2: 批量并发控制 | deferred → F03 | `git diff` 未添加 `--max-workers` 或并发逻辑。批量仍为串行。 |

**确认**: `git diff --stat` 显示仅 `utils/diagnose_web_access.py`（+22 行）和 `tests/tools/web/test_diagnose_web_access.py`（+89 行）被修改。所有变更均为 accepted findings 的修复，无 scope creep。

## 回归检查

- `pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q`: **27 passed in 0.34s** ✅
- `pyright dayu/ tests/ utils/`: **0 errors, 0 warnings, 0 informations** ✅
- `bash -n utils/diag_web.sh utils/diag_web_batch.sh`: 通过 ✅
- `git diff --check`: 通过 ✅
- forbidden import / wide-type scan: clean ✅
- `docs/host/issues-implementation-control.md` 有未提交变更，属 controller-owned dirty docs，非本轮修复范围，忽略。

## 新增 Finding

无。

## 残余风险与下一 Gate 建议

- live network / 真实 Playwright / storage-state 环境差异仍不在默认 CI 覆盖内 → 路由至 WU-TOOLS-01-F03。
- Diagnostic JSON schema F03 消费字段需 F03 plan 显式声明 → 路由至 WU-TOOLS-01-F03。
- 批量诊断串行执行 → 已 deferred，仅在 F03 实际成为瓶颈时优化。
- 以上残余风险均为 F02 scope 外的已知限制，不阻塞当前 gate。
