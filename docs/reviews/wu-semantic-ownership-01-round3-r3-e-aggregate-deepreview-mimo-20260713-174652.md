# R3-E Aggregate Deepreview（AgentMiMo）

## Scope

- Mode: aggregate deepreview over committed R3-E slice set
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E`
- Accepted commits:
  - S1: `a20efac7` — Web egress ownership
  - S2: `728e73af` — Web resource/challenge/search outcomes
  - S3: `94a12c9e` — Web diagnostic/storage/smoke oracle
  - S4: `7e4749e5` — Documents bounded source
- Plan truth: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`
- Aggregate validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-aggregate-validation.md`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-aggregate-deepreview-mimo-20260713-174652.md`
- Included scope: 24 files across `dayu/tools/web/`、`dayu/documents/processors/`、`dayu/tools/doc_tools.py`、`utils/`、`tests/`、`dayu/config/README.md`、`tests/README.md`、control docs
- Parallel review coverage: 3 个 subagent（accepted findings closure、cross-slice ownership drift、LLM-facing/README/control docs/scope）

## Findings

未发现实质性问题。

## Accepted Findings Closure

| Finding | 计划落点 | 状态 | Direct Evidence |
| --- | --- | --- | --- |
| DR-004: Web egress connect-peer enforcement | S1 | **已闭合** | `web_egress_policy.py` 新增 `WebEgressPolicy` + `AuthorizedHttpTarget`；`web_http_session.py` 新增 `_ApprovedHTTPConnection`/`_ApprovedHTTPSConnection`，`_new_conn()` 只使用 `approved_addresses`，`getpeername()` 验证 peer；每 hop 重新 authorize；`198.18.0.0/15` 默认拒绝 |
| DR-015: wire/decoded/warmup/DOM budget | S2 | **已闭合** | `web_resource_budget.py` 新增 frozen `WebResourceBudget`（7 字段）；增量 decoder `_decompress_incremental_limited` 按 chunk 累计 decoded bytes；`_BUDGETED_DOM_METRICS_SCRIPT` 用 TreeWalker 预检不读 `page.content()`；warmup `stream=True` |
| DR-016: Web diagnostic 不保存可逆 prefix | S3 | **已闭合** | `web_diagnostics.py` 新增 `WebContentDiagnostic` 只保存 `length`+`digest`；`project_safe_url()` 删除 userinfo/query/fragment；错误消息经 `redact_sensitive_diagnostic_values()` 脱敏；`_log_fetch_diagnostics` 只接受 projection type |
| DR-019: Doc source/result/directory pre-budget | S4 | **已闭合** | `bounded_source.py` 新增 `BoundedSourceSnapshot` 按 chunk 复制，`limit+1` byte 抛 `SourceBudgetExceeded`；`DocResourceBudget(32MiB, 10_000)` frozen 不可放宽；`read_file` 有界增量 decoder；`list_files` bounded heap；`search_files` 三维计数 |
| DR-032: smoke 独立 PASS oracle | S3 | **已闭合** | `smoke_web_ci.py` 新增 `ParentFixtureLedger` frozen dataclass；256-bit token sentinel；server stop → freeze → classify 顺序；`_fixture_ledger_gap()` 要求 ledger accepted + expected digest + negative controls；`artifact_ok` 不能单独 PASS |
| DR-033: diagnostic raw path 共享 egress + storage-state lifecycle | S1+S3 | **已闭合** | S1: `diagnose_web_access.py` 导入共享 `WebEgressPolicy`；S3: storage state 默认零写入，显式 opt-in + 正 TTL，atomic write（`fsync`+`os.replace`），startup reconciliation 只扫描 owner-named 文件 |
| DS: redirect response leak | S1 | **已闭合** | `web_fetch_orchestrator.py` 引入 `AuthorizedResponseLease`；redirect 循环 `finally` 中 `lease.close()`；`transferred` 标志确保成功 transfer 后 caller 负责 close |
| DS: challenge false positives | S2 | **已闭合** | `web_challenge_detection.py` 新增 `BotChallengeDecision` 封闭枚举；evidence class 分类；`BROAD_CONTENT`/`INFRASTRUCTURE_HEADER` 需组合才 confirmed；普通正文不单独判 blocked |
| DS: challenge/status mismatch skips fallback | S2 | **已闭合** | `web_tools.py` 所有 challenge fallback 改用 `challenge_fallback_action(decision, browser_available)`；confirmed 无论 status 都尝试 browser fallback |
| DS: DuckDuckGo shape drift silent empty | S2 | **已闭合** | `web_search_providers.py` 新增 no-results allowlist、challenge/login shape 判定；`malformed_count * 2 > container_count` 抛 `response_shape_changed`；未知 selector 不返回空成功 |

**10/10 accepted findings 全部闭合，无遗漏。**

## Cross-Slice Semantic Ownership Drift Check

| 检查点 | 结论 |
| --- | --- |
| Web diagnostic schema v2 + smoke consumer 同步 | 通过。`web_diagnostics.py` 定义唯一版本常量，`diagnose_web_access.py` 和 `smoke_web_ci.py` 精确校验 v2/revision 2，拒绝旧 prefix 字段，无 fallback |
| safe URL final_url 一致性 | 通过。requests/Playwright success payload 均经 `project_safe_url_or_empty()` 投影；诊断日志使用同一 owner 函数 |
| storage-state lifecycle 完整性 | 通过。`publish()` 时序为 `os.replace → published=True → chmod`；startup reconciliation 只扫描 owner-named 文件 |
| Doc bounded source + processor factory | 通过。`bounded_source.py` 只依赖标准库 + Source protocol；`create_doc_file_processor` 改为接收 Source，不重开路径 |
| 跨 slice 边界 | 通过。S4 不依赖 S1/S2/S3 内部细节；无 fallback 补偿；无 `hasattr/getattr` 兼容分支；无旧 schema 兼容逻辑 |

**5/5 检查点全部通过，未发现跨 slice 语义所有权漂移。**

## LLM-Facing Descriptions

| 检查点 | 结论 |
| --- | --- |
| Web tools 未暴露内部术语 | 通过。description 只含业务可读文本 |
| Doc tools 未暴露内部术语 | 通过。五个 tool description 只含字段语义说明 |
| partial fields 自解释 | 通过。`scan_complete`/`truncated_reason`/`content_truncated` 均附带下一步操作指引 |
| 参数 schema 无内部术语 | 通过 |

## README / Control Docs Consistency

| 检查点 | 结论 |
| --- | --- |
| `tests/README.md` 与测试覆盖一致 | 通过 |
| `dayu/config/README.md` 与 `resource_budget` 一致 | 通过 |
| `issues-implementation-control.md` R3-E 行记录 S1-S4 acceptance | 通过 |
| 无 S5/aggregate/Host/Engine/Fins control bookkeeping 越界 | 通过 |

## Scope Confirmation

- `git diff cd5e8595..7e4749e5 --name-only` 输出 57 个文件，全部在 S1-S4 允许范围内。
- 无 Fins、tool-security、file-authority、symlink-race、SSRF/TLS policy 实现代码。
- 无 Host/Engine/Fins 修改。

## Open Questions

无。

## Residual Risks

沿用各 slice 已记录的 accepted residual risks，无新增：

| residual | owner / destination |
| --- | --- |
| SIGKILL/主机崩溃不保证 Python cleanup | storage-state lifecycle + bounded source；依赖 startup reconciliation/TTL/system temp |
| digest 对低熵内容不构成机密保护 | `web_diagnostics`；仅用于 fixture 关联 |
| Playwright API 不提供 response body streaming | `diagnose_web_access.py`；Content-Length 早拒绝 + post body budget |
| Doc parser 内存表示可能高于输入大小 | 各 processor；后续 complexity budget WU |
| Doc symlink/rename TOCTOU | 后续 file-authority WU；S4 保证 byte cap on opened handle |
| External live URL 为 diagnostic-only | `smoke_web_ci.py` external/search classifier |
| pytest-cov dotted source tooling issue | 等价 coverage 路径已证明 >=80% |

---

**PASS。** 10/10 accepted findings 全部闭合，跨 slice 无语义所有权漂移，无 scope 越界，LLM-facing 描述与 README/control docs 一致。R3-E 准备进入 final closeout。
