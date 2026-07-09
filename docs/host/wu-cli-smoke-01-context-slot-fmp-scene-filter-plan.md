# WU-CLI-SMOKE-01 Context Slot / FMP / Scene Tool Filtering Fixed Plan

## Gate 与结论

- Gate：plan fix
- Work unit：WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- Agent：AgentCodex
- Plan decision：ready after review fixes
- Slice count：3
- Stop condition：本 artifact 只修正 plan，不实现生产代码、不修改测试、不 commit、不 push、不创建 issue/PR。

## First-principles 判断

问题成立，严重性中高。根因不是单个 prompt 文案写错，而是三个装配边界没有同源闭环：

1. `ScenePrepare` 已拥有 scene manifest 解释权，但当前只做 `{{slot}}` 替换，随后才计算 `tool_selection`。`dayu/runtime/scene_prepare.py` 中 `prepare()` 先 `_render_fragment_content(...)`，再 `_select_tools(...)`；`dayu/config/prompts/base/tools.md` 中 `<when_tag ...>` 和 `<when_tool ...>` 当前只是普通文本。因此未选工具的指引会泄露给 LLM。
2. CLI 入口把 `--ticker` raw string 直接映射到 `context_slot_values["fins_default_subject"]`，且未传 ticker 时写入 `"未指定具体公司"`。直接证据在 `dayu/cli/commands/prompt.py`、`dayu/cli/commands/interactive.py`、`dayu/cli/commands/session.py`。这违反 LLM-facing 文本约束：模型应看到自解释业务文本，而不是裸 ticker 或内部默认占位。
3. OLD 仓库已有可复用 FMP 公司信息能力，但新仓 `dayu.fins` 没有 resolver public 子包。FMP 公司信息应是 Fins 业务能力；Service/CLI 只负责装配和 fallback，不应复制解析逻辑。

当前方案不是过度设计：只把已有 manifest 语义补成闭环，不引入 workflow、动态 tool profile、Host/Engine contract 变更或 durable schema；FMP 只迁移最小公司信息 public contract，不扩展为证券主数据系统。

## 当前代码事实与 checkpoint 同步

- `prompt.json` 当前 `tool_tags_any` 是 `["fins-read", "web", "utils"]`；checkpoint commit `2a61fbfd` 已移除 `fins-download` 与 `fins-preprocess`。
- 当前 prompt manifests 中不存在字面 tag `fins-upload`；不要安排 implementation agent 去移除不存在的 manifest tag。
- `start_fins_upload` provider 和工具实现仍存在，但 upload 暴露面本计划不扩大，除非用户后续单独裁决本地文件授权与路径安全 UX。
- `get_current_time` 工具实际 tags 是 `utils` 和 `time`；manifest 当前用 `"utils"` 选中它。`utils/time` 不是 manifest 字面 tag，只能作为说明“utils/time 工具能力”的自然语言缩写。
- 当前 `dayu/config/prompts/base/soul.md` 不含 `{{base_user}}`；不要把 `soul.md` 列为必须修改文件，除非 implementation 前重新核实到代码已变化。
- 当前 `base_user` 残留范围应以 `rg -n "base_user" dayu/config/prompts dayu/cli tests utils` 为准：12 个 manifests、3 个 CLI 模块、tests 和 `utils/smoke_host_public_multiturn.py`。

## 用户意图与成功信号

- `download` / `preprocess` 这类长事务工具只在 `interactive` / `wechat` 等多轮场景暴露；`prompt` 单轮场景不暴露，除非未来单轮 prompt 显式支持等待长事务完成。
- upload 暴露面不扩大；当前没有 manifest 字面 `fins-upload` tag 需要移除。
- 真实工具 `get_current_time` 只在 `prompt` / `interactive` / `wechat` 暴露。其它 scene 若需要当前时间，只通过 LLM-facing context slot 注入文本，slot 名为 `current_time`。
- `fins_default_subject` 在 `interactive` / `wechat` 不需要；其它需要默认主体的 scene 仍可使用。命令行传入 `--ticker` 时，不把 raw ticker 给模型，而是生成：
  - `# 当前分析对象\n你正在分析的是 V。`
  - 或 `# 当前分析对象\n你正在分析的是 V（Visa Inc.）。`
- 未传 `--ticker` 时 `fins_default_subject` 返回空字符串，并且渲染结果不能留下额外空行、空白标题或“未指定具体公司”。
- `<when_tool ...>` / `<when_tag ...>` 是 `ScenePrepare` 应解释的条件块；没有被当前 scene 选中的工具或标签，其说明不得进入 system prompt。
- `<when_tag TAG>` 的语义基于实际选中工具的 catalog tags，并且必须保留这种语义：如果 scene 通过显式工具名选中某个工具，该工具携带的 tags 也应让对应 `<when_tag>` block 生效。不要把 `selected_tags` 改成只来自 manifest `tool_tags_any`，否则显式工具选择会无法展示 tag-scoped 指引。
- `base/tools.md` 不能继续用粗粒度 `<when_tag fins>` 包住所有 Fins 指引。必须拆分为更细粒度 block，例如 `<when_tag fins-read>` 与 `<when_tag ingestion>`，或对长事务指引用 `<when_tool start_fins_download>` / `<when_tool start_fins_preprocess>` 精确包裹；确保 prompt scene 只选 `fins-read` 时不会看到 download/preprocess/upload 指引。RF-01 的真实防护点是 prompt asset discipline 和测试，而不是把 `selected_tags` 收窄成 manifest-only 语义。
- 准备出的 `system_prompt` 不包含任何 `<when_tag`、`</when_tag>`、`<when_tool`、`</when_tool>` marker。
- `base_user` 删除后的验证命令 `rg -n "base_user" dayu/config/prompts dayu/cli tests utils` 预期为零残留；若只剩非 LLM-facing 文档引用，必须在 implementation artifact 中逐条说明为什么不是投影给 LLM 的内容。

## 非目标与 Scope Boundary

非目标：

- 不修改 Host / Engine public contract，不修改 durable schema，不改 EventLog / wait / ToolRuntime 状态机。
- 不实现单轮 prompt 长事务等待完成能力。
- 不把 FMP resolver 做成工具，不让 LLM 直接调用 FMP。
- 不改 `dayu.fins.storage` 财报文档存取边界，不绕过仓储协议访问财报文档。
- 不把 `dayu.runtime` 变成业务 slot resolver；runtime 只能做层中立条件块过滤、placeholder 渲染和空 slot 行清理。
- 不为旧接口、旧测试或旧 prompt 保留兼容逻辑。

Scope boundary：

- 允许触及 prompt asset/manifest、runtime scene prepare、Service/CLI slot 装配、FMP resolver public contract、相关测试与 README。
- 工作区已有用户修改必须保留并在其基础上整合，不得覆盖或回滚。

## 推荐落点

### Scene 条件块过滤

落点：`dayu.runtime.scene_prepare`

理由：`ScenePrepare` 已是 manifest 和 prompt fragment 的解释者，且只需要 `SceneToolCatalog`、`tool_selection` 与选中工具结果即可做过滤，不需要业务包。实现不能 import `dayu.fins` / `dayu.service` / `dayu.host` / `dayu.engine` / `dayu.ui`。

实现路径：

- 不新增 public request 字段。
- 在 `ScenePrepare.prepare()` 中先完成 `_select_tools(...)`，得到 selected tool names。
- 在过滤函数内部遍历 `catalog.tools`，用 selected tool names 以及对应工具的 catalog tags 构建 `selected_tags: frozenset[str]`，不要为此新增不必要的 `SceneToolCatalog` public API。
- `selected_tags` 不得只取 manifest `tool_tags_any`：显式工具名选择、`mode=all` 或其它非 tag-selection 路径选中的工具，也必须贡献自身 catalog tags，保证 `<when_tag>` 表示“当前实际可用工具集合携带的标签”。
- 对每个 fragment 先执行条件块过滤，再执行 placeholder 替换，再执行空 slot 行清理。
- `PreparedSceneInputs` 继续输出过滤后的 `system_messages` / `system_prompt` / digest。

过滤规则：

- `<when_tool NAME>`：仅当 `NAME` 在本 scene selected tool names 中保留 block body。
- `<when_tag TAG>`：仅当 `TAG` 在 selected tools 按 catalog tags 聚合出的 `selected_tags` 中保留 block body；不要从 manifest `tool_tags_any` 单独派生该集合。
- `mode=all` 的 selected tools 是 catalog 全量；`mode=none` 是空集合；`mode=select` 是选择结果。
- 条件块不支持嵌套；未闭合、错配、空条件名或非法 marker 统一 `ScenePrepareError` fail closed。
- 未命中的 well-formed block 被整体删除，包括 marker 行。
- marker 是 prompt asset 控制语法，允许继续存在于 raw asset；marker 永远不得进入 prepared LLM-facing 输出。

`base/tools.md` 重构规则：

- read-only 财报工具指引用 `<when_tag fins-read>` 包裹。
- 长事务摄取指引用 `<when_tag ingestion>` 或更精确的 `<when_tool start_fins_download>` / `<when_tool start_fins_preprocess>` 包裹。
- 不使用 `<when_tag fins>` 包住同时覆盖 read 与 ingestion 的大段说明；当前 S1 应移除 `base/tools.md` 中混合 read 与 ingestion 语义的 broad `<when_tag fins>` block，优先让 raw asset 中不再出现这种混合用途 block。
- 如果 upload 指引当前没有任何 scene 选中，不得因为改 marker 而扩大 upload manifest 暴露面。

### 空 slot 行清理

落点：`dayu.runtime.scene_prepare` 的 generic placeholder render 路径。

执行顺序必须固定：

1. per-fragment 条件块过滤。
2. per-fragment placeholder 替换。
3. per-fragment 空 slot 行清理。
4. 丢弃内容经 `strip()` 后为空的 fragment。
5. 用 `"\n\n"` 拼接剩余 fragment。
6. 对最终 `system_prompt` 做空行归一：3 个及以上连续空行压缩为 2 个换行。

空 slot 行定义：

- 原始行去掉前后空白后完全匹配 `{{slot_name}}`。
- 该 slot 的替换值为 `""`。
- 命中时删除整行，允许行首或行尾存在空白。
- 若原始行包含其它文本，例如 `当前对象：{{fins_default_subject}}`，即使 slot 为空也不得删除整行，只做普通替换。
- 条件块过滤或 placeholder 替换后 fragment 全空时，该 fragment 不参与最终 join，避免额外分隔空行。

测试必须覆盖：fragment 全空、placeholder 行带前导空白、placeholder 行含其它文本且 slot 为空、条件块删除后产生多个空行。

### Service scene context slot assembly

落点：新增 `dayu.service.scene_context`。

理由：职责是 scene context slot assembly，不只服务 prompt scene；它消费 CLI / future UI 的业务输入、调用 Fins public resolver、返回 LLM-facing 文本。放在 CLI 会复制到 prompt / session / future UI；放在 runtime 会违反业务语义边界；放在 Host / Engine 是反向依赖。

推荐 public contract：

- `EntrypointContextSlotRequest`
  - `ticker: str | None`：用户入口传入的业务 ticker；用于生成 `fins_default_subject`。
  - `now: datetime | None`：测试或调用方提供的当前时间；为 `None` 时由 Service helper 使用当前 `Asia/Shanghai` 时间。
  - `fmp_api_key: str | None`：由 Service/CLI 装配层从环境变量或配置显式传入；Fins resolver 不隐式读 env。
  - `fmp_timeout_seconds: float`：FMP resolver 超时，Service slot path 默认必须小于等于 5 秒。
- `fins_default_subject(ticker: str | None, company_name: str | None = None) -> str`
- `current_time(now: datetime | None = None) -> str`
- `build_entrypoint_context_slot_values(request: EntrypointContextSlotRequest) -> dict[str, JsonValue]`

LLM-facing 文本格式：

- `fins_default_subject(None, ...)` 返回 `""`。
- 无公司名时：`# 当前分析对象\n你正在分析的是 V。`
- 有公司名时：`# 当前分析对象\n你正在分析的是 V（Visa Inc.）。`
- `current_time(...)` 返回中文可读文本，格式固定为 `# 当前时间\n现在是 2026年7月7日 15:08（Asia/Shanghai，星期二）。`
- `current_time` 使用 `Asia/Shanghai`、24 小时制、中文星期；不投影 ISO 字符串，不把当前时间伪装成财报事实或业务事实。

FMP 装配规则：

- 环境变量名称固定为 `FMP_API_KEY`，与 OLD 行为一致。
- 若新实现需要常量，应在合适的公共配置/契约位置新增 `FMP_API_KEY_ENV: Final[str] = "FMP_API_KEY"`，或在 Service 装配边界使用已有常量；不得在 `dayu.fins.resolver` 内部隐式读取环境变量。
- 未配置 key、FMP 慢、请求失败、JSON 异常或无结果时，Service slot path fallback 到 ticker-only subject，不向 LLM 暴露错误文本。
- FMP resolver timeout 必须可配置；Service slot path 默认短超时，小于等于 5 秒，避免 CLI 被 FMP 慢请求长时间阻塞。

### FMP public contract

落点：新增 `dayu.fins.resolver` 子包：

- `dayu/fins/resolver/__init__.py`
- `dayu/fins/resolver/fmp_company_info.py`

推荐 contract：

- `FmpCompanyInfo(canonical_ticker: str, company_name: str, ticker_aliases: tuple[str, ...])`
- `FmpCompanyInfoResolver(api_key: str, opener: FmpHttpClientProtocol | None = None, timeout_seconds: float = 5.0)`
- `resolve_company_info(canonical_ticker: str) -> FmpCompanyInfo`

实现从 OLD 迁移两跳算法：先 `search-symbol` 定位公司名，再 `search-name` 搜索严格同名证券，alias 去重且 canonical ticker 始终首位。OLD 的 `list[str]` 改为 `tuple[str, ...]`，原因是新 public contract 应为不可变输出，避免调用方修改 resolver 返回对象。新代码不得使用 `Any`；HTTP/JSON 解析使用明确 `JsonValue`、typed parser 或 Protocol。

## Affected Files / Modules

允许修改：

- `dayu/runtime/scene_prepare.py`
- `dayu/config/prompts/base/tools.md`
- `dayu/config/prompts/manifests/audit.json`
- `dayu/config/prompts/manifests/confirm.json`
- `dayu/config/prompts/manifests/decision.json`
- `dayu/config/prompts/manifests/fix.json`
- `dayu/config/prompts/manifests/interactive.json`
- `dayu/config/prompts/manifests/overview.json`
- `dayu/config/prompts/manifests/prompt.json`
- `dayu/config/prompts/manifests/regenerate.json`
- `dayu/config/prompts/manifests/repair.json`
- `dayu/config/prompts/manifests/smoke_host_public_multiturn.json`
- `dayu/config/prompts/manifests/wechat.json`
- `dayu/config/prompts/manifests/write.json`
- `dayu/config/prompts/scenes/*.md`
- `dayu/service/scene_context.py`
- `dayu/service/entrypoint_runtime.py`，仅用于接入 Service-side context slot builder 时的窄改
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py`
- `dayu/fins/resolver/*`
- `utils/smoke_host_public_multiturn.py`
- 相关 runtime/service/cli/fins 测试
- README 触发范围内的 `dayu/fins/README.md`、`dayu/config/README.md`、`tests/README.md`，必要时根 `README.md` 或 `dayu/README.md`

禁止修改：

- Host / Engine 状态机与 durable schema。
- Fins storage 仓储协议。
- `dayu/config/prompts/base/soul.md`，除非 implementation 前重新运行 grep 证明该文件已重新出现 `{{base_user}}` 或其它本 work unit 必须处理的 placeholder。

## Contract / Schema / Public Interface Changes

- 新增 Fins public contract 子包 `dayu.fins.resolver`；包根 `dayu.fins` 继续不 re-export 业务符号。
- `ScenePrepare` 支持 prompt asset 条件块语法。这是 scene assembly 行为变更，不是 manifest schema 变更。
- prompt manifests 中删除 stale `base_user` context slot。
- `fins_default_subject` 的语义从 raw ticker/default string 变为 LLM-facing Markdown contribution；空 ticker 返回空字符串。
- `current_time` 是 LLM-facing context slot 文本函数，不等同 `get_current_time` 工具结果；格式必须自解释。
- CLI `--ticker` 的 Host operation context / session slot identity 可继续使用 normalized business id；但 LLM-facing context slot 不得使用 raw ticker。

## Implementation Slices

### Slice S1：Scene 条件块过滤与 prompt 暴露面闭环

Objective：让 `ScenePrepare` 根据 selected tools/tags 过滤 `base/tools.md` 条件说明，并调整 prompt asset marker 粒度，使单轮 prompt 不暴露长事务工具指引。

Allowed files/modules：

- `dayu/runtime/scene_prepare.py`
- `dayu/config/prompts/base/tools.md`
- `dayu/config/prompts/manifests/prompt.json`
- `dayu/config/prompts/manifests/interactive.json`
- `dayu/config/prompts/manifests/wechat.json`
- `tests/runtime/test_scene_prepare.py`
- `tests/runtime/test_scene_tool_selection.py`
- `tests/runtime/test_scene_assets_migration.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`

Exact changes：

- 先计算 selected tool names，再构建 selected tags，并在 fragment render 前过滤 `<when_tool>` / `<when_tag>`。
- selected tags 来自实际 selected tool names 对应的 catalog tags，不只来自 manifest `tool_tags_any`；显式选中工具时同样必须让该工具 tags 对应的 `<when_tag>` block 生效。
- `base/tools.md` 拆分粗粒度 Fins 指引：read 指引用 `<when_tag fins-read>`；download/preprocess 指引用 `<when_tag ingestion>` 或精确 `<when_tool>`；不要让 `<when_tag fins>` 同时覆盖 read 与 ingestion，当前资产最好不再保留 broad `<when_tag fins>` block。
- `prompt.json` 当前已经没有 `fins-download` / `fins-preprocess`；S1 只验证并保护该状态，不安排删除不存在的 `fins-upload` manifest tag。
- `interactive.json`、`wechat.json` 保持多轮 download/preprocess 暴露面；upload 不扩大。
- raw asset marker 可继续存在作为控制语法；测试从“raw marker 存在”迁移或补充为“prepared output 不含 marker”。

Tests and validation：

```bash
source .venv/bin/activate
pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py
pytest tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py
```

Expected assertions：

- prompt selected tools 不包含 `start_fins_download` / `start_fins_preprocess` / `start_fins_upload`。
- prompt `system_prompt` 包含 read-only Fins 指引和 `get_current_time` 指引，但不包含 download/preprocess/upload 指引。
- prepared prompt output 不得因为 read-only 工具携带 broad `fins` tag 而泄露 download/preprocess/upload 等长事务指引。
- asset migration 测试应检查 `base/tools.md` 不再存在混合 read 与 ingestion 语义的 broad `<when_tag fins>` block；当前 S1 以不保留 `<when_tag fins>` block 为推荐验收形态。
- interactive/wechat selected tools 包含 download/preprocess 与 `get_current_time`；upload 只在已有选择真实命中时出现。
- 所有 prepared prompt 不包含 `<when_tag` / `<when_tool` / closing marker。
- malformed condition block fail closed。

Completion signal：S1 相关 tests 通过，且没有生产代码保留 Service 二次解释 prompt fragments。

Stop condition：如果条件块语法需要 manifest schema 新字段才能表达，停止并回到 design；当前证据看不需要。

### Slice S2：FMP resolver public contract 与 Service slot 文本生成

Objective：移植 OLD FMP 公司信息能力为 `dayu.fins.resolver` public contract，并把 `fins_default_subject` / `current_time` 生成收束到 `dayu.service.scene_context`。

Allowed files/modules：

- `dayu/fins/resolver/*`
- `dayu/service/scene_context.py`
- `dayu/service/entrypoint_runtime.py`
- `dayu/cli/commands/prompt.py`
- `dayu/cli/commands/interactive.py`
- `dayu/cli/commands/session.py`
- `utils/smoke_host_public_multiturn.py`
- `tests/fins/test_fmp_company_info_resolver.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/service/test_host_assembly.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`

Exact changes：

- 新增 `dayu.service.scene_context`，定义 `EntrypointContextSlotRequest` 和三个 public helper。
- CLI 不再手写 LLM-facing `context_slot_values` 细节；改为调用 Service scene context builder，或传入 typed request 由 Service builder 生成 slot values。
- `interactive` / `wechat` 不声明也不提供 `fins_default_subject`；session list/purge 这类只为打开 Host 的路径不再生成 stale subject/base_user。
- `base_user` 常量、slot name、测试期望全部删除。`display_user="本地 CLI 用户"` 可保留用于 Host call context，但不得进入 LLM slot。
- FMP resolver 接收显式 API key，不在 Fins 内部读 env。Service/CLI 装配层读取 `FMP_API_KEY` 并显式传入。
- FMP key 缺失、请求失败、超时或无结果时 fallback 到 ticker-only subject；失败不得投影给 LLM。
- FMP resolver 默认 timeout 和 Service slot path 默认 timeout 均应短，Service path 默认小于等于 5 秒。

Tests and validation：

```bash
source .venv/bin/activate
pytest tests/fins/test_fmp_company_info_resolver.py
pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_host_assembly.py
pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py
rg -n "base_user" dayu/config/prompts dayu/cli tests utils
```

Expected assertions：

- FMP resolver fake HTTP 测试覆盖 `V` 成功、严格同名过滤、alias 去重、HTTP/JSON 错误、无结果和 timeout。
- `FmpCompanyInfo("V", "Visa Inc.", ("V", ...))` 的 alias 是 tuple，不是 list。
- `prompt --ticker V` 捕获的 LLM-facing context slot 为 `"# 当前分析对象\n你正在分析的是 V（Visa Inc.）。"`；无 FMP 时为 `"# 当前分析对象\n你正在分析的是 V。"`。
- `prompt` 未传 ticker 时 `fins_default_subject == ""`，最终 `system_prompt` 无额外空行或“未指定具体公司”。
- `current_time` slot 文本符合 `# 当前时间\n现在是 2026年7月7日 15:08（Asia/Shanghai，星期二）。` 这类中文格式，不包含 ISO。
- `rg -n "base_user" dayu/config/prompts dayu/cli tests utils` 为零残留，或只剩明确非 LLM-facing 文档引用并在 artifact 中说明。

Completion signal：slot 文本生成只有一个 Service-facing 真源；CLI 测试不再期待 raw ticker 或 `base_user`。

Stop condition：如果当前配置没有承载 FMP key 的 schema 字段，不新增 schema；先用 env `FMP_API_KEY` 注入并记录为实现选择。不得让 FMP 慢请求阻塞 CLI 超过默认短超时。

### Slice S3：Prompt assets / manifests / docs / aggregate validation

Objective：把 prompt assets 与 manifests 对齐新 slot contract，补 README 判断与全量受影响验证。

Allowed files/modules：

- `dayu/config/prompts/manifests/*.json`
- `dayu/config/prompts/scenes/*.md`
- `dayu/config/README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- 必要时根 `README.md` 或 `dayu/README.md`
- 仅限修正 S1/S2 测试夹具的测试文件

Exact changes：

- `{{fins_default_subject}}` 只放在需要默认研究主体的 scene `.md` 中；当前至少 `scenes/prompt.md`。其它 scene 是否加入，以 scene 文本真实需要为准，不机械添加。
- `current_time` 不机械添加。若某个非 prompt/interactive/wechat scene 文本确实需要当前时间，则 manifest 声明 `current_time`，scene `.md` 放 `{{current_time}}`，Service builder 注入 LLM-facing 文本。
- 删除 12 个 manifests 中 stale `base_user` context slot：`audit`、`confirm`、`decision`、`fix`、`interactive`、`overview`、`prompt`、`regenerate`、`repair`、`smoke_host_public_multiturn`、`wechat`、`write`。
- 不修改 `base/soul.md`，除非 implementation 前 grep 发现当前事实变化。
- 更新 `dayu/fins/README.md`：新增 `dayu.fins.resolver` public contract 当前能力。不得写未来计划。
- 更新 `dayu/config/README.md`：说明条件块 marker 是 `ScenePrepare` 支持的 prompt asset 控制语法，且不会进入 LLM 输出；说明 manifest 使用 `"utils"` tag 选择 `get_current_time`。
- 更新 `tests/README.md`：记录 scene 条件过滤、FMP resolver、slot builder 和 `base_user` 删除验证边界。

Tests and validation：

```bash
source .venv/bin/activate
pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py
pytest tests/fins/test_fmp_company_info_resolver.py
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_host_assembly.py
pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py
pytest tests/runtime/test_smoke_host_public_multiturn_assembly.py
rg -n "base_user" dayu/config/prompts dayu/cli tests utils
pyright
git diff --check
```

Optional real smoke, if provider credentials are available:

```bash
source .venv/bin/activate
dayu-cli --log-level debug prompt --base workspace/tmp/wu-cli-smoke-context-slot --ticker V "现在是什么时间，并说明当前分析对象"
dayu-cli --log-level debug prompt --base workspace/tmp/wu-cli-smoke-context-slot-no-ticker "总结你能做什么"
```

Expected assertions：

- First smoke may call `get_current_time` and prompt text contains current subject contribution for `V`.
- Second smoke must not show “未指定具体公司”，and debug log must not show long transaction tool calls.
- `rg -n "base_user" dayu/config/prompts dayu/cli tests utils` 按 S2 预期通过。

Completion signal：affected tests、pyright、`git diff --check` 通过；README 触发项已裁决并更新。

Stop condition：如果 README 约束与代码事实冲突，先更新代码事实或停止回到 plan review，不写未来态文档。

## 验证矩阵

- Runtime scene filtering：`tests/runtime/test_scene_prepare.py`、`tests/runtime/test_scene_tool_selection.py`、`tests/runtime/test_scene_assets_migration.py`
- Service assembly / entrypoint：`tests/service/test_entrypoint_runtime*.py`、`tests/service/test_host_assembly.py`
- CLI context slots：`tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py`、`tests/cli/test_session_command.py`
- Smoke helper：`tests/runtime/test_smoke_host_public_multiturn_assembly.py`、`utils/smoke_host_public_multiturn.py`
- FMP public contract：`tests/fins/test_fmp_company_info_resolver.py`
- Static：`pyright`
- Text hygiene：`rg -n "base_user" dayu/config/prompts dayu/cli tests utils`
- Whitespace：`git diff --check`

## README / Docs 更新判断

- 修改 `dayu/fins/` 会触发 `dayu/fins/README.md`：需要新增 resolver public contract 当前能力。
- 修改 `dayu/config/` 会触发 `dayu/config/README.md`：需要先读其 Agent 更新约束，再按职责说明 condition block 与 slot 约定。
- 修改 `tests/` 会触发 `tests/README.md`：需要按职责说明新增测试边界。
- 若 CLI 用户可见 `--ticker` 行为说明已有 README 文档，根 README 需要检查；只有当前 README 职责范围包含该行为时才更新。
- 本计划不改变 UI / Service / Host / Engine 分层关系；若实现过程中只是新增 Service helper，不需要更新 `dayu/README.md`，除非现有 README 已列出 Service composition root 细节且会变 stale。

## Risks / Open Questions

- FMP API 配额/rate-limit 或网络慢：Service slot path 默认短超时，小于等于 5 秒；失败 fallback 到 ticker-only subject，不向 LLM 暴露错误。
- upload 多轮暴露面：本计划不扩大 upload，避免意外授权本地文件上传路径；如要暴露 upload，需要用户单独裁决本地文件授权与路径安全 UX。
- 条件块语法兼容：marker 从“旧残留”重新定义为 `ScenePrepare` 支持的 prompt asset 控制语法，并用 prepared output 不泄露 marker 作为验收。
- 空 slot 行清理可能影响其它 placeholder。实现必须只删除“原始行只包含 placeholder/空白且替换后为空”的行，不得全局 strip 用户文本。
- 真实 FMP/LLM smoke 依赖外部 key 与网络，不能作为 CI 必需项；自动测试必须用 fake HTTP client / monkeypatch 覆盖。

## Completion Report Format

Implementation / review closeout 应包含：

- artifact path
- changed files
- accepted findings fixed
- rejected findings and reasons
- validation commands and results
- docs updates
- residual risks / uncovered areas
- no commit / no push confirmation unless用户另行授权
