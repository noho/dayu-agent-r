# WU-TOOLS-01-F02 Aggregate Deepreview Fix - Codex

## 元数据

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Fix gate：aggregate deepreview accepted fixes
- 日期：2026-06-09
- 输入计划：`docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- 输入裁决：`docs/reviews/wu-tools-01-f02-aggregate-deepreview-controller-adjudication.md`

## 第一性原理判断

本轮修复动机成立，严重性未被高估。

`--url` 与 `--url-file` 是互斥诊断模式选择。当前 `main()` 只按 `options.url_file` 分流；两者同时存在时批量模式会静默覆盖单 URL 输入，违背 accepted plan 的清晰失败要求。该问题是真实 CLI 语义缺陷，但修复边界可以收敛为分流前校验，不需要改动单 URL、批量执行或 diagnostic schema。

URL 安全与 header 脱敏 helper 是 opt-in live diagnostics 的安全/隐私边界，且 diagnostic artifact 未来可能进入 LLM 上下文。补 deterministic tests 合理；测试未证明现有 URL 安全或脱敏实现存在生产缺陷。

## 已修复 finding

### DS F1：`--url` 与 `--url-file` 缺少显式互斥校验

- 修改文件：`utils/diagnose_web_access.py`
- 修复内容：新增 `_validate_cli_mode(...)`，在 `main()` 分流前校验：
  - 同时提供 `--url` 与 `--url-file` 时返回业务可读错误。
  - 两者都未提供时返回业务可读错误。
- 根因证据：原 `main()` 只判断 `if options.url_file:`，导致 `--url-file` 非空时直接进入批量模式并忽略同时传入的 `--url`。
- 范围控制：合法单 URL 模式和合法批量模式语义未改变。

### MiMo F2 / DS F3 test-only：URL 安全与 header 脱敏缺少直接 deterministic tests

- 修改文件：`tests/tools/web/test_diagnose_web_access.py`
- 新增覆盖：
  - URL 规范化：裸 host 补 `https://`，拒绝空值、非 HTTP scheme、缺失 host。
  - URL 安全策略：默认拒绝 `localhost`、`.localhost`、`.local`、`0.0.0.0`、IPv4 loopback/private、IPv6 loopback/link-local、IPv4-mapped IPv6 私网地址。
  - IPv4-mapped IPv6 证据：`::ffff:10.0.0.1` 被 `_is_private_or_local_host(...)` 判定为 private/local；显式 `--allow-private-network-url` 对应 helper 参数可放行。
  - Header 脱敏：`Authorization`、`Cookie`、`X-Api-Key`、`X-Access-Token`、`Client-Secret` 被脱敏，非敏感 header 保留原值。
  - CLI 模式选择：同时传入与同时缺失均返回退出码 `2`，并输出清晰错误。

## 未触碰的 rejected / deferred findings

- 未改变 comparison bucket 对未采样 Playwright / fetch path 的保守分类语义。
- 未改变 `detect_bot_challenge` import。
- 未改变 shell wrapper 的 headed / manual-wait 默认值。
- 未增加 batch concurrency / max workers。
- 未修改默认 CI workflow、Web smoke 语义、Host / Engine / ToolRuntime contracts、production Web tools。
- 未修改 `docs/host/issues-implementation-control.md`。

## Production code 变更范围

除 CLI mutual-exclusion validation 外，没有修改 production code。

URL normalization / URL safety / header redaction 的新增 deterministic tests 全部通过，未暴露真实 helper bug，因此没有对这些 helper 做生产代码修改。

## 验证

| 命令 | 结果 |
|---|---|
| `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q` | 通过，`27 passed in 0.37s` |
| `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` | 通过，`0 errors, 0 warnings, 0 informations` |
| `bash -n utils/diag_web.sh utils/diag_web_batch.sh` | 通过 |
| `git diff --check` | 通过 |
| precise forbidden import / wide-type scan for `utils/diagnose_web_access.py` and `tests/tools/web/test_diagnose_web_access.py` | 通过，forbidden import scan clean，wide-type annotation scan clean |

## 残余风险

- live network、真实 Playwright、storage-state 环境差异仍不在默认 CI 覆盖内，继续路由给 WU-TOOLS-01-F03 定义 opt-in Web smoke 证据消费。
- Diagnostic JSON schema 的 F03 消费字段仍需 F03 plan 显式声明；本轮未扩大 utility schema。
- 批量诊断仍为串行执行；该性能优化已按 controller 裁决 deferred。
