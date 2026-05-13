## Work Gate

implementation

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施

## Assigned Slice

Slice 1: `dayu.host` public API typed contracts

## Approved Plan

docs/host/phase1-public-contract-runtime-plan.md

## Assigned Scope

- allowed files/modules:
  - `dayu/host/__init__.py`
  - `dayu/host/api.py`
  - `tests/host/__init__.py`
  - `tests/host/test_package_exports.py`
  - `tests/host/test_public_contracts.py`
  - `tests/host/test_import_boundary.py`
  - `tests/host/test_weak_typing_guard.py`
  - `dayu/host/README.md`
  - `dayu/README.md`
  - `tests/README.md`
  - `docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md`
- explicit non-goals:
  - 不实现 Host command function。
  - 不创建 durable store、EventLog row、dispatch record、policy provider set。
  - 不实现 runtime lane、runtime filelock、HostToolingOptions 或 ToolBundle options。
  - 不导入 Engine / Fins / Service / UI。
  - 不修改 `dayu/engine`、`tests/engine`、`dayu/fins`、`dayu/runtime`、`pyproject.toml`。

## Changed Files

- `dayu/host/__init__.py`
- `dayu/host/api.py`
- `tests/host/__init__.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_weak_typing_guard.py`
- `dayu/host/README.md`
- `dayu/README.md`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md`

## Plan Items Implemented

- 创建 `dayu.host` 公共命名空间。
- 在 `dayu.host.api` 实现 request / snapshot / status / error / context / stream cursor 最小类型清单。
- 所有公共 dataclass 使用 `frozen=True, slots=True`。
- 所有枚举使用 `enum.StrEnum`，并落地稳定 snake_case 字符串值。
- `HostMetadataEntry.value` 使用 `dayu.contracts.json_value.JsonValue`。
- `HostCommandFacet` 仅暴露 `host_handle_id`，不持有 store / policy / tool runtime 实现。
- 构造期校验覆盖空 id / name / reason、非法 cursor、follow-up queue / steer target 约束、bind slot 前置条件和 graceful cancel mode。
- `dayu.host.__init__` 只导出 Slice 1 承诺类型。
- 新增 package export、public contract、import boundary、weak typing guard 测试。
- 新建 `dayu/host/README.md`，同步 `dayu/README.md` 与 `tests/README.md` 当前事实。

## Not Implemented

- Host command function：明确 non-goal。
- durable store、EventLog row、dispatch record、policy provider set：明确 non-goal。
- runtime lane、runtime filelock、HostToolingOptions、ToolBundle construction input：属于后续 Slice。
- Engine / Fins / Service / UI 集成：明确 non-goal。

## Validation

- command:
  - `source .venv/bin/activate && pytest tests/host -q`
  - result: passed, `16 passed in 0.08s`
  - key assertions:
    - `dayu.host.__all__` 与 Slice 1 白名单严格一致。
    - status / error enum 字符串值稳定。
    - validation failure paths 覆盖空 id、非法 cursor、steer 缺 `target_run_id`、queue 携带 `target_run_id`、bind slot 缺 scope / slot_key、非 graceful cancel mode。
    - all public Host dataclass types 覆盖 frozen + slots 断言。
    - import boundary 阻止 `dayu.host` 导入 `dayu.engine` / `dayu.fins` / `dayu.service` / `dayu.ui`。
    - weak typing guard 阻止 `Any` / `object` / 无类型签名 / 裸容器注解。
- command:
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - result: passed, `0 errors, 0 warnings, 0 informations`
  - key assertions:
    - 新增 Host 生产代码与测试通过 pyright。

## Documentation Update

- updated:
  - `dayu/host/README.md`：记录当前已实现公共类型、校验边界、架构边界和 non-goals。
  - `dayu/README.md`：补充 `dayu.host` 当前公共类型命名空间事实。
  - `tests/README.md`：补充 `tests/host` 测试层级、运行命令与维护约定。
- not updated and reason:
  - 根目录 `README.md`：本 slice 未改变用户安装、配置、CLI 或项目级使用方式。
  - `dayu/engine/README.md`、`dayu/fins/README.md`、`dayu/config/README.md`：本 slice 未修改对应目录。

## Plan Gaps / Controller Questions

- 无阻塞缺口。
- 实现过程中未触发需要 controller 决定的新状态机、store schema、EventLog payload 或 policy provider shape。

## Residual Risks And Uncovered Areas

- risk: Host command path 尚未消费这些 request / snapshot 类型。
  - classification: accepted as covered by a later slice in the approved plan
  - owner or destination: Host Phase 后续 command path / durable store slices
- risk: Host tooling construction options 未实现。
  - classification: accepted as covered by a later slice in the approved plan
  - owner or destination: Phase 1 Slice 4
- risk: runtime lane / filelock 未实现。
  - classification: accepted as covered by a later slice in the approved plan
  - owner or destination: Phase 1 runtime slices

## Completion Signal

met: `dayu.host` 可导入且 public contract tests / pyright 均通过。

## Stop Condition Status

none hit

## Artifact Path

docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md
