# WU-SEMANTIC-OWNERSHIP-01 R08 累积代码审查 Controller 裁决

## 1. 裁决对象

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`
- umbrella 内部 remediation sub-WU：`R08`
- gate：S1+S2 累积 immutable code review
- accepted final plan SHA-256：`87cc332828640de8b4cb4550f29251894111ef3471621bebbef828b66a3ce23d`
- review lock：tracked `git diff --binary` SHA-256
  `4d346f2bd05d26673ed0a1ec680cd6a1fe68d976340dfea302c55ad912354d4b`
- S1 implementation artifact SHA-256：
  `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748`
- S2 implementation artifact SHA-256：
  `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648`
- AgentMiMo review：
  `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-review-mimo.md`
  （SHA-256 `6eb9db547c4114144f9c54688f239a18000fee277fadbcac4453549edd0042c3`）
- AgentDS review：
  `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-review-ds.md`
  （SHA-256 `21591800ebe714616d21c4d807434b9ed1d2086dae0cf386f3908978d52ba4a0`）

两路 reviewer 均独立重算并匹配三项 review lock。Controller 在 reviewer artifact
落盘后再次重算，tracked implementation hash 与 S1/S2 artifact hash 均未漂移。

## 2. 总结论

**REQUIRES CODE-REVIEW FIX**。

- reviewer 报告：MiMo 17 项（0 个 R08-scope blocking finding），DS 7 项；
- Controller accepted reviewer finding：0；
- Controller 独立 accepted finding：1；
- accepted finding 总数：1；
- blocker / 设计真源冲突：0；
- deferred finding：0。

核心 product contract、producer/public owner、optional reason、flat query params、唯一
`fact_count`、Host truncation composition、R07 no-touch、安全与 deferred boundaries
已经通过当前证据。但测试 diff 违反 accepted final plan 的精确 symbol boundary，并固化
与 R08 无关的 generic/compatibility 行为；因此当前 cumulative tree 不能进入 aggregate
deepreview 或 accepted commit。

## 3. Accepted finding

### R08-CR-CF01（HIGH）— `test_fins_read_runtime.py` 越过固定 symbol boundary

#### 直接证据

accepted final plan §5.1 明确规定：

1. S1 只允许迁移 `_extract_fiscal_from_xbrl_query` import、专用
   `_FiscalXbrlProcessor` fixture 和一个 fiscal node；
2. S2 只允许迁移 `_normalize_xbrl_query_payload` import 与既有六个
   normalize/dedup nodes；
3. 两个 step 都不得修改 generic LRU、form matching nodes，共享 import 只能作上述
   symbols 的直接机械调整。

当前 `tests/fins/test_fins_read_runtime.py` 另外新增了 4 个 plan 外节点：

- `test_read_helper_document_discovery_rules_preserve_public_semantics`
- `test_search_next_section_owner_ranks_exact_hits_per_query`
- `test_table_data_projection_owner_emits_self_describing_shapes`
- `test_navigation_and_xbrl_default_rule_owners_fail_closed`

并为这些节点新增 `_build_table_data_payload`、`_normalize_document_types`、
`_normalize_periods`、`_normalize_section_children`、`_normalize_taxonomy_name`、
`_resolve_default_xbrl_concepts`、`build_search_next_section_fields`、
`resolve_document_type_for_source`、`resolve_has_financial_data` 等 imports。

其中第一个节点还显式锁定 `availability`、
`has_structured_financial_statements`、`has_financial_statement_sections`、
`has_financial_statement`、`has_xbrl` 等与 R08 financial/XBRL result contract 无关的
既有兼容/投影分支。它们不是当前 changed semantic owner 的 contract evidence。

Controller 在 implementation 期间允许为 coverage closure 使用 S1/S2 test path
allowlist；该路径级许可不 supersede final plan 对此共享文件的更严格 symbol boundary，
也不授权 unrelated coverage padding。accepted plan §6.6/§6.7 的 `>=80.00%` 验证目标
不能反向扩大产品或测试语义范围。

#### Root owner

- test diff owner：`tests/fins/test_fins_read_runtime.py`
- R08 read-side changed owner：
  `dayu/fins/tools/read_runtime_helpers.py::_normalize_xbrl_query_payload`
- authoritative boundary：accepted final plan §5.1、§6.6、§6.7 与 AGENTS.md
  owner-level testing / no compatibility-shim 约束。

#### 必须修复

1. 删除上述 4 个越界节点及其专用 imports。
2. 证明共享文件 diff 只包含 plan 允许的 fiscal node、六个 normalize/dedup nodes
   与直接机械 import 调整；不得改 generic LRU/form matching nodes。
3. 不得把相同的 generic/compatibility assertions 搬到其它 test allowlist 文件。
4. 若删除后 changed-file coverage 下降，只能通过 R08 实际 changed owner 的 public
   processor contract、producer exact contract、public projection、normalize/dedup、
   real Host composition 或与本轮 changed owner 直接同源的稳定业务规则补齐；不得使用
   fake-only padding、private cache/method、偶然顺序、skip/xfail、pragma/omit、阈值豁免
   或扩大 production allowlist。
5. 完整重跑 accepted plan §6.6/§6.7；15 个实际 changed production Python 文件仍须
   exact-key `>=80.00%`，full pyright/changed Ruff/source scans/diff check/smokes 必须重跑。
6. fix 会使当前 Controller validation、review lock 和两路 review 全部失效；修复后必须
   产生新的 cumulative implementation/fix artifact、Controller validation 与两路完整
   cumulative re-review。

若在不违反上述边界的情况下无法保持逐文件 coverage 目标，立即 stop 回 Controller；
不得自行弱化 plan 或扩大 scope。

## 4. AgentMiMo findings 裁决

| Finding | 裁决 | 证据与理由 |
|---|---|---|
| F-01 duplicate JSON helpers | REJECT / NO FIX | 两个自包含 domain contracts 各自拥有 exact-key/JSON validation；当前只有两个消费者。抽第三个共享模块会增加耦合，没有 correctness drift 证据。 |
| F-02 XBRL data-quality string guard | REJECT / NO FIX | 与两个允许字面量比较会自然、精确拒绝非字符串；显式 `isinstance` 不改变 contract。 |
| F-03 `_resolve_processor_taxonomy(processor: object)` | REJECT / PRE-EXISTING | 该签名在 `HEAD` 已存在，当前 diff 零变更；不是 R08 引入，也不是当前 owner propagation 必需修改。 |
| F-04 XBRL double copy | REJECT / NO FIX | helper 的 normalization input copy 与 public builder 的 output ownership copy 属于不同边界，共同证明输入/输出容器不 alias；删除任一不是当前 correctness 修复。 |
| F-05 fiscal-period return type | REJECT / NO FIX | 字段缺席合法返回 `None`；normalize helper 仍声明 optional，后置 guard 是 fail-closed type narrowing，不是 dead compatibility。 |
| F-06..F-10 | REJECT / PRE-EXISTING OR OUT OF SCOPE | 所列 `Any`/`object`/logging 代码均非 R08 新增语义；full pyright 为零，没有当前传播错误。不得以 cleanup 名义越界。 |
| §6.3 private test access observation | REJECT / NO CURRENT FINDING | reviewer 自身确认 snapshot/cache tests 没有公开观察面，且这些节点不是本轮新增的 compatibility fix。 |

MiMo 的 product-contract PASS 证据保留；其总 verdict 不覆盖 Controller 独立发现的
`R08-CR-CF01`。

## 5. AgentDS findings 裁决

| Finding | 裁决 | 证据与理由 |
|---|---|---|
| FS-DS-01 two files just above 80% | REJECT / NO FIX | accepted gate 是每个 changed file `>=80.00%`，不是 100%。reviewer 未提供未覆盖分支已产生错误的直接证据；不得因阈值余量小发明额外测试范围。 |
| FS-DS-02 invariant RuntimeError | REJECT / NO FIX | `_get_statement_from_xbrl` 的每个 `None` result 分支都返回 typed reason；该 guard 只暴露内部 invariant 破坏。改为可被 `-O` 删除的 `assert` 会弱化 fail-closed，改为 `statement_not_found` 会掩盖 producer bug。 |
| FS-DS-03 intermediate fallback reason | REJECT / DESIGN INTENT | accepted plan 要求唯一 terminal business reason，不公开或累积中间尝试 diagnostics；没有当前 residual。 |
| FS-DS-04 dedup normalized/raw inputs | REJECT / NO FIX | normalized fact 提供公开 canonical fields，raw fact 仅提供未公开但去重必需的 `period_start`/segment/dimensions；docstring 与 tests 已明确该分工，没有两真源冲突证据。 |
| FS-DS-05 TypedDict in-place optional reason | REJECT / NO FIX | Python/pyright 均支持 `NotRequired` key 的受控赋值；full pyright 为零。一次性重构仅是风格偏好。 |
| FS-DS-06 `financials` protocol parameter | REJECT / PRE-EXISTING | 参数和 Protocol 不是 R08 新增；删除会扩大公共 processor signature scope。 |
| FS-DS-07 description punctuation | REJECT / NO FIX | description 已自足列出字段/类型/必填性/枚举/示例并通过 owner tests；无 LLM 误行为证据。 |

DS 的 product-contract、truncation、R07 no-touch、安全/deferred boundary PASS 证据保留。

## 6. 安全与 deferred 边界

- 本裁决不删除 filesystem containment、symlink、snapshot/revision/citation、atomic
  publication 或 Host truncation/fetch-more 安全/治理机制。
- 不实施统一 tool authorization framework。
- 不实施 R09-R12、Issues 142/151/175/177/178 或其它 deferred 能力。
- 不修改 R07 snapshot acquire/borrow/release、cache/revision、citation 或
  source-changed owners。

## 7. Next gate

AgentCodex 执行 `R08-CR-CF01` cumulative code-review fix，完整重验证并写 fix artifact；
随后 Controller 独立复核新 tree/hash/测试/coverage，再由 AgentMiMo 与 AgentDS 对完整
S1+S2+fix 累积 tree 并发 re-review。aggregate deepreview、accepted implementation
commit、R09-R12 与 umbrella closeout 均未获授权。
