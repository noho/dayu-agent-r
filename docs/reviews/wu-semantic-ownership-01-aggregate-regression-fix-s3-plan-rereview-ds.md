# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Plan Re-Review (AgentDS Second Independent)

## 0. Gate Identity

- 日期：`2026-07-19T16:10:49+08:00`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- Gate：Slice 3 corrected plan 第二路独立完整 plan re-review。不得只看 fix hunks，不得复用 AgentMiMo 结论。
- Re-review target：final plan SHA-256 `e870921ec608247a666d03ca7845c1d8a6453409392201a95eb16933ec53ef56`（`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`）。
- Review authority：Controller adjudication `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-controller-adjudication.md`（SHA-256 `c83e76d7c2d95a1df3d4f969d39c4ca907183947a977b2150672e9e6f19ee450`）；accepted ledger: `S3-PR-CF01`–`S3-PR-CF05` = `FIXED_IN_PLAN`，11 groups = `REJECTED_OR_NO_ACTION`。
- AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-fix-codex.md`（SHA-256 `1bce1c0b3db1719dbe59b02c46162d4af5339a46948422469a01511fce790eb0`）。
- Controller fix validation：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-fix-controller-validation.md`（SHA-256 `9e8c8abe57404b124814697d7e1ac947af08e4f5148209dc534be27d1c43e4d1`）；verdict `PASS / CF01_CF05_FIXED_IN_PLAN / READY_FOR_DUAL_COMPLETE_PLAN_REREVIEW`。
- Initial DS review（本次 re-review 的前置 review）：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-ds.md`（SHA-256 `c606f94e9353862ec30600360dfce2b21662cfbb13137d5c0b4422d0ed02fa3b`），verdict `PASS-WITH-RISKS`。
- Initial MiMo review：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-review-mimo.md`（SHA-256 `f3d59d0ac7e6f5528fd90f3ab6104f504b08242093d2f658bd505371a620c1fa`）。
- Updated plan correction artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-plan-correction-codex.md`（SHA-256 `f7500f03c9b8b703690c78e81cc75af3c15077b3e8e699757fec226345065c09`）。

## 0a. Review Method

本 re-review 采用以下方法：

1. 读取 final plan 全文、Controller adjudication、AgentCodex fix artifact、Controller fix validation、updated plan correction artifact、initial DS review 与 MiMo review。
2. 与 initial DS review 对照，识别 CF01–CF05 的修改轨迹。
3. 用项目 `.venv`（`source .venv/bin/activate`，`docling-core==2.74.0`，Python 3.11）独立验证所有 critical claim，**纠正 initial review 中 DS F01/F02/F04 的全局环境证据漂移**。
4. 逐项确认 rejected/no-action 中没有被偷带的 design change。
5. 重新挑战：schema-valid root ref、model-invalid loader、unknown/out-of-range、异常不吞、`cref`/`$ref` 边界、`ProvenanceItem` public path、multi-caption 规则、collect-only 门禁、完整 allowlist/README/219/security/quota/deferred/no-code。

## 1. Initial Review Drift Correction

Initial DS review 包含三项以**全局环境**（非项目 `.venv`）为证据的 finding，Controller 以直接 `.venv` 实验驳回：

| Initial Finding | 原始 claim | 项目 `.venv` 实际行为 | 纠正 |
|---|---|---|---|
| DS F01 | `not-a-valid-cref` 在 `load_from_json()` 不失败 | `RefItem.model_validate({"$ref": "not-a-valid-cref"})` → `ValidationError: string_pattern_mismatch`（regex `^#(?:/([\w-]+)(?:/(\d+))?)?$`）。模型校验拒绝。 | 全局环境中 Docling 版本差异导致 `RefItem` 缺少 Pydantic `pattern` validator；项目锁定 `.venv` 中该 ref 确实在 load boundary 失败。**DS F01 证据无效，Controller 驳回正确。** |
| DS F02 | `#/texts/NaN` 的 `int("NaN")` → `ValueError` | 同上 regex——`NaN` 不匹配 `\d+` → `ValidationError`，不会到达 `int()`。 | **DS F02 证据无效，Controller 驳回正确。** |
| DS F04 | `str.split()` 不处理 NBSP → 去重 gap | `.venv` Python 3.11 `str.split()` 默认将 NBSP（`\xa0`）、thin space（` `）、narrow NBSP（` `）全部作为 whitespace 分割。 | **DS F04 证据错误，Controller 驳回正确。** |

**本次 re-review 所有新 Python/Docling 实验均已在项目 `.venv` 中完成，不存在环境漂移。**

## 2. CF01–CF05 Closure Verification

### 2.1 CF01 — schema-valid document-root ref `#`

- **Plan 位置**: Final plan §4.3 item 2（模块级常量 `_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"`）与 item 5（fail-safe 边界）；Call path line 436–437（`caption_ref.cref == _DOCLING_DOCUMENT_ROOT_REF: skip`）；Test oracle item 4（`RefItem(cref="#")` 构造 root-ref public case）。
- **`.venv` 验证**: `RefItem.model_validate({"$ref": "#"})` 通过 Pydantic 校验（regex `^#(?:/([\w-]+)(?:/(\d+))?)?$` 接受单独的 `#`）。`RefItem.resolve(empty_doc)` 抛 `RuntimeError("Unsupported number of path components: 1")`。**Plan 方案正确**：在 typed `cref` 比较后跳过 resolve，不捕获 `RuntimeError`。
- **CF01 状态**: `CLOSED`。实现语义完整：常量名、typed 比较、不调用 resolve、不扩大 catch、无 warning/log。

### 2.2 CF02 — `cref` / `$ref` Python/JSON 边界

- **Plan 位置**: Final plan §4.3 item 2（"`cref`是Python typed field，serialized JSON中的alias才是`$ref`；production只能使用typed `cref`"）；Test oracle item 4（"Python构造和production判断统一使用字段`cref`，`$ref`只出现在上述serialized loader-boundary edit"）。
- **CF02 状态**: `CLOSED`。两个边界明确区分，implementation agent 不会混淆。

### 2.3 CF03 — page `ProvenanceItem` 与 `BoundingBox` 真实构造

- **Plan 位置**: Final plan §4.3 test oracle item 1（"page fixture必须用current public `ProvenanceItem(page_no=1, bbox=BoundingBox(l=0.0, t=0.0, r=1.0, b=1.0), charspan=(0, 1))`构造table provenance"）。
- **`.venv` 验证**: `ProvenanceItem` 的 `bbox` 字段类型为 `docling_core.types.doc.base.BoundingBox`（可从 `docling_core.types.doc.document` 导入）。`BoundingBox(l=0.0, t=0.0, r=1.0, b=1.0)` 构造成功，JSON round-trip 正常。`coord_origin` 默认 `TOPLEFT`。
- **CF03 状态**: `CLOSED`。使用正确的 public types，无 `ItemProv` 拼写错误。

### 2.4 CF04 — multi-caption rationale（单空格 + 大小写敏感）

- **Plan 位置**: Final plan §4.3 item 4（"选择单空格是因为`captions`只有有序ref列表、不携带ref间原始分隔符或标点元数据"；"大小写敏感是必要保真边界：大小写不同的原文可能承载不同业务含义"）。
- **CF04 状态**: `CLOSED`。Plan 不再只说"做连接"，而是明确解释了为什么选择单空格（数据模型限制）和大小写敏感（业务保真）。无新增标点猜测、casefold、Unicode normalization framework。

### 2.5 CF05 — coverage 前 collect-only fail-closed

- **Plan 位置**: Final plan §6.2（新增 preflight 段落 + collect-only 命令）。
- **`.venv` 验证**: `pytest --collect-only -q tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task` → exit 0，`1 test collected`，node ID 完整输出。
- **CF05 状态**: `CLOSED`。Fail-closed criteria（exit 0、唯一完整 node ID、summary 精确 `1 test collected`）明确。

## 3. Rejected / No-Action Re-Verification

逐项确认 Controller 的 11 组 rejected/no-action 提案在 final plan 中未被偷带：

| Candidate | Controller 裁决 | Final plan 检查结果 |
|---|---|---|
| MiMo 001 import 统一 | `REJECTED_WITH_REASON` | ✅ `TextItem` runtime import 理由在 §4.3 item 3 保留，其它 Docling names 维持 postponed/loader local |
| MiMo 003 warning 方案 | `REJECTED_WITH_REASON` | ✅ §4.3 item 5 明确 "不得产生 warning/log 副作用" |
| MiMo 005 枚举文本子类 | `NO_ACTION` | ✅ `isinstance(TextItem)` 保持不变 |
| MiMo 009 helper docstring 扩张 | `NO_ACTION` | ✅ 不复制 normalizer 语义 |
| DS F01 任意 invalid ref 可 load | `REJECTED_AS_ENVIRONMENT_DRIFT` | ✅ §4.3 item 6 固定 `not-a-valid-cref` 为 `.venv` 验证失败值 |
| DS F02 NaN ValueError | `REJECTED_AS_ENVIRONMENT_DRIFT` | ✅ 不捕获 `ValueError` |
| DS F04 NBSP text_utils | `REJECTED_AS_FALSE_EVIDENCE` | ✅ 无 NBSP special case / Unicode framework / `text_utils` 变更 |
| DS F05 context fallback | `NO_ACTION` | ✅ §4.3 item 3/5 多处禁止 context/header fallback |
| DS F06 typed gate | `CONFIRMED / NO_ACTION` | ✅ `isinstance(TextItem)` 不变 |
| DS F08 same-document path | `CONFIRMED / NO_ACTION` | ✅ `_build_tables()` 传同一 document |
| MiMo 007–013/015 all-locks | `CONFIRMED / NO_ACTION` | ✅ allowlist/locks/README/security/quota/residual unchanged |

**Verification**: 无偷带。被拒方案未以 "测试便利"、"防御性" 或其他名义重新进入 plan。

## 4. Complete Adversarial Re-Challenge

### 4.1 schema-valid root ref `#`

- **Claim**: `RefItem(cref="#")` 是 schema-valid 但 resolve 会抛 `RuntimeError`；plan 在 resolve 前用 typed `cref` 比较跳过。
- **`.venv` 反例试**: `RefItem.model_validate({"$ref": "#"})` → 成功（`cref='#'`）；`resolve()` → `RuntimeError`。无可绕过路径。
- **Test oracle**: Test oracle item 4 新增 `test_docling_json_processor_skips_document_root_caption_reference`——传入 root ref 与有效 ref 并存，root 被跳过，有效值保留。
- **结论**: ✅ 正确，无遗漏。

### 4.2 model-invalid loader

- **Claim**: `not-a-valid-cref` 在项目 `.venv` 的 `DoclingDocument.load_from_json()`（经过 `RefItem` Pydantic `pattern` validator）失败。
- **`.venv` 反例试**: `RefItem.model_validate({"$ref": "not-a-valid-cref"})` → `ValidationError: string_pattern_mismatch`。**确认在 load boundary 失败。**
- **补验**: 结构非法（`captions` entry 为非 object）→ `ValidationError: model_type`。两种边界均在 load 失败，不会进入 resolver。
- **结论**: ✅ 正确。Controller 纠正了我 initial review 中因为全局环境 `docling-core` 版本差异导致的误判。

### 4.3 unknown collection / out-of-range

- **Claim**: `#/missing/0` → `AttributeError`；`#/texts/999` → `IndexError`。Plan 在单次 `resolve()` 周围精确捕获这两个类型。
- **`.venv` 反例试**: 两者均可通过 model validation（regex 接受合法 `[\w-]+` 和 `\d+`）。`unknown/0` 抛 `AttributeError`（`doc.__getattribute__('unknown')` 对不存在 collection 失败）。`texts/999` 抛 `IndexError`（out-of-range index）。
- **补验**: 不存在 collection 名与 Python dunder 属性名冲突的边界——`RefItem.resolve()` 对 3-component cref 取 `path_components[1]` 为 path name，但 `doc.__getattribute__('texts')` 返回的是 Pydantic model field 的 concrete list value（不是 descriptor）。不存在因 dunder 名（如 `__class__`）导致意外行为的风险——`cref='#/__class__/0'` 中的 `__class__` 被 `doc.__getattribute__` 解析为 Pydantic model attribute，会与 `model_fields` 逻辑交互但实际不可达（Docling 不会产生 `__class__` collection name）。
- **结论**: ✅ `AttributeError` / `IndexError` 分类精确且为已知 Docling data integrity boundary。

### 4.4 异常不吞（non-dangling 异常传播）

- **Claim**: `RuntimeError`, `TypeError`, `ValueError` 及未分类异常必须继续暴露，禁止 `except Exception`。
- **验证**: §4.3 item 2（root ref 跳过，不调用 resolve → 不触发 RuntimeError）、item 5（只捕获 `AttributeError`/`IndexError`）、item 6（明确禁止捕获 `RuntimeError` 或 `except Exception`）。所有 resolve 可达的合法异常路径已被 CF01 + item 5 精确覆盖；可能的非法异常（如 Docling 内部 regression 引入的新异常类型）将正确传播。
- **结论**: ✅ 异常不吞边界完整且最小化。

### 4.5 `cref` / `$ref` Python typed-field vs JSON alias

- **Claim**: Production 只使用 `RefItem.cref`（Python typed field）；`$ref` 只在 serialized loader-boundary test 中使用。
- **验证**: `RefItem.model_fields` → `{'cref': FieldInfo(...)}`。`model_validate({"$ref": X})` → Pydantic alias 映射到 `cref`。`model_dump(mode='json')` → `{"cref": X}`。`doc.save_as_json()` → `{"$ref": X}`（Docling 使用自定义 serialization）。
- **结论**: ✅ 边界清晰。Test oracle item 4 明确 "Python 构造和 production 判断统一使用字段 `cref`"。

### 4.6 `ProvenanceItem` public path

- **Claim**: Page fixture 用 `ProvenanceItem(page_no=1, bbox=BoundingBox(l=0.0, t=0.0, r=1.0, b=1.0), charspan=(0, 1))` 构造 table provenance，经真实 Docling serialize/load。
- **`.venv` 验证**: `BoundingBox` 可从 `docling_core.types.doc.document` 导入（也可从 `docling_core.types.doc.base` 或 `docling_core.types.doc`）。构造成功，round-trip JSON 正常。`ProvenanceItem` 是 Docling `TableItem.prov` 的子项类型（每个 table cell 有一个 `ProvenanceItem`）。
- **补验**: Fixture 需要将 `ProvenanceItem` 附加到 `TableItem` 的每个 `TableCell.provenance`。Plan 的 fixture 描述 "构造 table provenance, 经真实 serialize/load 后断言 `get_page_content(1)['tables'][0]['caption']` 相同" ——需要确认 `get_page_content()` 的正确构造方式：
  - `DoclingDocument.pages` 包含 `PageItem` 列表。
  - `PageItem.page_no` 对应页码。
  - `DoclingProcessor.get_page_content(page_no)` 返回该页的 sections/text/tables。
  - Table 的 `provenance` 通过 `TableCell.provenance` 表达，而 `TableItem.prov` 是旧字段。
  - 要构造一个有真实 page provenance 的 table：需要 `PageItem` 包含 `TableItem` 的 ref，且 table cells 附带 `ProvenanceItem(page_no=1, ...)`。

  **风险提示（非 blocker）**: Plan 的 ProvenanceItem fixture 构造说明足够让 implementation agent 工作，但需要 agent 理解 Docling 的 page/table/provenance model。如果构造失败，应立即 STOP 交 Controller，不得伪造 `get_page_content()` 的 page cache。Plan §4.3 test oracle item 1 已写"禁止写 private state 或伪造 page cache"——覆盖了该风险。

- **结论**: ✅ 类型正确，fixture 可构造。implementation agent 需要一定 Docling model 熟悉度，但 plan 的 "STOP" 规则提供 safety net。

### 4.7 multi-caption（顺序/规范化/去重/连接/大小写）

- **Claim**: 严格作者顺序、`_normalize_whitespace` 规范化、大小写敏感精确去重、首次保留、单 ASCII 空格连接。
- **`.venv` 验证**:
  - `" ".join("  Hello\nWorld\t".split())` → `"Hello World"`。Correct.
  - `" ".join("Consolidated\xa0Statements".split())` → `"Consolidated Statements"`。NBSP 已由 `str.split()` 归一。Correct.
  - `"Hello".split()` → `["Hello"]` → `"Hello"`。单字正确。
  - 空字符串: `" ".join("".split())` → `""`，`_normalize_whitespace("")` → `""`，但 Plan §4.3 item 4 写"规范化为空的文本忽略"——需要 implementation agent 以 `not normalized_text`（空字符串为 falsy）判定。
- **补验**: 去重逻辑：`seen = set(); if norm_text not in seen: seen.add(norm_text); result.append(norm_text)`。这是标准精确去重实现。大小写敏感：`"Revenue" != "revenue"` → 两者分别保留。正确。
- **结论**: ✅ 规则完整，已补 rationale。无 hidden edge case。

### 4.8 collect-only fail-closed

- **Claim**: Coverage 前 `pytest --collect-only -q <exact_node>`，exit 0 + 唯一完整 node ID + `1 test collected` summary，否则 STOP。
- **`.venv` 验证**: 当前 HEAD 下 `1 test collected`，exit 0，输出完整 node ID。符合要求。
- **补充风险**: Plan 的 stop condition 写"node 不存在、重命名、collect error、0 个或多于 1 个结果均立即 STOP"——覆盖了静默失效的所有场景。即使 pytest 的 `--deselect` 对不存在节点可以成功（仅 warning），preflight 也会先发制人地 stop。
- **结论**: ✅ fail-closed 且不改变 AR-F06 `RETAINED / UNFIXED / UNWAIVED` 状态。

### 4.9 完整 allowlist / README / 219 / security / quota / deferred / no-code

逐项检查 final plan 全文：

| Boundary | Plan reference | Status |
|---|---|---|
| Production allowlist | §3.1（Slice 3 only `M dayu/documents/processors/docling_processor.py`） | ✅ 不变 |
| Test allowlist | §3.2（六路径） | ✅ 不变 |
| Protected zero-diff paths | §3.5（AR-F06/AR-F03/AR-F01/AR-F04/AR-F02/八个 AR-F05 non-Docling/AR-F07/design docs） | ✅ 不变 |
| README verdict | §3.4 + §4.3（根/`dayu`/`tests` 三 README `NO_UPDATE`） | ✅ 不变 |
| 219 changed production | §4.3 Slice exit + §6.2（最终 `219/219 >=80%`） | ✅ 不变 |
| Security matrices | §6.7（Doc/Web/Host/Fins/CLI 矩阵） | ✅ 不变 |
| Configured-secret classification | §6.7（`ACCEPTED_TRUSTED_INTERNAL` + `ZERO_REQUIRED` per-surface） | ✅ 不变 |
| Gemini quota | §4.3（`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`） | ✅ 不变 |
| AR-F06 | §1, §6.2, §7, §9（`RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`） | ✅ 不变 |
| AR-F07 | §1, §8, §9（`PENDING_RELEASE_BLOCKER`） | ✅ 不变 |
| Issues 142/151/175/177/178 | §4.3, §6.7 | ✅ 不扩域 |
| Topic 8 (Engine 240 chars) | §6.7 | ✅ no-code |
| Topic 9 (tool authorization) | §6.7 | ✅ 不引入 |
| Secret infrastructure | §1 endorsement + §6.7 | ✅ 不引入 |

## 5. Architecture / Overengineering / Overcoupling Re-Check

### 5.1 分层边界

- ✅ `dayu/documents/processors/docling_processor.py` → documents 处理层。Caption 解析是 Docling 表格投影的自然职责。
- ✅ `TextItem` 从 `docling_core.types.doc.document` 运行时导入（`isinstance` 需要），`docling-core>=2.74.0` 是必需依赖。
- ✅ `_DOCLING_DOCUMENT_ROOT_REF: Final[str] = "#"` 模块级常量——最小化，无新模块/新类/新抽象。

### 5.2 过度设计检查

- ✅ 无新 schema、新类型、新 resolver service、新状态机、兼容层。
- ✅ root ref 处理是最简单的 typed constant comparison（`==`），不是 parser/regex/exception-catch 方案。
- ✅ Multi-caption 语义复用现有的 `_normalize_whitespace`，不引入新框架。

### 5.3 过度耦合检查

- ✅ `_TableBlock.caption` → 三个 consumer（`list_tables` / `read_table` / `get_page_content`）——单向依赖，单一真源。
- ✅ Caption resolver 不依赖任何 consumer 实现细节。
- ✅ 无跨层穿透。

## 6. Initial MiMo Review Cross-Check

本次 re-review 不复用 AgentMiMo 结论。独立对照 MiMo 的 15 项 findings：

| MiMo # | Controller 裁决 | DS 独立确认 |
|---|---|---|
| 001 import 统一 | REJECTED | ✅ 确认未偷带——`TextItem` 有 runtime `isinstance` 理由，其它 names 保持 postponed |
| 002 多 caption rationale | CF04 接受（plan clarity） | ✅ CF04 已修复 |
| 003 warning 方案 | REJECTED | ✅ 确认未偷带 |
| 004 model-invalid loader | （被 CF01 方案覆盖） | ✅ 项目 `.venv` 已证实 `not-a-valid-cref` 在 loader 失败 |
| 005 枚举文本子类 | NO_ACTION | ✅ `isinstance(TextItem)` 足够 |
| 006 page provenance | CF03 接受（可执行性） | ✅ 确认 `ProvenanceItem` / `BoundingBox` 正确 |
| 007–013/015 全门禁 | CONFIRMED / NO_ACTION | ✅ 不变 |
| 014 rationale | CF04 接受（plan clarity） | ✅ 已加入 |

无 MiMo finding 被错误恢复或未处理。

## 7. Test Oracle Coverage Check

Final plan 的 8 个 test nodes 覆盖矩阵：

| Node | 覆盖的 plan 要求 |
|---|---|
| `test_docling_json_processor_projects_referenced_table_caption` | CF01: root ref skip / CF02: `cref`/`$ref` 边界 / CF03: page provenance / 三 public views (item 6) |
| `test_docling_json_processor_preserves_normalized_unique_caption_order` | CF04: 多 caption 顺序/规范化/去重/连接/大小写 |
| `test_docling_json_processor_returns_none_for_empty_or_blank_captions` | 空列表 / 全空白 → `None` |
| `test_docling_json_processor_skips_dangling_caption_references` | unknown collection `AttributeError` / 越界 `IndexError` / 坏 ref + 有效 ref 混合 |
| `test_docling_json_processor_skips_document_root_caption_reference` | CF01: `cref="#"` → skip / root + 有效 mixed / all-root → `None` |
| `test_docling_json_processor_rejects_model_invalid_caption_reference` | CF02: serialized `$ref` edit / Pydantic load failure / 不进入 resolver |
| `test_docling_json_processor_skips_non_text_caption_references` | `TableItem`/`PictureItem` → skip / 混合 / all-non-text → `None` |
| `test_docling_json_processor_propagates_caption_to_public_table_views` | `list_tables` / `read_table` / `get_page_content` 三 consumer 一致性 |

**Coverage gap check**: 所有 plan requirements 已被至少一个 test node 覆盖。未发现 uncovered contract。

## 8. Residual Risks

| Risk | Severity | Tracking |
|---|---|---|
| ProvenanceItem page fixture 构造复杂度 | 低 | implementation agent 需要 Docling model 熟悉度；plan 有 STOP 规则 |
| `S3-STOP-F01` 未修复（仍是 blocking defect） | 严重 | plan fix != production fix；implementation 必须先修 caption defect |
| AR-F05 其余八 owner coverage 未开始 | 中 | 属于 Slice 3 后续 steps，不在当前 plan gate scope |
| AR-F06/AR-F07 未关闭 | 高 | 已在 plan 中正确追溯 |
| Docling 版本升级可能导致 root-ref 行为变化 | 低 | `docling-core` 版本已锁定 `<3.0.0`；regex pattern 来自 Pydantic `RefItem` 定义 |

## 9. Final Plan Review Re-Verdict

```text
PASS
```

### 理由

1. **CF01–CF05 全部关闭**：五个 accepted plan findings 在 final plan 中完整准确修复，无遗漏。
2. **Rejected/no-action 零偷带**：11 组被拒/无动作提案未被以任何形式重新引入。
3. **所有 `.venv` 实验确认 plan claims**：root ref 行为、model-invalid loader 失败、NBSP 归一化、ProvenanceItem/BoundingBox 构造、collect-only 门禁——全部验证通过。
4. **Initial review drift 已纠正**：DS F01/F02/F04 的错误证据（全局环境 vs 项目 `.venv`）已被 Controller 和本次 fresh `.venv` 实验完全纠正。
5. **无新 blocking finding**：重新挑战的所有维度（schema-valid root、model-invalid loader、unknown/out-of-range、异常不吞、`cref`/`$ref`、ProvenanceItem、multi-caption、collect-only、完整 allowlist/README/219/security/quota/deferred/no-code）均通过了项目 `.venv` 直接证据验证。
6. **Plan 是 code-generation-ready**：Implementation agent 可以按 plan 逐条实施 production fix + 8 owner-contract test nodes，不需要重新设计异常分类、ref 边界处理或 caption 语义。

唯一的 material deferred risk：`S3-STOP-F01` 仍是 blocking production defect（plan fix ≠ production fix），必须在 implementation gate 首先关闭。

## 10. Controller Adjudication Entry

- **Re-review artifact SHA-256**: 本文件写入后由 Controller 从文件系统读取新鲜 hash。
- **Final plan SHA-256**: `e870921ec608247a666d03ca7845c1d8a6453409392201a95eb16933ec53ef56`
- **Verdict**: `PASS` — 无 blocking finding，零 accepted plan-fix 遗留。
- **下一 gate**: Controller 接受本 re-review（与 AgentMiMo re-review 完全一致后）→ `READY_FOR_IMPLEMENTATION_AUTHORIZATION` → Controller 明确发布新的 Slice 3 implementation authorization → AgentCodex 先在 production 关闭 `S3-STOP-F01`，再继续九 owner coverage。
