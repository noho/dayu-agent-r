# UF-FIX11 原子 S1+S2 Implementation 最终定向 Re-review（DS）

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- Gate：S1+S2 implementation re-review（第二路 reviewer 定向复核）
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- 复核对象：`docs/gateflow/uf-fix11-s1-s2-implementation-review-fix-20260817.md` 声明的 fix（4 个测试文件）与其后工作树最新 diff；对照上一轮 DS review（Finding-001/002/003）与 MiMo review（Finding-001/002 及 controller 裁决）
- 结论：**pass**
- 复核方式：逐项红测推演（生产分支删除/漂移时测试是否变红）+ 独立复跑新增 13 个 test node + 对照 fix artifact 与已记录的 715/2138/pyright 绿色证据
- 本 re-review 未修改任何文件，未 stage/commit

## 逐项复核

### DS Finding-001（material 非空/空数组）— 已修复，pass

- 修复内容：`test_pipeline_warning_parser_requires_filing_field_but_allows_material_missing` 增加 `SourceKind.MATERIAL` + 显式 `warnings=[]` → 解析为 `()`；`SourceKind.MATERIAL` + 唯一规范 warning → `ValueError(match="material terminal result")`。
- 红测推演：若删除 `ingestion_runtime.py:1773-1774` 的 material 非空拒绝分支，该 case 的规范 warning 通过 closed codec 后顺利构造结果，`pytest.raises(ValueError)` 落空 → 测试变红；且 `match="material terminal result"` 钉住 owner 专属消息，防止被其他 ValueError 误命中（假绿）。空数组合法分支反向成立：若生产改为拒绝显式空数组，正向断言变红。
- 无 cast/fake/顺序依赖；直接调用 parser owner，不经过 service/summary 反推。
- 独立复跑：`13 passed` 中包含该测试全部 4 个 case。

### DS Finding-002（cancelled/outcome 同源与 codec 负例）— 已修复，pass

- 修复内容：
  1. `test_publication_outcome_rejects_cancelled_warning`：真实构造 `FilingUploadPublicationOutcome`（status="cancelled" + 非空 warnings）→ `ValueError(match="cancelled publication outcome")`。
  2. `test_publication_outcome_rejects_warning_commit_outcome_mismatch`：内部 outcome 携带 ignored fact 但 `warnings=()` → `ValueError(match="必须与内部 commit outcome 同源")`。
  3. `test_company_metadata_warning_rejects_noncanonical_constructor_values`：runtime kind 为 str（`cast` 仅满足静态类型）→ TypeError；规范 kind + 非规范文案 → ValueError。
  4. `test_company_metadata_warning_json_projection_rejects_invalid_collections`：两个元素 → ValueError；元素为 str → TypeError。
  5. `test_company_name_ignored_warning_projection_rejects_nonexact_domain_fact`：输入 dict → TypeError。
- 红测推演（逐条）：
  - 若删除 cancelled 拒绝行（`filing_upload_publication.py:181-182`）：该 case 会落到同源交叉检查并抛 "publication warnings 必须与内部 commit outcome 同源"，与 `match="cancelled publication outcome"` 不匹配 → 测试仍变红（不会假绿）。
  - 若删除同源交叉检查：mismatch case 构造成功 → 变红。
  - 若删除 constructor 的 type-exact 检查：str kind 被接受 → 变红；删除文案检查：非规范文案被接受 → 变红。
  - 若删除 serializer 的长度检查：双元素序列化成功 → 变红；删除元素类型检查：str 元素走到 `to_json` 触发 AttributeError，与 `pytest.raises(TypeError)` 不符 → 仍变红。
  - 若删除 projection 类型检查：dict 被投影成功 → 变红。
- `cast` 使用合理：只满足静态类型，运行时传入非精确值，测试名与 docstring 显式声明 "runtime kind/非精确 fact"，无 fake 误导；所有断言命中 owner constructor/serializer/projection，不复制 SEC/CN/pipeline/UI 推断。
- 独立复跑：13 个 node 全绿，其中 5 个 codec/publication 负例按参数展开全部命中。

### DS Finding-003（按方法归属的 SourceKind AST contract）— 已修复，pass

- 修复内容：重写 `test_production_runner_parser_callsites_use_explicit_source_kind`：先定位唯一 `ProductionFinsUploadRunner`（断言恰 1 个类定义），再按所属方法收集 `from_pipeline_json` callsites；断言带 callsite 的方法集合恰为 `{_run_filing_upload, _run_material_upload}`，filing 方法恰 2 处且全部 FILING、material 方法恰 2 处且全部 MATERIAL，全类总数恰 4。
- 与生产结构核对：`service_runtime.py` 实际方法名与 callsite 行号（`_run_filing_upload`: 181/189，`_run_material_upload`: 229/250）与断言一致。
- 红测推演：
  - 原顺序依赖已消除：`dict[method_name] -> list` + 集合断言，物理重排 callsite 顺序不再产生假阳性。
  - 单点 kind 漂移（任一 filing callsite 改传 MATERIAL）→ 该方法的 `set(...) == {"FILING"}` 失败 → 变红；callsite 漂移到其他方法/新方法 → 方法集合断言失败 → 变红；移除 `source_kind` 关键字 → `keyword is None` 断言失败 → 变红。
  - 剩余收紧（有意为之）：要求表达式为 `SourceKind` 直接属性引用（拒绝别名 import），这是把 plan 的 "显式 SourceKind" 契约钉得更紧，非假阳性来源。
- 无 cast/fake/顺序偶然性。

### 空白名称 no-intent 测试（MiMo Finding-002 测试建议，ACCEPT）— 已落实，pass

- `test_fresh_upload_equivalent_or_missing_name_keeps_metadata` 参数矩阵现为 `(None, "   ", " 　  ", "  ＤＥＬＴＡ ＩＮＣ.  ")`，全部断言 `keep` 且 `company_meta_intent is None`。
- 行为核对：`_optional_upload_company_name` 对 ASCII 空格、U+3000、U+00A0（均为 `str.strip()` 默认覆盖的 Unicode 空白）折叠为 `None` → fresh keep；无 intent 即无 warning 事实，与 plan §6.1 "None 表示本次调用没有提交名称" 一致。
- 红测推演：若 pipeline 边界不再把空白折叠为 missing（如去掉 strip），空白 case 的 `name_change_requested` 变 True → stage → 断言变红。测试钉住 pipeline owner 语义，与 controller 对 MiMo Finding-002 production change 的 rejected-with-reason 裁决一致（测试只钉行为，不改 production）。

### MiMo Finding-001 / Finding-002 production change（REJECT-WITH-REASON）— 未修改，符合裁决

- 核对：`upload_company_meta.py:230` 仍为 `UploadCompanyNameRequiredError("create/update 时必须提供 --company-name")`，`company_meta_contract.py:324` 仍为 `ValueError("requested_company_name 必须为非空字符串")`——两层错误文案未统一、domain 防御未削弱、无新增错误常量或共享抽象。
- 两条 rejected 裁决均未被 fix 变相引入；fix artifact 如实记录为 rejected 而非 deferred。

## 验证记录

- 独立复跑新增 13 个 test node：`13 passed, 3 warnings in 0.86s`（与 fix artifact 声明的 1.13s/13 passed 一致）。
- 复用已记录绿色证据：§12.1 focused `715 passed`、§12.2 combined regression `2138 passed, 1 skipped`、全仓 pyright `0 errors`。未重跑昂贵套件，符合指示。
- 工作树核对：fix 后 dirty 文件集合与 S1+S2 allowed files 一致，无新增生产修改；四测试文件的新增 hunk 与 fix artifact 逐项对应；既有 S1+S2 测试（metadata-only skip capability、blocker bytes/tree、并发 barrier、SEC/CN roundtrip）未被重置或弱化。

## Residual Risk（非新 findings）

1. `company_metadata_warning.py` 剩余未覆盖分支：58（message 非 str TypeError）、97（from_json 非 Mapping）、103（字段非 str）为纯输入类型防御；135/160（kind 重复检查）在当前"最多一个元素"守卫下不可达（plan §6.3 要求保留该验证以防未来多 kind 扩展）。均为防御/不可达分支，controller 已按指示不重复 coverage，本轮不构成 finding。
2. 沿用上一轮 DS/MiMo 已分类项：name-only skip 的 writer lock/physical swap 成本、material 同类 warning 独立 work unit、commit durable 后 guard-release/cleanup 异常的运维可见性（均 `assigned to later work unit`）。
3. S3（summary/durable/direct/CLI/tool projection + README）边界未被本次 fix 触碰，仍属 `covered by later approved slice`。

## 结论

**pass**。DS Finding-001/002/003 与 MiMo Finding-002 测试建议均已按 owner contract 修复并经红测推演与独立复跑确认；controller rejected-with-reason 的两项 production change 未被变相引入；无新 findings、无 blocking open question、无未分类 residual risk。S1+S2 可进入 accepted slice commit 前置。
