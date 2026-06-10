# WU-TOOLS-01-F02 PR Review (AgentDS)

## 元数据

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- Review type：PR review (draft PR gate)
- Reviewer：AgentDS
- Date：2026-06-09
- PR：https://github.com/noho/dayu-agent-r/pull/132
- Branch：`phase/wu-tools-01-f02` -> `main`
- Design sources：`docs/host/design.md`, `docs/engine/design.md`
- Control source：`docs/host/issues-implementation-control.md`
- Plan artifact：`docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Readiness artifact：`docs/reviews/wu-tools-01-f02-draft-pr-readiness-controller.md`
- Prior aggregate deepreview：`docs/reviews/wu-tools-01-f02-aggregate-deepreview-ds.md`
- Prior aggregate rereview：`docs/reviews/wu-tools-01-f02-aggregate-deepreview-rereview-ds.md`

## Verdict

**pass**

无 blocking finding。PR 与 aggregate deepreview 接受态二进制等价（生产/测试代码零漂移），body 准确，非目标全部合规，所有自动化验证通过。residual risk 均有明确 owner。

---

## 1. 二进制等价校验：与 aggregate deepreview 比较

### 1.1 提交链

```
ded9e690 gateflow: accept plan for WU-TOOLS-01-F02
8f5bb379 gateflow: accept WU-TOOLS-01-F02 slice1
6984c514 gateflow: accept WU-TOOLS-01-F02 slice2
89604aa0 gateflow: accept WU-TOOLS-01-F02 slice3
        ← aggregate deepreview (initial) 在此提交上执行
        ← fix (CLI 互斥校验 + focused tests) 在此之后
        ← aggregate deepreview re-review 确认 fix
0f843b34 gateflow: accept WU-TOOLS-01-F02 deepreview
        ← 本提交为 deepreview 接受态（包含 fix）
05f1229e gateflow: ready WU-TOOLS-01-F02 draft PR
d75fcf7b gateflow: record WU-TOOLS-01-F02 draft PR
        ← HEAD = PR 132
```

### 1.2 漂移分析

`git diff 0f843b34..HEAD --stat`：

```
docs/host/issues-implementation-control.md         | 10 ++--
...draft-pr-readiness-controller.md                | 56 ++++++++++
2 files changed, 61 insertions(+), 5 deletions(-)
```

**生产代码（`utils/diagnose_web_access.py`）、测试代码（`tests/tools/web/test_diagnose_web_access.py`）、shell wrapper（`utils/diag_web.sh`、`utils/diag_web_batch.sh`）、URL corpus（`utils/web_ci_urls.jsonl`）均与 deepreview 接受态完全相同。** 无二进制漂移。

仅修改文件：
- `issues-implementation-control.md`：gate 从 `review` → `PR review`，active work unit 更新为 WU-TOOLS-01-F02，next entry point 更新。属于 Controller 职责范围内的状态推进。
- `draft-pr-readiness-controller.md`：新增 readiness 判定 artifact，记录 scope、validation、non-goal preservation、residual risks。

### 1.3 Deepreview Finding 状态回溯

原 aggregate deepreview 发现 2 个 minor finding：

| Finding | 原状态 | 当前状态 | 证据 |
|---|---|---|---|
| DS F1: `--url` 与 `--url-file` 同时传入时静默忽略 | minor | **已修复** | `_validate_cli_mode()`（line 776-794）在 `main()` 分流前校验互斥；`test_cli_requires_exactly_one_url_mode` 覆盖冲突与缺失两种路径 |
| DS F2: 批量模式无并发控制 | minor | **deferred** | 串行处理未变；已明确 owner 为 WU-TOOLS-01-F03 |

另有 MiMo F2/DS F3（URL 安全/header 脱敏测试缺口）已修复。4 个 rejected/deferred finding 均未被意外触碰（详见 aggregate deepreview re-review §2）。

---

## 2. PR Body 准确性校验

### 2.1 标题与分支

- PR 标题：`WU-TOOLS-01-F02 Web CI diagnostics pipeline` ✓ — 准确描述 work unit。
- Base：`main` ✓。Head：`phase/wu-tools-01-f02` ✓。
- Draft：true ✓（符合 draft PR gate 要求）。
- Mergeable：MERGEABLE ✓。Merge state：CLEAN ✓。

### 2.2 Summary 准确性

| PR Body 声明 | 实际证据 | 判定 |
|---|---|---|
| migrate opt-in Web diagnostics scripts and URL corpus into utils | `utils/diagnose_web_access.py` (2549 lines)、`utils/diag_web.sh`、`utils/diag_web_batch.sh`、`utils/web_ci_urls.jsonl` 全部新增 | ✓ |
| add current-contract `diagnose_web_access.py` using current Web ToolsDiscovery / ToolDefinition callable boundary | `_fetch_web_page_definition()` 通过 `ToolsDiscoveryProviderSpec` + `discover_tools` 获取定义，`_call_fetch_tool_async()` 通过 `definition.callable` 调用 | ✓ |
| add deterministic Web diagnostics tests | `tests/tools/web/test_diagnose_web_access.py` 14 个 test function，全部 monkeypatch/local | ✓ |
| 27 passed | `test_diagnose_web_access.py` 14 个 + `test_web_tools_provider.py` 13 个 = 27 | ✓ |
| pyright 0 errors | Controller 验证 + 独立复现一致 | ✓ |
| bash -n passed | shell wrapper 语法正确 | ✓ |
| No default live CI workflow or Web smoke gate | `.github/` 无变更 | ✓ |
| WU-TOOLS-01-S5-R2 remains owned by WU-TOOLS-01-F03 | control doc 仍标记 `deferred-with-owner`, destination F03 | ✓ |
| Host, Engine, ToolRuntime, durable schema, EventLog, and production Web tool behavior unchanged | diff 不触及 `dayu/host/`、`dayu/engine/`、`dayu/tools/web/`（仅 import public provider 接口） | ✓ |

### 2.3 Files Changed

PR files 列表（47 files）中除 7 个实现文件外均为 review artifact。实现文件：

| 文件 | 行数 | 角色 |
|---|---|---|
| `utils/diagnose_web_access.py` | +2549 | 核心诊断脚本 |
| `tests/tools/web/test_diagnose_web_access.py` | +820 | 确定性测试 |
| `docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md` | +484 | plan artifact |
| `utils/diag_web.sh` | +22 | shell wrapper |
| `utils/diag_web_batch.sh` | +23 | batch shell wrapper |
| `utils/web_ci_urls.jsonl` | +60 | URL corpus |
| `docs/host/issues-implementation-control.md` | ±8 | control doc 状态更新 |

无意外文件，无遗漏文件。

---

## 3. 非目标合规检查

按 plan §非目标逐项核对：

| 非目标 | 状态 | 证据 |
|---|---|---|
| 不定义 Web smoke pass/fail/skip gate | ✓ | 代码中无 pass/fail 判定逻辑；`summary.md` 仅统计计数 |
| 不关闭 WU-TOOLS-01-S5-R2 | ✓ | control doc §Residual Risk 仍标记 `deferred-with-owner`，destination WU-TOOLS-01-F03 |
| 不把 live network/browser diagnostics 放入默认 CI | ✓ | `.github/` 无变更；pytest 默认排除 live network |
| 不恢复 OLD ToolRegistry | ✓ | AST import guard 扫描 0 匹配；grep 确认 |
| 不恢复 OLD truncation manager | ✓ | 同上 |
| 不恢复 OLD fetch_more | ✓ | 同上 |
| 不恢复 OLD dayu.web/UI | ✓ | 同上 |
| 不重写 Web production behavior | ✓ | `dayu/tools/web/` 未在 diff 中出现 |
| 不修改 Host public contract | ✓ | `dayu/host/` 未在 diff 中 |
| 不修改 Engine public contract | ✓ | `dayu/engine/` 未在 diff 中 |
| 不修改 ToolRuntime contract | ✓ | 无 ToolRuntime 相关变更 |
| 不修改 durable schema | ✓ | 无 schema 变更 |
| 不修改 EventLog | ✓ | 无 EventLog 变更 |
| 不修改默认 CI workflow | ✓ | 无 CI workflow 变更 |

---

## 4. 正确性风险复核

### 4.1 CLI 模式校验

`_validate_cli_mode(options)` 在 `main()` line 2539 执行：
- `--url` 与 `--url-file` 同时提供 → `ValueError` → exit code 2 ✓
- 两者均缺失 → `ValueError` → exit code 2 ✓
- `test_cli_requires_exactly_one_url_mode` 覆盖上述两种错误路径 ✓

`_run_single_diagnose` 内部 line 1887 的 `raise ValueError("单 URL 模式必须提供 --url。")` 为防御性残留；`_validate_cli_mode` 执行后该路径不可达，但无害。

### 4.2 URL 安全 / Header 脱敏

`_validate_url_safety`（line 938-958）：
1. 拒绝非 http/https scheme ✓
2. 调用 `_is_private_or_local_host` 检查 localhost/private/local/loopback/link-local/reserved/multicast/unspecified ✓
3. `--allow-private-network-url` flag 显式放行 ✓

`_is_private_or_local_host`（line 906-935）：
- 覆盖 localhost、`.localhost`、`.local`、`0.0.0.0`
- `ipaddress.ip_address()` 覆盖 IPv4/IPv6 private、loopback（含 `::1`）、link-local、reserved、multicast、unspecified
- IPv4-mapped IPv6（`::ffff:10.0.0.1`）通过 `ipaddress.ip_address()` 正常捕获为 private ✓

`_redact_headers`（line 986-1008）：
- 对 authorization/cookie/token/secret/key 子串匹配脱敏为 `<redacted>` ✓
- 非敏感 header 保留原值 ✓
- 应用于 raw requests prepared headers、response headers、Playwright 事件 headers、navigation response headers 共 5 处 ✓

新增 4 个 focused test 覆盖上述路径：
- `test_url_normalization_requires_http_url`
- `test_url_safety_rejects_private_and_local_hosts_by_default`（含 IPv4-mapped IPv6）
- `test_header_redaction_masks_sensitive_header_values`
- `test_cli_requires_exactly_one_url_mode`

### 4.3 Diagnostic JSON 结构

`_build_single_diagnostic_payload`（line 1873）产出：
- 顶层：`schema_version: "web-diagnostics-v1"`、`generated_at`、`url`、`comparison_bucket` ✓
- `requests_profile`：含 `raw_requests_header_source: "diagnostic_local"` 标注 ✓
- `fetch_web_page_profile`：通过 current `ToolDefinition.callable` 调用 ✓
- `playwright_profile`：跳过时 `skipped=true` ✓

F03 最小稳定子集字段（`schema_version`、`url`、`comparison_bucket`、per-path `sampled`/`ok`/`status`/`error`）均已稳定提供 ✓。

### 4.4 批量输出

`_run_batch_diagnose`（line 2427）产出：
- `corpus.normalized.jsonl`：规范化 URL entries ✓
- `diagnostics/`：每个 URL 独立 JSON ✓
- `results.jsonl`：每行含 `url`、`diagnostic_path`、`comparison_bucket`、per-path 摘要字段 ✓
- `summary.json`：含 `child_process_error_count` 和 `child_returncodes` ✓
- `summary.md`：业务可读 Markdown ✓

`child_process_error` 行不写入普通 comparison bucket，`summary.json` 单独统计 ✓。

### 4.5 Shell Wrapper

- `diag_web.sh`：`set -euo pipefail`，URL 必填，默认 headed chrome + 30s manual wait + storage-state dir ✓
- `diag_web_batch.sh`：`set -euo pipefail`，URL 文件必填，额外参数透传 ✓
- 均通过 `bash -n` 语法检查 ✓

### 4.6 Control / Readiness Artifacts

- `issues-implementation-control.md`：gate=`PR review`，active work unit=`WU-TOOLS-01-F02`，next entry point=`Dispatch WU-TOOLS-01-F02 PR review to AgentMiMo and AgentDS` ✓
- `draft-pr-readiness-controller.md`：scope、validation、non-goal preservation、residual risks 均记录正确 ✓
- residual risk 表所有条目均有 `deferred-with-owner` 或 `transferred-to-issue` 状态 ✓

---

## 5. 自动化验证状态

| 验证项 | 结果 | 来源 |
|---|---|---|
| `pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q` | 27 passed | Controller + 独立复现一致 |
| `python -m pyright dayu/ tests/ utils/` | 0 errors | Controller + 独立复现一致 |
| `bash -n utils/diag_web.sh utils/diag_web_batch.sh` | passed | Controller + 独立复现一致 |
| `git diff --check` | passed | Controller + 独立复现一致 |
| forbidden import scan | 0 matches | Controller + 独立复现一致 |
| wide-type scan | 0 matches | Controller + 独立复现一致 |
| GitHub PR statusCheckRollup | empty（仓库无 CI workflow） | N/A — 非目标 |

---

## 6. PR-Level Findings

### Finding 1 (info): `_run_single_diagnose` 内防御性 URL 空值校验

- 位置：`utils/diagnose_web_access.py:1886-1887`
- 内容：`if not options.url: raise ValueError("单 URL 模式必须提供 --url。")`
- 严重性：info。`main()` 中 `_validate_cli_mode` 已保证该路径不可达，属于防御性残留。
- 建议：可在后续维护中移除以减少死代码，或保留作为 defense-in-depth。不构成 blocking issue。

无其他 PR-level finding。

---

## 7. Residual Risks

| ID | 严重性 | 描述 | Owner / Destination |
|---|---|---|---|
| F02-R3 | Medium | Web smoke pass/fail 标准与 evidence 消费方式待 F03 裁决 | WU-TOOLS-01-F03 / Issue #120 |
| F02-R4 | Medium | diagnostic JSON schema 的 F03 消费子集超出 F02 最小稳定子集时的兼容策略 | WU-TOOLS-01-F03 / Issue #120 |
| F02-R5 | Low | `_is_private_or_local_host` 不处理 IPv4-mapped IPv6 scope ID；test 已覆盖 `::ffff:10.0.0.1` | 后续维护 |
| F02-R6 | Low | Playwright 安装与 browser channel 因环境不同而异 | Environment / operator |
| F02-R7 | Low | `fetch_web_page` 内部实现变化可能导致 current adapter 行为改变 | WU-TOOLS-01 future changes |
| F02-R8 | Info | 批量模式无并发控制，60 URL 串行可能耗时较长 | WU-TOOLS-01-F03（可选优化） |

所有 residual risk 均有明确 owner/destination，均不阻断 draft PR merge。

---

## 8. 下一 gate 建议

**推荐：等待用户 merge 决策，然后进入 WU-TOOLS-01-F03 goal confirmation。**

理由：
1. 生产/测试代码与 aggregate deepreview 接受态二进制等价，无漂移。
2. PR body 准确，分支状态干净，mergeable。
3. 全部非目标合规。
4. 全部自动化验证通过（27 tests, 0 pyright errors, bash -n passed, git diff --check clean）。
5. 无 blocking PR-level finding。
6. 全部 residual risk 均有明确 owner/destination。

进入 WU-TOOLS-01-F03 前建议：
- 确认 WU-TOOLS-01-S5-R2 的 destination 从 WU-TOOLS-01-F02 转移到 WU-TOOLS-01-F03。
- F03 plan 中显式声明消费的 diagnostic JSON 字段及 mismatch 策略。
