# UF-FIX04 聚合双路审查控制侧裁决

## Gate record

- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Base: `f609a4d8`
- Reviewed HEAD: `0dfc9f34`
- Reviewers: AgentMiMo、AgentDS
- Decision: `two low findings accepted; fix required`
- Next entry point: `AgentCodex aggregate review fix`

## 总体裁决

AgentMiMo 给出 Pass；AgentDS 给出两个低严重度 finding，并确认 UF-FIX04 六项核心目标全部达成。控制侧接受 F1、F2，修复边界均仅在测试与治理 artifact，不修改生产行为。

## F1：接受——显式裁决 public DTO wording 统一并锁定新 contract

accepted plan 要求 `_parse_optional_iso_date` 继续拥有 download public DTO 错误 wording。baseline 对 `date.fromisoformat` 可解析但非 canonical 的 basic format（如 `20240229`）或 week-date 会抛 `must use canonical ISO format`；当前实现委托 strict shared owner 后统一映射为 `must be an ISO date`。`2024-2-9` 在 Python 3.11 baseline 本来就由 `fromisoformat` 拒绝并使用后一文案，不是实际漂移样例；真正发生 wording 变化的是 basic/week-date 类。

控制侧裁决：接受统一后的 `"{field_name} must be an ISO date"` 作为新的稳定 public DTO contract，不恢复双 message。原因：恢复第二分支需要 download wrapper 再次区分 canonical shape failure，与 strict date owner 重复解析/分类，违反本任务唯一语义 owner；错误类型与接受集均未变化，正常用户 download 输入也不消费该 DTO message。

最小修复：在 `tests/cli/test_fins_commands.py` 的 public ISO DTO contract test 中增加 baseline 可解析但 owner strict 拒绝的 `20240229`（可选再含 week-date）并断言统一后的 exact message；新增 aggregate fix artifact 明确 plan wording amendment。不得修改生产代码。

## F2：接受——移除 owner delegation spy 的偶然调用次数锁定

当前 runtime delegation test 精确断言 4 次 year、8 次相同 date，固化了“两次入口调用 × 每次内部双重静态校验 × 两个日期字段”的偶然结构。owner contract 只要求合法 year、filing date、report date 均委托 shared owner，值不被改写，并能进入 state-aware path；未来去重静态校验不应被该测试阻止。

最小修复：

1. filing/report 使用两个不同的合法日期，以便证明两个字段都委托 owner；
2. year calls 只断言非空且所有值均为当前 `fiscal_year`；
3. date calls 只断言两个字段值都至少出现一次，且不存在其它值；
4. 保留 deterministic identity、resolved action 与 request identity 断言；
5. 不对具体次数或当前双重静态校验结构作承诺。

## 验证与范围

- 运行两个修改测试、S2 focused、runtime 完整文件、CLI 完整文件；
- 运行全量 `python -m pyright dayu/ tests/ utils/` 与 `git diff --check`；
- production、README、冻结 registry/evidence 均不得修改；
- 不执行 UF-PF04，不处理其它 residual；
- 修复后由 AgentMiMo / AgentDS 双路 aggregate re-review，均 Pass 后方可提交 accepted deepreview artifact。
