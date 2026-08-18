# UF-FIX11 S3 Projection Boundary Amendment — DS 定向 Re-Review

- reviewer：DS（第二路，同一 review task 延续）
- 时间：2026-08-17 15:27:26 +0800
- review target：
  - `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`（工作树最新版，含 review-fix 修订）
  - `docs/gateflow/uf-fix11-s3-projection-boundary-amendment-20260817.md`（review-fix 后最新版）
  - `docs/gateflow/uf-fix11-s3-projection-boundary-review-fix-20260817.md`（controller adjudication）
  - `docs/reviews/uf-fix11-s3-projection-boundary-review-ds-20260817.md`（本路 initial review）
- scope：只读定向 re-review。未修改任何已有文件；未 stage/commit；仅新增本 artifact。
- 独立声明：本 re-review 仍未读取 MiMo 路 artifact 内容，MiMo Finding-001 仅经 review-fix 的
  adjudication 表述与 plan/amendment 的落地文本验证关闭。

## 1. 逐项关闭确认

### DS F-01（中，测试枚举缺口）— CLOSED

- amendment “Test and static contract” 第 1 条：`tests/fins/test_fins_ingestion_runtime.py` 覆盖
  `FinsUploadResultSummary` exact-element、at-most-one、`ok`/`skipped` success-only invariant；
  非精确元素、超过一个、`failed`/`cancelled`/`deleted` + 非空全部拒绝。
- 第 2 条：uploaded/skipped exact copy、**uploaded 空值 exact copy**、failed/cancelled/**deleted**
  与 generic non-upload 空值、CANCELLED + 非空 fail closed，全部点名。
- plan §6.6.2：`FinsUploadResultSummary` 成功集合 pin 为 exact `ok`/`skipped`，`deleted` 显式排除；
  `FinsResultSummary` “非 SUCCESS + 非空是非法 typed 组合，必须 fail closed”。
- plan §S3 Tests 同步落名 deleted 红测与 uploaded 空值投影。
- 验证点：原 finding 的三条反例（invariant 红测缺失、deleted 经 disposition 映射穿层、uploaded 空值
  无独立用例）全部被点名覆盖；success 集合语义与 S1+S2 pipeline invariant（`ingestion_runtime.py:1733-1740`）
  精确对齐。

### DS F-02（低，AST 穷举语义）— CLOSED

- amendment 第 3 条：AST contract **穷举** `ingestion_runtime.py` 中 `_direct_result_event` 全部
  `Call` 节点，数量 **exact 为两个**，warnings 实参集合 **exact 为 `summary.warnings` 与 `()`**，
  新增任何 callsite 立即红。
- plan §12.5 人工检查同步收紧：per-function 映射（`_direct_upload_terminal_events` 传
  `summary.warnings`、`_emit_claimed_direct_result` 传 `()`）。
- 补充分析（不构成 finding）：warnings 实参为集合级断言，理论上无法识别两处互换；但 generic helper
  作用域内不存在 `summary` 变量，互换无法通过编译/pyright，因此集合断言 + 类型检查足以锁定映射，
  属 code-generation-ready。

### DS F-03（低，summary 默认值/success 集合未 pin）— CLOSED

- amendment “Public summary empty state” 第二段：`FinsUploadResultSummary.warnings` 同样
  `= ()`，但 `_upload_summary_from_result` 必须显式传 `result.warnings` 不得依赖默认；可携带状态
  闭集精确为 `ok`/`skipped`，`failed`/`cancelled`/`deleted` 必须为空。
- plan §6.6.2 前两条与 §S3 Exact changes 第 2 条同步 pin。
- plan §S3 Tests：`tests/fins/test_fins_service_runtime.py` 断言 `_upload_summary_from_result`
  显式 exact copy。补充分析：行为断言（pipeline warnings 非空时 summary 必须相等）即可证伪
  “依赖默认值”实现，无需额外结构测试；该实现错误会直接表现为可观测空值，测试足以捕获。
- 验证点：原 finding 的两处未 pin（默认值策略、success 集合）均已显式裁决。

### DS F-04（低，test 落位与文件职责冲突）— CLOSED

- amendment 第 4 条：`tests/fins/test_fins_direct_stream.py` 只拥有 `FinsResultSummary` public
  invariant 与 stream contract，**禁止 import ingestion runtime private helper**；runtime
  helper/AST 测试落位 `tests/fins/test_fins_ingestion_runtime.py`。
- plan §S3 Tests 对应两条按文件拆分，与 amendment 一致。
- 验证点：落位与既有先例（`tests/fins/test_fins_ingestion_runtime.py:678`
  `_upload_result_details` owner 测试）一致；两文件均在 S3 allowed list，无 boundary 变化；
  禁止 import 条款使 `test_fins_direct_stream.py` 维持其模块 docstring 声明的最小职责。

### DS F-05（低，CANCELLED 归一化）— REJECTED-WITH-REASON，裁决正确，确认接受

复核 controller 的 rejected-with-reason，结论：**constructor fail-closed 优于 helper 静默归零，
裁决成立**：

1. **语义所有权**：success-only 是 `FinsResultSummary` public contract 的 invariant，唯一 owner 是
   其 constructor。helper 静默归零会在下游 helper 层复制同一规则，形成第二 enforcement 点——
   正是 CLAUDE.md 明令禁止的“下游补偿/fallback 补救错误语义”模式；本 amendment 的全部动机就是
   消除 silent loss 路径，再引入一条静默归零通道自相矛盾。
2. **既有归一化不可类比**：`_direct_result_event` 现有 CANCELLED 分支对 details/error_kind/
   error_message/download/failure 的强制替换，是 cancellation 状态机对这些字段的 canonical 重定义
   （cancelled 存在法定值）；warnings 没有 canonical cancelled 值，空仅是事实缺失。非空 + CANCELLED
   是非法 typed producer 组合，静默清空会掩盖 owner violation，fail-closed 保留可见失败。
3. **无运行时风险**：穷举两条真实路径——upload cancelled 的 summary 在 `FinsUploadResultSummary`
   invariant 层已拒绝非空（构造早于 `_direct_upload_terminal_events` 调用，`ingestion_runtime.py:4508-4513`
   顺序不变）；generic 路径显式传 `()`。不存在可触发的 CANCELLED + 非空路径，fail-closed 只拦截
   未来 producer bug，且发生在 event 入队前的构造点，失败可见、可测。
4. **测试锁定充分**：amendment 点名 “CANCELLED + 非空 direct result fail closed” 红测；
   plan §6.6.2、§S3 stop condition、§12.5 人工检查三层同步 pin “禁止静默归零”。

原 F-05 本为“不强制”的防御性偏好，controller 的裁决比原建议更符合项目语义所有权纪律，本路确认接受。

### MiMo Finding-001（observation helpers 冻结）— CLOSED

- amendment 新增段落：`_observation_failure_result`、`_observation_cancelled_result`、
  `_mark_observation_failed` 是非 SUCCESS observation 构造点，保持 `FinsResultSummary.warnings=()`
  自然空状态；**S3 禁止修改这三个函数**，不纳入 direct typed copy 白名单。
- plan §S3 stop condition 新增：三函数出现任何 diff 即停止。
- plan §12.5 新增 `rg` 命令（三函数 + `_direct_result_event` 于 production 与对应测试）与人工检查项
  （“三函数函数体无 diff”）。
- 验证点：冻结与白名单互斥关系明确；本路 initial review 的 R-1 残余（observation 构造点依赖默认值）
  以“冻结 + AST 穷举 + required builder param”三重机制收口，无需 docstring 软约束，关闭方式更强。

## 2. Code-generation-readiness 复核

- AST 穷举：count==2 + arg set exact + per-function 映射（plan §12.5）已 pin，可用 `ast` 遍历
  `ingestion_runtime.py` 模块源码直接实现；测试文件位于 repo root 运行约定内。✓
- test 落位：两文件职责、import 禁止条款、既有先例全部明确。✓
- deleted/empty/invariant 规格：`ok`/`skipped` 集合、`deleted` 排除、uploaded 空值、CANCELLED 红测、
  `FinsResultSummary` 非 SUCCESS 拒绝，全部以可执行断言文本表达，无“实现自行理解”残留。✓
- `_upload_summary_from_result` 显式复制：以行为断言可证伪（见 F-03 确认）。✓

## 3. 新增问题检查（无）

- **scope**：production/test/README allowed 文件全集未变；symbol 白名单仍为三个 helper，未因 fix 扩大。
- **owner**：未新增语义 owner；observation 三函数显式排除出 projection owner；success-only
  invariant 的唯一 enforcement 点锁定在 public constructor。
- **gate/commit**：plan-gate commit 文件清单不变（fix/re-review/acceptance artifacts 均已包含于
  “双路 review、fix、re-review 与 acceptance”条款）；当前 gate 为双路 re-review，S3 implementation
  仍暂停；工作树实测仅 docs diff，零 production/test/README 变更。
- **residual**：review-fix 声明“未分类 residual risk 为零”；本路 initial R-1~R-4 全部关闭或经
  rejected-with-reason 裁决（R-4 → F-05），无新增未分类残余。
- **overcoupling/状态机/并发/取消**：fix 仅收紧 plan 文本与测试规格，不引入任何新耦合；
  `_direct_upload_terminal_events` 纯构造、claim 时序、tuple 不可变性均未变化。

## 4. Trivial observations（非 finding，不阻塞）

- amendment 头部 “Gate metadata” 第 11 行 `completion status：READY FOR PLAN REVIEW` 与文末
  “Completion status” 段落的 `READY FOR RE-REVIEW` 不一致；文末为权威表述，建议 acceptance 前
  顺手同步头部一行。
- plan §16 “Plan amendment gate closeout” 的“当前 gate/当前 blocker/下一入口”仍描述 S1+S2 gate
  收口历史；§0 已正确切换到当前 S3 projection boundary review-fix gate，§16 属历史记录可接受，
  若后续 gate 再变建议在 §0 维护统一当前态。

## 5. Open questions

无。上一轮 OQ-1~OQ-3 均已由 controller 裁决落入 plan/amendment 正文。

## 6. Residual risks

- 长期风险（已接受、机械防线覆盖）：未来绕过 `_direct_result_event` 的新 SUCCESS 构造点依赖默认空值
  ——由 AST 穷举红测 + required builder param + observation 三函数冻结收口；追踪：S3 implementation
  review 人工确认三函数无 diff。
- CANCELLED + 非空 fail-closed 依赖 constructor invariant 而非 helper 层防御——经裁决为正确 owner
  boundary，追踪：S3 红测落地。

## 7. Final conclusion

**PASS**

DS F-01~F-04 逐项关闭且落地文本与 plan/amendment 两处同步一致；F-05 rejected-with-reason 裁决正确
（constructor fail-closed 是 success-only invariant 的唯一 owner 边界，helper 静默归零违反语义
所有权与禁止下游补偿约束）；MiMo Finding-001 经 amendment 冻结条款、stop condition 与 §12.5 静态
检查三重落地关闭。AST 穷举、test 落位、deleted/empty/invariant 规格均达到 code-generation-ready。
无新 scope/owner/gate/residual 问题，工作树保持 docs-only。可进入 controller acceptance 与
plan-gate commit。
