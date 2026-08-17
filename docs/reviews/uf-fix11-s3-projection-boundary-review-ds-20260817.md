# UF-FIX11 S3 Direct Projection Symbol-Boundary Amendment — DS 第二路独立 Plan Review

- reviewer：DS（第二路独立 adversarial review）
- 时间：2026-08-17 15:01:31 +0800
- review target：
  - `docs/gateflow/uf-fix11-s3-projection-boundary-amendment-20260817.md`（amendment）
  - `docs/gateflow/uf-fix11-s3-projection-boundary-blocker-20260817.md`（blocker）
  - `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`（accepted plan，含工作树未提交的 §6.6.2 / §S3 / §12.5 / §17 修订）
- 独立声明：本 review 未读取 MiMo 路 review artifact，所有结论仅基于上述文档与代码/测试直接证据独立得出。
- scope：只读 plan review。未修改 production/test/README/plan；未 stage/commit。

## 1. Reviewed target and scope

Amendment 主张：原 accepted S3 把 `dayu/fins/ingestion_runtime.py` 的 symbol 白名单限制为
`FinsUploadResultSummary`/invariant/serialization，但真实 direct typed copy 必经
`_direct_upload_terminal_events -> _direct_result_event -> FinsResultSummary`，白名单漏列导致
S3 implementation 只能静默丢 warning、从 details/raw request 反推或引入 shim。修订只扩大同一
allowed file 的 symbol 白名单（`_direct_upload_terminal_events`、`_direct_result_event`、
`_emit_claimed_direct_result`），参数策略为 builder 必填无默认、upload exact tuple、
generic 显式 `()`，`FinsResultSummary.warnings=()` 为合法空状态；并冻结其余所有边界。

Assumptions tested：

- A1：blocker 的 rg callsite 全集准确、无遗漏生产调用点；
- A2：三个新增 symbol 恰好构成 minimal sufficient 白名单；
- A3：upload exact tuple / generic 显式空是正确且唯一的 owner boundary 选择；
- A4：`FinsResultSummary.warnings=()` 默认值不会掩盖 production 漏传，invariant + 结构测试足够；
- A5：SUCCESS-only 语义覆盖 uploaded/skipped，failed/cancelled/deleted/non-upload 全为空；
- A6：direct/CLI/wait/durable 四路投影仍从同一 typed owner；
- A7：新测试全部落在 S3 allowed test files 内，无需越界文件；uploaded/skipped/failure/cancel/generic/AST 红绿测试无缺口；
- A8：plan/amendment 内部一致，gate/commit 边界、README、validation/static check 完整；
- A9：无 overcoupling，state-machine/并发/取消不受影响，无 semantic ownership drift。

## 2. 直接代码证据（本 review 独立复核）

- `dayu/fins/ingestion_runtime.py:4508-4519`：`start_upload` 取 `upload_runner.run_upload` 返回的
  typed `FinsUploadResultSummary`，同一对象传入 `_direct_upload_terminal_events`。✓ blocker 引用准确。
- `dayu/fins/ingestion_runtime.py:6510-6561`：`_direct_upload_terminal_events` 是唯一持有 upload
  summary 并调用 `_direct_result_event` 的 helper；当前调用（6547-6560）无 warnings 参数。✓
- `dayu/fins/ingestion_runtime.py:6434-6507`：`_direct_result_event` 当前签名无 warnings；
  `FinsResultSummary` production 构造发生在此（6497-6506）。✓
- `_direct_result_event` production callsites 全集 = 2：`6231`（`_emit_claimed_direct_result`，
  唯一 generic/non-upload callsite）与 `6547`（upload callsite）。`_emit_claimed_direct_result`
  唯一调用者为 `_emit_direct_result`（6190），覆盖 download/preprocess/upload-runner-None 等
  全部非 upload 或失败路径；production 中所有 `FinsResultStatus.SUCCESS` 构造（4386、4444 为
  preprocess）都经 `_emit_direct_result -> _emit_claimed_direct_result -> _direct_result_event`。✓
- `FinsResultSummary` production 构造点全集 = 4：6497（builder，唯一 SUCCESS-capable）、
  7229（`_observation_failure_result`，FAILURE）、7284（`_observation_cancelled_result`，CANCELLED）、
  7333（`_mark_observation_failed`，FAILURE）。后三者全部非 SUCCESS。✓
- `dayu/fins/direct_events.py` 无 `FinsUploadResultSummary` 引用；`direct_events.py:588-663`
  `FinsResultSummary` 为 frozen dataclass + `__post_init__` 校验，适合追加 warnings invariant。✓
- 四路投影同源链（代码验证）：
  - direct：`_direct_upload_terminal_events(summary)` → `FinsResultSummary` → `FinsEvent.result`；
  - CLI：`dayu/cli/output.py:233-258` 只读 `event.result`（SUCCESS 走 stdout，warnings 将走 stderr）；
    `dayu/cli/commands/fins.py:905-934` 只透传/渲染，无 summary 字段语义，无需修改；
  - wait：`ingestion_runtime.py:4128-4131` `record.result = item.result`（同一 FinsResultSummary
    对象进入 observation record），`dayu/service/fins_wait_adapter.py:541-586` 从 snapshot 投影；
  - durable：`FinsUploadResultSummary.to_json_summary()` 写入 job `result_summary`；
    re-read（8230/8254/8281）只消费 status/document_id。✓
- 所有 projection 源于同一个 `FinsUploadResultSummary` 实例（direct 路径 4508、durable job 路径
  4992 各取 runner 返回值，owner 链相同：`FinsUploadPipelineResult.warnings` 经
  `service_runtime._upload_summary_from_result:310-323` 机械复制）。✓
- S1+S2 已冻结事实（HEAD `5bb122d3`）：`FinsUploadPipelineResult.warnings` 已存在
  （`ingestion_runtime.py:1704`），invariant 仅允许 `ok`/`skipped` 携带（1733-1740），
  `company_metadata_warning.py` 提供 `company_metadata_warnings_to_json` 等双向闭集 codec。✓
- 工作树计划 diff 证实 blocker 前提：HEAD 版本 S3 白名单确为“仅 summary/invariant/to_json_summary”，
  本次未提交修订才加入三个 helper（`git diff` 736 行区段）。✓ blocker 的 root cause 成立。
- 工作树现状：`git status` 仅 docs 修改/新增（plan 修改、blocker、amendment、MiMo review artifact），
  零 production/test diff。✓

## 3. Findings

### F-01-未修复-中-S3 测试枚举缺两类 contract 红测与两个空值投影用例
- **位置**: amendment “Test and static contract” 清单；accepted plan §S3 “Tests” 段
- **问题类型**: 测试缺口
- **当前写法**: amendment 只列 uploaded/skipped exact copy、failed/cancelled 空、generic 空、
  AST 签名。plan §S3 Tests 同样只列投影断言与结构测试，未列新增 invariant 的构造器拒绝红测。
- **反例/失败场景**:
  1. `FinsResultSummary(warnings)` 的“仅 SUCCESS 可非空/最多一个/精确类型”invariant 与
     `FinsUploadResultSummary` 的 success-only invariant 是 S3 新增 contract 分支；若无显式红测，
     实现可能只写正向断言，invariant 分支实际未被执行（覆盖 gate 依赖 aggregate，分支检查人工执行），
     未来宽松化无人察觉。
  2. `deleted` 上传终态映射 `FinsUploadTerminalDisposition.COMPLETED` → direct
     `FinsResultStatus.SUCCESS`（`ingestion_runtime.py:325`、`6704`）。若 `FinsUploadResultSummary`
     success-only 的“success”集合被实现为按 disposition 判（含 deleted），delete 携带 warning 会
     穿过 summary 层进入 SUCCESS direct result，仅靠 S1+S2 pipeline invariant 兜底；amendment 测试
     清单没有 deleted 直接投影用例。
  3. “uploaded/skipped 但无 warning”的 exact copy（`summary.warnings == ()` → result `()`）没有
     单独用例；generic 用例不能替代 upload-空值同源断言（material upload 是 upload 路径）。
- **为什么有问题**: CLAUDE.md 要求“测试必须断言 owner 级 contract 行为”；S1+S2 对 parser 红测
  枚举到 missing/null/malformed/unknown/duplicate/超限，S3 对新增两个 summary invariant 的
  枚举明显薄于同 work unit 标准，属 plan 层面测试规格不完整。
- **直接证据**: amendment “Test and static contract” 四条清单原文；plan §S3 Tests 原文；
  `ingestion_runtime.py:323-326` disposition 映射（ok/skipped/deleted 全为 COMPLETED）；
  `ingestion_runtime.py:1733-1740` S1+S2 冻结的 ok/skipped-only 先例。
- **影响**: 实现 Agent 可能不写 invariant 红测；deleted 语义依赖跨层间接保证；后续变更可静默放宽
  success-only 契约。
- **建议改法和验证点**:
  1. 在 test 清单显式增加：`FinsResultSummary` FAILURE/CANCELLED + 非空 warning → raise；
     >1 warning → raise；非精确类型 → raise；`FinsUploadResultSummary` 同样三组红测。
  2. 明确 `FinsUploadResultSummary` success-only 的“success”集合必须与 pipeline invariant 一致
     （仅 `ok`/`skipped`，deleted 排除），并以 deleted 红测锁定。
  3. 增加 “uploaded 空 warning exact copy” 与 “deleted direct result 空 warning” 两个正例。
- **修复风险（低）**: 仅补测试规格文本，不动架构。
- **严重程度（中）**

### F-02-未修复-低-AST 结构测试须断言 callsite 全集枚举而非仅“两处显式传值”
- **位置**: amendment “Test and static contract” 第 4 条；plan §12.5 人工检查
  “没有第三个 production callsite”
- **问题类型**: 测试缺口 / 契约缺失
- **当前写法**: “AST/签名 contract 证明 `_direct_result_event` 的 warnings 无默认值，且两个
  production callsites 分别显式传 `summary.warnings` 与 `()`”。
- **反例/失败场景**: 若实现只做 `inspect.signature` 无默认 + 逐点断言两处 kwargs，未来新增第三个
  callsite 且显式传值时测试仍绿；“显式”不等于“全集”。这正是 `warnings=()` 默认值唯一可能的
  长期掩盖路径（新的 SUCCESS 构造点漏传被默认空吞掉）。
- **为什么有问题**: amendment 的核心论证是“builder 必填 + 两处显式 = 漏传不可达”；该论证只成立于
  AST 测试对 callsite 做穷举断言（收集全部 `_direct_result_event` Call 节点并断言其集合恰为
  `{summary.warnings, ()}`）。
- **直接证据**: amendment 第 4 条原文未出现“全集/穷举”字样；§12.5 人工检查可补但属人工步骤，
  测试层应可机检。
- **影响**: 结构防线的防回归能力弱于 amendment 论证所需。
- **建议改法和验证点**: 测试规格明确写“穷举 `ingestion_runtime.py` 中 `_direct_result_event`
  全部 Call 节点，断言 warning 实参集合恰为 {`summary.warnings`, `()`}，新增 callsite 即红”。
- **修复风险（低）**
- **严重程度（低）**

### F-03-未修复-低-`FinsUploadResultSummary.warnings` 是否带默认值未 pin，成功集合语义未 pin
- **位置**: accepted plan §6.6.2 第一/二条；amendment 未覆盖
- **问题类型**: 不可直接实施 / 契约缺失
- **当前写法**: plan 只说 “`FinsUploadResultSummary` 在 S3 增加 tuple 及 success-only invariant”，
  未规定该字段是否有 `= ()` 默认；amendment 只裁决了 `FinsResultSummary` 的默认值问题。
- **反例/失败场景**: 实现 Agent 可任选：
  - 带默认：`ProductionFinsUploadRunner.run_upload` cancelled 早退构造
    （`service_runtime.py:132`）与失败构造（`ingestion_runtime.py:4488/4971`）依赖默认；
  - 不带默认：需改这三处（仍在 allowed files 内，但改动面扩大）。
  两种选择都合法但改动面不同，plan 未裁决会产生实现漂移；且 “success” 集合（ok/skipped 还是含
  deleted）同样未 pin（与 F-01 第 2 点同源）。
- **为什么有问题**: 与 amendment 对 `FinsResultSummary` 默认值的明确裁决不对称；该字段的默认值
  策略直接决定 `_upload_summary_from_result` 之外三处构造是否需要显式传参，属于
  code-generation-ready 缺口。
- **直接证据**: plan §6.6.2 原文无默认值字样；`service_runtime.py:132`、
  `ingestion_runtime.py:4488/4971` 三处非 pipeline 构造点。
- **影响**: implementation Agent 需自行设计，可能扩大或缩小改动面；review 时无基准裁决。
- **建议改法和验证点**: 在 plan/amendment 中 pin：字段带 `= ()` 默认（与 pipeline result 先例
  一致），`_upload_summary_from_result` 仍必须显式机械复制 `result.warnings`；success 集合
  显式写为 {`ok`,`skipped`}（deleted 排除），理由与 S1+S2 pipeline invariant 对齐。
- **修复风险（低）**
- **严重程度（低）**

### F-04-未修复-低-direct copy 测试落位与 `tests/fins/test_fins_direct_stream.py` 既有文件职责冲突
- **位置**: amendment “Test and static contract” 指定 `tests/fins/test_fins_direct_stream.py` 必须覆盖
  uploaded/skipped/failed/cancelled/generic/AST
- **问题类型**: 最佳实践偏离 / 过度耦合（测试组织）
- **当前写法**: amendment 把 `_direct_upload_terminal_events`/`_direct_result_event` 的 runtime helper
  级 owner 测试落位在该文件。
- **反例/失败场景**: 该文件当前 100% 是 `ValidatedFinsEventStream` 契约测试（模块 docstring：
  “Fins direct stream 唯一终态 owner 的契约测试”，仅 import `direct_events`）。新增测试需要
  import/构造 `_FinsIngestionExecutionContext`、`FinsUploadResultSummary` 与 validated upload
  request，实质是 `ingestion_runtime` 内部 helper 单测；`tests/fins/test_fins_ingestion_runtime.py`
  （同为 allowed file）已有同性质先例（如 678 行 `_upload_result_details` owner 测试）。
- **为什么有问题**: 文件职责边界被混合，后续维护者定位困难；不是 boundary violation，但属于
  可避免的测试组织耦合。
- **直接证据**: `tests/fins/test_fins_direct_stream.py:1-24` import 与全部 15 个测试均为
  ValidatedFinsEventStream；`tests/fins/test_fins_ingestion_runtime.py:678` 同类 helper owner 测试先例。
- **影响**: 测试可维护性下降；后续 slice 可能继续向错误文件堆叠。
- **建议改法和验证点**: 二选一并 pin：把 direct copy/AST 测试落位
  `tests/fins/test_fins_ingestion_runtime.py`；或保留落位但同步更新
  `tests/fins/test_fins_direct_stream.py` 模块 docstring 明确其同时拥有 upload terminal
  projection owner 测试的职责。任一选择都不改变 allowed files。
- **修复风险（低）**
- **严重程度（低）**

### F-05-未修复-低-`_direct_result_event` CANCELLED 归一化分支未同步归零 warnings
- **位置**: amendment “Direct typed copy symbols” 第 2 条
- **问题类型**: 状态机漏洞（防御性缺口，非真实反例）
- **当前写法**: `_direct_result_event` 现状对 CANCELLED 强制归一化 details/error_kind/
  error_message/download/failure（6465-6482），amendment 未要求该分支对 warnings 同步处理。
- **反例/失败场景**: 当前真实调用链不会触发（upload cancelled summary 的 warnings 必为空，
  generic 显式传 `()`；否则 `FinsResultSummary` invariant 会 raise，属 fail-fast）。风险仅在未来
  某调用者传入非空 warnings + CANCELLED 时依赖 constructor raise 兜底，而非 helper 层显式归零。
- **为什么有问题**: 与既有 CANCELLED 归一化风格不一致；同时可作为 invariant 的本地化防线。
- **直接证据**: `ingestion_runtime.py:6465-6482` 现有归一化分支。
- **影响**: 极低；仅防御纵深。
- **建议改法和验证点**: 可在 amendment 中写明“CANCELLED 分支保持现状或同步置空 warnings 由
  implementation 二选一，但必须被 direct cancelled 测试覆盖”；不强制。
- **修复风险（低）**
- **严重程度（低）**

## 4. 用户指定核查点结论

1. **root cause 与 callsite 全集**：blocker 的 rg 全集经独立复核准确无误；`_direct_result_event`
   恰 2 个 production callsites，`_direct_upload_terminal_events` 恰 1 个 callsite，无遗漏生产调用点。
   白名单漏列的 root cause 由 `git diff` 对 HEAD 计划原文证实。
2. **symbol 白名单最小充分性**：`_direct_upload_terminal_events`（upload exact copy）、
   `_direct_result_event`（typed 必填参数 + FinsResultSummary 投影）、`_emit_claimed_direct_result`
   （generic 显式空）三个 symbol 构成最小充分集；observation 三个直接构造点均为非 SUCCESS，
   依赖字段默认值即可，无需入白名单。✓
3. **owner 正确性**：upload 传 `summary.warnings`（该对象与 durable `to_json_summary` 同实例同源），
   generic 显式 `()`，与 §7.2 传播图、S1+S2 冻结 parser 完全一致。✓
4. **`FinsResultSummary.warnings=()` 是否掩盖漏传**：当前生产 4 个构造点中唯一 SUCCESS-capable
   构造点（`_direct_result_event`）参数必填，3 个非 SUCCESS 构造点即使漏传也只能是合法的空状态，
   故现状不构成掩盖；长期风险仅存在于“未来新增绕过 builder 的 SUCCESS 构造点”，由 F-02 的穷举
   AST 测试与 invariant 收口（建议按 F-02 强化后视为充分）。改为 required 字段被 amendment 拒绝的
   理由成立（会迫使无关 download/preprocess 构造点与越界测试文件为 upload 专属事实重复表达空值）。✓
5. **SUCCESS-only**：pipeline 层已冻结（仅 ok/skipped）；S3 两个 summary 层将新增同 invariant；
   failed/cancelled/deleted/non-upload 全为空在 owner 链上成立。deleted 的 summary 层集合语义
   需按 F-01/F-03 pin。基本满足，有一处规格精度缺口。
6. **direct/CLI/wait/durable 同源**：代码验证四路均从同一 `FinsUploadResultSummary` 派生
   （wait 甚至持有同一 `FinsResultSummary` 对象，CLI 只渲染 `event.result`），不存在计划混淆链路。✓
7. **测试越界与缺口**：无需越界文件（`tests/service/test_fins_direct.py`、
   `tests/fins/test_fins_ingestion_tools.py` 既有构造点因字段默认值不受影响，已逐处核查）。
   但缺 invariant 红测、uploaded-空/deleted 用例（F-01）与 AST 穷举语义（F-02）。
8. **计划内部一致性、gate/commit 边界、README/validation/static check**：amendment 与 plan §6.6.2/
   §S3/§12.5/§17 一致；plan-gate commit 边界与 slice-amendment 先例（`0b4740fa`）一致，当前工作树
   仅 docs diff；README 保持归 S3，未被 amendment 触碰；§12.5 已补 callsite 人工检查项。✓
9. **overcoupling、state-machine/并发/取消、semantic ownership drift、residual**：无新增跨层耦合、
   无共享可变状态（tuple 不可变，`_direct_upload_terminal_events` 为纯构造，claim 时序不变）；
   CANCELLED 归一化缺口见 F-05；无 semantic ownership drift，本 amendment 反而消除了一条潜在
   下游补偿路径。✓

## 5. Open questions

- OQ-1：AST 测试是否按 F-02 实现为 callsite 穷举断言？（建议是，否则默认值论证的防线不闭合）
- OQ-2：`FinsUploadResultSummary.warnings` 默认值策略与 success 集合是否在 plan 正文 pin？
  （F-03，建议默认 `= ()` + 显式机械复制 + success={ok,skipped}）
- OQ-3：direct copy/AST 测试最终落位 `test_fins_direct_stream.py` 还是
  `test_fins_ingestion_runtime.py`？（F-04，二者均在 allowed files，需 amendment 或
  controller 裁定其一并同步文件职责声明）

## 6. Residual risks and suggested tracking destination

- R-1（接受的设计权衡）：`FinsResultSummary.warnings=()` 对“未来绕过 `_direct_result_event` 的
  SUCCESS 直接构造”的静默容忍。建议在 `FinsResultSummary.warnings` docstring 注明“SUCCESS
  生产构造必须经 `_direct_result_event` 显式声明 warnings”，并依赖 F-02 穷举 AST 测试防回归。
  追踪：S3 implementation review 时人工检查。
- R-2（spec 精度）：`FinsUploadResultSummary` success 集合含 deleted 的歧义（F-01/F-03）。
  追踪：S3 implementation 前必须收敛。
- R-3（测试组织）：direct copy 测试落位与文件职责冲突（F-04）。追踪：S3 implementation 前裁定。
- R-4（防御纵深）：CANCELLED 分支不归零 warnings（F-05），依赖 invariant fail-fast。
  追踪：S3 implementation review 时确认行为被 cancelled 测试覆盖。

## 7. Final conclusion

**PASS（pass-with-risks）**

Amendment 的动机、root cause、callsite 全集、symbol 白名单最小充分性与 owner 正确性全部经独立
代码证据复核成立；`warnings=()` 默认值不构成当前生产漏传掩盖，参数必填策略与 S1+S2 冻结边界一致；
四路投影同源链完整；gate/commit 边界与先例一致；无越界文件需求。未发现 blocker 级问题。

上述 5 个 findings（1 中 4 低）均不推翻方向：F-01/F-03 需在 S3 实施前收敛测试枚举与
success 集合语义，F-02 需把 AST 测试规格明确为穷举断言，F-04/F-05 为组织与防御性偏好。
建议 controller 裁决后由 amendment fix 一次性收口，再进入双路 re-review。
