# WU-SEMANTIC-OWNERSHIP-01 / R02-S2 plan drift Controller 裁决

## 1. 裁决身份与真源

本 artifact 由 umbrella Controller 在 `R02-S2 implementation` stop condition 触发后写入。当前工作仍是既有 `WU-SEMANTIC-OWNERSHIP-01` 的 overdesign remediation continuation；`R02` 与 `R02-S2` 都不是新的 work unit。

裁决依据按优先级为：

1. `AGENTS.md` 的语义 owner、禁止兼容 shim、测试与验证约束；
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` 的 Topic 2 产品裁决；
3. `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md` 的 accepted R02 contract；
4. 当前代码与真实 smoke 的直接证据；
5. `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s2-implementation-codex.md` 的 stop artifact。

## 2. 直接证据与根因

AgentCodex 已把 `_request_with_safe_redirects` 的 `transport_policy` 收紧为无默认值的必填 named parameter，并完成 Web fetch/search production caller 的传播。真实本地 smoke 中 Playwright、tool fetch、Docling 与 assembly path 成功，但下列三个 raw diagnostics cases 在 artifact 生成前失败：

- `local-html-requests`；
- `local-pdf-requests`；
- `local-challenge-control`。

稳定复现为：

```text
TypeError: _request_with_safe_redirects() missing 1 required keyword-only argument: 'transport_policy'
```

直接 caller 是 `utils/diagnose_web_access.py:_build_requests_profile`。它仍调用已经收紧的 orchestrator contract，却未传递 transport snapshot；对应 deterministic fake 位于 `tests/tools/web/test_diagnose_web_access.py`。

根因不是网络、Playwright、预算或环境不稳定，而是 accepted plan 自身的 allowlist / sequencing 矛盾：

- §4.3 与 §9.2 要求在一个原子 diff 内迁移全部 fetch/search callers，且不得留下 half-migrated caller；
- §6.3 却把 diagnostic utility 与其直接测试仅列入 S3，遗漏了这个已存在的 S2 direct consumer；
- §15.3 同时要求出现新的 production/test allowlist drift 时 stop 回 Controller。

因此 `R02-S2-DR-01` 是成立的 material plan drift。它不是可以接受到 S3 再修的临时破坏：slice 必须形成可独立验证的行为闭环，且 diagnostics v2/challenge 是 Topic 2 明确保留的产品行为。

## 3. Controller disposition

### R02-S2-DR-01 — accepted / plan-fix-required

精确接受以下时序修正：

- 将 `utils/diagnose_web_access.py` 前移到 S2，但只允许迁移 raw requests diagnostic direct caller 的 mandatory `transport_policy` 传播；
- 将 `tests/tools/web/test_diagnose_web_access.py` 前移到 S2，但只允许同步上述 direct caller fake/signature，并新增或收紧 owner-level 断言；
- transport 值必须从既有 Web provider parser owner 产生的 typed config snapshot 派生；utility 不得复制 `dns_peer_proof_enabled` / `allow_environment_proxy` 默认字面值、重写 raw parser、读取环境变量推导 policy，或构造第二套 transport defaults；
- 同一个 raw config input 必须交给既有 parser owner；utility 只消费其 typed `WebHttpTransportPolicy` projection。不得以 `getattr`、兼容 default、wrapper、loose parse 或 test shim 补偿；
- S2 validation 必须新增 diagnostic direct-node 测试，并运行完整 `tests/tools/web/test_diagnose_web_access.py`，证明 raw requests diagnostics、challenge artifact 与 retained v2/revision 2 contract未被 mandatory signature 迁移破坏；
- S2 deterministic local smoke 必须重跑到 exit 0，不能把三个 `artifact_missing` 归为环境失败。

本裁决不接受以下范围：

- 不前移 S3 的 storage-state lifecycle / CLI / TTL / owner filename / publish / reconcile 删除；
- 不前移 S3 的 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS`、`--max-network default=80` 或 DiagnosticResourceBudget 同源改造；
- 不改变 diagnostic ordinary artifact writer、profile schema、challenge detector、browser storage input 或 containment 行为；
- 不修改 `utils/smoke_web_ci.py`、`utils/diag_web_batch.sh`、根 README、Issue 178、R03、proxy credential schema或统一 tool authorization framework；
- 不新增 public permission/config framework，也不为这次传播创建 speculative abstraction。

## 4. Gate 与验证裁决

当前 implementation diff 与 stop artifact全部保留，不删除、不回滚。因为这是 accepted production/test allowlist 的 material修正，不能由 implementation Agent直接越界编码；先回到 narrow plan-fix gate：

1. AgentCodex 修改 R02 plan 的 §4.3、§6.1-6.3、§9.4-9.7、§13-15 与 completion要求，使 direct consumer、测试、smoke和 stop rule一致，并写 plan-drift fix artifact；
2. Controller 验证 plan fix；
3. AgentMiMo / AgentDS 对同一 immutable plan target 并发完整 re-review；
4. Controller 裁决 re-review；
5. 仅在双路闭合后恢复同一个 `R02-S2 implementation`，由 AgentCodex继续修复现有未提交 diff。

恢复 implementation 后至少必须通过：

- S2 provider focused/full tests；
- diagnostic direct-node与完整 `test_diagnose_web_access.py`；
- deterministic local Playwright/diagnostics smoke exit 0、零 local skip/failure；
- 所有 changed production `.py` 精确 coverage `>=80%`；`utils/**`虽免coverage，行为测试与真实smoke不可省略；
- 完整 pyright、`git diff --check`、challenge detector零diff、allowlist/source/propagation/docstring scans；
- README trigger复核。

## 5. 当前结论

`R02-S2-DR-01` 已裁决为 `accepted / plan-fix-required`。当前没有新的产品问题需要用户裁决；Topic 2 真源未矛盾。下一 gate 是同一 R02-S2 的 narrow plan-drift fix，不是新 WU、不是新 feature，也不进入 S3。
