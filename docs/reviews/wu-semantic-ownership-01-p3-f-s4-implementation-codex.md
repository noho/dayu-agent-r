# WU-SEMANTIC-OWNERSHIP-01 P3-F S4 Implementation - AgentCodex

## 动机检查

S4 问题真实存在：上传链路原先只要发现既有 company meta 就直接保留，等价于把“文件存在”当成 freshness 真源。该语义会让旧 upload resolver 版本产生的公司身份、名称和 alias 长期覆盖当前上传参数；同时 `updated_at` 只是审计写入时间，不能表达 resolver 语义是否仍然有效。因此 freshness 必须落在 upload company metadata owner，而不能由 read runtime、下载链路或测试夹具补特例。

## Owner Boundary

- 产生事实：上传入口提供 ticker、company_name、ticker_aliases，`dayu.fins.pipelines.upload_company_meta` 通过 ticker normalization 和 `RESOLVER_VERSION` 生成 upload company identity。
- 校验事实：`upsert_company_meta_for_upload(...)` 负责判断既有 meta 是否 fresh；只有 `existing_meta.resolver_version == RESOLVER_VERSION` 时可复用。
- 持久化事实：`CompanyMetaRepositoryProtocol.upsert_company_meta(...)` 写入 `CompanyMeta`，`updated_at` 仅作为审计时间。
- 投影事实：read runtime 仍只通过 company repository 读取 `company_name` / `market`，不刷新、不推断 freshness。

SEC/CN/HK 下载路径仍由各自 producer 写入公司元数据，未接入 upload freshness helper。

## 行为变更

- `dayu/fins/pipelines/upload_company_meta.py`
  - 新增 `_existing_company_meta_is_fresh(...)`，以 `resolver_version` 判定既有 upload company meta 是否可保留。
  - 同版本既有 meta 保持原行为：保留仓储值，并在传入 company 参数时继续记录忽略告警。
  - 旧版本既有 meta 不再静默复用，会使用当前上传字段重新校验并 upsert。
  - 旧版本既有 meta 且缺少 `company_name` 时，走原 create/update 校验，返回同类失败信息，不复用 stale 数据。
- `dayu/fins/README.md`
  - 补充 upload company meta freshness owner、`updated_at` 非 TTL、下载路径和 read runtime 边界。

## 测试覆盖

- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
  - 覆盖同版本既有 meta 被保留，当前 company 参数被忽略。
  - 覆盖旧版本既有 meta 用当前上传字段刷新。
  - 覆盖旧版本既有 meta 且缺少 `company_name` 时失败关闭，并保留旧仓储值不被错误改写。
- `tests/fins/test_cn_pipeline.py`
  - 覆盖 CN upload facade 通过同一 upload owner helper 刷新旧版本 company meta。

## Propagation Audit

1. 上传请求进入 SEC/CN upload stream，ticker/company_name/ticker_aliases 只作为 upload company metadata helper 的输入。
2. `upsert_company_meta_for_upload(...)` 读取既有 repository meta，并以 `resolver_version` 判定 freshness。
3. fresh meta：不重写仓储，保留既有 CompanyMeta；stale/missing meta：用当前字段校验并写入 CompanyMeta，`resolver_version=RESOLVER_VERSION`。
4. upload workflow 后续 source/blob 写入继续使用既有仓储协议，不复制 freshness 规则。
5. `FinsReadRuntime._read_company_info(...)` 只读取 repository meta 的 `company_name` 和 `market`，没有 refresh、TTL 或 resolver 推断逻辑。
6. LLM-facing read 输出由 repository meta 派生；不会把 `updated_at`、resolver 版本或下载/上传内部治理状态暴露成财报事实。

## README 决策

命中 `dayu/fins/` 变更触发条件，且本次变更属于 Fins company meta owner 语义，因此更新 `dayu/fins/README.md`。`tests/README.md` 未更新：测试组织、测试职责和运行命令没有新增公共约定。

## 验证结果

- `source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q`
  - 结果：`24 passed, 3 warnings in 0.91s`
  - warning：现有 `edgar` 依赖 deprecation warning。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
  - 附带 pyright 新版本提示。
- `git diff --check`
  - 结果：通过，无输出。

## 未覆盖风险

- 未新增 read runtime 专项测试；当前代码证据显示 `FinsReadRuntime._read_company_info(...)` 只读 repository meta，不执行 refresh 或 freshness 推断。本次新增测试已覆盖 upload owner 写入边界。
- 未修改 SEC/CN/HK 下载路径；下载 producer-owned refresh 语义依赖既有覆盖继续守护。
- 当前 workspace 中 `docs/host/issues-implementation-control.md` 有进入本任务前已存在的修改，未由本次 S4 编辑；指定禁止触碰的 untracked 文件未修改。
