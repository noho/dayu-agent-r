# WU-TOOLS-01-F02 Aggregate Deepreview — AgentMiMo

## 元数据

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- 审查类型：aggregate deepreview
- 审查者：AgentMiMo
- 日期：2026-06-09
- 输入 commits：plan ded9e690, Slice 1 8f5bb379, Slice 2 6984c514, Slice 3 89604aa0
- 设计真源：`docs/host/design.md`, `docs/engine/design.md`
- 计划真源：`docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`

## 审查范围

| 文件 | 角色 |
|------|------|
| `utils/diagnose_web_access.py` | 核心诊断脚本（~2528 行） |
| `utils/diag_web.sh` | 单 URL shell wrapper |
| `utils/diag_web_batch.sh` | 批量 shell wrapper |
| `utils/web_ci_urls.jsonl` | URL corpus（60 条） |
| `tests/tools/web/test_diagnose_web_access.py` | 确定性测试（~732 行） |

## 验证结果

| 验证项 | 结果 |
|--------|------|
| `pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q` | 23 passed |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings |
| `bash -n utils/diag_web.sh utils/diag_web_batch.sh` | 通过 |
| `git diff --check` | 通过 |
| forbidden import 扫描 | 无匹配 |
| wide-type (`Any`/`object`) 扫描 | 无匹配 |

## 结论

**verdict: pass-with-findings**

无阻断问题。实现正确、安全、符合设计约束。发现若干 non-blocking 观察项。

## Findings

### F-01 [LOW] `_classify_diagnostic_bucket` 对"两条路径成功、Playwright 未采样"返回 `partial_sample`

**文件**：`utils/diagnose_web_access.py:1823-1849`

**证据**：当 `requests_ok=True, fetch_ok=True, playwright_sampled=False` 时，decision tree 走到 `partial_sample`（line 1848），而非 `requests_and_fetch_success_playwright_failed`。这是因为 `requests_and_fetch_success_playwright_failed` 的条件（line 1837）要求 `playwright_failed = playwright_sampled and not playwright_ok`，当 `playwright_sampled=False` 时 `playwright_failed=False`，条件不满足。

**评估**：行为合理。`requests_and_fetch_success_playwright_failed` 的语义是"Playwright 被采样但失败"；当 Playwright 未被采样时，没有失败证据，归入 `partial_sample` 是正确的保守分类。计划中 bucket 5 的规则（"若 requests 是唯一被采样成功路径且其他路径未采样"）也支持这一行为。无需修改。

### F-02 [LOW] 缺少 `_is_private_or_local_host`、`_redact_headers`、`_validate_url_safety` 的单元测试

**文件**：`tests/tools/web/test_diagnose_web_access.py`

**证据**：测试覆盖了 corpus 解析、storage state、comparison bucket、fetch adapter、CLI 单/批量模式和 import guard，但未直接测试以下函数：
- `_is_private_or_local_host`：私有网络检测逻辑包含 IPv4/IPv6、localhost、`.local` 等分支。
- `_redact_headers`：header 脱敏逻辑包含 5 个敏感关键词匹配。
- `_validate_url_safety`：URL 安全校验组合了 normalization 和 private network 检测。
- `_normalize_url_for_http`：URL 规范化包含 scheme 补全和校验。

**评估**：这些函数逻辑相对简单，且通过 CLI 单 URL 测试间接覆盖了 happy path。`_is_private_or_local_host` 的 IPv6 分支和 `_redact_headers` 的边界匹配未被直接测试，但风险低。`utils/` 默认无覆盖率要求（plan 明确说明），且测试矩阵已覆盖 plan 要求的核心分支。作为后续改进项记录。

### F-03 [LOW] `_build_requests_profile` 导入并调用 `detect_bot_challenge`

**文件**：`utils/diagnose_web_access.py:44`, `utils/diagnose_web_access.py:1088`

**证据**：脚本顶部 `from dayu.tools.web.web_challenge_detection import detect_bot_challenge`，在 `_build_requests_profile`（line 1088）和 `_build_playwright_profile`（line 1653）中调用。

**评估**：`web_challenge_detection` 是无状态工具模块，不属于 OLD registry/truncation/fetch_more/UI 路径。导入符合计划"Required imports: current `dayu.tools.web` provider"的约束。`detect_bot_challenge` 的调用增强了 raw requests profile 的诊断价值（可检测 anti-bot challenge），是正确设计。无需修改。

### F-04 [INFO] shell wrapper 默认 `--headed` 和 `--manual-wait-seconds 30`

**文件**：`utils/diag_web.sh:19-20`, `utils/diag_web_batch.sh:19-20`

**证据**：两个 shell wrapper 都硬编码 `--headed` 和 `--manual-wait-seconds 30`。

**评估**：符合计划——shell wrapper 是"手工显式触发的 live/browser 诊断入口"，默认 headed 和人工等待是合理设计。批量 wrapper 同样使用 headed 模式可能在大规模 corpus 时需要人工交互，但用户可通过 `$@` 覆盖。无需修改。

### F-05 [INFO] `_classify_diagnostic_bucket` 的 `all_success` 不检查 challenge_detected

**文件**：`utils/diagnose_web_access.py:1823`

**证据**：当三条路径均成功且 `challenge_detected=True` 时，返回 `all_success` 而非 `playwright_challenge_detected`。这是因为 `all_success` 条件（line 1823）在 `playwright_challenge_detected` 条件（line 1825）之前被检查。

**评估**：测试用例 `all_success_before_challenge`（test file line 141-152）显式验证了这一行为：当所有路径成功且 challenge 被检测到时，`all_success` 优先。这符合计划规则 6（"三条路径均采样且均成功，返回 all_success"）和规则 5 的例外（"除非所有路径均完全成功且 challenge 只作为低置信提示"）。设计正确。

### F-06 [INFO] batch 子进程继承父进程环境变量

**文件**：`utils/diagnose_web_access.py:2466-2471`

**证据**：`subprocess.run(command, capture_output=..., text=True, check=False)` 未显式传入 `env` 参数。

**评估**：子进程继承父进程的环境变量（包括 `PATH`、`PYTHONPATH` 等），这是标准行为。对于 diagnostics utility 而言，继承环境是正确的——子进程需要访问相同的 Python 环境和 `dayu` 包。无需修改。

## 架构 / 非目标合规评估

### 成功信号逐项核对

| 成功信号 | 状态 | 证据 |
|----------|------|------|
| `utils/diagnose_web_access.py` 存在，支持单 URL 与批量模式 | ✅ | `main()` 根据 `options.url_file` 分发到 `_run_single_diagnose` 或 `_run_batch_diagnose` |
| `utils/diag_web.sh`、`utils/diag_web_batch.sh`、`utils/web_ci_urls.jsonl` 存在 | ✅ | 文件已创建 |
| 单 URL 模式输出包含 `requests_profile`、`fetch_web_page_profile`、可选 `playwright_profile` 与 `comparison_bucket` | ✅ | `_build_single_diagnostic_payload` 构造完整 payload |
| 批量模式写出 `corpus.normalized.jsonl`、per-url diagnostics、`results.jsonl`、`summary.json`、`summary.md` | ✅ | `_run_batch_diagnose` 依次写出所有文件 |
| `fetch_web_page` 通过 current `ToolDefinition.callable` 调用 | ✅ | `_fetch_web_page_definition` 通过 `discover_tools(spec)` 获取定义，`_call_fetch_tool_async` 通过 `definition.callable` 调用 |
| 缺少依赖时输出清晰 diagnostic/skip-safe evidence | ✅ | Playwright missing 输出 `playwright_package_missing`，URL policy 输出 `blocked_by_diagnostic_url_policy` |
| 默认 tests 使用 mocked/local evidence | ✅ | 所有测试通过 monkeypatch 控制，无 live network |

### 非目标逐项核对

| 非目标 | 状态 | 证据 |
|--------|------|------|
| 不定义 Web smoke gate | ✅ | 无 pass/fail/skip gate 逻辑 |
| 不关闭 `WU-TOOLS-01-S5-R2` | ✅ | 无相关操作 |
| 不把 live diagnostics 放入默认 CI | ✅ | 无 CI workflow 修改 |
| 不恢复 OLD imports | ✅ | AST guard 测试确认无 forbidden imports |
| 不重写 production Web tools | ✅ | 未修改 `dayu/tools/web/` production code |
| 不修改 Host/Engine/ToolRuntime contract | ✅ | 未修改 `dayu/host/`、`dayu/engine/` |
| 不把单站点失败判定为 regression | ✅ | 只输出证据和分类 |

### 设计真源对齐

| 对齐项 | 状态 |
|--------|------|
| Host governance 真源不受影响 | ✅ |
| Engine tool loop 不受影响 | ✅ |
| ToolsDiscovery 复用 current provider boundary | ✅ |
| LLM-facing 文本业务可读 | ✅ |

## 安全 / 隐私评估

| 检查项 | 状态 | 证据 |
|--------|------|------|
| header 脱敏 | ✅ | `_redact_headers` 对包含 authorization/cookie/token/secret/key 的 header 值替换为 `<redacted>` |
| storage state 内容不内联到 summary | ✅ | 只记录路径，`storage_state_note` 显式说明 |
| private/local URL 默认阻止 | ✅ | `_is_private_or_local_host` + `_validate_url_safety`，需 `--allow-private-network-url` 显式放行 |
| summary 无敏感信息泄漏 | ✅ | summary 只含计数和 bucket 分布 |

## 测试覆盖评估

**覆盖充分性**：充分。

测试矩阵覆盖了 plan 要求的所有核心场景：
- corpus 解析（JSONL/TXT/去重/非法行）
- storage state 路径解析
- comparison bucket 全矩阵（13 种 case）
- batch summary 计数
- fetch adapter 成功/失败 outcome 投影
- CLI 单/批量模式端到端（monkeypatch）
- forbidden import guard

**覆盖缺口**（non-blocking）：
- `_is_private_or_local_host` 的 IPv4/IPv6 分支未直接测试
- `_redact_headers` 的边界匹配未直接测试
- `_validate_url_safety` 组合逻辑未直接测试
- `_normalize_url_for_http` scheme 补全未直接测试
- CLI 错误路径（同时传 `--url` 和 `--url-file`）未直接测试

这些函数逻辑简单，且通过 CLI 端到端测试间接覆盖 happy path。作为 `utils/` 下的脚本，plan 明确"默认无覆盖率要求"，当前测试质量已超出最低要求。

## 残余风险

| 风险 | 严重性 | Owner | 目标 |
|------|--------|-------|------|
| live network 结果天然不稳定 | 低 | F03 | 通过 explicit opt-in 和 evidence-only 输出降低；F03 Web smoke 需定义 skip 策略 |
| Playwright 安装/channel 因机器不同而异 | 低 | F03 | F02 将缺失记录为 diagnostic profile failure |
| `fetch_web_page` internals 后续可能变化 | 低 | 维护者 | 通过 `ToolDefinition.callable` 调用比导入 private helper 更低耦合 |
| diagnostic JSON schema 需 F03 进一步裁决 | 中 | F03 | F02 保证 utility schema 子集稳定；F03 消费更多字段需重新声明 |
| `_is_private_or_local_host` 未覆盖 IPv6 scope ID | 低 | 维护者 | `ipaddress.ip_address()` 不解析 scope ID（如 `fe80::1%eth0`），但 diagnostics 场景极少见 |

## 建议

**下一 gate**：aggregate deepreview 通过，建议进入 draft PR gate。

**后续改进项**（不阻断）：
1. 为 `_is_private_or_local_host`、`_redact_headers`、`_validate_url_safety` 补充直接单元测试，增强边界覆盖。
2. F03 plan 中声明消费的 diagnostic JSON 字段子集，避免 schema drift。
