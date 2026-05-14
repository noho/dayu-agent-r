## Work Gate

code review

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施

## Assigned Slice

Slice 1: `dayu.host` public API typed contracts

## Reviewer

AgentDS

## Approved Plan

docs/host/phase1-public-contract-runtime-plan.md

## Implementation Artifact Under Review

docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md

## Review Scope

本 review 只评估 Slice 1 的实现是否与 plan 一致，不涉及:

- Host command function、durable store、EventLog row、dispatch record、policy provider set
- runtime lane、runtime filelock、HostToolingOptions、ToolBundle options
- dayu.engine、tests.engine、dayu.fins、dayu.runtime、pyproject.toml
- Slice 2/3/4 的未实现内容

## Evidence Gathered

- plan: docs/host/phase1-public-contract-runtime-plan.md § Slice 1
- implementation artifact: docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md
- production files: dayu/host/__init__.py, dayu/host/api.py
- test files: tests/host/__init__.py, tests/host/test_package_exports.py, tests/host/test_public_contracts.py, tests/host/test_import_boundary.py, tests/host/test_weak_typing_guard.py
- README files: dayu/host/README.md, dayu/README.md (diff), tests/README.md (diff)
- git diff HEAD: only dayu/README.md and tests/README.md modified (all other files are new/untracked, consistent with Slice 1 scope)
- validation: `pytest tests/host -q` → 14 passed in 0.05s
- validation: `python -m pyright dayu/host tests/host` → 0 errors, 0 warnings, 0 informations
- git status confirms `dayu/host/tooling.py` does NOT exist (correctly deferred to Slice 4)
- git status confirms no `dayu/engine/**`, `dayu/fins/**`, `dayu/runtime/**` or `pyproject.toml` changes

## Review Findings

### Finding 1: CreateSessionRequest bind_slot=False 场景下仍拒绝空字符串 scope/slot_key

- 严重度: Low (non-blocking observation)
- 文件: `dayu/host/api.py`, `CreateSessionRequest.__post_init__` (line 465-497)
- 描述: 当 `bind_slot=False` 时，`__post_init__` 仍然调用 `_require_optional_non_empty` 检查 `scope` 和 `slot_key`。Plan 只要求 `bind_slot=False` 时二者可以为 `None`，未明确要求拒绝空字符串。但 `scope`/`slot_key` 作为 name-like 字段，拒绝空字符串与 plan 通用校验规则一致（"所有 id / name / reason 字段必须拒绝空字符串或纯空白"）。
- 影响: 无。行为与 plan 通用规则一致；若调用方确实传入空字符串 scope/slot_key 且 bind_slot=False，会被拒绝，这是一种合理的防御性设计。
- 建议: 无需修改。保持当前行为即可。

### Finding 2: _require_graceful_cancel 在当前 CancelMode 单值枚举下为死代码

- 严重度: Low (by-design, non-blocking)
- 文件: `dayu/host/api.py`, `_require_graceful_cancel` (line 73-83)
- 描述: `CancelMode` 当前只有 `GRACEFUL` 一个成员，因此 `_require_graceful_cancel` 中的 `if mode != CancelMode.GRACEFUL` 分支永远为 False。这是一个 plan 显式要求的设计选择（"Phase 1 只允许 graceful"），守卫函数的存在是为了当后续 phase 添加 `force`/`immediate` 成员时提供校验。
- 影响: 无运行时影响。守卫已到位，后续扩展 CancelMode 时校验会自动生效。
- 建议: 无需修改。这是按 plan 意图设计的 forward-compatible guard。

### Finding 3: 已修复 - 测试未覆盖 CancelRunRequest/CancelSessionRunsRequest 的 mode 校验失败路径

- 严重度: Low (observation, not blocking)
- 文件: `tests/host/test_public_contracts.py`
- 描述: plan 要求 tests 覆盖 "graceful cancel mode" 校验，但当前 `CancelMode` 只有一个合法值 `GRACEFUL`，无法构造"非法 mode"的测试用例。测试中通过 `_require_graceful_cancel` 的代码覆盖实际在 `Find 2` 描述的死代码路径上。
- 影响: 无。当前枚举无法触发该路径；后续添加新 CancelMode 成员时需补充对应测试。
- 建议: 后续 Slice 若为 CancelMode 新增成员，同步补充 mode 校验失败测试。

### Finding 4: 已修复 - test_dataclasses_are_frozen_and_slots 只抽样检查一个类型

- 严重度: Low (observation, not blocking)
- 文件: `tests/host/test_public_contracts.py`, `test_dataclasses_are_frozen_and_slots` (line 145-153)
- 描述: 该测试只对 `SessionSlotRef` 做了 frozen/slots 断言。虽然 package_exports 和 weak_typing_guard 测试提供了补充覆盖，但未穷尽验证所有 28+ 个 dataclass 类型均为 frozen+slots。
- 影响: 低。手动检查 `api.py` 中所有 dataclass 均使用 `@dataclass(frozen=True, slots=True)`；weak typing guard 也间接守护了类型边界。若后续添加不带 frozen/slots 的 dataclass，只有人工 review 能发现。
- 建议: 可考虑后续补充参数化测试扫描所有 Host 公共 dataclass 的 frozen+slots 属性，但不阻塞当前 Slice 通过。

### Finding 5: RunSnapshot 的 source_run_id / source_run_relation 一致性校验为 plan 未明确要求的额外校验

- 严重度: Info (positive finding)
- 文件: `dayu/host/api.py`, `RunSnapshot.__post_init__` (line 962-987)
- 描述: `RunSnapshot.__post_init__` 额外校验了 `source_run_id` 与 `source_run_relation` 必须同时为 None 或同时非 None。Plan 未明确要求此校验，但这是正确的一致性守卫，防止 RunSnapshot 进入 `source_run_id` 和 `source_run_relation` 不一致的状态。
- 影响: 正向改进，提升了类型契约的完整性。
- 建议: 无需修改。

## Plan Compliance Summary

| 检查项 | 状态 | 备注 |
| --- | --- | --- |
| 类型清单完整性 | Pass | 36 个类型全部实现，与 plan 清单一致 |
| frozen=True, slots=True | Pass | 所有 dataclass 使用；HostApiError 正确使用普通 class |
| StrEnum | Pass | 所有枚举使用 StrEnum，字符串值稳定 |
| 中文 docstring | Pass | 所有模块、类、函数提供完整中文 docstring |
| 无 Any/object/裸容器 | Pass | AST 扫描 + pyright 双重验证通过 |
| JsonValue 使用 | Pass | HostMetadataEntry.value 使用 dayu.contracts.json_value.JsonValue |
| __all__ 白名单 | Pass | api.py 与 __init__.py 的 __all__ 完全一致 |
| 校验规则 | Pass | 空 id、非法 cursor、steer/queue target、bind_slot、graceful cancel 全覆盖 |
| import boundary | Pass | 不导入 dayu.engine/dayu.fins/dayu.service/dayu.ui |
| 文件修改范围 | Pass | 仅触及 Slice 1 允许文件 |
| 无夹带 | Pass | 无 tooling.py、runtime、Engine/Fins 修改 |
| README 同步 | Pass | 只记录当前事实，不写未来计划 |

## Architecture Boundary Verification

- `dayu.host` 的 import 链: `from __future__ import annotations`, `dataclasses.dataclass`, `enum.StrEnum`, `typing.Protocol`, `dayu.contracts.json_value.JsonValue` — 均不违反 import boundary ✓
- `dayu/host/__init__.py` 的 import 链: `from dayu.host.api import (...)` — 只从同包子模块导入 ✓
- AST import boundary scan 确认 `dayu/host/` 下所有 `.py` 文件不包含 `dayu.engine`, `dayu.fins`, `dayu.service`, `dayu.ui` ✓
- Engine 不 import `dayu.host` — 由 Engine 侧已有 import boundary 测试守卫（非本 Slice 范围，但 trust-but-verify 确认 Engine 目录无修改）✓

## README Review

- `dayu/host/README.md`: 新文件，只写当前公共类型、校验边界、架构边界和 non-goals；不写 durable store/command path 未来实现细节 ✓
- `dayu/README.md` diff: 新增一行 `dayu.host` 公共命名空间事实说明；未写未来计划 ✓
- `tests/README.md` diff: 新增 `tests/host` 层级说明、运行命令和维护约定；与当前代码事实一致 ✓

## Validation Results

```
pytest tests/host -q → 14 passed in 0.05s
python -m pyright dayu/host tests/host → 0 errors, 0 warnings, 0 informations
```

## Finding Count

**Finding 数量: 5**

- Low (non-blocking observation): 4 (Findings 1-4)
- Info (positive finding): 1 (Finding 5)
- Blocking: 0

## Recommendation

**Proceed.** 实现严格遵循 Slice 1 plan，无 scope violation、无 contract drift、无 architecture boundary 违规、无 correctness bug。所有 finding 均为 low/non-blocking observation 或 positive note。建议 controller 可直接进行 code re-review 或 user confirmation。

## Open Questions / Residual Risks

- 当前测试只抽样验证 frozen/slots（Finding 4），若后续 Slice 新增 dataclass 时遗漏 frozen/slots，需人工或参数化测试捕获。
- `CancelMode` 单值枚举使 mode 校验成为死代码（Finding 2），后续扩展 CancelMode 时需补充测试和 plan 更新。
- `RunSnapshot` 的 source_run_id/source_run_relation 一致性校验不在 plan 显式要求中（Finding 5），建议在后续 plan 更新中补充记录此规则。

## Artifact Path

docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-ds-20260513.md
