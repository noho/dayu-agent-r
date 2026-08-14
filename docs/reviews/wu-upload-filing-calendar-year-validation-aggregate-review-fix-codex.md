# UF-FIX04 聚合审查修复

## Gate record

- Work unit：`UF-FIX04 shared-calendar-year-validation`
- 输入：聚合双路 deepreview 与 controller adjudication
- 修复范围：仅 accepted F1/F2
- 生产代码：未修改
- 下一入口：AgentMiMo / AgentDS dual aggregate re-review

## 动机与 owner 边界

两个 accepted finding 均成立，但只属于测试 contract 缺口：

- F1 的业务真源仍是 shared full-date owner，download public DTO 只负责把 owner 拒绝统一投影为 `"{field_name} must be an ISO date"`。basic format `20240229` 在 Python 3.11 baseline 可被 `date.fromisoformat` 解析、但会被 strict owner 拒绝，因此它是真正覆盖 wording 统一的反例。恢复旧的 canonical-format 分支会在 wrapper 重复分类 owner 语义，不应修改生产。
- F2 的 owner contract 是合法 fiscal year、filing date、report date 均发生委托且值不被改写；当前重复静态校验次数不是公共语义。测试应锁定委托值集合、identity、resolved action 与 request identity，不应锁定 4/8 次偶然调用结构。

## 修改

### F1：public ISO DTO exact message

在 `tests/cli/test_fins_commands.py::test_download_public_iso_dates_delegate_shared_full_date_owner` 增加 `start_date="20240229"` 反例，并精确断言完整异常文本为：

```text
start_date must be an ISO date
```

未增加 week-date case；basic format 已足以覆盖 controller 指定的真实 wording 漂移类别，保持测试最小化。

### F2：delegation contract 去除次数耦合

在 `tests/fins/test_fins_ingestion_runtime.py::test_filing_calendar_year_static_admission_accepts_boundaries_and_delegates`：

- 使用不同且合法的 `filing_date="2024-02-29"` 与 `report_date="2024-03-01"`；
- `year_calls` 断言非空且值集合精确为当前 `fiscal_year`；
- `date_calls` 断言非空且值集合精确为上述两个日期，因此两者均至少出现一次且没有其它值；
- 保留 deterministic document identity、internal identity、`resolved_action == "delete"` 与 `first.request is request` 断言；
- 不再约束调用次数。

## 验证

所有命令均在仓库根目录执行并先激活 `.venv`；未执行 UF-PF04。

1. 两个修改测试：
   - `pytest tests/cli/test_fins_commands.py::test_download_public_iso_dates_delegate_shared_full_date_owner tests/fins/test_fins_ingestion_runtime.py::test_filing_calendar_year_static_admission_accepts_boundaries_and_delegates -q`
   - 结果：`3 passed, 3 warnings`，exit `0`。runtime node 按两个 fiscal year 边界参数化，因此合计三例。
2. S2 focused 六节点：
   - 结果：`89 passed, 3 warnings`，exit `0`。
3. runtime 完整文件：
   - `pytest tests/fins/test_fins_ingestion_runtime.py -q`
   - 结果：`258 passed, 3 warnings`，exit `0`。
4. CLI 完整文件：
   - `pytest tests/cli/test_fins_commands.py -q`
   - 结果：`124 passed, 3 warnings`，exit `0`。
5. 全量类型检查：
   - `python -m pyright dayu/ tests/ utils/`
   - 结果：`0 errors, 0 warnings, 0 informations`，exit `0`；另有 pyright 新版本提示。
6. Diff integrity：
   - `git diff --check`
   - 结果：无输出，exit `0`。

pytest 的三条 warning 均来自 `.venv` 中 `edgar` deprecated imports，与本次修复无关。

## Scope 与 residual

- 仅修改 `tests/cli/test_fins_commands.py`、`tests/fins/test_fins_ingestion_runtime.py`，并新增本 artifact。
- 未修改 production、README、frozen registry/evidence 或历史 artifact；未 stage、未 commit。
- 未执行 UF-PF04，也未处理其它 residual。
- 本修复完成后停止在 dual aggregate re-review；只有 AgentMiMo 与 AgentDS 均 Pass 后，控制侧才可继续后续 gate。
