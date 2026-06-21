# WU-TOOLS-01-F03-R4 Slice 6 documentation/design synchronization

## 动机判断

问题真实存在。直接证据是 `docs/host/design.md` 仍把 provider-level `allow_empty` 作为 `tool_discovery.json` 当前字段，并描述 enabled provider 空输出可由 `allow_empty=true` 放行；这已经和当前实现不一致。当前实现中 provider 是否参与发现由 `enabled` 控制，enabled provider 返回空工具集合是配置错误；scene `tool_selection.allow_empty` 是独立的 scene 工具选择空匹配语义。

## README 更新约束读取

- `dayu/config/README.md`：未定义独立 Agent 更新约束；已读取开头职责边界，仅说明当前默认配置、workspace 覆盖关系和 prompts 目录职责。
- `dayu/fins/README.md`：已读取 `Agent更新约束【必须遵守】`；本文档只写当前已实现的 Fins package 能力、边界和稳定机制，不写 work unit 过程。
- `tests/README.md`：已读取开头职责边界；测试事实以当前代码和测试目录为准。
- `dayu/README.md`：已读取 `Agent更新约束【必须遵守】`；当前总览文本没有与本 Slice 新事实产生实质冲突，未修改。
- 根 `README.md`：已读取 `Agent更新约束【必须遵守】`；未发现用户可见配置示例或工作流仍描述旧 provider allowlist / limits 字段，未修改。

## 修改内容

- `docs/host/design.md`
  - 从 `tool_discovery.json` provider 字段摘要中移除 provider-level `allow_empty`。
  - 将 ToolsDiscovery empty provider 语义改为：enabled provider 空输出是配置错误；禁用 provider 使用 `enabled=false`；scene `tool_selection.allow_empty` 只控制 scene 选择空匹配。

- `dayu/config/README.md`
  - 明确 enabled provider 空输出是配置错误，禁用 provider 使用 `enabled=false`。
  - 明确 packaged Fins `workspace_root="workspace/"` 是相对默认值，Service effective config 会相对 runtime workspace root 解析为绝对 Fins workspace root。
  - 明确 packaged Fins read limits 和 Doc limits 的默认值。
  - 保留 `doc-tools.enabled=false` 当前事实，并说明 enabled Doc provider 需要显式 `allowed_paths`。
  - 增加默认非上传 scene 不再使用 broad `"fins"` tag 选择 Fins 工具的说明，避免默认注册 upload provider 后误选 `start_fins_upload`。

- `dayu/fins/README.md`
  - 明确 read / download / preprocess / upload 四个 Fins provider 都要求 effective absolute `workspace_root`。
  - 删除旧 read provider 二级开关语义，只保留 provider-level `enabled`。
  - 明确 upload provider 不拥有本地源文件 allowlist 或授权配置；当前只在工具边界校验存在、普通文件和非空，本地文件来源可信性由调用方在 provider 外部承担。
  - 明确财报 source/blob/processed 写入仍必须通过 `dayu.fins.storage` 仓储协议。

- `tests/README.md`
  - 将 CLI upload 覆盖说明从 allowlist 前置校验改为存在性 / 普通文件 / 非空前置校验。
  - 更新 config loader、ToolsDiscovery、Service assembly helper、Fins awaiting assembly 和 Fins provider 覆盖描述，包含旧 `allow_empty` 拒绝、packaged `workspace/` 相对默认值、Service effective absolute 解析、Doc/Fins limits 和四个 Fins provider absolute workspace root 要求。

未修改 `docs/host/issues-implementation-control.md`，也未修改 scene manifest、生产代码、测试代码、`dayu/README.md` 或根 `README.md`。

## 验证

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`

- grep / manual check:
  - `rg -n "allow_empty|include_read_tools|allowed_upload_roots" docs/host/design.md dayu/config/README.md dayu/fins/README.md tests/README.md dayu/README.md README.md`
  - 活跃 README / design 剩余命中分类：
    - `docs/host/design.md`：scene `tool_selection.allow_empty` 独立语义；ToolsDiscovery 段落明确不允许 provider 空输出。
    - `dayu/config/README.md`：scene `tool_selection.allow_empty` 独立语义说明。
    - `tests/README.md`：旧 provider-level `allow_empty` 字段拒绝的测试覆盖说明。
  - `include_read_tools` / `allowed_upload_roots` 在上述活跃 README / design 中无命中。

- 全仓 grep 剩余命中分类：
  - `allow_empty`：scene manifest / ScenePrepare 选择语义、`ToolBundle._allow_empty` 内部 no-tool 构造、compaction label helper、direct event 空字符串校验、负向测试、历史 plan / review / archive / controller gate 文档。
  - `include_read_tools`：历史 plan / review / archive / controller gate 文档。
  - `allowed_upload_roots`：`tests/runtime/test_config_loader.py` 负向断言确认 packaged upload config 不包含该字段；其余为历史 plan / review / archive / controller gate 文档。

未运行 pytest。此次只修改 Markdown 文档和 review artifact，未修改 fixtures、manifest、生产代码或测试代码；本 Slice 的必要验证是 pyright 与 grep/manual check。

## 残留风险

- `docs/host/issues-implementation-control.md` 仍有 controller gate 更新和旧字段上下文命中；该文件是用户指定不要修改的总控文档，本次未触碰。
- 历史 plan / review / archive 文档仍保留旧语义记录；这些是历史材料，不作为当前稳定配置说明。
