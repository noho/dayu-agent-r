# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Corrected-plan Review Controller Adjudication

## 1. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` continuation；不是新 WU。
- Gate：Slice 3 corrected plan 双路完整 review 的 Controller 逐项裁决。
- Reviewed plan SHA-256：`ef4a0832f1885e4013d673294b944a56280619baab1f97d438896af5c8cbedcf`。

Review artifacts：

| Reviewer | Artifact | SHA-256 | Verdict |
| --- | --- | --- | --- |
| AgentMiMo | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-mimo.md` | `f3d59d0ac7e6f5528fd90f3ab6104f504b08242093d2f658bd505371a620c1fa` | material candidates，建议plan fix |
| AgentDS | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-ds.md` | `c606f94e9353862ec30600360dfce2b21662cfbb13137d5c0b4422d0ed02fa3b` | `PASS-WITH-RISKS / PLAN_FIX_REQUIRED` |

## 2. Controller direct environment evidence

Controller 没有直接接受 reviewer 的全局 Python 证据，而是在项目锁定环境执行：

```text
source .venv/bin/activate
docling-core = 2.74.0
```

Fresh evidence：

| Ref | Pydantic model | `resolve(empty_document)` |
| --- | --- | --- |
| `not-a-valid-cref` | `string_pattern_mismatch` | 不可达 |
| `#/texts/NaN` | `string_pattern_mismatch` | 不可达 |
| `#/missing/0` | accepted | `AttributeError` |
| `#/texts/999` | accepted | `IndexError` |
| `#` | accepted | `RuntimeError: Unsupported number of path components: 1` |

另外，Python `str.split()` 对NBSP、thin space与narrow no-break space均按whitespace分割；`_normalize_whitespace()`的`" ".join(text.split())`会把这些字符规范为普通单空格。AgentDS 的F01/F02/F04核心证据来自未激活项目`.venv`的全局Docling/Python环境，不能据此裁决current code。

AR-F06 exact scheduler node 在当前HEAD的fresh collect-only结果为`1 test collected`；plan仍应把存在性检查写成fail-closed gate，避免未来command drift。

## 3. Accepted plan findings

### S3-PR-CF01 — current-schema root ref边界

部分接受MiMo 003/004与DS F01，但以项目`.venv`直接证据重述：任意invalid string确实在load边界失败；真正遗漏的是schema-valid document-root ref `#`，它在public `resolve()`抛`RuntimeError`。Plan必须：

- 保留model-invalid ref在load边界失败的原规则，并固定一个在current `.venv`真实失败的值。
- 新增root ref public test。
- 只通过typed `RefItem.cref`与一个命名模块常量识别document-root sentinel并跳过；不得捕获全部`RuntimeError`、解析raw JSON pointer、匹配第三方异常文本或新增fallback/第二resolver。
- 继续只在单次resolve周围捕获current public implementation对unknown collection/out-of-range产生的`AttributeError`/`IndexError`；不增加warning/logging side effect。该catch是optional caption metadata owner的fail-safe，不是通用Docling错误处理。

### S3-PR-CF02 — JSON/Python ref术语

接受DS F03。Plan必须明确：Python typed field是`RefItem.cref`，真实Docling JSON alias是`$ref`；production只消费typed Python API，只有loader-boundary test编辑serialized `$ref`。

### S3-PR-CF03 — page provenance fixture

接受MiMo 006的可执行性部分，但更正类型名：current public type是`ProvenanceItem(page_no, bbox, charspan)`，不是`ItemProv`。Plan必须要求用真实`ProvenanceItem`与`BoundingBox`构造page provenance，并通过public serialize/load；不得改private table/page state。

### S3-PR-CF04 — multi-caption rationale

接受MiMo 002/014的plan clarity部分：说明单空格连接是因为current `captions: list[RefItem]`不携带ref间分隔元数据；大小写敏感去重避免把可能有业务区分的原文擅自折叠。不得因此新增标点猜测、case-fold、Unicode normalization框架或第二语义。

### S3-PR-CF05 — scheduler exclusion存在性

接受DS F07。每次coverage前先用exact `pytest --collect-only`确认node存在且唯一；失败立即STOP，不能让不存在的`--deselect`静默通过。该检查不改变AR-F06的retained/unfixed/unwaived状态。

## 4. Rejected / no-action findings

| Candidate | Decision | Direct reason |
| --- | --- | --- |
| MiMo 001 | `REJECTED_WITH_REASON` | `TextItem`需要runtime `isinstance`，其它Docling names仅作postponed annotations/loader local import；required dependency已固定，单一runtime import有直接理由，不要求机械统一全部imports。 |
| MiMo 003 warning方案 | `REJECTED_WITH_REASON` | warning/log不是caption业务事实或现有诊断contract，会增加operator noise；root ref可用typed sentinel精确处理，unknown/out-of-range已有public tests，无需日志副作用。 |
| MiMo 005 | `NO_ACTION` | `isinstance(TextItem)`已经覆盖所有其子类；无需枚举第三方subclass或增加无业务价值case。 |
| MiMo 009 | `NO_ACTION` | shared helper docstring和实现已明确连续whitespace→单空格，matrix已要求newline/tab/space；不复制helper语义。 |
| DS F01关于任意invalid ref load成功 | `REJECTED_AS_ENVIRONMENT_DRIFT` | 项目`.venv`中`not-a-valid-cref`被Pydantic拒绝；全局Python证据不适用。schema-valid root遗漏已由CF01独立接受。 |
| DS F02 | `REJECTED_AS_ENVIRONMENT_DRIFT` | 项目`.venv`中`#/texts/NaN`在model validation阶段被拒绝，不会进入`int()`；不得扩大`ValueError`catch。 |
| DS F04 | `REJECTED_AS_FALSE_EVIDENCE` | `str.split()`在当前Python对NBSP/thin/narrow-NBSP均归一；无需扩`text_utils`、记录不存在的limitation或改production allowlist。 |
| DS F05 | `NO_ACTION` | Corrected plan已多处禁止context/header/`infer_caption_from_context` fallback。 |
| DS F06/F08 | `CONFIRMED / NO_ACTION` | reviewer自身已确认typed gate和同document路径正确。 |
| MiMo 007-013/015 | `CONFIRMED / NO_ACTION` | allowlist、locks、README、security/quota、residual和全门禁正确。 |

## 5. Final ledger / next gate

```text
ACCEPTED_PLAN_FINDING = 5
REJECTED_OR_NO_ACTION = 11 groups
BLOCKER_BEFORE_FIX = 1 (covered by S3-PR-CF01)
DESIGN_CONTRADICTION = 0
IMPLEMENTATION_AUTHORIZED = NO
```

AgentCodex只可修改corrected plan与其plan-correction artifact来关闭CF01—CF05，并新增固定plan-fix artifact。现有production/tests/README/utility、control/Controller artifacts与两路review artifacts必须保持。Fix后必须由AgentMiMo/AgentDS对完整plan双路complete re-review。

```text
PLAN_FIX_REQUIRED / READY_FOR_AGENTCODEX_PLAN_FIX
```
