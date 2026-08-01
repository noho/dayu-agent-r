# S5/F13 Plan Amendment Review — Independent Adversarial Review

## 0. Review 元数据

- **Review 类型**：plan amendment review（独立 adversarial review）
- **Reviewed target**：
  - `docs/reviews/wu-cli-interactive-02-s5-f13-plan-amendment-proposal-codex.md`（amendment proposal）
  - `docs/host/wu-cli-interactive-02-conformance-fixes-plan.md` 中与 S5/F13 相关的修订（§9.1、§9.3、§9.6、§10.5、§13）
- **Work unit**：`wu-cli-interactive-02-conformance-fixes`
- **Slice / finding**：S5 / F13
- **基线 HEAD**：`331d38dcaeebe3a929b7fa52d4e161a1c6504c55`（已验证）
- **分支**：`codex/interactive-oracle`
- **Review 时间**：`2026-08-01T21:42:15+08:00`
- **Review 方法**：独立执行 repo-wide `rg` inventory（不依赖 MiMo 输出），逐条验证 amendment proposal 声称的构造闭包数据、CR 文件清单、安全 identity 规则与 validation closure
- **Review artifact**：`docs/reviews/plan-rereview-wu-cli-interactive-02-s5-amendment-ds-20260801.md`
- **Completion status**：`review complete / pass-with-minor-observations`

## 1. Review scope 与 focus

本次 review 的 scope 严格限定为：

1. Amendment proposal 声称的 35 FA / 19 files、4 OA / 3 files、7 CR files 是否与 HEAD 实际一致
2. 25-file 去重机械闭包是否全面（无遗漏、无多余）
3. Plan §9.1 的 allowed-file 修订是否正确覆盖全部机械变更点
4. Test identity 规则（§9.3 + amendment §3.2）的语义正确性与安全性
5. present/unavailable 配对在类型层面的安全性
6. §10.5 validation closure 是否覆盖全部机械闭包文件
7. Amendment 的 7 项 plan 修改是否均已在目标 plan 中正确落地
8. F13 frozen scope 一致性：无 scope creep、无 goal drift

不 review：S1-S4 implementation、G01-G07、MiMo 输出、真实 provider continuity evidence（G06）。

## 2. Assumptions tested

| # | Assumption | 验证方法 | 结果 |
|---|---|---|---|
| A1 | 35 个 `FinalAnswerData(...)` 直接构造，分布在 19 个 test 文件 | `rg -n --glob '*.py' '\bFinalAnswerData\s*\(' tests` | **成立**：35 个 test 构造点、19 个文件，与 proposal 完全一致 |
| A2 | 4 个 `EngineRunOutcomeFinalAnswer(...)` 直接构造，分布在 3 个文件 | `rg -n --glob '*.py' '\bEngineRunOutcomeFinalAnswer\s*\(' tests` | **成立**：4 个构造点（test_public_compact_smoke.py ×2、test_llm_compaction.py ×1、test_compaction_cancellation_scope.py ×1），3 个文件 |
| A3 | 7 个文件直接实现/override/delegate/消费 `ContextCompactor` typed return | `rg -n --glob '*.py' '\b(ContextCompactor\|FakeContextCompactor\|prepare_compactor_proposal_run_input\|run_prepared_compactor_proposal)\b' tests` + 逐文件验证 | **成立**：7 文件精确为 proposal 所列，无遗漏 |
| A4 | 无 `FinalAnswerData` / `EngineRunOutcomeFinalAnswer` alias 构造（factory/builder） | `rg -n --glob '*.py' 'def.*[Ff]inal[Aa]nswer\|def.*[Ee]ngine[Rr]un[Oo]utcome' tests/` + 逐函数审计 | **成立**：只发现 `isinstance` extractor 函数（`_final_answer_data`、`_final_data`），它们不构造对象；无 hidden factory |
| A5 | 无 `AsyncMock` / `autospec` / `patch` 基的 `ContextCompactor` 隐式 return | `rg` 搜索 AsyncMock+ContextCompactor、autospec+ContextCompactor、patch+ContextCompactor | **成立**：零命中 |
| A6 | `SuccessfulRunnerResponseIdentity` 类型不能携带 endpoint/credential/header/secret | 类型定义审查（plan §9.2） | **成立**：字段集为 `effective_provider`、`effective_model`、`RunnerRequestIdentity`、`ProviderRequestIdAvailability`、`provider_request_id`；刻意不包含敏感字段 |
| A7 | `build_runner_request_identity()` 支持 `attempt_id=None, execution_id=None`（compactor 路径所需） | 源码审查 `runner_identity.py:160-164` | **成立**：成对校验只要求 both-None 或 both-non-None；compactor 的 both-None 合法 |
| A8 | Plan §9.1 原已覆盖 5 文件，遗漏 20 文件，合计 25 | 逐文件比对原 §9.1 owner-level 清单与 expanded table | **成立**：5 文件重叠（test_engine_event_contract、test_llm_compaction、test_compaction_operation、test_dispatch_scheduler、test_engine_ingest_mapping），20 文件为新增缺口 |
| A9 | Amendment 的 7 项 plan 修改全部在目标 plan 中落地 | 逐项比对 proposal §3.1 与 plan 实际文本 | **成立**：7 项修改均在 plan §9.1/§9.3/§9.6/§10.5/§13 中找到对应 |

## 3. Findings

### 3.1 无阻塞性 finding

经过独立 inventory scan、逐文件交叉验证、安全 identity 类型审查和 validation closure 检查，**未发现 blocking 级别的问题**。Amendment proposal 的 claims 与 HEAD 实际状态一致，allowed-file 扩展准确，test identity 规则安全且符合 semantic ownership 原则。

### 3.2 观察项（non-blocking observations）

#### OBS-001-未修复-低-§10.5 support module 覆盖声明未明确列出 fake_compaction.py

- **位置**：Plan §10.5 第 845-849 行
- **问题类型**：文档缺口
- **当前写法**：Plan 明确列出 `public_smoke_support.py`、`recovery_support.py`、`stress_support.py`、`transient_stream_support.py` 四个 support module，说明它们通过完整 `tests/host` 回归和全量 pyright 关闭；但未提及同为 support module 且属于机械闭包的 `fake_compaction.py`
- **为什么有问题**：`fake_compaction.py` 是 `FakeContextCompactor` 的 owner，也是 S5 机械闭包中唯一需要改变 public API（`compact()` return type）的 test-support module。不明确列出其验证路径，可能导致 implementation agent 不确定如何验证该文件的 correctness
- **直接证据**：
  - `tests/host/fake_compaction.py` 是 test-support module（非 test module，pytest 不可直接收集）
  - Plan §10.5 行 845-849 的 support module 清单未包含 `fake_compaction.py`
  - `fake_compaction.py` 的消费者（test_compaction_operation.py、test_dispatch_scheduler.py、test_engine_ingest_mapping.py、test_llm_compaction.py、test_compaction_contract.py、test_compact_artifact_store.py）均已在 focused/regression pytest 中
- **实际风险**：低 — `pytest tests/host -q` 和全量 pyright 客观上覆盖了 `fake_compaction.py`；这只是文档清晰度问题
- **建议改法**：在 §10.5 的 support module 段落增加一句：`fake_compaction.py` 同样由消费者测试和全量 pyright 覆盖，其 `FakeContextCompactor` 的 identity 构造规则已在 §9.3 完整定义
- **修复风险**：低（仅文档修订）
- **严重程度**：低

#### OBS-002-未修复-低-inventory rescan 未覆盖 S4 新文件 `test_compaction_terminal.py` 可能引入的 FA/OA 站点

- **位置**：Plan §10.5 第 881-894 行（inventory rescan 命令）
- **问题类型**：切片间依赖验证缺口
- **当前写法**：Plan 的 pre/post inventory rescan 使用与 amendment proposal 相同的 `rg` 命令，但 `test_compaction_terminal.py` 是 S4 的 planned-new 文件，在 S5 执行前才被创建。如果 S4 implementation 在该文件中引入了 `FinalAnswerData(...)` 或 `EngineRunOutcomeFinalAnswer(...)` 构造（用于测试 compaction terminal guard），rescan 会发现新 hit，但 plan 只说 "出现新 hit 即停止并再次 amend"
- **为什么有问题**：S4 的 `test_compaction_terminal.py` 当前不存在，无法在 amendment 阶段预判其内容。如果 S4 引入 FA/OA 构造（可能性低但非零），S5 implementation 会因 "新 hit 不在 allowed files" 而停止，需要再次 amend —— 这是正确的 fail-closed 行为，但代价是 workflow 中断
- **直接证据**：`test_compaction_terminal.py` 是 planned-new（plan §16 确认），HEAD 不存在该文件
- **实际风险**：低 — S4 terminal guard 不涉及 Engine final answer 语义，引入 FA/OA 构造的可能性极低；即使引入，rescan 也会正确捕获
- **建议改法**：无需修改 plan。在 implementation 时，S4 完成后立即运行 pre-S5 inventory scan 确认无新增 hit，而不是到 S5 才运行
- **修复风险**：N/A（非 plan 级修改，属 implementation sequencing 建议）
- **严重程度**：低

#### OBS-003-未修复-低-`test_compaction_contract.py` 的 `isinstance(candidate, ConversationCompactOutputVNext)` 断言需要语义重写

- **位置**：`tests/host/test_compaction_contract.py:78`
- **问题类型**：实现注意事项
- **当前写法**：`assert isinstance(candidate, ConversationCompactOutputVNext)`
- **为什么有问题**：F13 后 `compact()` 返回 `CompactorProposal`，该 `isinstance` 检查必然失败。这不是简单的 "add field" 机械变更，而是需要语义重写：先 `isinstance(candidate, CompactorProposal)`，再通过 `.candidate` 访问内部值。Amendment 将此类归为 CR 机械变更，但未明确提及 `isinstance` 检查的语义转换
- **直接证据**：`test_compaction_contract.py:76-83` 的 `compact()` call site 与 `isinstance` 断言
- **实际风险**：低 — 这是 CR 分类下可预期的机械变更，implementation agent 能够处理
- **建议改法**：S5 implementation 时注意：所有 `isinstance(result, ConversationCompactOutputVNext)` 断言需改为 `isinstance(result, CompactorProposal)`；对 `result` 的字段访问需增加 `.candidate` 解包
- **修复风险**：低（纯机械变更）
- **严重程度**：低

## 4. 正向验证记录

以下各项经独立验证确认正确，不构成 finding：

| # | 验证项 | 结论 |
|---|---|---|
| V1 | 35 FA 构造点计数（排除 production `dayu/engine/agent.py:2449`） | 准确：35 个 test 构造点、19 个文件 |
| V2 | 4 OA 构造点计数（排除 production `dayu/engine/agent.py:3011`） | 准确：4 个 test 构造点、3 个文件 |
| V3 | 7 CR 文件清单 | 准确且全面：`rg` 全仓搜索确认无遗漏 |
| V4 | 25-file union（5 已覆盖 + 20 新增） | 准确：交叉比对原 §9.1 与 expanded table |
| V5 | 无 alias constructor / hidden factory | 确认：`_final_answer_data`、`_final_data` 等均为 `isinstance` extractor，不构造 |
| V6 | 无 mock/autospec/patch 基 CR | 确认：全仓零命中 |
| V7 | `SuccessfulRunnerResponseIdentity` 无敏感字段 | 确认：类型定义不含 endpoint/credential/header/secret |
| V8 | `attempt_id/execution_id=None` 合法 | 确认：`runner_identity.py:161` 成对校验通过 both-None |
| V9 | present/unavailable 配对 enforced at `__post_init__` | 确认：plan §9.2 明确 availability 与 request id 严格成对 |
| V10 | `FakeConversationCompactorVNext` 正确保持 candidate-only | 确认：不实现 `ContextCompactor`，只被 `FakeContextCompactor` 内部调用 |
| V11 | Plan §10.5 focused tests 覆盖全部 25 文件 | 确认：engine tests 覆盖 engine-side FA 文件；host tests 覆盖 host-side FA/OA/CR 文件；service test 覆盖 service FA 文件 |
| V12 | Plan §10.5 full regression `pytest tests/engine tests/host -q` 覆盖全部 | 确认：收集全部 test modules |
| V13 | Inventory rescan 命令的 `rg` 模式正确 | 确认：三种模式分别匹配 FA、OA、CR |
| V14 | Amendment 7 项 plan 修改已落地 | 确认：逐项比对 proposal §3.1 与 plan 实际文本 |
| V15 | §9.3 同源 identity 规则一致 | 确认：fake owner explicit identity / candidate-transforming preserve / candidate-only no identity / paired value |
| V16 | §13 S5 checklist 包含 25-file 闭包项 | 确认：checklist 第 2 项 |

## 5. Open questions

无 open question。以下均在本次 review 中通过直接证据关闭：

- **25-file union 是否全面？** → 是。全仓 `rg` + alias/mock scan 确认。
- **identity 类型是否安全？** → 是。类型定义强制 present/unavailable 配对，不携带敏感字段。
- **`FakeContextCompactor` 的 identity 构造规则是否可执行？** → 是。`build_runner_request_identity()` 已存在，接受 `attempt_id=None, execution_id=None`。
- **Validation closure 是否覆盖全部机械变更？** → 是。focused + regression + pyright + inventory rescan。
- **S4 是否会引入新 FA/OA/CR 站点？** → 已通过 pre/post inventory rescan 机制关闭；S4 terminal guard 语义上不涉及 FA/OA，概率极低。

## 6. Residual risks

| 风险 | 分类 | 处置 |
|---|---|---|
| S4 implementation 在 `test_compaction_terminal.py` 引入 FA/OA 构造 | `fail-closed by inventory rescan` | S5 implementation 前必须运行 pre-inventory scan；新 hit 停止并 amend |
| Implementation agent 错把 `isinstance(candidate, ConversationCompactOutputVNext)` 改为增加 default field 而非改为 `CompactorProposal` 解包 | `covered by pyright + plan prohibition` | Plan §9.1 明确禁止 optional/default/compatibility；pyright 会拒绝 `CompactorProposal` 赋值给 `ConversationCompactOutputVNext` |
| 同一 test identity 被多个 fake 复用（违反同源规则） | `covered by §9.3 explicit rules + code review` | Plan §9.3 和 amendment §3.2 规则明确；最终由 deepreview/code review 裁决 |
| HEAD 在 amendment 后、S5 implementation 前漂移（新 commit 引入新 FA/OA/CR） | `fail-closed by inventory rescan` | S5 implementation 立即运行 pre-inventory scan；出现新 hit 停止 |

## 7. Plan review conclusion

**结论：`pass-with-minor-observations`**

Amendment proposal 的 premise invalidation 成立，且 scope 评估准确：

1. **Motivation 成立**：F13 的 required `FinalAnswerData.response_identity`、`EngineRunOutcomeFinalAnswer.response_identity` 和 `ContextCompactor.compact() -> CompactorProposal` 确实会产生超出原 §9.1 的必然机械错误。原 §9.1 只覆盖 5 个文件，实际有 25 个文件需要变更。

2. **Inventory 准确**：独立 `rg` 扫描确认 35 FA / 19 files、4 OA / 3 files、7 CR files、25-file union 全部与 proposal 一致。无遗漏构造点，无 alias factory，无 mock/autospec 隐式 return。

3. **Allowed-file 修订正确**：Plan §9.1 的 expanded table 覆盖全部 25 个机械闭包文件；新增的 20 个文件均为纯机械变更（补齐 required field、解包 proposal identity、迁移 return annotation），不改变测试场景和行为断言。

4. **Identity 规则安全**：
   - `SuccessfulRunnerResponseIdentity` 不包含 endpoint/credential/header/secret
   - `present`/`unavailable` 配对由 `__post_init__` 强制
   - `attempt_id/execution_id=None` 是 compactor 语义的正确表达
   - Fake identity 规则明确：非敏感 test-only provider/model、canonical `build_runner_request_identity()`、同一次 invocation 的 identity、paired value 保留

5. **Validation closure 完整**：Focused tests + full `pytest tests/engine tests/host -q` + 全量 `pyright` + pre/post inventory rescan 覆盖所有 mechanical closure 文件。

6. **Scope 无 drift**：Amendment 严格限定在扩大 allowed-file 机械闭包，不新增 production owner、不修改 F13 contract、不改变 S4 guard。

三个低严重度 observation 均不阻塞 plan review 通过；OBS-001 建议在 §10.5 增加一行说明，可随 S5 implementation 一同修复。

### Amendment proposal status

**`pass`**：proposal 的前提成立、数据准确、方案安全、validation 完整。可以恢复 Gateflow 的 S5 implementation gate。

---

*Review 由独立 adversarial review 完成，未依赖 MiMo 输出。Reviewer 未修改任何 plan 或代码，未 commit/push/PR。*
