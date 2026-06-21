# Code Review — WU-TOOLS-01-F03-R4 Slice 6 文档/设计同步

## Scope

- Mode: current changes
- Branch: phase/wu-tools-01-f03-r4
- Base: ee5f2e19 (accepted Slice 5 commit)
- Output file: docs/reviews/wu-tools-01-f03-r4-slice6-code-review-ds.md
- Included scope:
  - `docs/host/design.md` — ToolsDiscovery provider 字段描述、空 provider 语义、scene `tool_selection.allow_empty` 分离
  - `dayu/config/README.md` — provider 字段表、Fins workspace_root 相对默认值/绝对解析、Doc/Fins limits、doc-tools.enabled=false、默认 scene 不上传
  - `dayu/fins/README.md` — 四个 provider absolute workspace_root、read 启用开关、upload 授权归属、storage 仓储边界
  - `tests/README.md` — config loader / tools discovery / assembly helpers / Fins awaiting assembly / Fins provider 覆盖描述同步
- Excluded scope:
  - `docs/host/issues-implementation-control.md` — controller gate 更新（用户指定不修改）
  - 生产代码、测试代码、scene manifest、`dayu/README.md`、根 `README.md`（未在本 Slice 变更）
  - 历史 plan / review / archive 文档（不作为当前稳定配置说明）
- Parallel review coverage: 无（单 reviewer 走读全部四个文件 diff + 当前全文关键段落）

## Findings

未发现实质性问题。

### 逐项验证

**Focus 1 — design.md: provider-level allow_empty 移除与语义更新**

- `docs/host/design.md:99`：`tool_discovery.json` 字段列表已从 `allow_empty` 更新为 `provider config`。与 `dayu/config/README.md:170-176` 的 provider 字段表一致（`import_path` / `entry_point` / `source_kind` / `source_id` / `enabled` / `config`）。
- `docs/host/design.md:2058`：ToolsDiscovery 段落明确"启用 provider 返回空工具集合是配置错误；需要让 provider 不参与发现时使用 provider-level `enabled=false`"。scene manifest 的 `tool_selection.allow_empty` 被单独标注为"只控制 scene 工具选择空匹配语义，不允许 ToolsDiscovery provider 返回空输出"。
- `docs/host/design.md:107`：scene `tool_selection.allow_empty` 独立语义保留，仅控制 scene 工具选择空匹配，与 provider 空输出无关。
- Host/Engine non-ownership 文本（`docs/host/design.md:111-119`）未修改，边界描述保持原样。

**Focus 2 — config README: 默认值与限制文档化**

- `dayu/config/README.md:180`：packaged Fins `workspace_root="workspace/"` 明确标注为 packaged relative default，并给出 Service effective absolute 解析示例（`/path/to/project` → `/path/to/project/workspace`）。
- `dayu/config/README.md:189`：Fins read limits 十个默认值全部显式写入（`processor_cache_max_entries=128` 等）。
- `dayu/config/README.md:191`：Doc limits 五个默认值全部显式写入（`list_files_max=200` 等），`doc-tools.enabled=false` 保留。
- `dayu/config/README.md:209`：默认非上传 scene 使用显式工具名选择 Fins read/download/preprocess 工具，避免 broad `"fins"` tag 误选 upload；`tool_selection.allow_empty` 与 ToolsDiscovery provider 空输出语义分离说明。
- Grep 确认：`include_read_tools` 和 `allowed_upload_roots` 在 `dayu/config/README.md` 中零命中。

**Focus 3 — fins README: provider 契约同步**

- `dayu/fins/README.md:111`：read provider 入口描述更新为"启用时必须通过 effective spec 提供绝对 `workspace_root`"；"read provider 是否参与发现只由 provider-level `enabled` 控制"。
- `dayu/fins/README.md:133`：三个 awaiting provider 的 workspace_root 要求；upload provider 明确"当前实现不把本地源文件授权建模为 upload provider 的配置职责"。
- `dayu/fins/README.md:410`：Fins workspace 规则第一条明确"四个 Fins provider 的 effective spec 都必须提供非空绝对 `workspace_root`"。
- `dayu/fins/README.md:414`：明确"upload provider 不拥有本地源文件 allowlist 或授权配置"；"仓储写入边界仍属于 `dayu.fins.storage`"。
- `dayu/fins/README.md:442`："本地源文件授权不是 provider-owned config"。
- `dayu/fins/README.md:444`："四者都要求 effective spec 提供绝对 `workspace_root`"。
- `dayu/fins/README.md:667`："四个 Fins provider 都要求 effective spec 中存在绝对 `workspace_root`"；"本地源文件授权由调用方在 provider 外部承担"。

**Focus 4 — tests README: 覆盖描述与当前测试一致**

- `tests/README.md:124`：config loader 覆盖描述新增"packaged tool discovery 中 Fins `workspace_root="workspace/"`、显式 Doc / Fins limits、`doc-tools.enabled=false` 和旧 provider-level `allow_empty` 字段拒绝"——最后一项描述的是拒绝旧字段的测试，不是将旧字段作为当前行为。
- `tests/README.md:125`：CLI upload 覆盖从"allowlist 前置校验"改为"存在性 / 普通文件 / 非空前置校验"。
- `tests/README.md:128`：tools discovery 覆盖从"空工具输出 fail-fast"改为"启用 provider 空工具输出 fail-fast"，精确限定了 fail-fast 的触发条件。
- `tests/README.md:129`：assembly helpers 覆盖新增"Fins packaged relative `workspace/` 到 Service effective absolute `workspace_root` 的解析、raw provider config 不变性"。
- `tests/README.md:141`：Fins awaiting assembly 覆盖从"provider config"改为"effective provider config"，并新增"相对 workspace root 无运行时根"的 fail-fast 场景。
- `tests/README.md:159`：Fins 测试覆盖描述中"read provider 启用时要求显式绝对 workspace root"改为"四个 Fins provider 启用时要求 effective absolute workspace root"。

**Focus 5 — 无 process/gate/PR 状态泄漏**

- 对四个目标文件全文检索 Slice/WU-TOOLS/gateflow/controller/PR/pull request/review status 等过程性术语，命中结果均为：
  - `LaneController`（Host runtime 组件，非 gate 流程）
  - `PRAGMA user_version`（SQLite schema version，非 Pull Request）
  - `EXPLICIT_PROVIDER`（ToolBundleSourceKind 枚举值）
  - Fins `PROGRESS` / `RESULT`（FinsEvent 类型）
  - 以上均非过程/PR 状态泄漏。

**Focus 6 — Grep 分类**

- `allow_empty` 在四个目标文件中的命中分类：
  - `docs/host/design.md:107`：scene `tool_selection.allow_empty` 独立语义 ✓
  - `docs/host/design.md:2058`：明确 scene `tool_selection.allow_empty` 与 provider 空输出分离 ✓
  - `dayu/config/README.md:209`：scene `tool_selection.allow_empty` 独立语义说明 ✓
  - `tests/README.md:124`：旧 provider-level `allow_empty` 字段拒绝的测试覆盖说明 ✓
  - 四个命中均为正确用法，未将 `allow_empty` 描述为当前 provider-level 字段。
- `include_read_tools` 在四个目标文件中：零命中 ✓
- `allowed_upload_roots` 在四个目标文件中：零命中 ✓
- 全仓 grep 中 `allow_empty` / `include_read_tools` / `allowed_upload_roots` 的剩余命中全部属于：
  - scene manifest / ScenePrepare 选择语义（`allow_empty` 独立语义）
  - `ToolBundle._allow_empty` InitVar（框架内部 no-tool 构造）
  - compaction label helper / direct event 空字符串校验（自有语义，与 provider 无关）
  - 生产代码 / 测试代码中的当前正确实现
  - 历史 plan / review / archive / controller gate 文档

### 交叉一致性检查

| 事实 | design.md | config/README.md | fins/README.md | tests/README.md |
|---|---|---|---|---|
| provider-level allow_empty 已删除 | :99 字段列表无 allow_empty | :170-176 字段表无 allow_empty | 不适用（不描述 config schema） | :124 描述拒绝旧字段的测试 |
| enabled provider 空输出 = 配置错误 | :2058 明确说明 | :178 明确说明 | :111 只由 enabled 控制 | :128 "启用 provider 空工具输出 fail-fast" |
| scene allow_empty 独立 | :107, :2058 分离说明 | :209 分离说明 | 不适用 | 不适用（scene prepare 自有行） |
| Fins workspace_root 相对默认 → 绝对解析 | 不适用（不描述 packaged 默认值） | :180 完整说明 | :410-411 完整说明 | :129 assembly helpers 覆盖 |
| Doc/Fins limits 显式默认值 | 不适用 | :189, :191 显式列出 | 不适用 | :124 提及 |
| doc-tools.enabled=false | 不适用 | :191 保留 | 不适用 | :124 提及 |
| upload 授权非 provider-owned | 不适用 | :189 校验说明 | :133, :414, :442, :667 | 不适用 |
| storage 仓储边界 | 不适用 | :189 | :133, :414 | 不适用 |

所有关键事实在四个文档之间一致，无矛盾。

## Open Questions

无。

## Residual Risk

- `docs/host/issues-implementation-control.md` 仍包含 controller gate 更新与旧字段上下文命中；该文件是用户指定不修改的总控文档，其中的旧术语不作为当前稳定配置说明。若该文件被外部读者当作当前设计事实引用，可能产生误导。
- 历史 plan / review / archive 文档（`docs/host/host-core-implementation/`、`docs/reviews/` 等）仍保留旧语义记录；这些是历史材料，不构成当前活跃文档的污染。
- 本 Slice 仅涉及 Markdown 文档变更，未修改任何生产代码、测试代码或配置文件。pyright（0 errors, 0 warnings, 0 informations）通过。文档一致性验证依赖 grep/manual check，未运行 pytest。

## Verdict

**通过。** 四个目标文件的变更准确反映了 Slice 1-5 已实现的 schema 与边界语义，未发现 blocking findings（0 项）。文档间交叉一致，旧字段名（`allow_empty` 作为 provider-level 字段、`include_read_tools`、`allowed_upload_roots`）在活跃文档中已全部清除或仅作为"旧字段拒绝"的测试描述出现。无 process/gate/PR 状态泄漏。
