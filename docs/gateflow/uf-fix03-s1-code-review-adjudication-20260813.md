# UF-FIX03 S1 code review 裁决

## 输入

- accepted plan：`docs/gateflow/uf-fix03-summary-bounded-errors-plan-20260813.md`
- implementation：`docs/gateflow/uf-fix03-s1-implementation-20260813.md`
- AgentMiMo review：`docs/reviews/code-review-20260813-213823.md`
- AgentDS review：`docs/reviews/code-review-20260813-214459.md`

## 裁决

### F1：S1 修改分支缺少 owner 行为覆盖

**接受。** `cn_pipeline.py` 的整文件覆盖率低于 80% 本身可按 accepted plan 对大型既有文件的规则记录具体既有缺口；但不能据此豁免本 S1 新增或修改的 owner 分支。当前至少存在以下 S1 行为缺口：

- service early-cancelled summary 未由行为测试证明 `requested_file_count=len(files)`、`stored_file_count=0`；
- direct runner-unavailable summary 未由行为测试证明相同 count 语义；
- summary 的 `skipped + requested_file_count=0` 拒绝分支未覆盖。

AST constructor audit 只能证明必填字段存在，不能代替值语义测试。修复必须增加 owner/integration 行为测试，并修正 implementation artifact 中“S1 修改路径已有 coverage”及“用户要求不得 commit”的失真表述。大型既有、未修改的 CN download/facade/helper 缺口继续作为明确 residual risk，不借本 WU 扩大范围。

### F2：workflow 级 conversion-cancelled catch 不可达

**接受。** 直接证据表明 converter 抛出的 `DoclingConversionCancelledError` 已由 `DoclingUploadService.prepare_upload(...)` 捕获并投影为 cancelled `UploadOperationResult`；workflow try block 的后续调用没有该异常的生产 raise path。因此 SEC/CN workflow 级 catch 是当前拓扑下不可达的重复 owner。

修复选择：删除 SEC/CN 两个 workflow 级 catch 及其中的 inline `UploadOperationResult(...)` 构造，把 production constructor inventory 与 AST audit 从六点收紧为四点。真实 cancellation owner 仍是 `DoclingUploadService` 的 typed cancelled result 与 precommit cancellation 路径。不得新增兼容分支或另一套 cancellation 映射。

此处对 accepted plan §6.1 的“当前六点”清单作证据化 amendment：该清单描述了实施前库存，不构成保留不可达代码的要求；owner 唯一性与最小边界优先。

## 修复 gate

S1 不得进入 accepted slice commit，直到：

1. 上述生产死分支删除，相关 imports 与 AST inventory 同步收紧；
2. 三个缺失行为测试补齐；
3. implementation artifact 表述纠正；
4. focused pytest、完整 pyright、coverage、`git diff --check`、old-field 与 frozen SHA audit 通过；
5. AgentMiMo 与 AgentDS 对修复后 S1 重新 review，且无未裁决实质 finding。

