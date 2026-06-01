# WU-CTX-02 + WU-CTX-03 Slice E focused re-review — AgentMiMo

## 审查范围

- **Gate**: Slice E focused re-review（AgentCodex 小修：DS F-1 修复）。
- **审查对象**: `tests/host/test_dispatch_scheduler.py` diff（import 新增 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN`；`_soft_compact_policy` 默认值改为该常量）。
- **Fix artifact**: `docs/reviews/wu-ctx-02-03-fix-sliceE-codex-20260601.md`。
- **前置 review artifacts**:
  - `docs/reviews/wu-ctx-02-03-code-review-sliceE-mimo-20260601.md`（MiMo，Accepted）
  - `docs/reviews/wu-ctx-02-03-code-review-sliceE-ds-20260601.md`（DS，Accepted，提出 F-1）

---

## 结论

**Accepted.**

DS F-1 已被正确修复，无 blocking findings，无测试语义漂移，README 无需变更。

---

## 核查范围

1. F-1 修复正确性
2. 测试语义漂移
3. README 影响
4. Fix artifact validation 可信度
5. Controller deferred items（MiMo info F-01、DS INFO F-2/F-3/F-4）

---

## Findings

### 无 blocking findings。

---

### 1. F-1 修复正确性

**通过。**

修复内容：

| 位置 | 修复前 | 修复后 |
|---|---|---|
| `tests/host/test_dispatch_scheduler.py:67` | （无导入） | `from dayu.host.context_policy import ... DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` |
| `tests/host/test_dispatch_scheduler.py:4443` | `max_reactive_compactions_per_run: int = 2` | `max_reactive_compactions_per_run: int = DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` |

验证点：

- 生产常量 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN = 2` 定义于 `dayu/host/context_policy.py:21`，且已列入 `__all__`（line 301），是合法 public export。
- 测试文件导入路径 `dayu.host.context_policy` 与生产代码一致，无歧义。
- 常量当前值为 `2`，与修复前硬编码值相同——运行时行为零变化。
- DS F-1 所述"双重真源"风险已消除：未来若修改 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN`，测试默认值自动跟随。

### 2. 测试语义漂移

**无漂移。**

- `_soft_compact_policy` 的默认值语义不变（值仍为 `2`，来源从字面量改为常量引用）。
- 新增测试 `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` 显式传入 `max_reactive_compactions_per_run=2`，不依赖默认值，不受本次修改影响。
- 其余 3 处调用方不传 `max_reactive_compactions_per_run`，默认值语义不变。
- pytest 57 passed 确认无回归。

### 3. README 影响

**无需变更。**

本次修改仅涉及测试文件内部 import 和 helper 默认值来源，不改变：
- 测试覆盖范围或断言行为
- 用户手册中的命令或配置说明
- 开发手册中的架构或接口描述
- 测试手册中的覆盖说明

`tests/README.md` 已在 Slice E 实现中同步更新（连续 reactive overflow dispatch-loop 覆盖说明），本次小修不产生额外触发条件。

### 4. Fix artifact validation 可信度

**可信。**

- `pytest tests/host/test_dispatch_scheduler.py -q` → 57 passed：与 MiMo review、DS review 的验证结果一致（均 57 passed）。
- `python -m pyright dayu/ tests/ utils/` → 0 errors：导入 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` 为已导出符号，类型正确（`int`），pyright 无报错合理。
- 未新增 commit，fix artifact 明确声明"不提交 commit"，与 gate 流程一致。

### 5. Controller deferred items

以下 items 均由 controller 裁决 deferred，不属于本次修复范围，此处仅确认状态：

| Item | 状态 | 说明 |
|---|---|---|
| MiMo F-01（冗余 `<=` 断言） | Controller deferred | approved plan 要求同时校验 `==` 和 `<=`，作为 plan oracle 保留。不作为 info 要求修复。 |
| DS INFO F-2（超时常量语义归类） | Not in scope | 常量命名已表达语义区别，不影响正确性。 |
| DS INFO F-3（`del snapshot` 模式） | Not in scope | 与既有代码风格一致，无风险。 |
| DS INFO F-4（`_event_types_for_run` limit=200） | Not in scope | 既有代码通用风险，非本 Slice 引入。 |

---

## 残余风险

1. **极低风险**：`DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` 若未来被重构为非 `int` 类型（如改为 `Enum`），pyright 会立即报错，不构成隐藏风险。
2. **无新增风险**：本次修改未引入新的测试 seam、新的生产依赖、或新的常量定义。
