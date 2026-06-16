# WU-CLI-FINS-OBS-01 Slice D0 Code Review

## 基本信息

- Reviewer：AgentMiMo
- 日期：2026-06-16
- 结论：**PASS**
- Scope：D0 lightweight observation handle contract-only checkpoint
- Plan 真源：`docs/host/wu-cli-fins-obs-01-replacement-plan.md`
- Implementation artifact：`docs/reviews/wu-cli-fins-obs-01-slice-d0-implementation-codex.md`

## 验证

| 验证项 | 结果 |
|---|---|
| `pytest tests/fins/test_fins_ingestion_tools.py -q` | 47 passed, 3 warnings（edgar deprecation） |
| `pyright dayu/fins/ingestion/observation_handle.py dayu/fins/ingestion/__init__.py tests/fins/test_fins_ingestion_tools.py` | 0 errors, 0 warnings |
| `pyright dayu/ tests/`（全量） | 0 errors, 0 warnings |

## Review Checklist

### 1. 是否只定义 contract，不实现 registry/runtime/wait adapter，不删除旧 job store

**PASS**

- `observation_handle.py` 只定义 `dataclass`、`Enum`、`Protocol`、纯函数。没有 registry 实例、没有 `__init__` 注册逻辑、没有 process-local store。
- `__init__.py` 只新增 re-export，不改已有符号。
- `test_fins_ingestion_tools.py` 只新增 contract-level 断言。
- `ingestion_runtime.py`、`wait_adapter.py`、tool helpers 均未修改。
- 旧 job store / sidecar 未被删除或降级。

### 2. handle/token 是否不含 job id、sequence、cursor、storage path；corrupt token / missing process-local observation source 能分类 LOST

**PASS**

- `FINS_OBSERVATION_HANDLE_ID_PREFIX = "finsobs_"`，正则 `[a-z0-9]{16,96}`。
- `_DISALLOWED_TOKEN_FRAGMENTS` 包含 `job`、`sequence`、`cursor`、`resume`、`token`、`tool_call`、`storage`、`.dayu`、`/`、`\\`。
- `_validate_handle_id` 在 `FinsObservationHandle.__post_init__` 和 `observation_handle_id_to_resume_token` / `parse_observation_handle_id_token` 中都被调用。
- resume token 等于 handle id，不含额外 metadata。
- `PERMANENT_CORRUPT_HANDLE` 和 `PERMANENT_NOT_FOUND` 都映射到 `FinsObservationResolutionKind.LOST`。
- 测试覆盖了 corrupt token → `ValueError` + LOST 映射，以及 missing observation source → LOST。

### 3. 状态到 wait resolution 的中立映射是否固定且不导入 Host

**PASS**

- `FinsObservationResolutionKind` 是独立 enum，不导入 `dayu.host`。
- `observation_status_resolution_kind` 和 `observation_poll_error_resolution_kind` 是纯函数、确定性 if-chain。
- `observation_handle.py` 只导入 `dayu.contracts.cancellation.CancellationToken`、`dayu.fins.direct_events`、`dayu.fins.ingestion_runtime`（request types）；无 Host 导入。
- 6 种 status → 5 种 resolution 的映射表在测试中固定覆盖。

### 4. 是否违反 AGENTS.md 类型/docstring/分层/README 规则

**PASS**

- 每个函数和类都有中文 docstring，包含 `:param`、`:returns`、`:raises`。
- 模块有概览 docstring。
- 类型签名完整，无 `object`、`Any` 或无类型参数。
- 分层正确：`observation_handle.py` 在 `dayu.fins.ingestion` 内，只依赖 `dayu.contracts` 和 `dayu.fins`，不反向依赖 Host/Engine/Service/UI。
- `tests/README.md` 已更新，记录了新增 observation handle contract 测试。
- `dayu/fins/README.md` 按 plan 约定留给 Slice E 统一清理。

### 5. 是否需要新增 residual risk

**不需要新增**。现有 `WU-CLI-FINS-OBS-01-R7`（D0 review gate）和 `WU-CLI-FINS-OBS-01-R8`（process-local registry 并发安全）已覆盖 D0 相关 residual。

## Findings

无 blocking findings。以下为 nonblocking 观察：

### F-NB-01：message 禁止片段测试只覆盖 `cursor` + `/`

- 文件：`tests/fins/test_fins_ingestion_tools.py:250-257`
- 严重度：nonblocking
- 说明：`test_observation_contract_rejects_job_cursor_and_storage_text` 只测试了 message 包含 `cursor /tmp/fins evidence missing` 的场景。`_validate_message` 也拒绝 `job`、`sequence`、`storage` 等片段，但没有独立 message 级断言。handle id 侧的禁止片段覆盖更完整。由于 `_validate_handle_id` 和 `_validate_message` 共用 `_DISALLOWED_TOKEN_FRAGMENTS`，且 handle id 测试已充分覆盖该列表，风险低。
- 是否阻塞：否

### F-NB-02：`observation_handle.py` 通过 request types 导入耦合 `ingestion_runtime`

- 文件：`dayu/fins/ingestion/observation_handle.py:24-28`
- 严重度：nonblocking
- 说明：contract module 导入 `FinsDownloadRequest` / `FinsPreprocessRequest` / `FinsUploadRequest`，这些类型目前定义在 `ingestion_runtime.py`。该导入方向是 `fins.ingestion` → `fins.ingestion_runtime`，不违反分层。但 Slice C 重构 `ingestion_runtime` 时需注意这些 request types 的归属稳定性。
- 是否阻塞：否

## 结论

D0 实现严格遵守 contract-only checkpoint 范围：只定义 handle/status/snapshot/token/resolution 映射契约，不实现 registry、runtime、wait adapter，不删除旧 job store。handle/token 不含 job/cursor/path 语义，corrupt/missing 场景正确分类 LOST，状态映射固定且不导入 Host。类型、docstring、分层、README 规则均合规。验证通过（47 passed, pyright 0 errors）。无需新增 residual risk。

**结论：PASS。**

---

## Follow-up Review（DS-D0-01 fix + residual 裁决）

- 日期：2026-06-16
- 触发：DS-D0-01 finding fix、R7 closed、R9 新增
- Fix artifact：`docs/reviews/wu-cli-fins-obs-01-slice-d0-review-fix-codex.md`
- 结论：**PASS**

### DS-D0-01 fix 核对

**已正确修正。**

- `_HANDLE_ID_PATTERN` 从 `[a-z0-9]` 收敛为 `[a-f0-9]`（`observation_handle.py:37`）。hex-only 字符集消除了 `_DISALLOWED_TOKEN_FRAGMENTS` 与全字母表之间的张力：`job`(`j∉[a-f]`)、`cursor`(`u∉[a-f]`)、`sequence`(`q/s/u` 部分不在 hex 集合中但 `e/c` 在；不过 `qu` 连续出现使完整词不可能匹配 `[a-f0-9]{16,96}`）等英文词无法通过正则。`_DISALLOWED_TOKEN_FRAGMENTS` 作为 defense-in-depth 保留，仍能拦截 `storage`(`a`/`e`/`g`→`g∉hex`，不匹配)、`deadbeef` 等纯 hex 英文片段。
- `_HANDLE_ID_MIN_RANDOM_CHARS` 已重命名为 `_HANDLE_ID_MIN_HEX_CHARS`（`observation_handle.py:33`）。
- 测试新增 `finsobs_gggggggggggggggg`（`g∉[a-f0-9]`）作为 corrupt token 参数（`test_fins_ingestion_tools.py:149`），覆盖 non-hex 字符拒绝。
- 测试从 47 passed 增至 48 passed；pyright 0 errors。

### Residual 裁决核对

**R7 closed 合理。** 关闭依据是 D0 review 确认 implementation 保持 contract-only、未扩大为 runtime/wait adapter implementation。该依据与本次 review 事实一致。

**R9 新增合理。** R9 追踪 Slice D 的两项必要覆盖：
1. bounded retry / max wait 保护：当前 contract 只定义 `TRANSIENT_UNAVAILABLE -> PENDING`，不约束重试次数或总等待时间。Slice D wait adapter 必须实现 bounded loop，防止无限 poll。
2. corrupt resume token → LOST 端到端覆盖：当前 contract 层已验证 `parse_observation_handle_id_token` 对 corrupt token 抛 `ValueError`，但 wait adapter 从 durable wait record 读取 resume token 后的 try/except → LOST resolve 路径尚未有 E2E 测试。

R9 的 owner（Slice D implementation and review gates）和 scope（retry guard + corrupt-token E2E）与 plan 的 Slice D 步骤一致，不扩大 D0 contract-only 范围。

### 新增阻塞检查

**无新增阻塞。** hex-only 收敛是纯收紧变更，不改变已有合法 handle 格式（`[a-f0-9] ⊂ [a-z0-9]`），不影响 Slice A/B 已通过的测试或接口。R9 的 scope 明确限于 Slice D，不阻塞 D0 closeout。

### Follow-up 结论

DS-D0-01 已正确修正，R7 closed / R9 新增的 residual 裁决合理，无新增阻塞。

**Follow-up 结论：PASS。**
