# Code Re-Review（UF-FIX06 Slice 2，AgentDS 第二路）

## Gate 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：`code review fix Slice 2` → `code re-review`
- Reviewer：AgentDS（第二路独立严格 re-review，与初轮同会话、未 clear）
- 日期：2026-08-15
- 基线 commit：`c1db7b49`（与初轮 review 相同）
- 评审对象：Controller 裁决 `docs/reviews/uf-fix06-slice2-code-review-adjudication-20260815.md`（accepted A1-A5）、fix artifact `docs/gateflow/uf-fix06-slice2-code-fix-20260815.md`、最新未提交 workspace diff
- Output file：`docs/reviews/code-re-review-slice2-ds-20260815.md`
- 初轮 artifact：`docs/reviews/code-review-slice2-ds-20260815.md`（pass-with-risks，F1-F5）

## 复跑验证结果（均在 `source .venv/bin/activate` 后；未运行 UF-PF06/UF-PF12）

- `pytest tests/fins/test_upload_format_contract.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_upload_batch.py -q`：`342 passed, 3 warnings`。
- `pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_tools.py -q`：`688 passed, 3 warnings`。
- 合计 `1030 passed`，与 fix artifact 声称一致（初轮 1026 → 本轮 +4：A1/A4 文案片段、A2 三处 fail-fast/长名用例、A5 无新增用例）。
- pyright（6 changed production + 6 changed test 文件）：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 无 eager Docling import 复查：以 `builtins.__import__` 拦截实测 `dayu.fins.upload_format_contract`、`dayu.cli.arg_parsing`、`dayu.fins.tools.upload_tools` 均可无 docling import 导入。
- 范围审计：workspace diff 仍仅含 Slice 2 允许的 6 个 production / 6 个 test 文件与 gateflow/review artifacts；未触及 Slice 3/4 文件、registry、oracle/scenario、design doc、README、冻结 evidence；review artifacts 只读（旧 review 未改）；未 commit。

## Accepted findings 逐项核验

### A1 — files required/forbidden 文案自足同源：fixed

- 生产证据：`dayu/fins/upload_format_contract.py:561-576` `project_fins_upload_format_text` 中 filing 分支为「auto/create/update 必须至少提供一个文件，并按给定顺序上传…delete 不得提供文件」，material 分支为「upload_kind=material 时，auto/create/update 必须至少提供一个文件；…delete 不得提供文件」。
- 同源实测：CLI `upload_filing` 子 parser 的 `--files` help `== FINS_UPLOAD_FORMAT_TEXT.filing_files`；tool schema `files.description == FINS_UPLOAD_FORMAT_TEXT.upload_tool_files`，两侧 6 个关键片段（must-provide / delete-forbidden / JSON candidate 两条 / XML candidate / material must-provide）全部命中。
- 测试证据：`test_text_projection_is_self_contained_and_uses_exact_suffix_order` 断言 12 个片段同时存在于 filing 与 tool 两文案；`tests/cli/test_arg_parsing.py` help 测试与 `tests/fins/test_fins_ingestion_tools.py` schema 测试分别断言各自消费面。
- 未发现新文案与 tool runtime 行为矛盾（`_upload_files_from_arguments` 的 create/update 拒绝空 files、delete 拒绝 files 与文案一致）。

### A2 — 240 字符 invariant fail-fast 与长 basename 分类：fixed

- 生产证据：
  - `upload_format_contract.py:25,61-82` `_bounded_format_failure_message`：完整模板 message ≤ 240 时保留 canonical label，否则退回 role-specific 固定有界文案；`FinsUploadFormatError.file_label`（`:89,110`）始终为公共 label owner 产生的完整 canonical basename，不截断、不伪造。
  - `ingestion_runtime.py:687-712` `FinsUploadUsageFailure.__post_init__`：open code（非 `FinsUploadUsageCode | FinsUploadFormatFailureKind`）→ TypeError、message 非 str → TypeError、空 message → ValueError、>240 字符 → ValueError。
- Adversarial 实测（本次 review 复现）：
  - 精确窗口：label 228 字符（模板 12 字符）→ message 恰好 240，完整 label 保留于 message 且 `file_label` 完整；
  - label 229/230 字符 → message 退化为 11/12 字符 role-specific fallback，`file_label` 仍完整保留；
  - companion/material 长名同样有界且 label 完整；
  - label > 240 字符 → 公共 canonicalizer 既有语义投影为固定隐藏标签（`direct_events.py:1070-1087`），非本 fix 的截断或伪造；
  - validator 长 basename 路径：仍抛 `FinsUploadUsageError`（`code is PRIMARY_SUFFIX_UNSUPPORTED`、message 有界），`__cause__` 保留完整 label——合法超长安全 basename 未退化为 runtime/unexpected；
  - `FinsUploadUsageFailure(code="open_code", ...)` / 空 message / 241 字符 / 非 str message 四种非法构造全部按声明 fail-fast；`fins_upload_usage_failure` factory 与合法格式 usage 投影继续正常工作。
- 测试证据：`test_long_canonical_basename_keeps_label_and_bounds_primary_material_messages`（230 字符 primary+material，label 完整、message 为 fallback、无父路径）、`test_upload_usage_failure_fact_rejects_open_code_and_unbounded_message`（三种非法构造）、`test_filing_validator_keeps_long_canonical_label_with_bounded_usage_message`（usage 分类不变）、material CLI 参数化长名测试（普通与 230 字符 `.doc` 均在 Service 前 usage exit、零调用）。

### A3 — material CLI docstring：fixed

- 证据：`dayu/cli/commands/fins.py:711` `:raises FinsUploadFormatError: 任一文件不具备 converter-required 格式时抛出。`；`_validated_upload_files` docstring（`:1118-1126`）同步声明两种异常。

### A4 — `.json` candidate 限定：fixed

- 生产证据：`upload_format_contract.py:566`「.json 仅是 Docling JSON 候选，不代表任意 JSON 内容可转换」，与 `.xml` 的 XBRL candidate 限定并列于同一 projection。
- 两侧实测：CLI help 与 tool schema（同一 projection 派生）均含该文案；`tests/cli/test_arg_parsing.py` 与 `tests/fins/test_fins_ingestion_tools.py` 分别断言「.json 仅是 Docling JSON 候选」「不代表任意 JSON 内容可转换」片段。

### A5 — 格式化 churn 恢复与 governance 注释：fixed

- churn 审计（本次 review 逐行核验）：
  - `dayu/fins/upload_batch.py`：diff 由初轮 96 行收敛到 23 行，剩余全部为语义变更（删除旧 allow-list、`accepts_primary` 消费、`__all__` 收敛）；
  - `tests/fins/test_upload_batch.py`：diff 零删除行（纯新增 109 行测试）；
  - `tests/cli/test_arg_parsing.py`：diff 零删除行（纯新增 38 行 help 测试）；
  - `tests/cli/test_fins_commands.py`：16 行删除全部为语义更新（旧 usage 矩阵场景、docstring、参数化）；
  - `tests/fins/test_fins_ingestion_runtime.py` 删除行全部为废弃 usage code 相关断言。
- governance 注释：`tests/fins/test_upload_batch.py:469`「Governance audit：锁定唯一 owner 边界，避免行为测试无法察觉的重复 allow-list 回流。」
- fix artifact 对三个文件「本 Slice 之前即存在基线 Black 差异、仅对 changed ranges 执行 Black check」的说明与实测一致，未重新引入整文件 churn。

### Deferred 项核验 — delete+files 行为未改变

- 实测与初轮一致：`action=delete, files=(report.pdf,)` 仍通过 validator，selection 为 `for_delete()` 空态、`request.files` 原样保留；无 CLI adapter/schema 特例提前收紧。符合裁决「不改变该历史行为，作为 residual 交给后续独立 work unit」。

## New findings

无新 blocking/中高危 finding。以下为观测项（不要求修复）：

- N1（observation）：长 basename 触发 fallback 时，CLI 输出的 message 不含具体文件名（label 保留于 `FinsUploadFormatError.file_label` 与 `__cause__`，不进入 message）。裁决明确允许该形态（「只有人类可读 message 在无法同时容纳完整 label 与 240 字符上界时退回固定的 role-specific 文案」），不构成缺陷。
- N2（observation）：240 边界以两个常量存在于两层（`upload_format_contract._FORMAT_ERROR_MESSAGE_MAX_CHARS` 与 `ingestion_runtime._MAX_TEXT_CHARS`），当前同值且各有独立 invariant 语义；若未来调整边界需两处同步。可接受。
- N3（observation）：`fins_upload_usage_failure` factory 的长度检查与 `FinsUploadUsageFailure.__post_init__` 构成同 owner 重复防御，冗余但无害；dataclass 层校验使任何 bypass factory 的构造路径也被兜住，符合裁决要求。

## 初轮 findings 状态总表

| 初轮 finding | Controller 裁决 | 本次核验 |
| --- | --- | --- |
| F1（LLM-facing files 要求不自足） | A1 accepted / must-fix | **fixed**（A1） |
| F2（240 上限可被格式路径绕过） | A2 accepted / must-fix | **fixed**（A2） |
| F3（material stream docstring 漏报异常） | A3 accepted / must-fix | **fixed**（A3） |
| —（Controller 增补 `.json` candidate） | A4 accepted / must-fix | **fixed**（A4） |
| —（Controller 增补 churn 审计） | A5 accepted / must-fix where safely separable | **fixed**（A5） |
| F4（delete+files 静默丢弃） | deferred / no-action（后续独立 work unit） | 未改变（复核一致） |
| F5（源码 audit 断言脆弱） | deferred / no-action（补 governance 注释） | 注释已补（A5 范围） |

## Verdict

**pass**

- Blocking findings：**0**。accepted A1-A5 全部在正确 owner boundary 闭环：同源 projection 自足说明 files required/forbidden 与 JSON/XML candidate 限定；格式 owner 保留完整 canonical `file_label` 且 message 恒 ≤240；usage public fact 自身对 closed code union、非空与 240 上界 fail-fast；docstring 补齐；纯 Black churn 已恢复、governance 注释已加。
- Adversarial 验证覆盖：长 basename 精确窗口（228/229/230/240/241+）、三种非法 usage public fact 构造、validator/material CLI 的 usage 分类与零副作用、delete+files 历史行为不变、两侧文案同源、无 eager Docling import。
- 复跑 `1030 passed`、pyright `0 errors, 0 warnings, 0 informations`、`git diff --check` 通过，与 fix artifact 声称一致。
- 无新 blocking finding；N1-N3 为观测项。

未修改生产代码、测试、旧 review；未运行 UF-PF06/UF-PF12；未 commit。
