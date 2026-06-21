# Code Review — WU-TOOLS-01-F03-R4 Slice 6

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f03-r4`
- Base: `ee5f2e19` (gateflow: accept WU-TOOLS-01-F03-R4 slice 5)
- Timestamp: 20260621-085204
- Output file: `docs/reviews/wu-tools-01-f03-r4-slice6-code-review-mimo.md`
- Included scope:
  - `docs/host/design.md` — ToolsDiscovery provider field description and empty-output semantics
  - `dayu/config/README.md` — provider fields, packaged defaults, limits, workspace resolution, scene selection
  - `dayu/fins/README.md` — four Fins provider workspace requirement, read switch, upload authorization non-ownership
  - `tests/README.md` — coverage descriptions for config loader, tools discovery, service assembly, Fins providers
  - `docs/reviews/wu-tools-01-f03-r4-slice6-implementation-codex.md` — Codex implementation review artifact (read-only, not reviewed for correctness)
- Excluded scope:
  - `docs/host/issues-implementation-control.md` — controller gate updates (per user directive)
  - Production code / test code / manifest changes — no changes expected or found
- Parallel review coverage: 无

## Verdict

**Accept — 未发现实质性问题。**

所有文档修改已与当前实现对齐。旧字段 (`allow_empty`, `include_read_tools`, `allowed_upload_roots`) 已从活跃 design/README 中移除；残留命中仅限于 scene `tool_selection.allow_empty` 独立语义说明和测试负向断言覆盖描述。

## Findings

未发现实质性问题。

以下为验证过程中的详细证据记录，确认各焦点无偏差：

### 1. design.md: provider-level `allow_empty` 移除

- **`docs/host/design.md:99`** — `tool_discovery.json` 字段摘要已从 `enabled 与 allow_empty` 改为 `enabled 与 provider config`。✅
- **`docs/host/design.md:2058`** — ToolsDiscovery 段落已改为"启用 provider 返回空工具集合是配置错误；需要让 provider 不参与发现时使用 provider-level `enabled=false`"。✅
- **`docs/host/design.md:107`** — scene `tool_selection.allow_empty` 仍在，语义是 scene 工具选择空匹配，与 provider 空输出无关。两处 `allow_empty` 命中分别属于不同语义域，不冲突。✅
- 直接代码证据：`dayu/runtime/tools_discovery.py:263` 的 `ToolBundle(definitions=(), _allow_empty=True)` 仅在无 provider 贡献 definitions 时使用（即所有 provider 都被禁用），与 provider 级 `allow_empty` 无关。✅

### 2. config README: packaged defaults 和 workspace resolution

- **`dayu/config/README.md:178`** — 已增加"启用 provider 返回空工具集合是配置错误"。✅
- **`dayu/config/README.md:180`** — 已明确 `workspace_root="workspace/"` 是 packaged relative default，Service 会解析为绝对路径。✅
- **`dayu/config/README.md:189`** — 已列出 Fins read limits 显式默认值，与 `dayu/config/tool_discovery.json:11-22` 逐字段一致。✅
- **`dayu/config/README.md:191`** — 已列出 Doc limits 显式默认值，与 `dayu/config/tool_discovery.json:63-69` 逐字段一致。✅
- **`dayu/config/README.md:191`** — `doc-tools.enabled=false` 已记录，与 `tool_discovery.json:60` 一致。✅
- `include_read_tools` 和 `allowed_upload_roots` 在 config README 中无命中。✅
- **`dayu/config/README.md:209`** — 已说明默认非上传 scene 使用显式工具名而非 broad `"fins"` tag。与 `dayu/config/prompts/manifests/confirm.json` 等 manifest 中 `tool_names` 列出 read/download/preprocess 工具、`tool_tags_any` 仅含 `"web"` 的实际状态一致。✅

### 3. fins README: four providers require effective absolute workspace_root

- **`dayu/fins/README.md:111`** — read provider "启用时必须通过 effective spec 提供绝对 `workspace_root`"。✅
- **`dayu/fins/README.md:130-133`** — 三个 awaiting provider "都必须通过 effective spec 获得绝对 `workspace_root`"。✅
- **`dayu/fins/README.md:410`** — "四个 Fins provider 的 effective spec 都必须提供非空绝对 `workspace_root`"。✅
- **`dayu/fins/README.md:414`** — "upload provider 不拥有本地源文件 allowlist 或授权配置"。✅
- **`dayu/fins/README.md:667`** — "本地源文件授权由调用方在 provider 外部承担"。✅
- 直接代码证据：
  - `dayu/fins/tools/provider.py:74-80` — `parse_fins_workspace_root_config` 要求非空字符串且 `is_absolute()`。✅
  - `dayu/fins/tools/upload_provider.py:36` — upload provider 调用同一个 `parse_fins_workspace_root_config`。✅
  - `dayu/fins/tools/upload_tools.py:409-427` — `_resolve_upload_file_path` 只校验 `is_file()` 和非空，无 allowlist。✅
  - `dayu/service/host_assembly.py:943-1012` — Service effective config 解析相对路径为绝对路径。✅

### 4. tests README: coverage descriptions 匹配当前测试

- **`tests/README.md:124`** — config loader 覆盖描述已增加 "packaged tool discovery 中 Fins `workspace_root='workspace/'`、显式 Doc / Fins limits、`doc-tools.enabled=false` 和旧 provider-level `allow_empty` 字段拒绝"。与 `tests/runtime/test_config_loader.py:1083-1098` 的 `test_tool_discovery_provider_allow_empty_is_rejected` 一致。✅
- **`tests/README.md:140`** — tools discovery 覆盖描述已改为"启用 provider 空工具输出 fail-fast"。与 `tests/runtime/test_tools_discovery.py:420` 的 `test_empty_provider_without_allow_empty_fails` 一致。✅
- **`tests/README.md:150`** — Fins awaiting assembly 覆盖描述已增加 "relative workspace root 无运行时根"。✅
- **`tests/README.md:125`** — CLI upload 覆盖描述已从 "allowlist 前置校验" 改为 "存在性 / 普通文件 / 非空前置校验"。✅
- `include_read_tools` 在 tests README 中无命中。✅
- `allowed_upload_roots` 在 tests README 中无命中。✅
- 测试文件中的旧字段引用仅限于负向断言：`tests/runtime/test_config_loader.py:413` (`assert "allowed_upload_roots" not in upload_provider.config`)。✅

### 5. 无 process/gate/PR status 泄漏

- 在 `docs/host/design.md`、`dayu/config/README.md`、`dayu/fins/README.md`、`tests/README.md` 中未发现 WU process status、gate status、PR status 或 merge status 信息。✅
- `docs/host/issues-implementation-control.md` 未被修改（per user directive）。✅

### 6. Grep classification

全仓 grep 剩余命中分类（已在 Codex artifact 中记录，本 review 独立验证一致）：

- `allow_empty`：
  - 活跃 docs 命中：`design.md:107` (scene `tool_selection.allow_empty` 独立语义)、`design.md:2058` (ToolsDiscovery 不允许 provider 空输出)、`config/README.md:209` (scene 独立语义说明)、`tests/README.md:124` (负向测试覆盖)。✅
  - 生产代码：`dayu/runtime/tools_discovery.py:263` (`ToolBundle._allow_empty` 内部构造)。✅
  - 测试：仅负向断言。✅
  - 历史 plan/review/archive/controller gate 文档。不属于活跃配置说明。✅
- `include_read_tools`：无活跃 docs/生产代码/测试命中。✅
- `allowed_upload_roots`：`tests/runtime/test_config_loader.py:413` 负向断言，其余为历史文档。✅

## Open Questions

无。

## Residual Risk

1. **历史文档残留**：历史 plan / review / archive 文档仍保留旧字段语义记录。这些是历史材料，不作为当前稳定配置说明，不影响实现正确性。
2. **`docs/host/issues-implementation-control.md`** 仍有 controller gate 更新和旧字段上下文命中。该文件是用户指定不修改的总控文档，需由 controller 另行更新。
3. **测试未运行**：本次 review 仅涉及 Markdown 文档修改，未修改 fixtures、manifest、生产代码或测试代码。Codex artifact 记录 pyright 通过 (`0 errors, 0 warnings, 0 informations`)。pytest 未在本次 Slice 6 文档同步中运行，但文档修改不影响测试行为。
4. **upload 本地文件授权**：`fins README` 明确"本地源文件授权由调用方在 provider 外部承担"，这是正确的当前状态描述，但未来 Host / policy 设计仍需决定是否引入系统级文件读取授权机制。文档已正确标记此为未来工作。
