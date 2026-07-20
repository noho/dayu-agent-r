# WU-SEMANTIC-OWNERSHIP-01 P2-A Plan Re-Review — AgentMiMo

## Scope

- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-a-plan.md`（controller adjudication 后版本）
- Initial reviews: `docs/reviews/plan-review-20260709-p2-a-mimo.md`, `docs/reviews/plan-review-20260709-p2-a-ds.md`
- Controller adjudication/fix: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-review-controller-adjudication.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p2-a-plan-controller-validation.md`
- Review mode: re-review，确认所有 accepted plan-review findings 已关闭且无新增阻断问题。

## Verdict

**pass**。所有 accepted plan-review findings 已关闭，无新增阻断问题。

## Accepted Findings Closure Check

### F-01 (MiMo): S1 glue facade risk — prompt/interactive 内部调用链是否也改用新 public helper

**Status: closed。**

Plan S1 Exact allowed changes 第 143 行已明确："prompt / interactive command modules 的 `_run_prompt_command_async` / `_run_interactive_command_async` 内部也必须调用新 public helper；`session.py` 也调用同一 helper。原 private `_prepare_*` / `_execute_*` 函数从 prompt / interactive command modules 删除，不保留同名转发。"

第 144 行补充："不在 `prompt.py` / `interactive.py` 保留仅转发旧私有函数；测试引用旧私有 helper 的地方必须迁移到新 public helper，或改用 command main path。"

这确认了模式 A（完全迁移）：private helpers 的函数体移到新模块，prompt.py / interactive.py 内部也改用新 public helper，旧 private 函数删除。不会产生 glue facade。

### DS-F01 (DS): S1 context slot values 构造策略未明确

**Status: closed。**

Plan S1 Exact allowed changes 第 147 行已明确："prompt / interactive 的 context slot 构造仍由各自 command module 拥有：prompt 继续由 prompt command 计算 ticker / FMP 相关 `context_slot_values`，interactive 继续由 interactive command 计算 interactive slots。新 helper 的 prepare API 接受已构造的 `context_slot_values`，不得根据 scenario 字符串自行分发 slot 构造规则。"

裁决为方案 A：新 helper 接受已构造的 slot values，context slot 构造差异保留在各自 command module。

### DS-F02 (DS): S1 与 RuntimeDisplayController 的设计一致性未讨论

**Status: closed。**

Plan Section 3 Owner Boundary 第 95 行已明确："新的 existing-session execution helper 与既有 `RuntimeDisplayController` 职责不重叠：`RuntimeDisplayController` 继续拥有 thinking guard、final-before-terminal cleanup、cancel cleanup 与 display lifecycle close；P2-A 新 helper 只拥有 existing-session runtime prepare / Host submit-watch execution composition / command execution identity。两者可以被同一 command 调用，但不得互相包裹成 facade。"

职责分工清晰：`RuntimeDisplayController` 拥有 display/thinking/cancel cleanup lifecycle，新 helper 拥有 session 执行准备/提交/错误处理 lifecycle。

### F-02 (MiMo): S2 RuntimeError 语义过宽

**Status: closed。**

Plan S2 Exact allowed changes 第 181 行已改为："定义 CLI 私有 contract violation 异常，例如 `FinsDirectStreamContractViolation(RuntimeError)`。它只表达 CLI 观察到 Service direct stream contract 被破坏，不承载 Fins 业务结果语义。"

第 182 行："将 `_consume_fins_direct_events(...)` 在 async iterator 结束且未返回 terminal result 时改为抛出 `FinsDirectStreamContractViolation(...)`。该错误由 `run_fins_direct_command` 的通用 `Exception` catch 渲染为 CLI failure，不作为 usage error。"

自定义异常继承 `RuntimeError` 保持兼容，语义精确，可被测试用异常类型断言。

### F-03 (MiMo) / DS-F04 (DS): import-boundary test 未被列为必做验证

**Status: closed。**

Plan S1 Tests/assertions 第 155 行已明确："新建 `tests/cli/test_import_boundary.py` 或在等价 CLI boundary 测试文件中加入 AST-level 断言，禁止 `dayu/cli/commands/session.py` 从 `dayu.cli.commands.prompt` / `dayu.cli.commands.interactive` 导入下划线私有符号。该断言是必做自动化测试，不得只依赖人工 `rg`。"

Validation Matrix 第 262 行已包含 `source .venv/bin/activate && pytest tests/cli/test_import_boundary.py` 作为必跑验证。

### DS-F03 (DS): prompt/interactive NOT_FOUND exit-code policy 未显式说明

**Status: closed。**

Plan S3 exit-code policy 第 221 行已明确："prompt / interactive 首次 ensure/create/submit 阶段即使收到 `NOT_FOUND`，也默认是 Host 配置、slot、Session lifecycle 或运行期状态错误；用户没有显式提供 session id selector，因此不得映射为 usage error。"

判断依据清晰：用户没有显式提供 session id selector，NOT_FOUND 是 Host 配置/运行时错误，不是用户 CLI 参数错误。

### DS validation coverage note: HostApiError pure helper tests optional

**Status: closed。**

Plan S3 Tests/assertions 第 232 行已从"可添加"升级为"必做"："helper 的 pure functions 必须有轻量单元测试，覆盖 NOT_FOUND explicit selector -> usage、label TOCTOU -> failure、prompt/interactive NOT_FOUND -> failure、generic HostApiError -> failure。"

## New Blocking Issues

无。

## 结论

Controller adjudication 接受的全部 7 个 findings 均已在 plan 中落实：

| Finding | Source | Status |
|---|---|---|
| F-01: S1 glue facade risk | MiMo | closed — prompt/interactive 内部也改用新 public helper，旧 private 删除 |
| DS-F01: context slot 构造策略 | DS | closed — 新 helper 接受已构造值，slot 构造留在 command module |
| DS-F02: RuntimeDisplayController 关系 | DS | closed — 职责边界已区分 |
| F-02: RuntimeError 语义过宽 | MiMo | closed — 改用 `FinsDirectStreamContractViolation(RuntimeError)` |
| F-03/DS-F04: import-boundary test | MiMo/DS | closed — AST-level 自动化测试为必做项 |
| DS-F03: NOT_FOUND exit-code policy | DS | closed — prompt/interactive NOT_FOUND 默认 EXIT_FAILURE 已显式说明 |
| HostApiError helper tests | DS | closed — pure function 单测为必做项 |

Plan 已达到可接受状态，可进入 implementation。
