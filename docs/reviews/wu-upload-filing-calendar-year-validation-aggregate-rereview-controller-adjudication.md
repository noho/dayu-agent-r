# UF-FIX04 聚合 re-review 控制侧裁决

## Gate record

- Work unit：`UF-FIX04 shared-calendar-year-validation`
- Base：`f609a4d8`
- Reviewed HEAD：`0dfc9f34`
- Reviewers：AgentMiMo、AgentDS
- Decision：`Pass`
- Next entry point：accepted deepreview commit

## 总体裁决

AgentMiMo 与 AgentDS 均独立给出 Pass。聚合审查接受的两个低严重度 finding 已关闭，没有 remaining finding，也没有新增 finding。

## Finding closure

### F1：download public DTO 错误文案统一

- 接受统一后的 `"{field_name} must be an ISO date"` 作为稳定 contract，不恢复重复解析或双文案分支。
- 回归测试使用 Python 3.11 baseline 可解析、但 strict shared owner 拒绝的 compact ISO 输入 `20240229`，以 exact equality 锁定新文案。
- AgentDS 复核并纠正了原 finding 示例：`2024-2-9` 在 baseline 本来就被 `date.fromisoformat` 拒绝，真正发生 wording 变化的是 basic/week-date 输入类。该事实纠正不改变 finding 的核心及修复结论。
- 修复只修改测试，没有在 download wrapper 或 shared owner 中增加重复分类。

### F2：runtime owner delegation 测试不再固化调用次数

- filing date 与 report date 改为两个不同的合法日期。
- 测试只要求 year/date owner 至少被调用、收到的值集合精确正确且无额外值，不再承诺当前内部重复调用次数。
- deterministic identity、internal identity、resolved action 与 request identity 断言均保留。

## 独立验证汇总

- 两个修改测试：`3 passed`
- accepted plan focused nodes：`89 passed`
- `tests/fins/test_fins_ingestion_runtime.py`：`258 passed`
- `tests/cli/test_fins_commands.py`：`124 passed`
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`
- `git diff --check`：通过

## Scope integrity

- aggregate fix 只修改 `tests/cli/test_fins_commands.py` 与 `tests/fins/test_fins_ingestion_runtime.py`。
- production、README、冻结 oracle/scenario registry 与既有 evidence 均未修改。
- 未执行 `UF-PF04`，未处理其它 `upload_filing` finding。

## Conclusion

聚合 re-review gate 通过，可以提交 accepted deepreview artifacts 与相应测试 contract 修正。
