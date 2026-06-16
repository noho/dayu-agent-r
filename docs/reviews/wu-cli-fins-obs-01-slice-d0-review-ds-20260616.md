# WU-CLI-FINS-OBS-01 Slice D0 Code Review — AgentDS

## 审查范围

- **Plan 真源**: `docs/host/wu-cli-fins-obs-01-replacement-plan.md` Slice D0
- **控制文档**: `docs/host/issues-implementation-control.md`
- **Implementation artifact**: `docs/reviews/wu-cli-fins-obs-01-slice-d0-implementation-codex.md`
- **审查对象**: diff HEAD 未提交改动 + 新增 `dayu/fins/ingestion/observation_handle.py`

## 改动概览

| 文件 | 类型 | 行数 |
|---|---|---|
| `dayu/fins/ingestion/observation_handle.py` | 新增 | 371 |
| `dayu/fins/ingestion/__init__.py` | 修改 | +26/-2 |
| `tests/fins/test_fins_ingestion_tools.py` | 修改 | +200 |
| `tests/README.md` | 修改 | +2 |

## 验证结果

| 命令 | 结果 |
|---|---|
| `pytest tests/fins/test_fins_ingestion_tools.py -q` | 47 passed, 3 warnings (edgar deprecation) |
| `pyright dayu/fins/ingestion/observation_handle.py dayu/fins/ingestion/__init__.py tests/fins/test_fins_ingestion_tools.py` | 0 errors, 0 warnings |

## 逐项核对

### 1. 是否只定义 contract，不实现 registry/runtime/wait adapter，不删除旧 job store

**结论: PASS**

证据：

- `observation_handle.py` 仅定义 `FinsObservationHandle` (dataclass), `FinsObservationStatus` (enum), `FinsObservationPollErrorKind` (enum), `FinsObservationResolutionKind` (enum), `FinsObservationSnapshot` (dataclass), `FinsObservationRuntime` (Protocol) — 全部是类型/契约定义。
- `FinsObservationRuntime` 所有方法体均为 `...` (Protocol stub)，不含实现。
- 未定义任何 registry、poller、wait adapter 实现类（`rg` 验证：`class.*Registry\|class.*Poller\|class.*Adapter\|class.*Store` 无命中）。
- 未定义任何 process-local dict/list 存储 handle。
- diff 未触及 `dayu/fins/ingestion_runtime.py`、`dayu/fins/ingestion/wait_adapter.py`、`dayu/fins/tools/`、`dayu/service/host_assembly.py`。
- 旧 job store 路径 `<workspace_root>/.dayu/fins_ingestion/jobs/<job_id>.json` 未修改、未删除。
- `observation_handle.py` 不含任何 "job_store"、"job_id"、"sidecar"、"events.jsonl"、"read_job_events"、"request_cancel" 引用。

### 2. handle/token 是否不含 job id、sequence、cursor、storage path，并且 corrupt token / missing process-local observation source 能分类 LOST

**结论: PASS**

证据：

- `FinsObservationHandle` 字段: `handle_id`, `operation_kind`, `created_at` — 无 `job_id`、`sequence`、`cursor`、`storage_path` 字段（`observation_handle.py:83-94`）。
- `_DISALLOWED_TOKEN_FRAGMENTS` 包含 `"job"`, `"sequence"`, `"cursor"`, `"resume"`, `"token"`, `"tool_call"`, `"storage"`, `".dayu"`, `"/"`, `"\\"` (`observation_handle.py:40-51`)。
- `parse_observation_handle_id_token` 校验 token 格式及禁止文本，非法 token 抛出 `ValueError` (`observation_handle.py:243-253`)。
- corrupt token → LOST: 测试覆盖 `observation_poll_error_resolution_kind(PERMANENT_CORRUPT_HANDLE) is LOST` (`tests/fins/test_fins_ingestion_tools.py:147-167`) — 各类 corrup token（空字符串、错误前缀、含 "job"/"cursor" 子串、含路径分隔符）均被 `parse_observation_handle_id_token` 以 `ValueError` 拒绝。
- missing observation → LOST: 测试覆盖 `observation_poll_error_resolution_kind(PERMANENT_NOT_FOUND) is LOST` (`tests/fins/test_fins_ingestion_tools.py:170-180`)。
- token 只承载 opaque `finsobs_...` handle id: `observation_handle_id_to_resume_token` 返回 `handle_id` 字符串，不含其他字段 (`observation_handle.py:231-240`)。

**注意**: Finding DS-D0-01（见下文）指出 `_DISALLOWED_TOKEN_FRAGMENTS` 在 handle_id 校验中可能对合法随机字符串产生误判，但这不是 contract 缺陷，而是实现生成器需注意的约束。

### 3. 状态到 wait resolution 的中立映射是否固定且不导入 Host

**结论: PASS**

证据：

- `observation_handle.py` 未导入任何 `dayu.host` 或 `dayu.service` 模块（`rg` 验证：无命中）。
- `FinsObservationResolutionKind` 是 Fins 层内定义的中立 enum，不依赖 Host wait outcome 类型 (`observation_handle.py:73-80`)。
- `observation_status_resolution_kind` 映射固定：
  - `PENDING` / `RUNNING` → `PENDING`
  - `SUCCEEDED` → `COMPLETED`
  - `FAILED` → `FAILED`
  - `CANCELLED` → `CANCELLED`
  - `LOST` → `LOST` (`observation_handle.py:256-274`)
- `observation_poll_error_resolution_kind` 映射固定：
  - `TRANSIENT_UNAVAILABLE` → `PENDING`
  - `PERMANENT_NOT_FOUND` → `LOST`
  - `PERMANENT_CORRUPT_HANDLE` → `LOST` (`observation_handle.py:277-289`)
- 测试覆盖所有 6 种 observation status → resolution kind 映射 (`tests/fins/test_fins_ingestion_tools.py:183-195`)。
- 映射函数是纯函数，不导入外部状态、不依赖 Host registry。

### 4. AGENTS.md 类型/docstring/分层/README 规则

**结论: PASS**

类型规则：

- 所有函数/方法有完整类型标注，无 `object`、`Any`、无类型参数。
- `FinsObservationHandle` / `FinsObservationSnapshot` 使用 `@dataclass(frozen=True, slots=True)` 冻结不可变。
- `FinsObservationRuntime` 是 `Protocol` 类，方法签名完整标注。
- `__post_init__` 方法有返回类型 `-> None`。

docstring 规则：

- 模块有完整中文概览 docstring (`observation_handle.py:1-7`)。
- 所有 class、function 有完整中文 docstring，含参数、返回值、异常说明。
- `FinsObservationSnapshot.__post_init__` 有完整 docstring (`observation_handle.py:126-131`)。
- 私有辅助函数 `_validate_handle_id`、`_validate_aware_datetime`、`_validate_message`、`_validate_retry_after` 均有完整中文 docstring。

分层规则：

- `observation_handle.py` 仅导入 `dayu.contracts.cancellation`（跨层契约）、`dayu.fins.direct_events`（Slice A 契约）、`dayu.fins.ingestion_runtime`（请求类型）—— 全部在 Fins 层或更底层。
- 未导入 `dayu.host`、`dayu.service`、`dayu.engine`、`dayu.ui`。
- `FinsObservationResolutionKind` 是层中立分类，不在 Host 层定义——属于 plan 要求的 "不导入 Host" 语义。
- `__init__.py` 的重新导出是向 `__all__` 增加新符号，不是 compatibility re-export。

README 规则：

- `tests/README.md` 已更新，新增 observation handle contract 测试事实 (`tests/README.md:179`)。
- `dayu/fins/README.md` 已按 plan 检查，实际编辑集中在 Slice E——符合 plan 规定。
- Implementation artifact (`docs/reviews/wu-cli-fins-obs-01-slice-d0-implementation-codex.md:46-51`) 记录了 README impact assessment。

**注意**: Finding DS-D0-02（见下文）指出 `observation_handle.py:23-28` 对 `ingestion_runtime.py` 请求类型的依赖随 Slice C 演变需注意同步。

### 5. 是否需要新增 residual risk

**结论: 是，以下新增 residual risks 需追踪**

见 Findings 汇总表。

---

## Findings

### DS-D0-01: `_DISALLOWED_TOKEN_FRAGMENTS` 在 handle_id 校验中存在合法随机字符串误判风险

- **文件**: `dayu/fins/ingestion/observation_handle.py:40-51`，`_validate_handle_id` at line 292
- **严重度**: LOW
- **是否阻塞**: 否（非阻塞，contract 本身正确）

`_HANDLE_ID_PATTERN` 允许 `finsobs_[a-z0-9]{16,96}` 的随机部分使用全字母表。`_DISALLOWED_TOKEN_FRAGMENTS` 中的 `"job"`, `"token"`, `"storage"`, `"resume"`, `"sequence"`, `"cursor"` 都是有效 `[a-z0-9]` 子串。如果 handle 生成器使用 full `[a-z0-9]` alphabet（而非 hex-only `[a-f0-9]`），随机生成的 handle id 有非零概率包含这些子串，导致合法 handle 被 `ValueError` 拒绝。

实际操作中，若生成器使用 `uuid.uuid4().hex` 或 `secrets.token_hex()`（仅 `[a-f0-9]`），这些禁止子串均不可能出现（`j`, `u`, `q`, `m`, `t`, `o`, `k`, `g` 均非 hex 字符）。但 contract 层面未声明生成 alphabet 约束。

**建议**: 在 Slice C/D 实现 registry handle 生成器时，在代码注释中明确说明必须使用 hex-only alphabet 以避免校验误判；或在 contract 中收敛 `_HANDLE_ID_PATTERN` 为 `[a-f0-9]` 以消除歧义。

### DS-D0-02: `FinsObservationRuntime` Protocol 依赖 `ingestion_runtime` 请求类型

- **文件**: `dayu/fins/ingestion/observation_handle.py:23-28`
- **严重度**: LOW
- **是否阻塞**: 否（非阻塞，依赖的是稳定 dataclass 类型）

`FinsObservationRuntime` protocol 从 `dayu.fins.ingestion_runtime` import `FinsDownloadRequest`、`FinsPreprocessRequest`、`FinsUploadRequest` 作为方法签名参数类型。这三个类型是在 Slice C 允许修改范围内的模块。如果 Slice C 重构这些请求类型（例如拆分为 direct-stream 版本与 observed 版本），D0 protocol 需要同步调整。

当前这三个类型是简单 dataclass/union，语义稳定，且 plan 未要求 Slice C 修改 request types。风险低但需在 Slice C 实现时确认兼容性。

**建议**: Slice C 实现前重新核对 D0 protocol 仍兼容当前 `FinsDownloadRequest` / `FinsPreprocessRequest` / `FinsUploadRequest` 定义。若类型变化，在 D0 module 同步更新 type reference。

### DS-D0-03: `TRANSIENT_UNAVAILABLE → PENDING` 映射无最大重试/超时 guard

- **文件**: `dayu/fins/ingestion/observation_handle.py:287-288`
- **严重度**: LOW
- **是否阻塞**: 否（非阻塞，重试策略属于 wait adapter 实现层）

`observation_poll_error_resolution_kind` 将 `TRANSIENT_UNAVAILABLE` 无条件映射为 `PENDING`。如果 observation source 持续返回 transient unavailable（例如底层存储暂时不可用但长时间未恢复），wait adapter 会无限保持 pending 并重试。

Plan 已明确 "retry policy belongs to wait adapter implementation (Slice D)"，当前 contract 映射本身正确。Risk 在于 Slice D 实现 wait adapter 时如果忽略 max retry / max wait 保护，生产环境中可能产生永不 resolve 的 wait record。

**建议**: 将此 risk 记录在 control doc 的 residual risk 表中，owner 为 Slice D implementation gate。

### DS-D0-04: `test_observation_handle_corrupt_token_maps_to_lost` 测试结构混合同一 test body 的两个独立 contract 证明

- **文件**: `tests/fins/test_fins_ingestion_tools.py:147-167`
- **严重度**: LOW
- **是否阻塞**: 否（非阻塞，两个 contract 元素均覆盖正确）

当前测试在一个 parametrized test body 中同时验证：
1. `parse_observation_handle_id_token(corrupt_token)` 抛出 `ValueError`
2. `observation_poll_error_resolution_kind(PERMANENT_CORRUPT_HANDLE) is LOST`

两者之间未建立因果连接：test 没有证明 "corrupt token 被解析后映射为 PERMANENT_CORRUPT_HANDLE，再映射为 LOST"。当前是两个独立断言的并置。正确覆盖此因果链需要 wait adapter 集成测试，属于 Slice D 范围。当前断言各自正确，不算遗漏。

**建议**: Slice D 实现 wait adapter 时补充 corrupt token 到 LOST 的端到端集成测试。

---

## 总体结论

**PASS-WITH-FINDINGS**

### 通过项

| 检查项 | 结论 |
|---|---|
| 只定义 contract，不实现 registry/runtime/wait adapter | PASS |
| 不删除/不修改旧 job store | PASS |
| handle/token 不含 job id/sequence/cursor/storage path | PASS |
| corrupt token 可分类 LOST | PASS |
| missing process-local observation source 可分类 LOST | PASS |
| 状态到 wait resolution 映射固定 | PASS |
| 映射函数不导入 Host | PASS |
| 类型标注完整，无 Any/object/untyped | PASS |
| 中文 docstring 完整 | PASS |
| 分层依赖无反向依赖 | PASS |
| README impact assessment 已记录 | PASS |
| pytest 47 passed | PASS |
| pyright 0 errors | PASS |

### Findings 汇总

| ID | 文件:行号 | 严重度 | 阻塞 | 描述 |
|---|---|---|---|---|
| DS-D0-01 | `observation_handle.py:40-51` | LOW | 否 | `_DISALLOWED_TOKEN_FRAGMENTS` 在 full `[a-z0-9]` alphabet 存在合法 handle 误判风险；hex-only 生成可规避 |
| DS-D0-02 | `observation_handle.py:23-28` | LOW | 否 | Protocol 依赖 `ingestion_runtime` request types，Slice C 重构时需同步核对 |
| DS-D0-03 | `observation_handle.py:287-288` | LOW | 否 | `TRANSIENT_UNAVAILABLE → PENDING` 无 max retry guard，wait adapter 实现需保护 |
| DS-D0-04 | `tests/fins/test_fins_ingestion_tools.py:147-167` | LOW | 否 | corrupt token test 与 LOST 映射 test 未建立因果链，Slice D 需补端到端测试 |

### 新增 Residual Risks

| ID | 状态 | 描述 | Owner |
|---|---|---|---|
| WU-CLI-FINS-OBS-01-D0-R1 | open | handle ID 生成 alphabet 约束未在 contract 中声明；若生成器使用 full `[a-z0-9]`，`_DISALLOWED_TOKEN_FRAGMENTS` 可能误判 | Slice C/D implementation gate |
| WU-CLI-FINS-OBS-01-D0-R2 | open | `TRANSIENT_UNAVAILABLE → PENDING` 映射需在 wait adapter 实现中补充 max retry / max wait 边界保护 | Slice D wait adapter implementation gate |

### 已有 Residual Risks 状态更新

| ID | 更新 |
|---|---|
| WU-CLI-FINS-OBS-01-R7 (Slice D0 review gate) | 本轮审查确认 D0 未扩大成 runtime/wait adapter implementation；R7 可标记为 `closed` |
| WU-CLI-FINS-OBS-01-R8 (concurrency safety) | 不在 D0 范围；R8 保持 `open`，owner 为 Slice C/D |

---

## 附录: 完整核对清单

### plan Slice D0 实施步骤 vs 实现状态

| 步骤 | 状态 |
|---|---|
| 1. 定义 `FinsObservationHandle` / `FinsObservationStatus` / `FinsObservationPollErrorKind` / `FinsObservationSnapshot` / `FinsObservationRuntime` protocol | ✅ |
| 2. `ToolAwaitSpec.resume_token` 只承载 opaque handle_id；corrupt token 映射 LOST | ✅ |
| 3. 默认 observation source 是 process-local；Host restart / runtime crash 后找不到 handle 时 resolve LOST；不得无限重试 | ✅ (contract 层明确；实现层在 Slice C/D) |
| 4. contract 注释和测试明确：CLI direct 不消费 handle，Service direct API 不返回 handle，handle 不包含 job id/sequence/cursor/storage path | ✅ |
| 5. 未触发 durable mini-design 停止条件 | ✅ |

### plan Slice D0 停止条件 vs 实现状态

| 停止条件 | 状态 |
|---|---|
| 如果当前 Host wait recovery requirement 要求跨重启继续等待 → 未触发 | ✅ |
| 如果 handle contract 需要改 Host wait record schema → 未触发 | ✅ |

### plan Slice D0 预期测试 vs 实现覆盖

| 测试 | 状态 |
|---|---|
| handle token 解析成功 / corrupt token → LOST 分类 | ✅ `test_observation_handle_resume_token_is_opaque_handle_id`, `test_observation_handle_corrupt_token_maps_to_lost` |
| process-local observation source 找不到 handle → LOST 分类 | ✅ `test_process_local_missing_observation_maps_to_lost` |
| `FinsObservationSnapshot` terminal status → completed/failed/cancelled/lost 映射表固定 | ✅ `test_observation_status_resolution_mapping_is_fixed` |
| contract 不允许把 job id/sequence/cursor/storage path 放进 LLM-facing wait description | ✅ `test_observation_contract_rejects_job_cursor_and_storage_text` |
| snapshot terminal / retry-after 字段组合校验 | ✅ `test_observation_snapshot_terminal_and_retry_after_contract` |

### AGENTS.md 硬约束核对

| 约束 | 状态 |
|---|---|
| 禁止使用 `object` / `Any` / 无类型参数 / 无类型返回值 | ✅ |
| 禁止兼容性 re-export / wrapper | ✅ |
| 函数必须提供完整中文 docstring | ✅ |
| 禁止反向依赖 | ✅ (no Host/Service/Engine imports) |
| 禁止 god object/function/dataclass | ✅ |
| 禁止 hasattr/getattr 滥用 | ✅ (未使用) |
| 禁止魔法数字/字符串 | ✅ (常量命名清晰) |
| 禁止无必要的嵌套函数 | ✅ |
| 优先级优先使用模块级私有辅助函数 | ✅ (`_validate_*` 函数均为模块级私有) |
| 模块间依赖最小化 | ✅ (仅 3 个必要 import) |

---

## Follow-up: DS-D0-01 Fix 与 Residual Risk 裁决核对 (2026-06-16)

### 审查范围

- Fix artifact: `docs/reviews/wu-cli-fins-obs-01-slice-d0-review-fix-codex.md`
- 只核对 DS-D0-01 修正、R7/R9 裁决、是否引入新阻塞。

### DS-D0-01 修正验证

**改动** (`observation_handle.py:33-39`):

- `_HANDLE_ID_PATTERN` 从 `[a-z0-9]` 收敛为 `[a-f0-9]`
- `_HANDLE_ID_MIN_RANDOM_CHARS` 改名为 `_HANDLE_ID_MIN_HEX_CHARS`

**正确性分析**:

| 检查 | 结果 |
|---|---|
| hex-only `[a-f0-9]` 禁止 `j`, `g`, `m`, `o`, `q`, `t`, `u`, `k` 等非 hex 字符 | ✅ |
| `_DISALLOWED_TOKEN_FRAGMENTS` 全部禁止子串均不可出现在 hex 字符串中 (`"job"` 含 `j`, `"cursor"` 含 `u`, `"sequence"` 含 `q`/`u`, `"resume"` 含 `m`/`u`, `"token"` 含 `t`/`o`/`k`, `"storage"` 含 `t`/`o`/`g`) | ✅ |
| `_validate_handle_id` 中 `_DISALLOWED_TOKEN_FRAGMENTS` 检查降级为纯 defense-in-depth——hex pattern 已在 regex 层排除全部禁止子串 | ✅ |
| `_validate_message` 中的禁止片段检查不受影响（message 无字符集约束） | ✅ |

**测试覆盖**:

- 新增 corrupt token parametrize case: `f"{FINS_OBSERVATION_HANDLE_ID_PREFIX}gggggggggggggggg"` — 非 hex 字符 `g` 导致 pattern mismatch → `ValueError` ✅
- 测试从 47 passed → 48 passed ✅

**验证通过**: `pytest tests/fins/test_fins_ingestion_tools.py -q` 48 passed; `pyright` 0 errors.

### Residual Risk 裁决核对

| ID | 旧状态 | 新状态 | 裁决 | 合理性 |
|---|---|---|---|---|
| R7 (D0 scope guard) | open | **closed** | D0 review 已确认 contract-only，未扩大成 runtime/wait adapter implementation | ✅ 合理：双方 review (MiMo + DS) 均确认 D0 scope 合规 |
| R9 (retry guard + E2E LOST) | — | **open** | 新增，owner 为 Slice D | ✅ 合理：DS-D0-03 (TRANSIENT_UNAVAILABLE retry) 与 DS-D0-04 (corrupt token → LOST E2E) 确属 Slice D wait adapter 实现范围 |

**R9 描述**: "D0 only fixed neutral `TRANSIENT_UNAVAILABLE -> PENDING` and corrupt-token/missing-handle LOST mapping. Slice D wait adapter implementation must add bounded retry / max wait protection for repeated transient unavailable and end-to-end corrupt resume token -> LOST coverage."

该描述准确捕获 DS-D0-03 和 DS-D0-04 的实质——contract 映射本身正确，但 wait adapter 实现层需补充保护。owner 正确指向 Slice D。 ✅

### 未引入新阻塞

| 潜在风险 | 判断 |
|---|---|
| hex-only 收敛是否过于严格？ | 否：16^16 ≈ 1.8×10^19 空间远大于实际需求，hex 是 industry standard (UUID, secrets.token_hex) |
| pattern 变更是否影响已有测试？ | 否：测试 handle `"finsobs_aaaaaaaaaaaaaaaa"` 使用 `a`，在 hex 范围内 |
| `_DISALLOWED_TOKEN_FRAGMENTS` 在 `_validate_handle_id` 中是否冗余？ | 是，但作为 defense-in-depth 保留合理——万一日后有人改 pattern 放宽字符集，禁止片段检查作为第二道防线仍然生效 |
| 控制文档更新是否一致？ | R7 closed 理由与 review 结论一致；R9 描述精确，不扩大 D0 scope |

### Follow-up 结论

**PASS**

DS-D0-01 已通过 hex-only `[a-f0-9]` 收敛正确修正，非 hex token 拒绝测试已追加，residual risk R7/R9 裁决合理，未引入新阻塞 finding。

### Findings 状态更新

| ID | 原结论 | Follow-up 后 |
|---|---|---|
| DS-D0-01 (handle ID forbidden fragment 误判风险) | LOW, 非阻塞 | **已修正** (hex-only pattern + non-hex token test) |
| DS-D0-02 (Protocol 依赖 ingestion_runtime types) | LOW, 非阻塞 | 不变；由既有 R6 追踪 |
| DS-D0-03 (TRANSIENT_UNAVAILABLE 无 retry guard) | LOW, 非阻塞 | 不变；转由 R9 追踪 |
| DS-D0-04 (corrupt token test 未建因果链) | LOW, 非阻塞 | 不变；转由 R9 追踪（E2E 覆盖） |
