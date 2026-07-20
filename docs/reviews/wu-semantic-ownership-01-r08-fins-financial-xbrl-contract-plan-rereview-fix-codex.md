# WU-SEMANTIC-OWNERSHIP-01 / R08 fixed-plan re-review fix — AgentCodex

## 1. Gate identity

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 umbrella |
| internal sub-WU | `R08` Fins Financial/XBRL contract；不是新 WU |
| gate | fixed-plan re-review accepted findings fix |
| timestamp | `2026-07-17 04:15:11 +0800` |
| Controller evidence follow-up timestamp | `2026-07-17 04:23:01 +0800` |
| source plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| authoritative adjudication | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-controller-adjudication.md` |
| before plan SHA-256 | `07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5` |
| follow-up input plan SHA-256 | `361b92cb1484adc9a5f47e5d60ce9c963411f7cc348216434cca18332310209d` |
| follow-up input artifact SHA-256 | `21d3cffe4dfc4ee375302271da1ae153d47dc27443693ba4cf5b27804e0b0402` |
| after plan SHA-256 | `bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251` |
| result | **FIX COMPLETE / PLAN REVIEW PASS / READY FOR CONTROLLER VALIDATION** |

本 gate 只修 Controller accepted 的 `R08-RR-PF-01..02`，不是新 WU，不重开 `R08-PF-01..07`，也不进入 implementation。问题动机成立：S1 正式命令确实把共享文件的六个 S2 consumer nodes 提前收集；forced-truncation 计划也确实缺少 current-tree 可执行构造。这两项都会让 implementation/review gate 错误归责或无法验收，不是文案偏好。

## 2. Reviewed target、scope 与 assumptions tested

### 2.1 Reviewed target and scope

- 唯一 plan target：`docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`。
- 唯一裁决真源：上述 Controller adjudication。
- 唯一 accepted fix scope：S1 pytest/coverage symbol slice；S2 forced-truncation 真实 provider/ToolRuntime 构造。
- 本 gate authored paths 只有 target plan 与本 artifact。

### 2.2 Assumptions tested

| assumption | 直接证据与结论 |
|---|---|
| Controller 锁定的 plan 就是当前输入 | 修改前本地 SHA-256 为 `07268a12...ecde5`，与 adjudication 完全一致。 |
| S1 正式命令会错误运行 S2 nodes | 修改前 §5.4 的 pytest 与 coverage 都传入整个 `tests/fins/test_fins_read_runtime.py`；§5.1 同时把六个 normalize/dedup nodes 明确归 S2，冲突成立。 |
| 当前 allowlist 有真实 pre-Host 观测 seam | `tests/fins/test_fins_storage_provider.py` 的真实 provider `ToolDefinition.callable` 可返回进入 Host 前的 completed business value，无需 patch callable 或 mock processor/read。 |
| 当前 allowlist 有真实 Host truncation/fetch_more seam | 现有 `_tool_runtime(...)` 使用 `DefaultToolRuntimeFactory(EffectiveToolBundleBuilder())`、process-backed definitions 与 `_AcceptingPort`；显式启用 `FrameworkToolName.FETCH_MORE` 和 manager 后可通过公开 executor 观察 cursor envelope 与 fetch-more remainder。 |
| provider config 能稳定强制截断 | `query_xbrl_facts_max_items` 是 provider `limits` 的正整数配置并直接形成 `facts` 的 `LIST_ITEMS` `ToolTruncateSpec`；真实 fixture 当前返回 3 条 facts，limit 1 得到 visible 1 + remainder 2。正式测试只断言 facts 数大于命名 limit，不冻结 3。 |
| `post_fact_count=None` 是否说明 Host 删除 sibling | 否。完整公开 shape 显示 `fact_count` 在当前 pre/post 两边都不存在；此前 `.get("fact_count")` 返回 `None` 是取值路径错误。当前旧 contract 的 `deduped_fact_count=3` 与 `total=15` 在 Host 替换 `facts` 前后均原样保留，顶层 key set 完全相同。 |
| 无需 Host/private seam 才能验证 owner 分离 | 公开 effective bundle 可证明 `fetch_more` 由 Host 注入；公开 completed envelope 的 cursor/scope-token 可经同一 executor 调用 `fetch_more` 并逐项重组原 facts。正式测试可用字段存在性、直接索引、pre/post key-set 与非 `facts` sibling 等式证明未来 `fact_count` 被保留，无需访问 manager cursor 表、私有 helper/constants、digest 或 raw accept payload。 |

## 3. Accepted findings closure

### R08-RR-PF-01 — closed

| 项 | 修复前 | 修复后 |
|---|---|---|
| plan 位置 | §5.4 修改前 lines 413-415 | §5.1 line 374；§5.4 lines 412-422；§9 line 734 |
| 正式 pytest | 运行整个共享 `test_fins_read_runtime.py` | 只运行 `test_sec_fiscal_inference_consumes_countless_xbrl_contract` exact node；其余 S1 files/registry 保持完整运行。 |
| 正式 coverage | 收集整个共享文件 | 对共享文件使用相同 exact fiscal node selection。 |
| S2 ownership | 六个 normalize/dedup nodes 虽声明归 S2，却会在 S1 被收集 | 明确六个 nodes 只由 S2 完整迁移、focused/coverage/full 收集与验收；禁止 S1 收集、`skip` / `xfail`、删/改名逃收集、compat fixture 或 production shim。 |

Closure 判定：S1 正式测试与 coverage 不再把预期的 S2 consumer propagation 误报成 S1 failure；S2 的六个 nodes 没有被削弱、提前迁移或绕过。

### R08-RR-PF-02 — closed

| 项 | 修复前 | 修复后 |
|---|---|---|
| plan 位置 | §6.4 修改前 lines 534-545；§6.5 lines 561-563 | §6.4 lines 543-553；§6.5 lines 570-592；§9 line 752 |
| 真实构造 | 只写抽象 `forced-truncation path` | 固定在现有 allowlist `tests/fins/test_fins_storage_provider.py`，把 `_tool_runtime(...)` 窄扩为含严格类型 `extra_config` / `enable_truncation_manager` keyword-only 参数且保持默认行为，复用真实 provider、factory、process capsule 与 accept port。 |
| 强制条件 | 未说明如何稳定超限 | 命名 `_FORCED_XBRL_MAX_ITEMS = 1`，经 provider `limits.query_xbrl_facts_max_items` 投影；先断言真实 pre-Host facts 数大于 limit。 |
| pre-Host owner | 只要求等式，没有观测点 | 先通过真实 provider `ToolDefinition.callable` 捕获 typed public value；先断言 `"fact_count" in pre_value`，再以直接索引断言 exact contract 与 `pre_value["fact_count"] == len(pre_value["facts"])`，保存完整 value/facts 副本。禁止用 `.get` 混淆字段缺失。 |
| Host owner | 只概括 cursor/fetch_more 仍属 Host | 再经启用 manager 的真实 ToolRuntime，证明 provider bundle 不定义而 Host effective bundle 注入 `FrameworkToolName.FETCH_MORE`；断言 pre/post 顶层 key set 相同、除 `facts` 外全部 sibling 逐项相等、`post_value["fact_count"] == pre_value["fact_count"]`，并经同一 executor 的 `fetch_more` 将 visible prefix + remainder 逐项还原为 pre-Host facts。 |
| private/越界路径 | 未具体禁止测试如何取证 | 明确禁止 `.get("fact_count")`、mock/monkeypatch、私有 manager/cursor 表、私有 envelope helper/constants、digest/raw accept payload、Host 修改、Issue 177 实施和 R09 routing；post key set 改变、`fact_count` 缺失/变值或 public seam 不可观测即 stop 回 Controller。 |

Closure 判定：forced-truncation 组合验证已是 current-tree code-generation-ready 机制，且 Fins typed value 与 Host cursor/fetch_more 的语义 owner 保持分离。

## 4. Adversarial review lenses

- **Architecture boundary review**：pre-Host business callable 只证明 Fins public contract；post-Host executor 只证明 Host governance envelope/fetch_more。`fact_count` 的存在与等式在 pre-Host owner 证明，Host 层只证明该 sibling 未被目标字段替换影响；计划不要求 Fins 解析 Host envelope，也不把 Host cursor 变成财报事实。
- **Best-practice review**：使用真实 fixture、真实 provider config、真实 process-backed ToolRuntime 和公开 outcome；测试条件基于“facts 数大于 limit”而非冻结 fixture 恰有三条，具备可维护性。
- **Optimal-solution review**：窄扩既有 `_tool_runtime(...)` 且保持默认关闭，比新增 Host test、复制 factory 装配或 mock 截断更小；现有 allowlist 足以完成取证。
- **Overengineering review**：没有新增 production protocol、builder、adapter、cursor abstraction 或第二 contract；测试只增加一个命名 limit、一个 exact node 与 helper 显式参数。
- **Overcoupling review**：provider business bundle 不拥有 `fetch_more`，Host effective bundle 注入事实单独断言；pre/post 两段只以公开 ToolDefinition/ToolRuntime contract 相接，没有跨层私有状态耦合。

未发现超出 Controller 两项 accepted findings 的新 material finding。

## 5. Rejected / no-fix paths absence

| Controller 已拒绝意见 | 本 fix 处置 |
|---|---|
| optional-reason 私有 helper 指令 | 未加入 `_required_financial_reason` / `_required_xbrl_reason` 的保留、重命名、替换或 key-check 指令；§4.1/§4.2 既有 terminal validator contract 不变。 |
| reason frozenset 额外 checklist | 未新增 reason frozenset checklist、第二值集 owner 或实现步骤；既有 reason 闭集与 owner tests 不变。 |
| 把 truncation routing 跟踪到 R09 | 未接受。计划明确禁止 R09 truncation routing；R09 仍是 wait poller，Issue 177 仍是 out-of-scope 既有跟踪，不在 R08 实施。 |

同时未修改 Host、control、design、code、tests、README 或旧 artifacts，未实施 Issue 177，未进入 implementation。

## 6. Open questions and residual risks

### Open questions

无。current-tree 公开 seam 已通过完整 shape 探测；`fact_count` 当前缺席是 R08 尚未实施的旧 contract 事实，不是 Host 删除 sibling，也不与 Controller 裁决冲突。若 implementation 时 post key set 改变、`fact_count` 缺失/变值或 seam 漂移为不可观测，plan 已给出唯一 stop 条件并要求回 Controller，不授权替代私有路径。

### Residual risks and tracking destination

- Host 截断 `facts` 后不会原子改写 sibling `fact_count`；本 R08 只验证 pre-Host Fins 等式及 post-Host owner 分离，不宣称 envelope 是第二个 Fins result。该既有 generic truncation 能力风险继续由 Issue 177 跟踪，不路由 R09，也不在本 gate 实施。
- 新 fixed plan 仍须由 Controller validation 锁定 SHA，再由 AgentMiMo / AgentDS 对整份 plan 做 complete re-review；本 artifact 不能替代后续 gate。

以上均不是本次 plan-fix blocker。

## 7. Scope and validation evidence

### 7.1 Before/after plan identity

- Before：`07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5`，757 lines。
- First fix / follow-up input：`361b92cb1484adc9a5f47e5d60ce9c963411f7cc348216434cca18332310209d`，770 lines。
- Final after evidence correction：`bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251`，770 lines。
- `R08-RR-PF-01..02`：`2/2 closed`。

### 7.2 完整 public outcome shape 与判定

重跑只读取三份公开 `ToolCompletedOutcome.result.value`，没有读取 accept candidate、manager、cursor store、digest 或私有 envelope helper。公开 shape 如下；cursor/scope token 的随机字符串只按公开 opaque string 类型记录：

```text
PRE_HOST_TOOL_COMPLETED_RESULT_VALUE
{
  citation: {
    accession_no, document_id, filing_date, fiscal_period, fiscal_year,
    form_type, source_provider, source_type, ticker
  },
  data_quality: "xbrl",
  deduped_fact_count: 3,
  document_id: "fil_0000320193-24-000123",
  facts: [
    {concept, content_type, decimals, fiscal_period, fiscal_year, label,
     numeric_value, period_end, period_start, period_type, scale,
     statement_type, text_value, unit},
    {同一完整字段集；2023 period/value},
    {同一完整字段集；2022 period/value}
  ],
  query_params: {
    concepts, fiscal_period, fiscal_year, max_value, min_value,
    period_end, statement_type
  },
  reason: null,
  ticker: "AAPL",
  total: 15
}

POST_HOST_TOOL_COMPLETED_RESULT_VALUE
{
  citation: <与 pre 完整相等>,
  data_quality: "xbrl",
  deduped_fact_count: 3,
  document_id: "fil_0000320193-24-000123",
  facts: {
    fetch_more: {cursor: <opaque string>, scope_token: <opaque string>},
    truncated: true,
    value: [<pre facts[0] 完整对象>]
  },
  query_params: <与 pre 完整相等>,
  reason: null,
  ticker: "AAPL",
  total: 15
}

FETCH_MORE_TOOL_COMPLETED_RESULT_VALUE
[
  <pre facts[1] 完整对象>,
  <pre facts[2] 完整对象>
]
```

精确 field matrix：

```text
pre_keys  = citation|data_quality|deduped_fact_count|document_id|facts|query_params|reason|ticker|total
post_keys = citation|data_quality|deduped_fact_count|document_id|facts|query_params|reason|ticker|total
pre/post "fact_count" membership = false / false
pre/post deduped_fact_count       = 3 / 3
pre/post total                    = 15 / 15
visible/remainder                 = 1 / 2
fetch_more absent from provider bundle / injected by Host = true / true
```

判定：先前 `post_value.get("fact_count") is None` 不是 Host public contract 删除或包裹 sibling，而是当前 R08 实施前 pre/post value 都没有未来字段 `fact_count`；使用 `.get` 把“字段不存在”误写成了可比较值。公开 shape 直接证明 Host 只替换目标 `facts`，其它顶层 sibling 与 key set 保持不变。修正后的 plan 要求 implementation 后先证明 pre-Host `fact_count` 存在，再通过直接索引和完整 sibling 等式证明 post-Host 保留它；若实际不成立即 stop 回 Controller。

### 7.3 No-index diff check

| 对象 | 命令 | 结果 |
|---|---|---|
| fixed plan | `git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` | `PASS`：零 whitespace/error diagnostic；exit `1` 只表示 untracked 文件与 `/dev/null` 存在预期内容 diff。 |
| 本 fix artifact | `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-fix-codex.md` | `PASS`：零 whitespace/error diagnostic；exit `1` 只表示 untracked 文件与 `/dev/null` 存在预期内容 diff。 |

### 7.4 Worktree boundary

开始时已有用户 worktree 状态：`docs/host/issues-implementation-control.md` 为 tracked modified；R08 plan、旧 plan/re-review/controller artifacts 为 untracked。本 gate 不覆盖或误认这些既有状态。本次 authored content delta 只有：

```text
docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-fix-codex.md
```

未 stage、commit、push 或创建 PR。未运行 implementation tests、coverage、pyright 或 Ruff：本 gate 没有代码/测试修改，且明确禁止进入 implementation。follow-up 只读 probe 使用当前 `.venv`、真实 AAPL fixture 与真实 ToolRuntime，完整输出上述三份公开 `result.value`；该 probe 不写产品或测试文件。其它受保护文件的 SHA-256 在 follow-up 前后保持不变。

## 8. Final plan review conclusion

**`pass`**。两项 Controller accepted plan finding 已按最小 owner boundary 完整关闭；无新 material finding、open question 或 product blocker。停止在 Controller validation，不进入 implementation。
