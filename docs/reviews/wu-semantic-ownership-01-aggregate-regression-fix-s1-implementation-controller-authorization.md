# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix Slice 1 implementation Controller authorization

## 1. Entry lock

- 时间：`2026-07-18 17:08:19 +0800`。
- Slice base / HEAD：`ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`。
- Accepted-plan commit完成后worktree与staged tree均clean。当前implementation dispatch前，staged tree仍为空；worktree只包含Controller随后新建/更新的本authorization、accepted-plan commit validation与control gate tracking三个protected paths。AgentCodex必须在开始时记录其最终status/hash并全程保持不变；这些路径不属于implementation mutable scope。
- Accepted plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，SHA-256 `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714`。
- Accepted plan commit validation：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-accepted-plan-commit-controller-validation.md`。
- Gate：Slice 1 current-schema / test-oracle closure，关闭 `AR-F01`、`AR-F03`、`AR-F04`。

## 2. Exact mutable scope

只授权AgentCodex修改以下三个test owners，并新建固定implementation artifact：

```text
M tests/service/test_host_admin.py
M tests/tools/web/test_smoke_web_ci.py
M tests/host/test_public_compact_smoke.py
A docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-implementation-codex.md
```

Production、README、workflow、config、design、control、既有review artifacts与其它`tests/**`/`utils/**`全部零diff。不得stage、commit、push、PR、启动subagent/reviewer或开始Slice 2/3。

## 3. Required implementation

严格按accepted plan §2.4、§2.5、§4.1实施：

- `test_host_admin.py` fixture写出current required 12-field `wait_poller_policy`并保持原测试目标；不得给production loader加默认值/fallback。
- `test_smoke_web_ci.py`用typed module-level test harness统一包裹现有六个in-process `smoke.main`调用；snapshot/restore root与所有concrete logger状态，finally清理本次新增handler/logger entry，success/failure都证明identity/order/state恢复；standalone product logging零diff。
- `test_public_compact_smoke.py`删除candidate-id/raw guess，只用唯一current runner-call manifest的typed compaction request digest关联唯一current compact artifact；missing/duplicate/wrong/missing digest均fail closed。
- 所有新增/修改函数、类、模块遵守中文docstring和strict typing；不新增compatibility、fallback、loose scan、private mirroring或test-order依赖。

## 4. Mandatory validation and stop rules

- 运行计划§4.1 focused tests、real compactor、standalone Web与public-awaiting smokes。
- Fresh运行§6全部门禁：canonical non-coverage suite只允许已知AR-F02 import-boundary单节点失败；exact-exclusion coverage同样只允许该中间失败且九个AR-F05路径标`OPEN_BY_SEQUENCE`；其它路径不得低于80%。
- Full pyright zero；full Ruff exact-set relative toSlice base无增量且三个mutable tests零finding；build wheel/sdist；six scans；README/security/secret/deferred/no-code ledger；diff-check、staged-empty与exact allowlist。
- 读取`tests/README.md`更新约束并记录`NO_UPDATE`直接理由，不修改README。
- 若logger registry无法完整恢复、current compact schema与计划证据冲突、测试暴露production defect、需要额外path或任何stop condition触发，立即停止并保存直接证据，不扩大scope。

Implementation artifact必须记录entry/final hashes、完整命令/exit/pass-fail/coverage/build/smoke/scans、scope/README/security/deferred/no-code ledger、失败分类和Slice exit verdict。完成后停在Controller validation；不得自行发送review任务。
