# UF-FIX11 S3 Implementation — DS 第二路独立 Review

- reviewer：DS（第二路严格独立 adversarial review）
- 时间：2026-08-17
- review target：
  - `docs/gateflow/uf-fix11-s3-implementation-20260817.md`（implementation artifact）
  - 工作树未提交全 diff（5 个生产文件、6 个测试文件、3 个 README）
  - accepted 前置：`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`、
    `docs/gateflow/uf-fix11-s3-projection-boundary-amendment-20260817.md`、
    `docs/gateflow/uf-fix11-s3-projection-boundary-acceptance-20260817.md`、`5bb122d3`、`f6893c29`
- 独立声明：本 review 未读取 MiMo 路 review artifact，所有结论仅基于上述文档与代码/测试直接证据独立得出。
- scope：只读 review。未修改任何既有文件；未 stage/commit。只新增本 artifact。

## 1. Reviewed target and scope

S3 的主张：S1+S2 已由 commit owner 在 publication lock 内产生 typed warning；S3 的真实缺口是该值进入
runtime summary、durable JSON、direct public result、CLI 与 completed wait projection。实现只修改 accepted
S3 allowed files 与 amendment 新增的三个 direct symbols，不重新解析 warning、不读取 storage、不改 S1+S2
parser/codec。

Assumptions tested：

- A1：`FinsUploadResultSummary.warnings` / `FinsResultSummary.warnings` 的 exact-element、at-most-one、
  success-only invariant 正确实现且与 S1+S2 pipeline invariant 同形；
- A2：upload/generic 两个 `_direct_result_event` callsite 全集穷举成立，builder 必填无默认、helper 内无写回；
- A3：direct、durable、CLI、wait 四路投影从同一个 typed tuple 派生，无第二条推导链；
- A4：failed/cancelled/deleted 与 generic non-upload 在所有真实路径不可能携带 warning；
- A5：CLI 双流（stdout 摘要 / stderr warning）与 exit code 在所有 disposition 下正确且无重复/顺序问题；
- A6：durable save/re-read 不丢失、不重算 warning，空值为 `[]`；
- A7：测试 owner 落位正确、红测覆盖构造 invariant、fake 注入不绕过 owner 语义；
- A8：README 三处改动均在各自职责边界内且与已实现行为一致；
- A9：validation 声明（focused/combined/coverage/pyright/static boundary）可独立复现。

## 2. 直接代码证据（本 review 独立复核，含独立重跑）

### 2.1 同源链逐环验证

- **生产 warning 唯一来源（S1+S2 冻结）**：`FinsUploadPipelineResult.warnings`
  （`ingestion_runtime.py:1705`）invariant 仅允许 `ok`/`skipped` 非空（`1734-1742`）；parser
  `from_pipeline_json`（`1768-1787`）对 FILING missing fail closed，`SourceKind.MATERIAL` + 非空 warnings
  同样 fail closed（`1774`）——material 不可能携带 warning 进入 S3 层。✓
- **service 汇合点**：`service_runtime.py:310-324` `_upload_summary_from_result` 显式
  `warnings=result.warnings`，不依赖默认值。✓
- **direct**：`_produce_direct_upload`（`ingestion_runtime.py:4522-4541`）取
  `upload_runner.run_upload` 返回的同一 summary → `_direct_upload_terminal_events` →
  `_direct_result_event(..., warnings=summary.warnings)`（`6577`）→ `FinsResultSummary`。✓
- **durable**：`_run_upload_job`（`5010-5029`）同一 summary 的 `to_json_summary()` 写入 job record；
  `to_json_summary()`（`1934`）无条件输出 `"warnings"` 数组，空为 `[]`（codec
  `company_metadata_warnings_to_json` 对 `()` 返回 `[]`）。✓
- **wait**：observation drain（`4110-4145`）把 direct RESULT 事件的**同一** `FinsResultSummary` 对象放进
  `record.result`；`fins_wait_adapter._completed_result_value`（`578-588`）用同一 codec 序列化
  `result.warnings`。wait 与 direct 是同一 typed 对象的两次投影，不是两条推导链。✓
- **CLI**：`dayu/cli/output.py:236-244` SUCCESS 分支先 stdout 摘要、后逐条 stderr warning；
  `_upload_result_details`（`6897-6934`）不包含 warnings，无重复输出。exit code 由
  `event.result.exit_code` 决定（`dayu/cli/commands/fins.py:916-1000`），renderer 返回 `None` 不改写。✓

### 2.2 构造点全集（类型/default 是否掩盖第三方构造点）

生产 `FinsUploadResultSummary(` 全集 = 4：`service_runtime.py:132`（cancelled 早退，默认 `()` 合法）、
`service_runtime.py:310`（显式 copy）、`ingestion_runtime.py:4500`（runner-None failed，默认 `()` 合法）、
`ingestion_runtime.py:4983`（job failed，默认 `()` 合法）。全部非 success 或显式 copy，无静默丢失路径。✓

生产 `FinsResultSummary(` 全集 = 4：`6514`（builder，唯一 SUCCESS-capable）、`7248`/`7303`/`7352`
（三个 observation helpers，全部非 SUCCESS，`git diff` 证明零 diff，默认 `()` 是正确空状态）。✓

无 `dataclasses.replace` 作用在两个 summary 类型上（grep 验证），不存在 replace 丢 warning 路径。✓

### 2.3 取消线性化

`_produce_direct_upload` 先构造事件、后 `claim_upload_summary`（`4534-4541`）；
`claim_upload_summary`（`2578-2601`）只返回 disposition 派生 status 或 `None`（drop），**不**像
`claim_terminal` 那样把取消请求改写为 CANCELLED。晚到取消不把已 commit 的 success（可带 warning）改写为
cancelled——与 plan §8.5 first-committer 语义一致；提交前取消由 runner 返回 cancelled summary（invariant
强制 warning 为空）。不存在"cancelled 终态携带 warning"路径。✓

### 2.4 独立重跑 validation（全部在仓库根目录、venv 激活后执行）

- S3 focused：`543 passed, 3 warnings`（edgar deprecation），与 artifact 声明一致。
- Combined regression：`2152 passed, 1 skipped, 3 warnings`，与声明一致。
- Branch coverage（同 include 列表）：
  `ingestion_runtime.py` 89%、`service_runtime.py` 88%、`direct_events.py` 83%、`cli/output.py` 82%、
  `fins_wait_adapter.py` 91%——与 artifact 声明的五个数字完全一致，逐文件均 ≥80% gate。✓
- pyright：`0 errors, 0 warnings, 0 informations`，与声明一致。
- `git diff --check`：通过。`git diff --name-only`：严格等于 S3 allowed files（5 生产 + 6 测试 + 3 README），
  无越界文件。
- `rg -n "def commit_batch" dayu tests`：production 3 个定义（Protocol + 2 impl）、tests 7 文件/9 定义，
  全部注解 `CompanyMetaCommitOutcome | None`，与 §9.2 清单 exact 对应。
- AST 测试实现逐行核对：callsite 全集穷举（`ast.walk` 收集全部 `Call` 节点，断言数量恰 2、keyword 必存在、
  `ast.unparse` 实参集合恰为 `{"summary.warnings", "()"}`）；`kw_defaults[warnings_index] is None` 正确检测
  "无默认值"（有默认值会是 `ast.Constant` 节点而非 `None`）；helper 内全部 `warnings` Name 节点为 `Load`
  （含 CANCELLED 分支无写回）。✓

## 3. Findings

### F-01-未修复-低-`_completed_result_value` docstring 未记录新增 warnings 字段

- **位置**: `dayu/service/fins_wait_adapter.py:566-588`
- **问题类型**: 文档完整性（项目编码硬约束：函数必须提供完整中文 docstring，包含参数、返回值）
- **当前写法**: 函数体新增 `"warnings": company_metadata_warnings_to_json(result.warnings)`，但 docstring 的
  Returns 描述仍只写"download 使用 nested 自解释对象；其它 operation 保持业务 details"，未提及 completed
  value 现在对**所有** completed operation 显式包含 `warnings` 数组。
- **反例/失败场景**: 未来维护者阅读 docstring 以为 completed value 只有 operation/status/title/download/
  details 五个键；该字段对非 upload completed 也是显式 `[]`，属于已接受的 schema 扩展，docstring 不记录会
  造成"代码与契约文档漂移"。
- **直接证据**: `fins_wait_adapter.py:578-583` 新增行与 `566-576` docstring 原文。
- **影响**: 低；不影响运行时行为，但违反 CLAUDE.md docstring 约束。
- **建议改法和验证点**: Returns 描述补一句"completed value 恒包含 `warnings` 数组（非 upload 为 `[]`）"。
- **严重程度（低）**

### F-02-未修复-低-plan 要求的"end-to-end mocked CLI command"未覆盖命令循环层

- **位置**: `tests/cli/test_fins_commands.py:3069-3160`
- **问题类型**: 测试规格完成度（plan §S3 Tests："end-to-end mocked CLI command：uploaded 与 skipped 都
  覆盖"）
- **当前写法**: warning 双流行为由 production `_direct_upload_terminal_events` + `render_fins_direct_event`
  + `capsys` 覆盖；exit code 断言针对**事件字段**（`result_event.result.exit_code == EXIT_SUCCESS`），不经过
  `dayu/cli/commands/fins.py` 命令循环（`fins.py:916-1000` 的渲染、exit code 收集与 `return
  terminal.exit_code`）。uploaded/skipped 两个 warning 场景在命令级路径上没有测试。
- **反例/失败场景**: 若未来命令循环在渲染后引入额外 exit code 改写、stderr 二次输出或 summary 二次消费，
  warning 场景的端到端行为漂移不会被测试网捕获（无 warning 场景有既有命令级测试，但 warning 场景没有）。
- **为什么有问题**: renderer 层与命令层的组合行为（"stderr 有 warning 文案且 exit 0"）是 plan 明确要求的
  用户可见契约；当前测试证明了两个组件各自正确，未证明组合正确。
- **直接证据**: `tests/cli/test_fins_commands.py:3141-3154`（生产 builder + renderer 直调，无命令入口）；
  plan §S3 Tests 原文。
- **影响**: 低；renderer 返回 `None`、exit 由 event 字段驱动（零 diff），当前组合行为实际正确，属测试网
  缺一环。
- **建议改法和验证点**: 补一个 mocked 命令级用例（如既有 `test_fins_commands.py` 的 mock direct stream
  惯例）跑通 uploaded+warning 场景，断言进程 exit 0、stdout 摘要、stderr warning；或由 controller 裁决该
  场景由 renderer 层测试等价覆盖、plan 措辞收窄。
- **严重程度（低）**

### F-03-未修复-低-runtime 层无"真实 pipeline 产出 warning"的复合链路回归

- **位置**: `tests/fins/test_fins_ingestion_runtime.py:6303-6402` 与 `tests/fins/test_fins_service_runtime.py:445-482`
- **问题类型**: 测试缺口 / residual 观察（plan 允许该 seam，非违约）
- **当前写法**: S3 direct-stream 测试通过 `_FakeUploadRunner(summary)` 注入预构造 summary；
  `_upload_summary_from_result` 的 copy 测试直接构造 `FinsUploadPipelineResult`。`ProductionFinsUploadRunner.run_upload`
  从未在任一测试中以非空 warnings 运行（grep 验证）。
- **反例/失败场景**: 若未来 `ProductionFinsUploadRunner` 内部对 result 做 replace/归一化/中间重建而丢
  warnings，`_upload_summary_from_result` 单测与 direct-stream fake 测试都无法捕获——每环单独正确，复合
  链路断裂无回归网。
- **为什么是低/非 blocker**: plan 明确把真实 warning 生产关闭在 S1+S2；S1+S2 在真实 workflow 层已有 exact
  warning 断言（`test_sec_pipeline_upload_filing_stream.py:1778/1847/3201`、
  `test_cn_pipeline.py:1629/1698`、`test_filing_upload_publication.py`），且 runner 主体零 diff、copy 为
  单行机械投影，断裂面积极小。
- **直接证据**: `tests/fins/test_fins_ingestion_runtime.py:4256` `_FakeUploadRunner` 定义与 `6295/6354` 注入点；
  grep `run_upload` + warnings 无复合用例。
- **影响**: 低；防回归网在 runner 内部重构场景下有一处空白。
- **建议改法和验证点**: 可分配后续 work unit（或 controller 裁决为 accepted tradeoff）：一个用真实
  `ProductionFinsUploadRunner` + 假 pipeline facade 返回 warning JSON 的复合用例，断言
  summary/direct/durable 三投影同值。
- **严重程度（低）**

## 4. 用户指定核查点结论

1. **success warning 是否在真实路径因默认值或 replace 丢失**：否。production 两个 summary 类型构造点全集
   已穷举：唯一 success-capable 生产构造要么显式 copy（`_upload_summary_from_result`），要么经 builder 必填
   参数（`_direct_result_event`）；无 `dataclasses.replace` 作用于 summary。默认 `()` 只出现在
   failed/cancelled/deleted/runner-None 构造点，均为合法空状态。✓
2. **failed/cancelled 是否可能带 warning / completed wait 为非 upload 新增不兼容业务字段**：
   pipeline invariant（S1+S2）→ parser fail-closed（含 MATERIAL 非空 fail closed）→ 两个 S3 summary
   invariant → CLI 仅 SUCCESS 分支打印 → wait failed/cancelled 无 warnings 键且不从 error message 推断，
   全链无泄漏。completed wait 对非 upload（download）新增 `warnings: []` 是 plan §6.6.2 已接受的 tradeoff
   且 artifact 已记录；键名业务可读、空数组为自然空状态，download 工具 schema 描述不枚举 completed value
   键（`download_tools.py:163-167`），无 LLM-facing 文本缺口。✓
3. **CLI renderer 对所有 success/disposition 正确且无重复/顺序问题**：SUCCESS 先 stdout（标题+摘要）后
   stderr（逐条 message）；CANCELLED/FAILURE 分支不打印 warning（invariant 保证为空）；`_upload_result_details`
   与 `_print_terminal_business_summary` 均不含 warnings，无重复。exit code 由事件字段驱动且 warning 不改写。
   ✓（命令层组合测试见 F-02）
4. **direct 与 wait 是否各自从同一 source 而非计划误画链路**：wait 的 observation `record.result` 与 direct
   RESULT 事件的 `FinsResultSummary` 是**同一对象实例**（`4110-4145`），`_completed_result_value` 只序列化该
   实例的 `warnings`；durable 与 direct 同取 runner 返回的同一 summary。计划链路图与实际代码一致，无
   第二条推导。✓
5. **kill/rollback/未完成发布是否可能产生终态 warning**：kill 无 terminal projection（S1+S2 契约）；rollback
   终态为 failed/cancelled，受 invariant 拒绝；晚到取消不把已 commit success 改写为 cancelled
   （`claim_upload_summary` 不按取消请求改写 status，first-committer 语义），故也不存在"改写前已带 warning
   的 success 被静默换成 cancelled"路径。✓
6. **类型/default 是否掩盖第三方构造点**：见 §2.2，全部构造点已穷举，无掩盖。AST 测试对 callsite 全集、
   必填无默认与 helper 内无写回三层锁定，覆盖"未来新增构造点漏传"的长期风险。✓
7. **tests 是否缺真实 uploaded/skipped 或仅测 replace 注入**：S3 层用 fake-runner 注入（plan 允许的 seam）；
   真实 uploaded/skipped warning 生产已在 S1+S2 的真实 workflow/pipeline 测试关闭（SEC 3 处、CN 2 处 exact
   断言）。复合链路缺口见 F-03（低）。✓
8. **README 是否超出职责/错误承诺**：根 README 改动（`README.md:344`）严格按最终用户手册边界写用户可见
   行为（fresh name 不被改写、warning 走 stderr 且 exit 0、skipped alias 原子保存、删除"不要填写公司名称"
   建议），无内部架构/状态机/评审历史；`dayu/fins/README.md` 改动与 S1+S2 已接受的 skip 状态机、outcome
   owner 与投影链一致；`tests/README.md` 描述与新增测试矩阵一致。三处均无未实现行为承诺。✓
9. **coverage/pyright/边界**：全部独立复现成功（§2.4），数字与 artifact 声明完全一致；artifact 对首次
   coverage 78% → 补测 → 82% 的过程披露诚实。`_observation_failure_result`/`_observation_cancelled_result`/
   `_mark_observation_failed` 零 diff 确认。

## 5. Open questions

- OQ-1：F-01 的 `_completed_result_value` docstring 补记是否由 controller 直接裁决修复？
- OQ-2：F-02 的命令级 warning 用例是补测试还是收窄 plan 措辞（renderer 层等价覆盖）？
- OQ-3：F-03 的复合链路回归是否接受为 S3 closeout 的 residual（`assigned to later work unit`），还是
  controller 要求本轮补？

## 6. Residual risks and suggested tracking destination

- R-1（accepted tradeoff）：completed wait 对所有 operation 显式 `warnings` 数组（非 upload 为 `[]`）。
  追踪：已由 plan §6.6.2 与 implementation artifact "Accepted tradeoffs" 记录，无需新增动作。
- R-2（测试网）：命令层组合测试缺一环（F-02）。追踪：S3 review fix 或 controller 裁决。
- R-3（测试网）：runner 复合链路无回归网（F-03）。追踪：建议 `assigned to later work unit`，与 S1+S2
  acceptance 已记录的 later residuals 同列。
- R-4（文档）：`_completed_result_value` docstring（F-01）。追踪：S3 review fix。
- R-5（既有 S1+S2 later residuals，非本 slice 引入）：name-only metadata batch 的 writer lock/physical swap
  成本、material upload 类似行为、真实 CLI/network/scenario/oracle/frozen evidence、post-commit
  guard-release 报错可见性——S3 未触碰，维持原分类。

## 7. Final conclusion

**PASS**

S3 implementation 对 accepted plan 与 projection-boundary amendment 的执行完整且精确：

- 四个投影层全部从同一 typed tuple 机械派生，无重算、无 replace 丢失、无默认值掩盖；production 构造点
  全集穷举后不存在静默丢 warning 路径。
- failed/cancelled/deleted/kill/rollback/晚到取消在全部真实路径无法携带 warning，防线为 owner 层
  invariant（fail closed）而非下游补偿。
- builder callsite 穷举、必填无默认、helper 无写回的 AST 结构测试与 amendment 裁决逐字对应；observation
  helpers 零 diff 确认。
- CLI 双流与 exit、wait completed/failed/cancelled、durable save/re-read 均与 plan contract 一致，红测/
  正例/负例覆盖 owner 级行为。
- 三个 README 改动均在各自职责边界内且与实际实现一致。
- validation 声明（543 focused / 2152 combined / 逐文件 coverage 89-88-83-82-91 / pyright 0 / static
  boundary）由本 review 独立重跑全部复现。

3 个 low findings（1 文档、2 测试网缺口）均不构成 blocker，不影响"warning 同源、success-only、双流、exit
0"的已交付契约。建议 controller 裁决 OQ-1/2/3 后进入 review fix 或直接记录 residuals。
