# WU-SEMANTIC-OWNERSHIP-01 R08 cumulative Controller validation

## 1. Gate 与结论

- 本文验证既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R08 S1+S2 累计实现，不创建新 WU，也不把 S1 作为可独立接受的历史 slice。
- accepted final plan：`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`，SHA-256 为 `87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`。
- implementation artifacts：`docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md` 与 `docs/reviews/wu-semantic-ownership-01-r08-s2-cumulative-implementation-codex.md`。
- implementation base HEAD：`28b096c7b371afdcff271c6ab4ab971901f83798`；staged tree 为空。

结论：**PASS / READY FOR DUAL COMPLETE IMMUTABLE CUMULATIVE CODE REVIEW**。

## 2. Immutable tree lock

Controller 独立复核最终 implementation tree：

- 23 个 tracked changed paths；2 个 untracked implementation artifacts；总计 25 个 exact allowlist paths。
- 完整 tracked `git diff --binary` SHA-256：`4d346f2bd05d26673ed0a1ec680cd6a1fe68d976340dfea302c55ad912354d4b`。
- S1 artifact SHA-256：`d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748`。
- S2 cumulative artifact SHA-256：`08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648`。
- AgentCodex artifact 内 24 个非递归 content hashes 与 Controller 重算一致；S2 artifact 自身由上述外部 hash 锁定。
- `git diff --check` 通过；没有 production、tests、README、implementation artifact 之外的未提交路径。

Reviewer 必须同时重算 tracked binary diff hash 和两个 artifact content hash。任一值变化都使本 lock 与 review 失效，必须回 Controller 重新验证，不得继续给出旧树结论。

## 3. 语义 owner 与范围复核

Controller 复核确认：

- producer contract 删除 mandatory locator、raw total、双 count 和不可行动的内部原因；完整结果省略 `reason`，partial 结果必须携带封闭 actionable reason。
- SEC、BS report form、BS 6-K、HTML/OCR 与 fiscal/XBRL producer 消费同一 Fins-owned typed contract；Service/CLI 没有新增或重复 terminal 判定。
- tools 层只有 `PublicFinancialStatementResult`、`PublicXbrlQueryResult` 两个公共 typed projection；旧 tools 类型名没有 alias、re-export、wrapper 或 compatibility shim。
- XBRL read composition 固定为 producer validation、输入副本、normalize、stable deduplicate、public projection；唯一 `fact_count` 赋值是 `result_types.py` builder 内的 `len(returned_facts_copy)`。
- tool description 从同一 result owner helper 生成；字段、类型、枚举、optional reason、动作和 `SEC_EDGAR` 示例自足。
- `fiscal_period` schema 消费共享 `FISCAL_PERIODS`；number 参数保持 JSON number，bool 由 callable/schema 边界拒绝。
- forced truncation 只验证 Host 对 Fins pre-Host facts 的 public envelope/fetch-more composition；Fins 未实现 cursor 或 `fetch_more`，Host truncation owner 未改。
- R07 snapshot/borrow/release/revision/citation/source-changed 的 21 个函数 AST 与 HEAD 相同；storage、Host、Engine、Service、UI、prompts 和 security containment/symlink/atomic boundaries 零 diff。
- 未实施 R09-R12、Issues 142/151/175/177/178、统一 tool authorization 或其它 deferred scope。

没有发现与 controller discussion、`docs/fins/design.md` 或 accepted final plan 直接矛盾的代码证据。

## 4. Controller 独立验证

AgentCodex 在最终树报告：

- focused owner matrix：`119 passed, 50 deselected`；S1 fiscal exact node：`1 passed`；S2 public matrix：`332 passed`；
- forced pre-Host → Host envelope → public `fetch_more`：`1 passed`；真实 AAPL XBRL / HTML financial / no-statement：`3 passed`；
- aggregate：`390 passed`；full Fins：`857 passed, 1 existing skip`；
- full pyright：`0 errors`；actual-changed Python Ruff：`All checks passed!`；全部 source/AST/LLM/README/security/no-touch scans与 diff check 通过。

Controller 在锁定树上独立运行五个高风险节点：

```text
test_real_sec_processor_reads_and_projects_aapl_fixture
test_real_bs_six_k_processor_uses_html_and_ocr_fallbacks
test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation
test_fins_read_financial_statement_projects_statement_not_found
test_financial_projection_and_citation_share_borrowed_snapshot_during_publication
```

结果：`5 passed, 3 existing deprecation warnings`。

Controller 还独立得到：

- full `pyright`：`0 errors, 0 warnings, 0 informations`；
- public/tool/schema/serializer/LLM forbidden scan：零命中；
- `git diff --check`：通过；staged paths：空；
- binary diff 与 artifacts hashes 精确匹配本 artifact 第 2 节。

## 5. Exact-key coverage ledger

Controller 从 `workspace/tmp/r08-cumulative-coverage.json` 以 repo-relative exact key 重算 15 个实际 changed production 文件；manifest 非空、无 missing key，全部 `>=80.00%`：

| Production path | Coverage |
|---|---:|
| `dayu/fins/domain/financial_result_contract.py` | 88.56% |
| `dayu/fins/domain/xbrl_result_contract.py` | 89.30% |
| `dayu/fins/pipelines/sec_fiscal_fields.py` | 91.37% |
| `dayu/fins/processors/bs_report_form_common.py` | 83.73% |
| `dayu/fins/processors/bs_six_k_processor.py` | 80.17% |
| `dayu/fins/processors/financial_base.py` | 100.00% |
| `dayu/fins/processors/html_financial_statement_common.py` | 80.34% |
| `dayu/fins/processors/report_form_financial_statement_common.py` | 89.01% |
| `dayu/fins/processors/sec_processor.py` | 85.17% |
| `dayu/fins/processors/sec_xbrl_query.py` | 82.69% |
| `dayu/fins/processors/six_k_form_common.py` | 81.91% |
| `dayu/fins/tools/fins_tools.py` | 86.49% |
| `dayu/fins/tools/read_runtime.py` | 84.51% |
| `dayu/fins/tools/read_runtime_helpers.py` | 85.83% |
| `dayu/fins/tools/result_types.py` | 100.00% |

新增测试没有直接调用 private processor `_collect_*` / `_get_xbrl()`，没有 skip/xfail、pragma/omit、阈值豁免或空执行。双路 reviewer 仍必须 adversarial 检查全部 coverage closure tests：只接受 public processor contract 或唯一稳定业务规则 owner 的断言；若发现测试锁定无关兼容行为、偶然调用顺序、fake-only 路径或仅为走行的断言，必须作为 finding 报告，不能因 coverage 数字通过而忽略。

## 6. Handoff

下一 gate 是 AgentMiMo 与 AgentDS 对同一完整 R08 S1+S2 cumulative tree 并发执行 `/deepreview`。审查必须覆盖 correctness、producer/public exact contract、reason matrix、query params、input immutability、stable dedup、single count owner、真实 Host truncation composition、R07 no-touch、LLM-facing description、tests/coverage quality、overdesign、security/deferred boundaries 和 accepted plan 一致性。

所有 accepted findings 必须由 AgentCodex 修复并在新 hash 上完整重跑 §6.6/§6.7，再经双路完整 re-review。当前不得 stage/commit implementation、进入 aggregate deepreview、R09 或后续 umbrella gate。
