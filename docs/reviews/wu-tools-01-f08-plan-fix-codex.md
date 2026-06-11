# WU-TOOLS-01-F08 Plan Fix

## 元信息

- Work unit：`WU-TOOLS-01-F08`
- Gate：plan fix
- 日期：2026-06-11
- Agent：AgentCodex
- Plan artifact：`docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`
- Controller adjudication：`docs/reviews/wu-tools-01-f08-plan-review-controller-adjudication.md`

## Scope

本 gate 只修 plan，不修改生产代码、测试、README，不 stage、不 commit、不 push、不进入 implementation。

实际修改文件：

- `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`
- `docs/reviews/wu-tools-01-f08-plan-fix-codex.md`

## Accepted Findings 修复状态

| Finding | Controller 要求 | 修复状态 | 修复说明 |
|---|---|---|---|
| F08-PR-MIMO-01 | `tests/fins/test_processor_registry.py` 必须 mandatory，除非 implementation 前有直接证据证明已有 focused 文件更合适；无论如何必须有 focused Fins registry behavior test | 已修复 | Plan 的测试章节已将 `tests/fins/test_processor_registry.py` 改为必选文件，并补充例外条件：只有 implementation 前有直接代码证据证明已有 focused Fins registry 测试文件更合适才可换位置。Plan 同时明确不允许用既有 pipeline tests 跳过 focused Fins registry behavior test。 |
| F08-PR-MIMO-02 | Fins registry 测试优先使用 `name -> (class, priority)` mapping / priority bucket 断言，避免完整列表顺序硬编码 | 已修复 | Plan 的 Fins test 断言已改为优先通过 public `list_processors()` 构造 `name -> (class, priority)` 映射，并断言 priority bucket / overlay contract；明确不要硬编码完整列表顺序，除非顺序本身是被测行为。 |
| F08-PR-DS-01 | 澄清 `docs/host/issues-implementation-control.md` 是唯一 `docs/host` old-name cleanup control target；历史 plan artifact 可保留旧引用 | 已修复 | Plan 的成功信号、总控更新和 residual risk 章节已明确：`docs/host/` 下历史 plan artifact 可保留旧引用，除非它们是当前稳定控制状态；本 WU 在 `docs/host/` 下的 old-name cleanup control target 只有 `docs/host/issues-implementation-control.md`。 |
| F08-PR-DS-02 | 澄清 focused registry tests 是 contract tests，既有 pipeline tests 是 integration coverage，二者互补 | 已修复 | Plan 的测试章节已新增说明：focused registry tests 是 contract tests，直接锁定 documents 默认 registry 与 Fins overlay contract；既有 pipeline tests 是 integration coverage。二者互补，不能互相替代。 |
| F08-PR-DS-03 | deferred：full `tests/fins` 若失败，implementation closeout 要区分 rename regression 与预存 heavy fixture/environment issue；focused tests 是主要证明 | 已修复 | Plan 的验证命令和 residual risk 章节已补充：若 full `tests/fins` 失败，implementation closeout 必须分类说明失败属于 rename regression 还是预存 heavy fixture / environment issue；focused registry tests 是本 WU 行为不变的主要证明。 |

## Validation

本 gate 按用户要求不运行 pytest / pyright；只进行了 plan review artifact、controller adjudication 和 plan 文本核对。未修改生产代码、测试或 README。

## Blocking Open Questions

None。

## Residual Risk

无未分类 residual risk。DS F3 已按 deferred 要求写入 plan，implementation closeout 负责在实际运行 full `tests/fins` 后分类说明可能的 heavy fixture / environment failure。

## Completion

Plan fix completed. 建议下一 gate：focused plan re-review。
