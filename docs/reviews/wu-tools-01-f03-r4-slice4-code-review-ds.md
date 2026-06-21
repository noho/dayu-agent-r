# Code Review — WU-TOOLS-01-F03-R4 Slice 4

## Scope

- **Mode**: current changes (working tree vs accepted Slice 3 commit)
- **Branch**: `phase/wu-tools-01-f03-r4`
- **Base**: `3f7fd44a` (gateflow: accept WU-TOOLS-01-F03-R4 slice 3)
- **Output file**: `docs/reviews/wu-tools-01-f03-r4-slice4-code-review-ds.md`
- **Included scope**:
  - `dayu/fins/tools/upload_provider.py`
  - `dayu/fins/tools/upload_tools.py`
  - `dayu/config/tool_discovery.json`
  - `dayu/config/prompts/manifests/*.json` (10 default non-smoke manifests)
  - `tests/fins/test_fins_ingestion_tools.py`
  - `tests/runtime/test_scene_prepare.py`
  - `tests/runtime/test_config_loader.py`
  - `tests/tools/test_combined_tools_acceptance.py`
  - `dayu/config/README.md`
  - `dayu/fins/README.md`
  - `tests/README.md`
  - `docs/reviews/wu-tools-01-f03-r4-slice4-implementation-codex.md` (Codex 自述，用于交叉验证)
- **Excluded scope**: Slice 5/6 未来工作、`docs/host/issues-implementation-control.md`（controller 所有）、smoke manifests（非默认用户 scene）、`docs/host/design.md` / `docs/engine/design.md`（只作为设计真源参照，不在本 Slice 修改范围）
- **Design truth**: `docs/host/design.md` and `docs/engine/design.md`
- **Plan source**: `docs/host/host-issues/wu-tools-01-f03-r4-tools-discovery-spec-plan.md`，Section Slice 4
- **Parallel review coverage**: 无。本 review 为单人深度走读。

## Findings

### 1-未修复-低-`_resolve_upload_file_path` 缺少符号链接行为覆盖

- **入口/函数**: `_resolve_upload_file_path(raw_path: str) -> Path`
- **文件(行号)**: `dayu/fins/tools/upload_tools.py:409-427`
- **输入场景**: 用户传入指向 workspace 外现有非空普通文件的符号链接作为 `files` 元素
- **实际分支**: `candidate = Path(raw_path).expanduser().resolve(strict=False)` 解析符号链接指向的真实路径；`is_file()` 跟随符号链接返回 `True`；`stat().st_size` 跟随符号链接返回真实文件大小
- **预期行为**: 语义合理——符号链接指向的仍是用户要求上传的文件。当前实现正确接受此类路径。
- **实际行为**: 符号链接被接受，上传 observation 正常启动。行为正确但无显式测试覆盖此路径。
- **直接证据**: `upload_tools.py:422-426`，`Path.is_file()` 默认跟随符号链接；测试文件中无 `symlink` 相关 upload 用例
- **影响**: 行为正确，测试缺口为低风险；若未来 `_resolve_upload_file_path` 被修改（如添加 `strict=True` 或其他校验），缺少回归保护
- **建议改法和验证点**: 在 `tests/fins/test_fins_ingestion_tools.py` 增加一个用例：构造指向现有非空普通文件的符号链接，验证 `_resolve_upload_file_path` 返回 resolved 路径并正常通过校验
- **修复风险（低）**: 纯测试补充，不影响生产行为
- **严重程度（低）**: 当前行为正确，仅缺少回归覆盖

### 2-未修复-低-场景测试依赖需手动同步的硬编码 scene ID 列表

- **入口/函数**: `test_default_non_upload_scenes_do_not_select_upload_tool`
- **文件(行号)**: `tests/runtime/test_scene_prepare.py:366-388`；常量定义 `_DEFAULT_NON_UPLOAD_SCENE_IDS` 在行 45-56
- **输入场景**: 未来新增默认 scene manifest 文件到 `dayu/config/prompts/manifests/`
- **实际分支**: 新 manifest 不会被 `_DEFAULT_NON_UPLOAD_SCENE_IDS` 覆盖，因此不会被本测试验证
- **预期行为**: 新增默认 scene 应该也被验证不会误选 `start_fins_upload`
- **实际行为**: 测试只覆盖硬编码列表中的 10 个 scene；新增 scene 可能通过 broad tag（如果错误引入）选中 upload 而不被此测试捕获
- **直接证据**: `test_scene_prepare.py:45-56` 硬编码了 10 个 scene ID；测试 `366-388` 只遍历此列表
- **影响**: 如果新增 manifest 错误使用 `"fins"` tag，不会被现有 CI 捕获。属于维护性风险而非当前缺陷
- **建议改法和验证点**: 可考虑在测试中动态发现 `_PACKAGE_MANIFEST_ROOT` 下所有 manifest 文件，排除已知非默认 scene（如 `smoke_*`、`audit`、`overview`、`conversation_compaction`），然后对所有默认 scene 执行相同断言。或在 `_DEFAULT_NON_UPLOAD_SCENE_IDS` 旁加注释提醒同步更新
- **修复风险（低）**: 动态发现方案需要维护排除列表；注释方案更轻量
- **严重程度（低）**: 不影响当前正确性

### 3-未修复-低-`test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` 未穿透 repository 写入边界

- **入口/函数**: `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`
- **文件(行号)**: `tests/fins/test_fins_ingestion_tools.py:928-948`
- **输入场景**: workspace 外本地文件成功启动 upload observation
- **实际分支**: 使用 `_NoOpExecutor` 只记录 submit 调用，不执行真实 upload pipeline。断言覆盖：`ToolAwaitingOutcome` 返回、job IDs 不含源目录、源目录无 `.dayu` 治理目录
- **预期行为**: 需要证明 source/blob 写入仍落在 Fins workspace repository，且不写入源文件目录
- **实际行为**: 只证明了 source-side 边界（源目录无副作用），未穿透验证 destination-side 边界（repository 写入落在 workspace 内）。本测试的设计意图是 source-side boundary proof，repository 写入边界由 `tests/fins/test_fins_ingestion_runtime.py` 等测试覆盖
- **直接证据**: `_NoOpExecutor` 定义在 `test_fins_ingestion_tools.py:574-609`，只做 `submitted_job_ids` 记录；测试断言在行 944-948
- **影响**: 当前通过其他测试间接覆盖，但如果 repository 写入路径被重构，此处缺少显式回归断言
- **建议改法和验证点**: 可考虑在测试 docstring 中显式注明 "repository write boundary verification is covered by ingestion runtime pipeline tests"，避免未来读者误判覆盖缺口。或增加一个集成测试：用真实 executor 跑完 upload 后检查 workspace repository 中出现了预期文件
- **修复风险（低）**: 注释补充无风险；集成测试需要真实 upload pipeline 依赖
- **严重程度（低）**: 边界已有其他测试间接覆盖，本测试的 source-side focus 设计合理

## Open Questions

1. **`docs/host/design.md` 中旧 `allow_empty` 段落是否需要更新？** 计划将此归入 Slice 6（文档同步）。当前 `docs/host/design.md` 可能仍描述已删除的 provider-level `allow_empty`。这不影响 Slice 4 代码正确性，但若 Slice 6 被延迟，设计文档与实现之间存在暂时不一致。建议在 Slice 4 closeout 时至少标注已知差距。

2. **`_resolve_upload_file_path` 是否应对明显异常路径（如 `/dev/null`、`/proc/` 等特殊文件系统路径）做额外防御？** 当前只检查 `is_file()` 和 `st_size > 0`。`/dev/zero` 是 character device，`is_file()` 返回 `False`，会被拒绝。`/dev/null` 的 `is_file()` 在不同 OS 上行为不同（macOS 上返回 `False`）。当前校验对常见特殊路径已足够，但未显式测试。非阻塞问题。

## Residual Risk

1. **上传本地文件授权未解决（计划已确认）**: 删除 provider-local allowlist 后，任何进程可访问的现有非空普通文件都可作为 `start_fins_upload` 的输入。这是有意的设计决策——当前没有 Host 级统一权限系统，provider-local allowlist 不是可信的全局权限边界。未来 Host / policy 设计需要决定本地文件读取的授权、审计或 sandbox 机制。**风险已记录在 plan residual risks 中。**

2. **自定义 workspace overlay 的 `fins` tag 暴露**: 如果用户 workspace overlay 中的 scene manifest 仍使用 `tool_tags_any: ["fins"]`，升级后 `start_fins_upload` 会被选中。包内默认 manifest 已全部修复，但自定义 overlay 不受此 Slice 保护。**这是 plan 中确认的 residual risk，需要 rollout notes 或 migration guide。**

3. **CWD 依赖**: `_resolve_upload_file_path` 对相对路径的解析依赖进程 CWD（`Path.resolve()` 行为）。在旧代码中同样存在此依赖，但 allowlist containment 提供了二次约束。Now without allowlist，CWD 变化可能导致同一相对路径解析到不同绝对路径。对于 LLM 生成的工具调用参数，LLM 应倾向于使用绝对路径（由用户或上游工具提供）。**实际风险低，因为 LLM-facing schema 描述的是 "local file paths"，且上游工具/用户通常提供绝对路径。**

4. **`tests/runtime/test_smoke_host_public_multiturn_assembly.py` 本次未修改**: smoke 测试使用包内默认配置运行。Codex 报告 38 passed（与 scene_prepare 合计）。未逐条验证 smoke 测试的断言是否因 upload 默认注册而需要更新。如果 smoke 测试中有对工具数量或 source refs 数量的精确断言，可能需要同步更新（如 `test_combined_tools_acceptance.py` 中将 `source_refs` 从 5 更新到 6）。Codex 报告的通过数表明 smoke 测试兼容当前变更，但未独立验证。

5. **`docs/host/design.md` 和 `docs/engine/design.md` 未在本 Slice 更新**: 按计划归入 Slice 6。当前设计文档中关于 `allow_empty`、`allowed_upload_roots` 的描述可能与实现不一致。不影响代码正确性。

## Verdict

**无 blocking finding。** Slice 4 实现精确遵循 plan 中定义的 exact changes，逐条对照通过：

| Focus Area | 结果 |
|---|---|
| 1. Upload provider 删除 allowed_upload_roots，始终注册 start_fins_upload | ✅ 通过 |
| 2. Upload tool 删除 allowlist，保留 action/file count/存在/非空/delete 校验 | ✅ 通过 |
| 3. Repository/write boundary 保留，源路径仅为输入 | ✅ 通过 |
| 4. Packaged config: enabled=true，无 allowed_upload_roots | ✅ 通过 |
| 5. 默认 manifest 不通过 broad tag 选中 upload，allow_empty 未变 | ✅ 通过 |
| 6. LLM-facing schema 文本自解释，无 configured upload roots 措辞 | ✅ 通过 |
| 7. README 更新为最小触发同步，无 overrun | ✅ 通过 |
| 8. Tests/pyright/rg 充分 | ✅ 通过（3 个低严重度测试覆盖建议） |

**Blocking findings: 0**

**验证摘要**（来自 Codex 报告，已交叉核对 diff 与文件内容）：
- `pytest tests/fins/test_fins_ingestion_tools.py -q`: 47 passed
- `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`: 38 passed
- `pytest tests/tools/test_combined_tools_acceptance.py -q`: 8 passed
- `pytest tests/runtime/test_config_loader.py -q`: 41 passed
- `pyright dayu tests utils`: 0 errors, 0 warnings, 0 informations
- `rg -n "allowed_upload_roots\|_CONFIG_ALLOWED\|parse_allowed_upload" dayu tests utils`: 仅 `test_config_loader.py:413` 反向断言
- `rg -n "_normalize_allowed_upload_roots\|_resolve_upload_path" dayu tests utils`: 无命中
- `rg -n '"fins"\|fins-upload\|"ingestion"' dayu/config/prompts/manifests/`: 无命中（所有 10 个默认 manifest 已清理 broad tag）
- `rg -n "start_fins_upload" dayu/config/prompts/manifests/`: 无命中（upload 不出现在任何 manifest 的 tool_names 或 tool_tags_any 中）
- `rg -n '"allow_empty"' dayu/config/tool_discovery.json`: 无命中
