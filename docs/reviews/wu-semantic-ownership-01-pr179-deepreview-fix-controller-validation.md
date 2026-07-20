# WU-SEMANTIC-OWNERSHIP-01 PR179 deepreview fix Controller validation

## Scope lock

- Finding：`PR179-DR-F01`，来源与裁决见 `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-controller-adjudication.md`。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-fix-codex.md`，133 lines，SHA-256 `b4d0f19c8330017f969ad5d3bfff043e3bfc969ebaec30f33e3e8ced6e0c7d4e`。
- Production/test exact paths：`dayu/host/tool_runtime.py`、`tests/host/test_toolruntime_executor.py`。
- Production + test binary diff SHA-256：`810bfb9cc01728cc98725177b613b29cc6483be22f5d833a1fcbf627d8aab6ba`。
- 最终文件 SHA-256：
  - `dayu/host/tool_runtime.py`：`f376dfe547f5f72c314fe018b28f49b5bdf504476b72484602eed3ba04ec28ea`。
  - `tests/host/test_toolruntime_executor.py`：`d73a69e900baaf619004c061f18c62288783026ea8258fb699ab9370cc80c8b3`。
- Controller/control/reviewer artifacts 均保持各自 owner；staged tree 为空，没有 commit 或 push。

## 独立代码复核

Controller 逐行复核 production/test diff，结论为 PASS：

1. 已删除 `_TOOL_RUNTIME_GOVERNED_ERROR = "host_tool_governed_error"`，production 无剩余引用。
2. `_governed_failure_outcome()` 在构造 `ToolFailedOutcome` 前复用 `_validate_policy_decision_fields()`；`None`、空字符串、纯空白 message 以及缺失 reason 均 fail closed。
3. `ALLOW` 与 `REUSE` 都不是 failure decision，误入此 projection boundary 时显式失败；`HINT`、`REQUIRE_JUSTIFICATION`、`HARD_STOP` 与 `GOVERNED_ERROR` 等合法 governed-failure 类别仍使用自己的非空业务 message。
4. outcome message 只取已验证的 `policy_decision.message`；reason code 仍留在 Host internal governance，不被重解释成业务文本。
5. 没有在 Tool Trace、audit、Memory、RunInput、Compact、renderer 或 schema 下游增加 blacklist、normalization、fallback 或 shim。
6. 对抗测试同时验证即时 outcome owner 与 `ToolAcceptGovernance` accept/audit 构造边界；malformed decision 没有 outcome 或 accepted fact 可供持久化与 LLM projection。

## Controller fresh validation

所有命令均在 `source .venv/bin/activate` 后由 Controller 独立运行：

- Focused adversarial：`6 passed, 62 deselected`。
- ToolRuntime owner aggregate：`179 passed`。
- Accepted-result projection + Phase 6 integration：`37 passed`。
- Coverage：`162 passed, 17 deselected`；`dayu/host/tool_runtime.py` `1993 statements / 299 missed / 85%`，满足修改生产文件 `>=80%`。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- Scoped Ruff：`All checks passed!`。
- `git diff --check`：PASS。
- staged tree：空。
- Production scan `host_tool_governed_error|_TOOL_RUNTIME_GOVERNED_ERROR`：零命中。
- Host reason-as-message / message fallback scan：零命中。

Coverage 命令排除 17 个 process 节点，是因为 macOS spawn 与 pytest-cov 注入组合会改变 multiprocessing function identity；同一 17 个节点已包含在无 coverage 注入的 `179 passed` owner aggregate 中。该验证工具限制不属于 product finding，也未用 skip/xfail 修改测试。

## README、安全与边界

- 已核对 `dayu/host/README.md` 与 `tests/README.md` 更新约束。本 fix 不改变公共接口、状态机、装配、用户工作流或测试分层，README 无需修改。
- Config 与 Host internal SQLite/EventLog 仍是 trusted-local domain；本 fix 只阻止内部治理码成为 LLM-readable message。
- 未实现统一 tool authorization framework；未设计 permission schema / DSL、role/capability 或 sandbox。
- Web private/custom port 默认 allow、DNS/peer/resource budgets、filesystem containment、symlink/no-follow、atomic write、process fencing 均未修改。
- Issue 142、151、175、177、178 与既有 Web/WeChat/render trackers 能力均未偷带。

## Gate result

- `PR179-DR-F01`：implemented / Controller-validated / pending dual PR re-review。
- New finding：0。
- Blocker：0。
- Open design question：0。
- Unclassified residual：0。
- Correct next gate：AgentMiMo / AgentDS 对完整 PR diff 并发 re-review，特别验证 malformed policy decision 的 fail-closed 传播、合法 governed kinds 行为、无下游 shim 与安全/no-code/deferred boundaries。不得 commit、push、merge 或 mark ready。
