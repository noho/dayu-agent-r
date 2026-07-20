# WU-SEMANTIC-OWNERSHIP-01 P2-A Plan Re-review — AgentDS

## Verdict

**pass**

All accepted plan-review findings from MiMo (F-01, F-02, F-03) and DS (DS-F01, DS-F02, DS-F03, DS-F04) are confirmed closed in the current plan. No new blocking findings.

## Re-review Scope

- Plan: `docs/host/wu-semantic-ownership-01-p2-a-plan.md`
- Initial reviews: `docs/reviews/plan-review-20260709-p2-a-mimo.md`, `docs/reviews/plan-review-20260709-p2-a-ds.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-review-controller-adjudication.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-controller-validation.md`

## Confirmation Checklist

### 1. S1: prompt.py / interactive.py 内部调用新 helper，删除旧 private helper，不留转发 facade

**Confirmed.** Plan §5 S1 Exact allowed changes (line 143) 明确要求：

> prompt / interactive command modules 的 `_run_prompt_command_async` / `_run_interactive_command_async` 内部也必须调用新 public helper；`session.py` 也调用同一 helper。原 private `_prepare_*` / `_execute_*` 函数从 prompt / interactive command modules 删除，不保留同名转发。

Line 144 进一步禁止"仅转发旧私有函数"。这与 MiMo F-01 的建议修复完全一致。

### 2. S1: context slot values 由各 command module 构造，新 helper 接收已构造值

**Confirmed.** Plan §5 S1 Exact allowed changes (line 147) 明确：

> prompt / interactive 的 context slot 构造仍由各自 command module 拥有：prompt 继续由 prompt command 计算 ticker / FMP 相关 `context_slot_values`，interactive 继续由 interactive command 计算 interactive slots。新 helper 的 prepare API 接受已构造的 `context_slot_values`，不得根据 scenario 字符串自行分发 slot 构造规则。

这与 DS-F01 建议的方案 A 完全一致。Controller adjudication 也已确认："Context slot construction remains command-local because prompt and interactive have different context slot rules; the shared helper should not infer business slot semantics from scenario strings."

### 3. S1: 与 RuntimeDisplayController 的职责边界已说明

**Confirmed.** Plan §3 Owner Boundary (lines 95-96) 明确：

> 新的 existing-session execution helper 与既有 `RuntimeDisplayController` 职责不重叠：`RuntimeDisplayController` 继续拥有 thinking guard、final-before-terminal cleanup、cancel cleanup 与 display lifecycle close；P2-A 新 helper 只拥有 existing-session runtime prepare / Host submit-watch execution composition / command execution identity。两者可以被同一 command 调用，但不得互相包裹成 facade。

这与 DS-F02 的建议修复完全一致。两个 CLI shared helper 的职责分工已明确文档化。

### 4. S2: 已改为 CLI-private `FinsDirectStreamContractViolation(RuntimeError)`

**Confirmed.** Plan §5 S2 Exact allowed changes (line 181) 明确：

> 定义 CLI 私有 contract violation 异常，例如 `FinsDirectStreamContractViolation(RuntimeError)`。它只表达 CLI 观察到 Service direct stream contract 被破坏，不承载 Fins 业务结果语义。

Line 182 将抛出的异常从 `RuntimeError` 改为 `FinsDirectStreamContractViolation`。这与 MiMo F-02 的建议修复完全一致。Controller adjudication 也已确认："The specific `FinsDirectStreamContractViolation` remains CLI-private and does not move Fins business facts into CLI."

### 5. S1/S7: 已要求 AST-level CLI import-boundary 自动化测试

**Confirmed.** 两处确认：

- Plan §5 S1 Tests/assertions (line 155)："新建 `tests/cli/test_import_boundary.py` 或在等价 CLI boundary 测试文件中加入 AST-level 断言，禁止 `dayu/cli/commands/session.py` 从 `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive` 导入下划线私有符号。该断言是必做自动化测试，不得只依赖人工 `rg`。"
- Plan §7 Validation Matrix (line 262) 必跑列表包含 `pytest tests/cli/test_import_boundary.py`。

这与 MiMo F-03 和 DS-F04 的建议修复完全一致。Rollback verification point (line 165) 的 `rg` 检查是补充手段，不是替代。

### 6. S3: prompt/interactive NOT_FOUND 默认 EXIT_FAILURE，HostApiError helper 单测已要求

**Confirmed.** 两处确认：

- Plan §5 S3 exit-code policy (line 221)："prompt / interactive 首次 ensure/create/submit 阶段即使收到 `NOT_FOUND`，也默认是 Host 配置、slot、Session lifecycle 或运行期状态错误；用户没有显式提供 session id selector，因此不得映射为 usage error。"
- Plan §5 S3 Tests/assertions (line 232)："helper 的 pure functions 必须有轻量单元测试，覆盖 NOT_FOUND explicit selector -> usage、label TOCTOU -> failure、prompt/interactive NOT_FOUND -> failure、generic HostApiError -> failure。"

与 DS-F03 和 DS validation coverage note 的建议修复完全一致。注意措辞从原稿的"可添加"升级为"必须有"。

### 7. 无新增阻断问题

**Confirmed.** 对修改后的 plan 做了完整的 adversarial pass，检查以下维度：

- **分层违规**：S1/S2/S3 均不引入反向依赖或跨层语义泄漏。CLI helper 可依赖 Service，Service 不反向依赖 CLI。HostApiError presentation 留在 CLI，不进入 Service。
- **Owner boundary 一致性**：S1 新 helper 拥有 session execution composition；S2 contract violation 是 CLI-private；S3 presentation helper 拥有 CLI 展示/退出码映射。三个 slice 的 owner boundary 与 §3 表格一致。
- **Scope creep**：§4 Non-goals 明确不触碰 P2-B、P2-C、P1-A/B/C、Host public API、Host durable schema、Engine runner、Fins storage。无越界。
- **Stop conditions**：§4 定义了三个 stop condition，均具体且可操作。
- **Validation coverage**：§7 必跑矩阵覆盖了 S1/S2/S3 的所有核心测试文件，建议补充也列出了 import-boundary、arg-parsing、runtime-display 等边缘测试。
- **Propagation audit**：§8 预定义了四条路径的 audit 要求，与 §3 owner boundary 一致。

无新增阻断 finding。

## Findings Closure Summary

| Finding ID | Source | Severity | Plan Fix Location | Status |
|---|---|---|---|---|
| MiMo F-01 | glue facade risk | LOW | §5 S1 line 143 | Closed |
| MiMo F-02 | RuntimeError too broad | LOW | §5 S2 line 181 | Closed |
| MiMo F-03 | import-boundary test absent | LOW | §5 S1 line 155, §7 line 262 | Closed |
| DS-F01 | context slot underspecified | MEDIUM | §5 S1 line 147 | Closed |
| DS-F02 | RuntimeDisplayController relation | LOW | §3 lines 95-96 | Closed |
| DS-F03 | NOT_FOUND exit-code policy | LOW | §5 S3 line 221 | Closed |
| DS-F04 | import-boundary test not mandatory | LOW | §5 S1 line 155, §7 line 262 | Closed |
| DS validation note | helper unit tests optional | LOW | §5 S3 line 232 | Closed |

All 8 accepted findings are confirmed closed. 0 outstanding findings. 0 new blocking findings.

## Residual Note

Plan 当前质量已满足 P2-A plan acceptance 条件。Implementation agent 应严格按 §4 stop conditions 执行——若在实施中发现 shared prompt/interactive execution 不能在不复制 REPL/terminal rendering 语义的情况下抽取，或 Fins direct Service contract 未覆盖某真实 command path，或 prompt/interactive HostApiError exit-code policy 需要改变用户可见 CLI contract，应立即停止并让 controller 重新裁决。
