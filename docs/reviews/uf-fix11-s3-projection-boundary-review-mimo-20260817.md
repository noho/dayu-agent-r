# UF-FIX11 S3 Direct Projection Symbol-Boundary Amendment — Adversarial Plan Review

## Review metadata

- reviewer：MiMo（adversarial plan review）
- date：2026-08-17
- timestamp：20260817-145429
- reviewed target：`docs/gateflow/uf-fix11-s3-projection-boundary-amendment-20260817.md`
- scope：S3 direct projection symbol-boundary amendment；不 review S3 完整实现计划（属于 §10 Slice S3 范围）
- blocker reviewed：`docs/gateflow/uf-fix11-s3-projection-boundary-blocker-20260817.md`
- parent plan reviewed（§6.6.2/§7.2/§10 S3/§12/§17）：`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- code evidence：`dayu/fins/ingestion_runtime.py`、`dayu/fins/direct_events.py`、S3 allowed test files
- skill：`/Users/leo/.agents/skills/planreview/SKILL.md`

## Assumptions tested

1. blocker 声称的 root cause（typed copy 漏列）是否有直接代码证据。
2. blocker 是否遗漏了第三个 production callsite。
3. symbol 扩张是否最小且足够。
4. `_direct_result_event` 的 no-default `warnings` 参数是否会破坏取消/非 upload 生命周期。
5. `FinsResultSummary.warnings` 的空 tuple 默认值是否语义自然。
6. test plan 是否能在不修改 out-of-scope tests 的情况下红测。
7. direct→CLI→wait 是否保持单一 typed source。
8. amendment 是否内部一致、commit boundary/gate order 完整。
9. 是否存在 overcoupling、scope leak、semantic owner drift 或未分类 residual risk。

## Findings

### 001-未修复-低-observation helpers 构造点未在 frozen boundary 中显式列举

- **位置**：§ "Direct typed copy symbols" 和 "Stop condition"
- **问题类型**：契约缺失（低严重度，不影响 amendment 可行性）
- **当前写法**：amendment 只列举了 S3 在 `ingestion_runtime.py` 允许修改的三个 symbol：`_direct_upload_terminal_events`、`_direct_result_event`、`_emit_claimed_direct_result`。stop condition 禁止修改 "上述三个 symbols 之外的 producer"。
- **反例/失败场景**：`ingestion_runtime.py` 中还有三个直接构造 `FinsResultSummary` 的 production 代码：`_observation_failure_result`（L7229）、`_observation_cancelled_result`（L7284）、`_mark_observation_failed`（L7333）。这些不经过 `_direct_result_event`，也不属于 direct projection 链。当 `FinsResultSummary` 增加 `warnings` 字段后，它们会自然获得默认值 `()`，无需修改。但 stop condition 的 "三个 symbols 之外的 producer" 表述可能被误读为"可以修改其他 producer"。
- **为什么有问题**：implementation agent 可能认为需要为这三个 observation helper 显式传 `warnings=()` 以"保持一致性"，导致不必要的代码变更。
- **直接证据**：
  - `ingestion_runtime.py:7229`：`_observation_failure_result` 直接构造 `FinsResultSummary`。
  - `ingestion_runtime.py:7284`：`_observation_cancelled_result` 直接构造 `FinsResultSummary`。
  - `ingestion_runtime.py:7333`：`_mark_observation_failed` 直接构造 `FinsResultSummary`。
  - 这三处均不在 `_direct_result_event` 的调用链中，也不在 `_direct_upload_terminal_events` 或 `_emit_claimed_direct_result` 的调用链中。
- **影响**：implementation agent 可能产生不必要的 diff，但不导致语义错误。
- **建议改法和验证点**：在 stop condition 中补充一句："`_observation_failure_result`、`_observation_cancelled_result`、`_mark_observation_failed` 等非 direct projection 构造点不得修改；它们通过 `FinsResultSummary` 的默认值自然获得 `warnings=()`。"
- **修复风险**：低
- **严重程度**：低

## Challenges answered（无 finding 级别的问题）

### Challenge 1：blocker root cause / 唯一 typed copy 点是否有直接代码证据，是否漏掉第三个 production callsite

**结论：证据充分，未遗漏。**

blocker 的 `rg` 输出列出了 `_direct_result_event` 的全部出现位置：

```text
dayu/fins/ingestion_runtime.py:6231:  event = _direct_result_event(     ← callsite 1（_emit_claimed_direct_result 内）
dayu/fins/ingestion_runtime.py:6434:  def _direct_result_event(        ← 定义
dayu/fins/ingestion_runtime.py:6547:  result_event = _direct_result_event(  ← callsite 2（_direct_upload_terminal_events 内）
```

只有两个 production callsite。`_direct_upload_terminal_events`（callsite 2）是 upload path，`_emit_claimed_direct_result`（callsite 1）是 generic/non-upload path。其余 `FinsResultSummary` 构造点（L7229、L7284、L7333）不经过 `_direct_result_event`，不属于 direct projection 链。

amendment 正确识别了这两个 callsite 并分别指定传值策略。没有第三个 production callsite。

### Challenge 2：ingestion_runtime.py symbol 扩张是否最小且足够

**结论：最小且足够。**

amendment 增加的三个 symbol：

| Symbol | 必要性 | 充分性 |
|--------|--------|--------|
| `_direct_upload_terminal_events` | 是：upload path 的 typed copy 入口 | 是：唯一能访问 `FinsUploadResultSummary.warnings` 并传给 `_direct_result_event` 的位置 |
| `_direct_result_event` | 是：`FinsResultSummary` 的唯一 direct projection 构造点 | 是：新增 `warnings` 参数后，所有 direct result 都经过此点 |
| `_emit_claimed_direct_result` | 是：唯一 generic/non-upload callsite | 是：必须显式传 `warnings=()` 以满足 no-default 约束 |

三个 symbol 构成完整闭环：upload path 通过 `_direct_upload_terminal_events` 传 `summary.warnings`，non-upload path 通过 `_emit_claimed_direct_result` 传 `()`，两者汇入 `_direct_result_event` 构造 `FinsResultSummary`。无需更多 symbol。

### Challenge 3：`_direct_result_event` required no-default + 两 callsite 显式值是否会破坏取消/非 upload 生命周期

**结论：不会。**

- **取消路径**：`_direct_upload_terminal_events` 在 `disposition is CANCELLED` 时仍调用 `_direct_result_event`（L6547-6559）。amendment 要求传 `warnings=()`（cancelled 无 warning），与 §8.5 "cancel 不产生 warning" 一致。`_direct_result_event` 内部的 cancelled 特化逻辑（L6465-6482）不涉及 `warnings`。
- **非 upload 路径**：`_emit_claimed_direct_result` 传 `warnings=()`，与 §8.4 "generic non-upload result 保持空" 一致。
- **observation 路径**：`_observation_failure_result`/`_observation_cancelled_result`/`_mark_observation_failed` 不经过 `_direct_result_event`，直接构造 `FinsResultSummary`，通过默认值 `()` 获得空 warnings，无需修改。

no-default 约束只强制两个 production callsites 显式传值，不改变任何生命周期语义。

### Challenge 4：`FinsResultSummary.warnings` 默认空 tuple 是否语义自然且不成为 compatibility fallback / 漏传掩盖

**结论：语义自然，不是 fallback。**

amendment § "Public summary empty state" 给出了充分论证：

1. **producer 参数仍必填**：`_direct_result_event` 的 `warnings` 无默认值，每个 producer 必须显式声明。
2. **`__post_init__` 校验**：exact 类型校验、最多一个 warning、仅 SUCCESS 可非空。
3. **测试覆盖**：upload tests 断言 exact copy，failed/cancelled/non-upload tests 断言空值。

默认值的语义是"跨 download/preprocess/upload operation 的合法无 warning 状态"。绝大多数合法终态确实无 company metadata warning。把 `warnings` 改为 required 会迫使修改大量无关构造点（L7229、L7284、L7333 及所有 S3 allowed test 文件中的现有构造），仅用于重复表达自然空状态。

**关键区分**：默认值作用于 `FinsResultSummary`（public summary dataclass），不作用于 `_direct_result_event`（producer helper）。producer 必须显式传值；public summary 的默认值只是数据表达。

### Challenge 5：test plan 能否在不修改 out-of-scope tests 的情况下红测捕获 upload warning 丢失、failed/cancelled 误报与 nonupload 回归

**结论：可以。**

S3 allowed test files 包含 `tests/fins/test_fins_direct_stream.py`、`tests/cli/test_output.py`、`tests/cli/test_fins_commands.py`、`tests/service/test_fins_wait_adapter.py`。

- **upload warning 丢失**：在 `test_fins_direct_stream.py` 中新增测试，mock upload with warnings，断言 direct result 的 `FinsResultSummary.warnings` exact copy。
- **failed/cancelled 误报**：断言 failed/cancelled direct result 的 `warnings == ()`。
- **nonupload 回归**：断言 generic non-upload result 的 `warnings == ()`。
- **结构 contract**：AST 检查 `_direct_result_event` 的 `warnings` 参数无默认值。

现有 test constructions（如 `test_fins_direct_stream.py:144` 的 `_result_summary()`）不指定 `warnings`，将获得默认值 `()`，不会破坏。新增测试通过断言（而非修改现有构造）验证行为。

### Challenge 6：direct→CLI→wait 并非相同 consumer 路径时，amendment 是否仍保持单一 typed source

**结论：保持。**

amendment §7.2 的数据流：

```text
FinsUploadResultSummary.warnings
  ├── to_json_summary -> durable job record.result_summary
  ├── FinsResultSummary.warnings -> direct event -> CLI stderr
  └── service runtime -> wait adapter completed result
```

所有 consumer 都从同一个 `FinsUploadResultSummary.warnings` typed tuple 派生。每个路径只做 typed copy/serialize，不重新比较 company names 或读取 storage。单一 typed source 是 `FinsUploadResultSummary.warnings`，不是 `_direct_result_event`。

### Challenge 7：plan 更新是否内部一致，commit boundary / gate order 是否完整

**结论：内部一致，完整。**

- §17 与 blocker/amendment 的 motivation、frozen boundaries、symbol list、parameter strategy 一致。
- plan-gate commit boundary（只允许 docs，禁止 production/test/README）与主 plan §10 的 plan-gate commit boundary 一致。
- gate order：amendment review → fix → re-review → acceptance → plan-gate commit → S3 implementation。完整且无遗漏。
- stop condition 与主 plan §10 S3 的 stop condition 一致（不修改 Host/Engine、不从 raw fields 推断、不扩大文件范围）。

### Challenge 8：是否存在 overcoupling、scope leak、semantic owner drift 或未分类 residual risk

**结论：未发现。**

- **Overcoupling**：amendment 只扩大 symbol 白名单，不改变文件范围、业务目标或 warning owner。三个 symbol 形成最小闭环。
- **Scope leak**：production/test/README allowed 文件全集不变。amendment 只修改 `ingestion_runtime.py` 内的实现细节。
- **Semantic owner drift**：warning 的唯一 semantic owner 仍是 `company_meta_contract.py`（domain fact）→ `company_metadata_warning.py`（public projection）。amendment 不改变 owner 结构。
- **Residual risk**：amendment 的 "Residual classification" 节正确分类。无未分类 residual。

## Open questions

无。amendment 的设计决策（no-default 参数、空 tuple 默认值、symbol 列表）都有直接代码证据支撑，且与主 plan 的 typed contract、owner 和 state machine 一致。

## Residual risks

| 风险 | 分类 | 跟踪目标 |
|------|------|----------|
| observation helpers 可能被误改 | `covered by resumed S3`（stop condition 已隐含禁止，Finding 001 建议显式化） | S3 implementation |
| S3 完整实现的其余 projection/CLI/wait 测试 | `covered by resumed S3` | S3 implementation |
| S1+S2 parser/codec 冻结边界 | `assigned to later work unit`（已在 S1+S2 acceptance 中冻结） | S1+S2 accepted commit |

## Conclusion

**PASS**

amendment 结构完整、证据充分、边界清晰。blocker 的 root cause 有直接代码证据支撑，symbol 扩张最小且足够，参数策略不破坏现有生命周期，测试计划可在 allowed files 内覆盖关键场景。唯一的低严重度 finding（observation helpers 未在 stop condition 中显式列举）不影响 amendment 的可实施性，建议在 implementation 阶段补充。
