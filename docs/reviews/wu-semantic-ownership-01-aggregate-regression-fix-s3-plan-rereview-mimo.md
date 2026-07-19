# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Final Plan — Complete Re-Review（AgentMiMo）

## 1. Review identity

- 日期：`2026-07-19`。
- Review target：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，SHA-256 `e870921ec608247a666d03ca7845c1d8a6453409392201a95eb16933ec53ef56`。
- Review scope：完整 final plan（§0–§10），不只 fix hunks。包括 CF01–CF05 修正、updated correction artifact、plan-review-fix codex artifact、Controller fix validation、Controller plan-review adjudication、DS review、initial MiMo review。
- 独立 re-review：不复用前一路结论，不启动 subagent。
- Review posture：constructively adversarial，默认假设 plan 至少有一个重要问题直到证据证明其可靠。

## 2. Assumptions tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | S3-STOP-F01 root cause 唯一且 owner 边界正确 | ✅ confirmed |
| A2 | CF01 root ref typed sentinel 正确处理 schema-valid `#` | ✅ confirmed — `RefItem(cref='#')` 通过 Pydantic pattern validator，`resolve()` 抛 `RuntimeError`；plan 用 `_DOCLING_DOCUMENT_ROOT_REF = "#"` 在 resolve 前跳过 |
| A3 | CF02 `cref`/`$ref` Python/serialized alias 边界明确 | ✅ confirmed — `RefItem.model_fields` 只有 `cref`；`$ref` 是 Pydantic JSON alias |
| A4 | CF03 `ProvenanceItem` + `BoundingBox` 可公开 serialize/load | ✅ confirmed — `ProvenanceItem(page_no=1, bbox=BoundingBox(l=0.0, t=0.0, r=1.0, b=1.0), charspan=(0, 1))` 构造成功 |
| A5 | CF04 单空格连接与大小写敏感去重有数据模型理由 | ✅ confirmed — `list[RefItem]` 不携带 ref 间分隔元数据 |
| A6 | CF05 AR-F06 exact collect-only fail-closed | ✅ confirmed — plan §6.2 要求 `pytest --collect-only` 必须 exit 0 且唯一输出完整 node |
| A7 | model-invalid ref 在项目 `.venv` load boundary 失败 | ✅ confirmed — `not-a-valid-cref` 被 Pydantic pattern `^#(?:/([\w-]+)(?:/(\d+))?)?$` 拒绝 |
| A8 | dangling ref `AttributeError`/`IndexError` 精确 | ✅ confirmed — `#/missing/0` → `AttributeError`，`#/texts/999` → `IndexError` |
| A9 | `TextItem` runtime isinstance 覆盖所有文本子类 | ✅ confirmed — `SectionHeaderItem`, `TitleItem`, `ListItem`, `CodeItem`, `FormulaItem` 均为 `TextItem` 子类 |
| A10 | Rejected/no-action proposals 未进入 plan | ✅ confirmed |

## 3. CF01–CF05 逐项关闭确认

### CF01 — root ref 边界

**状态：CLOSED**

- Plan §4.3 item 2 固定 `_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"` 为命名模块常量。
- Resolver 遍历 `table_item.captions` 时先比较 `caption_ref.cref == _DOCLING_DOCUMENT_ROOT_REF`，命中则跳过且不调用 `resolve()`。
- 不捕获全部 `RuntimeError`、不匹配异常文本、不解析 raw JSON pointer。
- Model-invalid ref 固定 `.venv` 真实失败值 `not-a-valid-cref`，由 Pydantic pattern validator 在 load boundary 拒绝。
- 新增 root-ref public test node `test_docling_json_processor_skips_document_root_caption_reference`。

**直接证据**：
- `RefItem(cref='#')` → Pydantic accepted → `resolve()` → `RuntimeError("Unsupported number of path components: 1")`
- `RefItem(cref='not-a-valid-cref')` → Pydantic `string_pattern_mismatch` at load boundary
- Plan 精确区分两者：root ref 由 typed sentinel 处理，model-invalid 由 load boundary 处理。

**无遗留问题**。

### CF02 — cref/$ref 术语

**状态：CLOSED**

- Plan §4.3 item 2 明确："`cref`是Python typed field，serialized JSON中的alias才是`$ref`；production只能使用typed `cref`，不得读取serialized dict / `$ref`"
- Test oracle item 4 明确："Python构造和production判断统一使用字段`cref`，`$ref`只出现在上述serialized loader-boundary edit"

**直接证据**：`RefItem.model_fields` 只有 `cref`。

**无遗留问题**。

### CF03 — page provenance fixture

**状态：CLOSED**

- Plan §7 test oracle item 1 固定："page fixture必须用current public `ProvenanceItem(page_no=1, bbox=BoundingBox(l=0.0, t=0.0, r=1.0, b=1.0), charspan=(0, 1))`构造table provenance，经真实serialize/load后断言`get_page_content(1)["tables"][0]["caption"]`相同"

**直接证据**：`ProvenanceItem` 和 `BoundingBox` 在项目 `.venv` 构造成功，字段与 plan 描述一致。

**无遗留问题**。

### CF04 — multi-caption rationale

**状态：CLOSED**

- Plan §4.3 item 4 补充了两个直接理由：
  1. "选择单空格是因为`captions`只有有序ref列表、不携带ref间原始分隔符或标点元数据"
  2. "大小写敏感是必要保真边界：大小写不同的原文可能承载不同业务含义，owner不得用casefold或其它近似规则擅自折叠"
- 不新增标点猜测、casefold、Unicode normalization framework 或第二语义。

**无遗留问题**。

### CF05 — AR-F06 exact collect-only fail-closed

**状态：CLOSED**

- Plan §6.2 新增 collect-only preflight：
  ```
  pytest --collect-only -q tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
  ```
  "只有该命令exit 0、输出唯一该完整node id且summary为`1 test collected`时才能继续coverage；node不存在、重命名、collect error、0个或多于1个结果均立即STOP"

**直接证据**：Controller 在当前 HEAD 确认该 node 存在且 collect-only 输出 `1 test collected`。

**无遗留问题**。

## 4. DS F01 环境漂移确认

DS review 的核心 finding（F01：model-invalid ref 不在 load boundary 失败）基于**全局 Python 环境**的实验证据。Controller 在项目 `.venv`（`docling-core==2.74.0`）中独立验证：

- `RefItem.cref` 有 Pydantic pattern validator：`^#(?:/([\w-]+)(?:/(\d+))?)?$`
- `not-a-valid-cref` → `string_pattern_mismatch` at load boundary
- `#/texts/0/extra`（4 组件）→ `string_pattern_mismatch` at load boundary

因此 DS F01 的核心前提（"load 成功但 resolve 时 RuntimeError"）在项目锁定环境中不成立。Controller 以 `REJECTED_AS_ENVIRONMENT_DRIFT` 裁决正确。

DS F01 中唯一有独立价值的部分——schema-valid root ref `#` 的处理——已被 CF01 独立接受并修正。

## 5. Rejected/no-action proposals 确认

逐项确认以下方案**未进入 final plan**：

| Proposal | Controller status | plan 中是否存在 |
|---|---|---|
| MiMo 001 TextItem import 统一 | `REJECTED_WITH_REASON` | ❌ 不存在 |
| MiMo 003 warning log | `REJECTED_WITH_REASON` | ❌ 不存在（§4.3 item 5 明确"不得产生warning/log副作用"） |
| MiMo 005 枚举 TextItem 子类 | `NO_ACTION` | ❌ 不存在 |
| MiMo 009 _normalize_whitespace docstring | `NO_ACTION` | ❌ 不存在 |
| DS F01 任意 invalid ref 可 load | `REJECTED_AS_ENVIRONMENT_DRIFT` | ❌ 不存在 |
| DS F02 NaN/ValueError catch | `REJECTED_AS_ENVIRONMENT_DRIFT` | ❌ 不存在 |
| DS F04 NBSP 特例/text_utils 抽取 | `REJECTED_AS_FALSE_EVIDENCE` | ❌ 不存在 |
| DS F05 context fallback | `NO_ACTION` | ❌ 不存在（§4.3 item 6 明确禁止） |

## 6. 完整 scope 重新挑战

### 6.1 异常边界

- `captions=[]` → `None` ✅
- root ref `#` → typed sentinel skip，不调用 resolve ✅
- `#/missing/0` → `AttributeError` from `resolve()` → caught, skip ✅
- `#/texts/999` → `IndexError` from `resolve()` → caught, skip ✅
- `not-a-valid-cref` → Pydantic `ValidationError` at load boundary → 不是 resolver 输入 ✅
- `#/texts/0/extra` → Pydantic `ValidationError` at load boundary ✅
- `resolve()` 到非 `TextItem` → skip ✅
- `TextItem.text` 规范化为空 → skip ✅
- 全部 skip → `None` ✅
- `TypeError`/`ValueError`/`RuntimeError`（非上述已知）→ 暴露 ✅

**异常分类完整，无 blind spot。**

### 6.2 Multi-caption 公共语义

- ref 顺序保留 ✅
- `_normalize_whitespace()` 规范化 ✅
- 空白结果忽略 ✅
- 大小写敏感精确去重，首次保留 ✅
- 单 ASCII 空格连接 ✅
- 全空 → `None` ✅

**业务规则完整且有直接数据模型理由。**

### 6.3 Public views / provenance

- `list_tables()` → `_TableBlock.caption` ✅
- `read_table()` → `_TableBlock.caption` ✅
- `get_page_content()` → `_TableBlock.caption` ✅
- Page fixture 使用真实 `ProvenanceItem` + `BoundingBox` ✅

**三个 public consumer 统一消费同一投影。**

### 6.4 Allowlist / locks

- Production allowlist：Slice 3 只有 `M dayu/documents/processors/docling_processor.py` ✅
- Test allowlist：六个路径 ✅
- Protected zero-diff paths：完整列出 ✅
- Entry hash protection：六个 test paths + nine control/Controller/reviewer artifacts ✅

**无扩域。**

### 6.5 README

- `NO_UPDATE` 裁决正确：caption 修复不改变用户可见行为 ✅
- 恢复 implementation 后仍需 fresh 读取约束 ✅

### 6.6 219 coverage

- `dayu/documents/processors/docling_processor.py` 已在 219 集合中 ✅
- 修改不改变集合成员 ✅
- 最终要求 219/219 >=80% ✅

### 6.7 Security / quota / deferred / no-code

- Config/Host internal = `ACCEPTED_TRUSTED_INTERNAL` ✅
- Tool Trace/audit/public/LLM/log = `ZERO_REQUIRED` ✅
- Gemini = `EXPECTED_TEST_ACCOUNT_QUOTA` ✅
- AR-F06 = `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX` ✅
- AR-F07 = `PENDING_RELEASE_BLOCKER` ✅
- Issues 142/151/175/177/178、Topic 8/9 不变 ✅

## 7. Findings

**无新 findings。**

CF01–CF05 全部关闭，异常边界完整，multi-caption 语义正确，public views 一致，allowlist/locks 精确，README/219/security/quota/deferred/no-code 无漂移，rejected proposals 未进入 plan。

## 8. Open questions

无。

## 9. Residual risks

1. **Docling 版本升级风险**：当前 `docling-core` 的 `RefItem` 有 Pydantic pattern validator；若未来版本移除或改变该 validator，model-invalid ref 可能在 load boundary 不再失败。但 caption resolver 的 fail-safe（`AttributeError`/`IndexError` catch）和 root sentinel 仍提供保护。
   - **跟踪目的地**：CI 依赖版本锁定。

2. **Coverage 路径数量**：Docling owner 从 63.46% 到 80%+ 需要大量 test cases。Plan 的 caption matrix（8 个 test nodes）加上其余 payload sniff/section/table/page/search cases 是否足够，需 implementation 时验证。
   - **跟踪目的地**：Slice 3 implementation gate。

## 10. Final plan review conclusion

**pass**

Final plan（SHA-256 `e870921ec608247a666d03ca7845c1d8a6453409392201a95eb16933ec53ef56`）在 CF01–CF05 修正后，所有已知问题已关闭。异常边界完整，public contract 明确，test oracle code-generation-ready，allowlist/locks 精确，门禁无漂移。没有发现 blocker 或新 findings。

建议 Controller 发布 Slice 3 implementation authorization。

## Artifact

```
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-rereview-mimo.md
```

SHA-256：`44f306ba747f3503261d80eee931e8cac6b081f9067ed7392a6dc479903c8267`。
