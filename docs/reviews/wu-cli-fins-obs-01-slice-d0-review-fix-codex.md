# WU-CLI-FINS-OBS-01 Slice D0 Review Fix

## 范围

- Slice：D0 lightweight observation handle contract-only checkpoint
- Review artifacts：
  - `docs/reviews/wu-cli-fins-obs-01-slice-d0-review-mimo-20260616.md`
  - `docs/reviews/wu-cli-fins-obs-01-slice-d0-review-ds-20260616.md`

## 裁决

### Accepted and Fixed

- DS-D0-01：`_HANDLE_ID_PATTERN` 允许 full `[a-z0-9]`，但 `_DISALLOWED_TOKEN_FRAGMENTS` 禁止 `job` / `token` / `cursor` 等英文片段，未来随机生成器若使用全字母表可能误伤合法 handle。已把 handle id 收敛为 hex-only `[a-f0-9]`，并新增 non-hex token 拒绝测试。

### Accepted as Residual

- DS-D0-03 / DS-D0-04：D0 只固定 `TRANSIENT_UNAVAILABLE -> PENDING` 与 corrupt-token / missing-handle 到 LOST 的 contract 分类。Slice D wait adapter implementation 必须补 bounded retry / max wait 保护，并补 corrupt resume token -> LOST 的端到端测试。已记录为 `WU-CLI-FINS-OBS-01-R9`。

### Deferred Without New Risk

- DS-D0-02 / MiMo F-NB-02：`FinsObservationRuntime` 依赖当前 `FinsDownloadRequest` / `FinsPreprocessRequest` / `FinsUploadRequest` 类型。该风险由既有 `WU-CLI-FINS-OBS-01-R6` 的 Slice A/C shared runtime boundary 追踪，不新增 residual。
- MiMo F-NB-01：message 禁止片段测试覆盖不如 handle id 侧细。当前 contract 共享同一禁止片段集合，且已有 message 包含 `cursor` 与 path 的负向测试；不阻塞 D0。

## 修改

- `dayu/fins/ingestion/observation_handle.py`
  - `_HANDLE_ID_PATTERN` 从 `[a-z0-9]` 收敛为 `[a-f0-9]`。
  - `_HANDLE_ID_MIN_RANDOM_CHARS` 改名为 `_HANDLE_ID_MIN_HEX_CHARS`。
- `tests/fins/test_fins_ingestion_tools.py`
  - corrupt token 参数增加非 hex handle id。
- `docs/host/issues-implementation-control.md`
  - `WU-CLI-FINS-OBS-01-R7` 标记 closed。
  - 新增 `WU-CLI-FINS-OBS-01-R9` 追踪 Slice D 的 retry guard 与 corrupt-token 端到端 LOST 覆盖。

## 验证

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q`
  - 48 passed，3 条第三方 `edgar` deprecation warning。
- `source .venv/bin/activate && pyright dayu/fins/ingestion/observation_handle.py dayu/fins/ingestion/__init__.py tests/fins/test_fins_ingestion_tools.py`
  - 0 errors，0 warnings。
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`
  - 103 passed，3 条第三方 `edgar` deprecation warning。
- `source .venv/bin/activate && pyright dayu/ tests/ utils/`
  - 0 errors，0 warnings。
- `git diff --check`
  - clean。
