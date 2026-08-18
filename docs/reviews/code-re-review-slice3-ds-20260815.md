# Code Re-Review（UF-FIX06 Slice 3，AgentDS 第二路独立严格 re-review）

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：Slice 3 code review fix → code re-review
- Reviewer：AgentDS（与初轮同一 reviewer 身份，基于裁决与 fix artifact 独立复核）
- 日期：2026-08-15
- 基线 commit：`affa665b`（未变）
- 输入裁决：`docs/reviews/uf-fix06-slice3-code-review-adjudication-20260815.md`（FIX REQUIRED，accepted A1-A5）
- 输入 fix：`docs/gateflow/uf-fix06-slice3-code-fix-20260815.md`
- 初轮 artifact：`docs/reviews/code-review-slice3-ds-20260815.md`（pass，F1-F5；本 artifact 为独立新文件，初轮 artifact 未修改）
- Output file：`docs/reviews/code-re-review-slice3-ds-20260815.md`
- 约束遵守：未修改 production/test/既有 artifact；未 commit；未运行 UF-PF06/UF-PF12

## 复跑验证结果（均在 `source .venv/bin/activate` 后）

- A3/A4/A5 反例聚焦：`15 passed, 3 warnings`（test_upload_failure 全文件 + 两个 service 级新反例 +
  SEC workflow 级新反例）。
- Slice 3 focused matrix（7 个 test 文件）：`501 passed, 3 warnings`（初轮 493 → +8，恰为 A3 1 条、
  A4 2 条、A5 5 个 test item；warnings 为 3 条既有 edgar deprecation，skip 为需显式环境开关的
  真实 Docling integration）。
- Changed-file Pyright（4 production + 3 代表性 test 文件）：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 范围审计：`git diff affa665b --name-only` 恰为 11 个 Slice 3 allowed 文件；`git status --porcelain`
  过滤 allowed 模式后为空。`dayu/config`、`dayu/documents`、`dayu/fins/processors/registry.py`、
  `dayu/fins/tools`、`dayu/fins/README.md` 零 diff；仓库内无 oracle/evidence/scenario 目录可被触碰。
  untracked 仅 5 个 docs artifact 与 `tests/fins/test_upload_failure.py`，无 registry/evidence 文件。

## Accepted A1-A5 逐项核验

### A1 — failure kind 文档补齐 USAGE：fixed

- 证据：`upload_failure.py:80` kind 属性说明现为「usage、content、storage 或 runtime 分类」，
  与 `FinsUploadFailureKind` 四个成员一一对应。类 docstring「closed public category」不变。
- 独立复核：枚举与文档同文件同源，无第二处 kind 分类文案可漂移。

### A2 — 转换 helper 漏报 typed cancellation：fixed

- 证据：`docling_upload_service.py:752-758` Raises 现为五项独立声明：
  `DoclingConversionCancelledError`（转换前或两次转换之间观察到取消）、`FinsUploadFailureError`
  （filing 转换失败）、`DoclingConversionError`（material 转换失败原样抛出）、`RuntimeError`
  （未产生主 Docling 文件）、`ValueError`（preparation/original_assets 不一致）。
- 独立复核：取消与 material 失败不再共用同一 RuntimeError 概括；「原样抛出」与 A4 服务级
  `exc_info.value is cause` 身份断言一致。diff 核算：该文件较初轮净增 4 行，全部位于本 Raises
  块（hunk `@@ -724,37 +732,43 @@` 行数差 +2 另加原文案重排），循环体无任何生产语义变更。

### A3 — prepare 阶段第二项前取消反例：fixed

- 证据（`test_prepare_material_cancellation_before_second_conversion_discards_partial_work`）：
  两文件 material + `_CancelOnNthCheck(cancel_at=4)`。
- 独立核对检查点计数（当前 `prepare_upload` 布局）：line 301 检查 #1、line 323 检查 #2、
  `_build_pending_assets` 第一项 loop-top #3（未取消 → 转换 `first.pdf` 完成）、第二项 loop-top
  #4（已取消 → `raise DoclingConversionCancelledError` → prepare 层 catch → cancelled 计划）。
  `cancel_at=4` 精确命中第二项转换前的 loop-top raise 分支，非 converter 抛出路径。
- 断言完备性：`status == "cancelled"`、`file_events == []`（首项 partial conversion_started 被丢弃）、
  `stored_file_count == 0`、`calls == ["first.pdf"]`（前一转换允许完成、第二项未开始）、
  `begin_calls == 0`（零 batch，经 `_BatchIdentityUploadBatchingRepository` spy）、
  `published_tree_sha256 == {}` 与 source meta FileNotFoundError（零 source/blob）。裁决要求的
  「cancelled plan、空 file events、partial assets/events 丢弃、零 batch、零发布」全部被直接断言。

### A4 — material 第 N 项转换失败原子性反例：fixed

- 服务级证据（`test_prepare_material_nth_conversion_failure_discards_partial_work`）：
  `[ok.pdf, corrupt.docx]` + `_SelectiveFailingDoclingConverter` 在第二项抛 `DoclingConversionError`
  （CONVERTER_EXECUTION）。断言 `exc_info.value is cause`——**异常对象身份原样保留**（Service 不
  包装、不伪造），`calls == ["ok.pdf", "corrupt.docx"]`（调用顺序），`begin_calls == 0`、
  发布树为空、source meta 不存在（前序派生资产不发布）。
- workflow 级证据（`test_upload_material_nth_conversion_failure_is_content_terminal_without_source_publication`）：
  真实 `SecPipeline` + `_FailingMaterialDoclingConverter`。断言事件流恰为
  `[UPLOAD_STARTED, UPLOAD_FAILED]`，failure exact dict 为 `kind=content`、
  `code=docling_converter_execution`、`file_label=None`——既有 catch-all 经共享 failure owner 投影
  content terminal，且**不把未经 owner 证明的文件名归给 failure**（catch 以 `file_label=None` 调用，
  DoclingConversionError 分支忠实透传 None）。`get_source_meta` FileNotFoundError +
  `portfolio/AAPL/materials` glob 为空证明零 source/blob 发布。
- 说明：该测试容忍 workflow 既有的 company staging 先行提交（prepare 前的既有顺序，未变），
  零发布断言边界精确落在 material source 层，与裁决要求一致。

### A5 — closed public failure fact 自身校验 kind/code：fixed

- 生产证据（`upload_failure.py:93-118, 185-203`）：
  - `FinsUploadFailureReason.__post_init__` 新增：`type(self.kind) is not FinsUploadFailureKind`
    与 `type(self.code) is not FinsUploadFailureCode` 分别抛 TypeError（open 字符串/伪造枚举被拒，
    `is not` 语义对 `str` 基类的 Enum 正确闭合）；随后经 `_FAILURE_KIND_BY_CODE[code]` 校验
    kind/code 一致，错配抛 ValueError。错误组合不可能经直接构造后 `to_json()`——对象根本不会产生。
  - 分组真源改为 `_FAILURE_CODES_BY_KIND`（kind → codes），module import 三重 guard：
    kind 键完整（`frozenset(_FAILURE_CODES_BY_KIND) != frozenset(FinsUploadFailureKind)` →
    RuntimeError）、code 互斥（分组大小和 == 并集大小，任一重叠即 RuntimeError）、code 完整
    （并集 == 全枚举）。`_FAILURE_KIND_BY_CODE` 由同一分组 comprehension 派生，单一真源。
  - JSON parser 继续消费同一 `_FAILURE_KIND_BY_CODE`（`:369`），未复制映射。
- 测试证据（`test_upload_failure.py` 新增 5 个 test item）：
  - `test_upload_failure_reason_direct_construction_rejects_kind_code_mismatch`：3 组已知错配
    （content+unsupported_upload_format / usage+docling_converter_execution /
    runtime+storage_io）→ ValueError 且 message 精确匹配。
  - `test_upload_failure_reason_direct_construction_rejects_open_enum_values`：`cast` 注入的
    open `"usage"` kind 与 open code 分别 → TypeError 且 message 精确匹配。
  - `test_upload_failure_kind_code_mapping_is_disjoint_complete_and_single_source`：断言 kind
    覆盖、code 互斥、code 完整、派生映射 == 重算映射（同源契约）。
- 独立复核：guard 的「互斥 ⟺ 大小和 == 并集大小」等价性成立（各分组当前肉眼可证无交集，且任一
  未来重叠会在 import 时 fail closed）；`__post_init__` 对 `_FAILURE_KIND_BY_CODE` 的引用在实例化
  时解析，模块级无提前构造，无 NameError 窗口；全部既有 production 构造点（
  `fins_upload_failure_from_exception` 六个分支、empty/prevalidation factories）kind/code 对均与
  映射一致，全矩阵通过证明无回归。

## 新 findings（本轮主动 pass）

### R1 [observation，non-blocking] JSON parser 的 kind/code 预检与 `__post_init__` 判重

- 证据：`upload_failure.py:369-371` parser 在构造前先做一次 `_FAILURE_KIND_BY_CODE` 一致性预检，
  而紧随其后的 `FinsUploadFailureReason(...)` 构造会经 `__post_init__` 做同一判断。两者复用同一
  映射对象，语义无分歧，错误路径最终都会被拒；parser 预检保留了解析语境专属的
  「upload failure kind 与 code 不一致」文案。
- 影响：逻辑重复（同一判断两处执行），无正确性或 fail-closed 风险。
- 建议（可选）：后续清理时可将 parser 预检收敛为仅依赖 `__post_init__`，或反之保留并在
  docstring 注明分工；不作为本 slice 修复要求。

### R2 [observation，non-blocking] A3 测试与 prepare 检查点计数强耦合

- 证据：`cancel_at=4` 依赖当前 `prepare_upload` 恰好 3 次前置 `_is_cancelled` 调用（line 301、
  323、首项 loop-top）。若未来在 prepare 上游新增任一取消检查点，该测试将命中不同取消位置，
  需要同步调整。
- 影响：测试作为「第二项转换前取消」的精确 tripwire 有效，但脆弱；这是计数型 token 固有权衡，
  且任何偏离都会以测试失败显式暴露，不构成掩盖。
- 建议（可选）：在测试 docstring 注明 `cancel_at` 与检查点布局的对应关系，降低未来维护成本。

## 范围与保护路径审计

- 允许范围：`git diff affa665b --name-only` = 11 个 Slice 3 allowed 文件（4 production + 7 test），
  与裁决「保持条件」一致；未新增 production 文件。
- protected：`dayu/config`、`dayu/documents`、`dayu/fins/processors/registry.py`、`dayu/fins/tools`、
  `dayu/fins/README.md` 零 diff；仓库树内无 oracle/scenario/evidence 目录；untracked 仅 docs
  artifacts 与 `tests/fins/test_upload_failure.py`。旧 review artifact（含初轮
  `code-review-slice3-ds-20260815.md`）未被修改。
- 生产语义 delta：`docling_upload_service.py` 仅 A2 Raises 文案（净 +4 行）；`upload_failure.py`
  为 A1 文案 + A5 校验/分组；`sec_upload_workflow.py`、`cn_pipeline.py` 与初轮完全一致（10 行
  diff 未变）。初轮已确认的 Service/workflow 语义、取消优先级、事件精确性、primary_document 首项
  语义均无回退（全矩阵通过）。

## 结论

- **PASS**
- Blocking findings：**0**
- Non-blocking findings：R1、R2（均为 observation，不要求本轮修复）
- Accepted A1-A5：全部 fixed，均有生产/测试直接证据并经独立复跑确认。

## Residual risks

- `dayu/fins/README.md:201` 旧 `FINS_UPLOAD_FILE_SUFFIXES` 引用：accepted plan 归 Slice 4，本 fix
  按约束未动（初轮 F5 维持 deferred）。
- deferred：material empty content、delete + files、UF-FIX07（collision/显式 primary/batch
  association）保持既有 residual 分类。
- 真实 Docling integration 默认 skip（需 `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`）；真实格式矩阵
  由 UF-PF06/UF-PF12 owner 验证，本轮按约束未运行。
- coverage invocation 问题（NumPy C extension collection-time 重复加载）已由 fix agent 归因并
  绕过，属工具调用问题；本轮复跑未触碰 coverage invocation。
