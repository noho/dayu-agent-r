# WU-SEMANTIC-OWNERSHIP-01 P3-C Final Plan Micro-Fix — AgentCodex

## Gate 与范围

- Gate：final plan micro-fix
- Timestamp：`2026-07-10T17:09:59+0800`
- 修改目标：`docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`
- 裁决输入：`docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-controller-adjudication.md`
- 独立复审输入：`docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-mimo.md`、`docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-ds.md`
- 允许变更：只修改原 plan，并新增本 artifact
- 禁止变更：生产代码、测试、control doc、README、既有 artifacts、commit、push、PR

## 动机、owner boundary 与直接证据

`P3-C-RR2-PF-01` 动机成立，且严重程度被正确限定为低：它不改变运行行为设计，但会让
S2 在删除唯一 compact material loop 后遗留生产 dead code。

语义 owner boundary 是 `dayu/host/run_input.py` 内的 ordinary/fallback material projection：

1. `build_run_input_material_blocks()` 当前在 `run_input.py:2518` 调用
   `_compact_material_source_ref(compact)`，随后在 `2519-2530` 的唯一
   `compact.messages` loop 中生成 `compact:*` / `SESSION_SUMMARY` material block。
2. `_compact_material_source_ref()` 定义于 `run_input.py:3123`；当前精确 source scan 只发现
   上述一个调用点与一个定义。S2 删除 loop 后，该 helper 没有合法消费者。
3. `_run_input_message_content()` 定义于 `run_input.py:3024`。除将被删除的 compact loop
   调用外，它仍被 memory message loop、continuity message loop和
   `_memory_material_kind()` 调用，因此不是 dead code，不能随本 finding 清理。

最佳修复不是引入通用 dead-code abstraction，也不是在下游保留兼容调用，而是在唯一调用者
所属的 S2 exact changes 中同步删除 helper 定义，并用同名零匹配 scan 封闭验收。

## P3-C-RR2-PF-01 修复

状态：`fixed in plan`

原 plan 已做以下最小修订：

1. §4.3 记录 final micro-fix closure，并明确不改变此前
   `P3-C-PF-01` 至 `P3-C-PF-06`、三个 residual observations、
   `P3-C-RR-PF-01` 至 `P3-C-RR-PF-05` 与 controller coverage follow-up 的 closure。
2. §6.4 明确 `_compact_material_source_ref()` 的唯一调用者是待删
   `build_run_input_material_blocks()` compact-message loop，函数定义必须与 loop 同一变更删除。
3. S2 exact changes item 6 同步点名删除 loop、`_compact_material_source_ref()`、失去职责的
   `compact` 参数及 call-site 传参。
4. §6.4 与 S2 明确保留仍有其它调用者的 `_run_input_message_content()`，禁止扩成无关 helper
   cleanup。
5. §9 新增 hard acceptance scan：

   ```bash
   rg -n '_compact_material_source_ref' dayu/host/run_input.py
   ```

   预期零匹配；任何定义、调用或 alias 残留都使 S2 验收失败。

## Assumptions tested

- 唯一调用者假设：通过当前 `run_input.py` 精确符号扫描成立。
- helper 删除边界假设：compact provenance 的 equality、raw-tail selection、evidence 去重、
  manifest/audit 均由 typed `CompactArtifactView` 直接承担，不依赖该 material source-ref helper。
- 不相关 helper 保留假设：`_run_input_message_content()` 仍有至少三个非 compact-loop 调用路径。
- sequencing 假设：删除动作全部位于 S2，未跨越 S1/S3 owner closure。

## Closure 与 regression audit

- 首轮 `P3-C-PF-01` 至 `P3-C-PF-06`：保持 closed。
- 三个 residual observations：保持 absorbed/closed。
- `P3-C-RR-PF-01` 至 `P3-C-RR-PF-05`：保持 closed。
- Controller coverage follow-up：`test_llm_compaction.py` 的 S2 focused、aggregate matrix、
  `--cov=dayu.host.llm_compaction` 与单文件 `--fail-under=80` 均保持不变。
- Implementation slices：仍为 S1/S2/S3 三个 slice；只收紧 S2 dead-helper completion signal。
- Propagation path：compact material loop 与 helper 一起删除；typed compact provenance 继续直接
  服务 equality、raw-tail、evidence 去重、manifest/audit；不产生新的 LLM-facing 投影。

## Validation

- 仅执行 Markdown whitespace checks；本 gate 未修改代码或测试，因此不运行 pytest、coverage
  或 pyright。
- 计划验证：`_compact_material_source_ref` 已在 S2 exact changes 与 §9 hard gate 同时覆盖。
- 范围验证：原 plan 与本 artifact 是本 gate 唯一允许的写入目标。

## Open questions

无。

## Residual risks

无新增 residual risk。既有 P3-E/P3-J 分配与三个 slice 的 stop conditions 保持不变。

## Conclusion

`pass`。`P3-C-RR2-PF-01` 已 fixed in plan；原 plan 保持三个 slices、全部前序 closure 与
coverage follow-up，可进入 AgentMiMo + AgentDS final parallel plan re-review。

Blocking questions：0。
