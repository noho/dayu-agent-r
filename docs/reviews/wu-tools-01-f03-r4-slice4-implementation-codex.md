# WU-TOOLS-01-F03-R4 Slice 4 Implementation Artifact

## 范围

本次只实施 Slice 4：删除 Fins upload provider / upload tool 的本地文件 allowlist 限制，恢复 packaged upload provider 默认注册，并调整默认 scene 工具选择，避免 broad Fins tag 误选 `start_fins_upload`。

未修改 `docs/host/issues-implementation-control.md`，未提交，未 push，未做 code review。

## 改动

- `dayu/fins/tools/upload_provider.py`
  - 删除 `allowed_upload_roots` 配置解析、空 allowlist 返回空工具集分支、相关常量和 `__all__` 导出。
  - `discover_tools(...)` 现在只解析 effective absolute `workspace_root`，创建 `DefaultFinsRuntime`，并始终返回 `build_fins_upload_tool(ingestion_runtime)`。
- `dayu/fins/tools/upload_tools.py`
  - 删除 `FinsUploadToolCallable.allowed_upload_roots` 和 `build_fins_upload_tool(..., allowed_upload_roots=...)` 参数。
  - `_upload_request_from_arguments(...)` 与 `_upload_files_from_arguments(...)` 不再接收 allowlist。
  - 用 `_resolve_upload_file_path(raw_path: str) -> Path` 替代 allowlist resolver：只做 expand、resolve、存在、普通文件、非空校验。
  - 更新 `files` LLM-facing schema 描述，去除 configured upload roots 文案。
- `dayu/config/tool_discovery.json`
  - `financial-upload-tools.enabled` 恢复为 `true`。
  - 未重新引入 `allowed_upload_roots`。
- `dayu/config/prompts/manifests/*.json`
  - 当前默认非上传 Fins scene 不再用 broad `"fins"` tag。
  - 对 Fins read/download/preprocess 工具使用显式 `tool_names`；需要 Web 的 scene 保留 `"web"` tag。
  - 未修改 `tool_selection.allow_empty`。
- 测试
  - 更新 upload callable/provider 构造。
  - 删除空 allowlist provider 返回空工具集、相对 allowlist fail-fast、路径越界失败预期。
  - 增加缺失文件、目录、空文件校验，以及 workspace 外本地文件可启动 upload observation 且源目录无治理状态副作用的覆盖。
  - 增加默认 manifest 通过 `ScenePrepare` 后不选中 `start_fins_upload`，但仍选中 Fins read/download/preprocess 与 Web 工具的断言。
  - 更新 packaged upload 默认启用和 combined tools 工具数/source refs 断言。
- README
  - 按触发规则最小同步 `dayu/config/README.md`、`dayu/fins/README.md`、`tests/README.md` 中与本 Slice 直接冲突的旧 upload allowlist / 默认不注册上传工具描述。

## 验证

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q`
  - 47 passed，3 个第三方 `edgar` deprecation warnings。
- `source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`
  - 38 passed，3 个第三方 `edgar` deprecation warnings。
- `source .venv/bin/activate && pytest tests/tools/test_combined_tools_acceptance.py -q`
  - 8 passed，3 个第三方 `edgar` deprecation warnings。
- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py -q`
  - 41 passed。
- `source .venv/bin/activate && pyright dayu tests utils`
  - 0 errors，0 warnings，0 informations。
- `rg -n "allowed_upload_roots|_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD|parse_allowed_upload_roots_config" dayu tests utils`
  - 仅剩 `tests/runtime/test_config_loader.py` 中对 `allowed_upload_roots` 不存在于 packaged upload config 的反向断言。
- `git diff --check`
  - 无输出。

## Config / README 决策

- `financial-upload-tools` 默认启用是本 Slice 的目标，不再用 provider config 表达本地文件读取 allowlist。
- 默认 scene 不引入 exclude 语义；因为 `ScenePrepare` 当前只做显式工具名与 tag 命中的并集，所以用显式 `tool_names` 表达默认 Fins read/download/preprocess 能力。
- README 只同步当前代码事实，不扩写 work unit 过程、测试清单以外的新文档内容。

## 残留风险

- 本 Slice 不实现 Host policy、sandbox 或统一本地文件授权；upload tool 只做输入文件形态校验。
- 新增的 workspace 外文件成功测试覆盖 observation 启动边界与源目录无治理状态副作用，不执行真实 Docling upload conversion；真实 repository 写入边界仍由既有 Fins upload pipeline / storage 测试覆盖。
