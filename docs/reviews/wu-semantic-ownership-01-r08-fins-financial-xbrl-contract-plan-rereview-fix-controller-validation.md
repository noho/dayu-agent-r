# WU-SEMANTIC-OWNERSHIP-01 / R08 re-review plan-fix Controller validation

## 1. Gate identity

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 umbrella 的 overdesign remediation continuation |
| internal sub-WU | `R08` Fins Financial/XBRL contract；不是新 WU |
| gate | re-review plan-fix Controller validation |
| timestamp | `2026-07-17 04:26:31 +0800` |
| final fixed plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| final fixed plan SHA-256 | `bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251` |
| AgentCodex fix artifact | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-fix-codex.md` |
| fix artifact SHA-256 | `5d912a2e03e0284380fa0719288b993fde14be6027b36f945d4e87eb7215ef53` |
| result | **PASS / READY FOR SECOND DUAL COMPLETE PLAN RE-REVIEW** |

## 2. Accepted findings closure

### R08-RR-PF-01 — closed

- S1 正式 pytest 仍完整运行 S1-owned financial/download/registry tests，但共享 `tests/fins/test_fins_read_runtime.py` 只运行 `test_sec_fiscal_inference_consumes_countless_xbrl_contract` exact node。
- S1 coverage 对共享文件使用同一 exact node，不再收集六个 S2 normalize/dedup nodes。
- 计划明确六个 S2 nodes 必须在 S2 完整迁移、focused/coverage/full 收集；禁止 S1 提前迁移、运行、skip、xfail、改名逃收集或 compatibility shim。
- 逐 production file `>=80%`、S1 scoped green、full-pyright exact propagation ledger 等门禁保持不变。

### R08-RR-PF-02 — closed

- Forced-truncation test 固定在既有 allowlist `tests/fins/test_fins_storage_provider.py`，窄扩现有真实 `_tool_runtime(...)`，保持默认 manager 关闭行为不变。
- 显式路径复用真实 AAPL workspace、provider limits、`DefaultToolRuntimeFactory`、process-backed definitions、public `ToolDefinition.callable`、public ToolRuntime executor 与 Host-injected `fetch_more`；没有新增 Host test、mock 或私有 manager seam。
- pre-Host 必须先证明 `fact_count` 字段存在，再以直接索引断言 `fact_count == len(facts)`；post-Host 必须证明 key set 保持、除 `facts` 外所有 sibling 逐项相等、`fact_count` 原值保留，而 `facts` 单独成为 current public cursor envelope；visible prefix 与 public `fetch_more` remainder 必须重组成 pre-Host facts。
- public seam 不可观测、post key set 变化、`fact_count` 缺失/变值时，唯一行为是 stop 回 Controller；禁止改 Host、使用私有字段、mock 或实施 Issue 177。

结论：`R08-RR-PF-01..02` 为 `2/2 closed`；原 `R08-PF-01..07` 未被重开，仍为 `7/7 closed`。

## 3. Evidence correction audit

Controller 在第一版 fix evidence 中发现 `post_fact_count=None` 与 plan 要求矛盾，退回同一任务重跑完整 public shape。纠正后的直接证据显示：

- 当前 R08 实施前的 pre/post 旧 contract 都没有未来 `fact_count`，因此 `.get("fact_count")` 返回 `None` 是错误取值路径，不是 Host 删除 sibling。
- 当前真实 shape 的 pre/post key set 完全相同；Host 只把 `facts` 三项 list 替换为 visible 一项的 cursor envelope，旧 siblings `deduped_fact_count=3` 和 `total=15` 原样保留。
- public `fetch_more` 返回剩余两项，visible + remainder 与 pre-Host facts 顺序一致。

Final plan 已禁止用 `.get` 观察目标字段，要求 S2 实施后以 membership + direct indexing + complete sibling equality 重新证明真实 future contract。该纠正与既有 Controller 裁决一致：Fins 只拥有 pre-Host typed result 等式，Host cursor envelope 是独立治理层，不是第二个 Fins result。

## 4. Rejected paths and scope

- 未增加 optional-reason 私有 helper 指令；terminal validator owner 与状态机规则保持原计划表达。
- 未增加 reason frozenset 第二 checklist/owner。
- 未把 truncation 路由到 R09；Issue 177 保持 out-of-scope owner，不在 R08 实施。
- 未修改 control、design、code、tests、README、Host 或旧 artifacts；未 stage/commit/push/PR。

## 5. Validation evidence

- Final plan SHA-256 重算：`bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251`。
- Fix artifact SHA-256 重算：`5d912a2e03e0284380fa0719288b993fde14be6027b36f945d4e87eb7215ef53`。
- `git diff --check`：PASS。
- 两个 untracked artifact 分别执行 `git diff --no-index --check /dev/null <path>`：零 whitespace/error diagnostic；exit `1` 只表示预期内容 diff。
- staged paths：空。
- Controller scans 确认 S1 formal node selection、S2 full-node ownership、direct-index sibling assertions、stop rule 和 rejected-path absence 均已写入 final plan。

## 6. Handoff

下一 gate 是 AgentMiMo / AgentDS 对 final fixed SHA `bb37b88b...0251` 的第二次并发完整 plan re-review。两路必须复核原七项与新两项 closure、完整 public-shape evidence、整份计划的 owner/slice/LLM/test/scope 一致性；不能只看最后两处 diff。两路 re-review 与 Controller adjudication 全部通过前，不授权 implementation、commit、R09-R12、deferred Issue、统一 authorization、push 或 PR。
