# AAPL 下载与 canonical ticker 布局：Slice 2 实施记录

## 目标

把文件系统仓储的 ticker locator 恢复为 `portfolio/<canonical ticker>`，同时保留
document ID 的 opaque private locator，并验证 `list_documents` 与其余八个 Fins
read tools 仍只通过仓储协议读取。

## 语义 owner

- ticker 归一化唯一真源：`dayu.fins.ticker_normalization`。
- ticker 物理布局与 descriptor 双向校验：
  `dayu.fins.storage._fs_identity`。
- ticker 变体及公司 alias 到已发布 canonical ticker 的解析：
  `dayu.fins.storage._fs_company_meta_core`。
- read tools 的输入归一化与业务输出：
  `dayu.fins.tools.read_runtime`；本切片未在该下游增加 fallback。

## 实施

- ticker namespace 的 storage locator key 改为已校验的 canonical ticker。
- storage mutation/read 边界拒绝小写、市场后缀、公司名和路径形态等非 canonical
  ticker；不会在仓储层静默改写。
- filing/material/processed/rejected document namespace 继续使用 namespace-separated
  SHA-256 private locator。
- `resolve_existing_ticker` 仅把 ticker 真源可识别的候选用于直接目录 lookup；
  无法识别的公司 alias 继续走已发布公司元数据 alias 索引。
- fresh schema 下不读取、迁移或删除旧 `portfolio/id-*` 目录。
- README 同步说明 canonical ticker 布局、document private locator 与读取工具的
  non-leak 边界。

## Read tools 影响验证

- `list_documents` 新增 `aapl.us` 与 `apple` 集成用例，均解析到
  `portfolio/AAPL` 并返回 canonical `AAPL` 公司事实。
- 九个 read tools 的 completed / failed / cancelled 投影全部回归：
  canonical ticker 是允许公开的业务值；revision、document private key、
  local URI、workspace path 与 snapshot temp path 仍不得泄漏。
- read tools、processor 和 service runtime 未直接拼接 `portfolio` 或依赖
  `id-*` 目录名；访问继续经过 company/source/processed 仓储协议。

## 验证

- `pytest -q tests/fins/test_fins_storage_provider.py tests/fins/test_fins_storage_atomicity.py`
  ：247 passed。
- `pytest -q tests/fins`：1015 passed，1 skipped。
- 新增 `list_documents` variant/alias 用例：2 passed。
- `python -m pyright dayu/ tests/ utils/`：0 errors。
- 受影响生产文件 coverage：
  - `sec_filing_collection.py`：97%
  - `_fs_company_meta_core.py`：91%
  - `_fs_identity.py`：82%

## 已知边界

- 这是按项目 schema 约束执行的 fresh-layout 变更；已有 `portfolio/id-*` 数据不会
  自动迁移，也不会被本实现删除。
- SEC live 下载的网络行为不纳入 deterministic pytest；Slice 1 已用真实故障
  accession 的 provider payload 形态覆盖 `primaryDocument` 投影。
