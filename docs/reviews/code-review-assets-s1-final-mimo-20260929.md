RUNTIME/PROVIDER/MODEL: codex/mimo/mimo-v2.6-pro
CANARY=mimo-ae05ea19

# Code Review

## Scope

- Mode: current changes
- Branch or PR: `codex/upload-material-assets`
- Base: `1453a659a79d4c9a93838412dfdecfa7feeddf98`
- Output file: `docs/reviews/code-review-assets-s1-final-mimo-20260929.md`
- Review timestamp: `20260929-173335`
- Included scope: 当前 tracked `git diff`、未跟踪 production owner、相邻测试、accepted goal/plan、S1 F1-F14/R1/R2 总控裁决、F12/F13/F14 修复记录、README/文档变更，以及真实 CLI/tool 测试路径。
- Excluded scope: 不修改产品、测试、README、goal、plan、旧 review/裁决、主队列；不实施 O05/O16/O25；不 commit、push、PR、merge。
- Parallel review coverage: 无。未派发子 Agent；本轮独立走读并复核。

### 锁定状态

- HEAD `1453a659a79d4c9a93838412dfdecfa7feeddf98`：匹配。
- tracked `git diff --binary` SHA-256 `05d8977450722aa7cefbd51607ceec14721a1301b7d109ab4e98d46213b6c14b`：匹配。
- 关键未跟踪 owner：
  - `dayu/fins/storage/asset_filename_contract.py`：`c2c91eeebb8cc5f16a6aea3f72db916102addf1228282c35ecd7994655eb706f`
  - `dayu/fins/upload_asset_plan.py`：`707d12a79c5cec4c97047749bc68bd0593a6e93adb39249aeac751bd791be7fc`
  - `dayu/fins/upload_usage_contract.py`：`eac24f88fc6de8b8bd99811ce2e2042ff1cdd663e434d0ad417524e864bd532e`
- F14 记录列出的其它未跟踪文件均匹配，唯独 `docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md` 当前 SHA-256 为 `ddcc2b7dbc9237166d8e9e87340e2d21b06d1d8b0e9e546b3cda6e1e75debfcc`，记录锁定值为 `65ebb9e3e8d41d2db7d438668a8c793908cebcd6b73512814847fd651d72f9c7`。这是总控文档后续追加 F14 候选核验造成的非 owner 锁漂移；关键 owner 锁未漂移，因此本结论不对该文档历史版本作通过声明。

## Findings

### 001-未修复-[中]-路径解析循环被误判为非法文件名

- **入口/函数**: `admit_fins_upload_material_request` -> `plan_upload_assets` -> `normalize_upload_asset_path`
- **文件(行号)**: `dayu/fins/upload_asset_plan.py:92-109,256-264`
- **输入场景**: material 文件路径是自引用 symlink loop；文件名本身合法，但 `Path.resolve(strict=False)` 在解析循环时抛出 `RuntimeError`。
- **实际分支**: `plan_upload_assets` 的统一 `except (UnicodeEncodeError, ValueError, RuntimeError)` 把该 `RuntimeError` 记录为 `invalid_path`，最终抛 `FinsUploadAssetPlanReason.INVALID_ASSET_NAME`。
- **预期行为**: `normalize_upload_asset_path` 的文档明确承诺循环解析的 `RuntimeError` 透传；F13 的目标是把 NUL、未知 `~user` 等用户输入解析失败收口为 typed usage，同时保留真正操作性路径失败的独立分类。应区分 `expanduser` 的未知用户错误与 `resolve` 的 symlink loop/操作性错误。
- **实际行为**: 独立探针返回 `{\"loop_exception\":\"RuntimeError\",\"loop_reason\":\"invalid_asset_name\"}`；tool/CLI 会把它当作用户可重命名修正的 `invalid_argument`，提示“缩短或重命名文件”，而不是路径解析/存储操作失败。
- **直接证据**: `upload_asset_plan.py:109` 调用 `expanduser().resolve(strict=False)`；`upload_asset_plan.py:261` 同时捕获 `RuntimeError`；`normalize_upload_asset_path` 的 Raises 已写明循环 `RuntimeError` 透传，两个合同互相矛盾。探针使用真实临时自引用 symlink，未经过 mock。
- **影响**: 错误分类和用户修复建议错误；高成本路径问题被伪装成文件名问题，真实 CLI/tool 的错误类别与底层执行事实不一致。
- **建议改法和验证点**: 在唯一路径 owner 内分开捕获 `expanduser` 与 `resolve`；只把 NUL、代理字符、未知 `~user` 和非法 basename 归 `INVALID_ASSET_NAME`，symlink loop/操作性解析失败保留 typed operational failure。补 symlink loop、未知用户、NUL 正逆序测试，并验证 tool/CLI 不创建 observation/job、不发布。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### 002-未修复-[中]-裸 UploadAssetPlan 可绕过 handoff 不变量进入 Docling 边界

- **入口/函数**: `DoclingUploadService.prepare_upload` -> `_prepare_upload_asset_plan` -> `_build_original_assets` / `_build_pending_assets`
- **文件(行号)**: `dayu/fins/upload_asset_plan.py:83-90`、`dayu/fins/pipelines/docling_upload_service.py:364-405,880-932,1449-1482`、`dayu/fins/ingestion_runtime.py:1405-1458`
- **输入场景**: 直接构造 `UploadAssetPlan`，令 `ordered_pairs` 指向 `one/deck.txt`，`converter_pairs` 指向 `two/other.txt` 但沿用同一 `original_name/docling_name`；绕过 `ValidatedFinsUploadMaterialRequest`。
- **实际分支**: `_prepare_upload_asset_plan` 对 material 只检查 `isinstance(selection, UploadAssetPlan)` 和空/非空，不检查 ordered/converter pair 的路径和身份一致性；下游 `originals_by_name[pair.original_name]` 取原件 bytes，却把另一个 pair 的 `file_path.name` 交给 converter。
- **预期行为**: plan 是转换、派生名、primary、指纹和发布的同一 immutable identity handoff；其自身或 Docling 边界必须拒绝内部不一致，不能依赖上层 wrapper 偶然补校验。
- **实际行为**: 独立探针显示裸 plan 被 `_prepare_upload_asset_plan` 接受，并返回 `converter_pairs[0].path` 为 `two/.../deck.txt`；`ValidatedFinsUploadMaterialRequest.__post_init__` 才会拒绝这种跨字段漂移。
- **直接证据**: `UploadAssetPlan` 没有 `__post_init__` 不变量；`_prepare_upload_asset_plan` 没有 pair 对齐校验；`_build_pending_assets` 在 `docling_upload_service.py:956-970` 按 `original_name` 查 bytes、按 `pair.path.name` 调 converter。
- **影响**: 直接调用 lower service 或未来接入新入口时，可能在错误 bytes/文件名对应下付费转换并在发布前才触发完整性拒绝；typed handoff 的 source of truth 被拆成两个可写边界。
- **建议改法和验证点**: 让 `UploadAssetPlan.__post_init__` 收束 ordered/converter/original/derived 不变量，或让 Docling material 边界只接受经过同一 owner 校验的 handoff；补 plan 构造期反例和 service 边界反例，确认错误发生在 converter/存储前。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。

### 003-未修复-[低]-usage category 与 planner-only code 的校验只覆盖单向

- **入口/函数**: `FinsUploadUsageFailure.__post_init__` / `fins_upload_usage_failure` / `FinsUploadToolCallable.__call__`
- **文件(行号)**: `dayu/fins/upload_usage_contract.py:56-102,211-256`、`dayu/fins/tools/upload_tools.py:117-127`
- **输入场景**: 构造 `FinsUploadUsageFailure(code=ASSET_NAME_COLLISION, message=安全文案, category=REQUEST)`，或由公共工厂以默认 REQUEST category 创建 planner-only code。
- **实际分支**: `__post_init__` 只拒绝 `category=ASSET_PLAN` 且 code 不在 planner mapping 的组合，没有拒绝 planner-only code 标成 REQUEST；tool 因 category 不是 ASSET_PLAN 而投影 `invalid_argument`。
- **预期行为**: F14 要求 typed category 是 usage 语义真源，同一 fact 不因异常 cause 改变；planner-only code 必须保持 ASSET_PLAN，只有明确共享 code 才允许 REQUEST/ASSET_PLAN 两种 category。
- **实际行为**: 独立探针返回 `request_category_with_plan_code_accepted: true`；该 fact 的公开 code 与 tool error 类别可以被错误 owner 构造后静默漂移。
- **直接证据**: `upload_usage_contract.py:95` 只有 ASSET_PLAN -> planner codes 的单向校验；`upload_tools.py:117-127` 只能消费 category，无法修复错误 category。
- **影响**: 当前 planner producer 正确，但公共 usage owner 的 typed invariant 不完整，未来重抛/adapter/fake 可重现 F14 所针对的公开错误漂移。
- **建议改法和验证点**: 在 usage owner 显式区分 shared codes 与 planner-exclusive codes，双向校验 category/code；补 planner-only REQUEST、shared code 双 category、有/无 cause 的 tool 结果一致性测试。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

### 004-未修复-[低]-LLM-facing files schema 未自足说明新的名字准入规则

- **入口/函数**: `build_fins_upload_tool` -> `_upload_parameters_schema` -> `FINS_UPLOAD_FORMAT_TEXT.upload_tool_files`
- **文件(行号)**: `dayu/fins/tools/upload_tools.py:230-330`、`dayu/fins/upload_format_contract.py:635-645`
- **输入场景**: LLM 选择多个 material 文件，可能提交重复 basename、`meta.json`/`.identity.json` 变体、同 stem 不同后缀或不适合保存的文件名。
- **实际分支**: schema 的 `files` description 只说明路径存在、非空、后缀和转换资格，`maxItems` 只表达数量；没有说明重复名字、控制名、派生名冲突和完整 basename 映射规则。
- **预期行为**: LLM-facing schema/说明应自足写出当前任务的输入约束和禁止事项，让无状态模型在调用前能稳定选择可接受文件。
- **实际行为**: README 有完整用户规则，但 tool schema 本身没有这些关键规则；模型只能在失败后依赖错误文案重试。
- **直接证据**: `upload_format_contract.py:635-645` 的 `upload_tool_files` 文案未包含 `MAX_MATERIAL_UPLOAD_FILES` 之外的名字冲突/控制名规则；`ToolParametersSchema` 只有 `maxItems`。
- **影响**: 增加不必要的 tool 失败重试，且工具契约与 LLM-facing 文本约束不完全一致；不直接造成存储损坏。
- **建议改法和验证点**: 由 format/text owner 在 `upload_tool_files` 中加入简洁、自足的数量、重复 basename、控制名和 `deck.txt -> deck.txt_docling.json` 映射说明，并以 schema snapshot 测试锁定。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

- 无。O16 的 delete 携带 files 动作规则、O25 的 primary 选择规则和 `fins-material-file-existence-admission` 仍按既有边界留待独立工作单，不作为本轮通过条件。

## Residual Risk

- `NFC + casefold + NFC` 只是保守碰撞键，可能多拒；目标卷 `NAME_MAX<255`、路径 TOCTOU 和其它平台 alias 仍由 storage 最终完整性防线处理。
- material fingerprint 仍只含原件 `name`、`sha256`、`size`、`source`，不包含派生名；旧 source 的错误 stem-derived 文件名若与新输入同 fingerprint，仍可能走既有 identical-skip 而不修复旧文件。这是 accepted plan 已登记的残余，不是本轮新回归。
- 文件状态预检的 `Path.is_file()`/`exists()` 对部分 OSError 会返回 False，保留了原行为；本轮没有把该独立 WU 改成 typed operational failure。
- 当前真实 CLI/tool 路径由测试覆盖：`test_upload_tool_material_path_failure_uses_planner_usage_owner`、`test_upload_tool_projects_same_usage_fact_independent_of_exception_cause`、`test_real_cli_long_duplicate_basename_is_typed_usage_without_publication`、`test_real_cli_backslash_basename_is_typed_usage_without_publication`、`test_real_cli_unknown_home_uses_planner_usage_without_publication`、`test_material_cli_path_precheck_keeps_existing_usage_before_service`。这些测试覆盖真实 JSON/argv、exit、无 observation/job/发布和文件状态预检；未在本轮另跑完整100次真实 Docling 转换，受控 100 次调度由 `test_material_hundred_inputs_schedule_hundred_controlled_converter_calls` 覆盖。
- batch/skip/version/manifest 由 `test_execute_upload_skips_when_source_fingerprint_matches`、`test_upload_source_fingerprint_is_stable`、`test_execute_upload_uses_one_caller_batch_for_blobs_and_final_meta`、`test_prepare_material_cancellation_before_second_conversion_discards_partial_work` 及 SEC/CN material 流测试覆盖；material 失败不发布 source，成功计数只计 original。

## Verification

- 受影响测试矩阵：`1703 passed, 1 skipped`，3 条第三方 `edgar` deprecation warning；没有测试失败。
- `source .venv/bin/activate` 后运行 `pyright`：`0 errors, 0 warnings, 0 informations`；工具提示可升级到 pyright 1.1.414，但当前 1.1.408 验证通过。
- 逐改 production 文件 coverage 均达到 80%：`fins.py 86.21%`、`direct_events.py 87.79%`、`observation_handle.py 93.70%`、`ingestion_runtime.py 91.24%`、`_filing_upload_fresh_validation.py 100%`、`cn_pipeline.py 92.73%`、`docling_upload_service.py 89.81%`、`filing_upload_publication.py 87.36%`、`sec_pipeline.py 86.67%`、`sec_upload_workflow.py 93.75%`、`service_runtime.py 93.10%`、`storage/__init__.py 100%`、`_fs_maintenance_core.py 90.91%`、`_fs_source_integrity.py 85.69%`、`asset_filename_contract.py 100%`、`upload_tools.py 93.75%`、`upload_asset_plan.py 92.21%`、`upload_failure.py 96.10%`、`upload_usage_contract.py 94.55%`、`fins_direct.py 100%`。
- `git diff --check`：通过。
- 一次探索命令 `rg -n "upload_failure|upload_usage_contract|upload_asset_plan" dayu/fins/upload_format_contract.py dayu/fins/direct_events.py dayu/fins/storage/*.py` 退出码为 1，因为预期无匹配；该命令未作为证据，失败已如实保留。

## Conclusion

不建议把当前候选直接作为无条件 merge 通过。F1-F14/R1/R2 的已修内容、真实 tool/CLI 零副作用、数量边界、命名同源、batch/skip/version/manifest 和 README 触发范围均有证据，但本独立复审发现 2 个中等级 owner/boundary 缺口和 2 个低等级 contract/LLM-facing 缺口；应先修复 001、002，并同步收口 003、004，再按同一 tracked+完整未跟踪锁进行下一轮复审。关键 production owner SHA 与 tracked diff 均匹配；总控裁决文档存在一处非 owner 锁漂移，不能据此扩大通过范围。
