# WU-SEMANTIC-OWNERSHIP-01 过度设计与本地最小设计陷阱专项审查

## 结论

本次按 `$deepreview --all` 的严格证据门审查，确认 **3 个未修复 finding：1 个高严重度、2 个中严重度**。它们都位于明确范围 `b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD` 内，并且都已改变 LLM-facing 投影、共享消费者语义、公开工具错误或测试契约；不是 style、命名或“未来可以更好”的建议。

已知候选 `DocResourceBudget(32 MiB, 10,000)`、`BoundedSourceSnapshot`、`list_files/search_files` partial contract 本身 **不构成 finding**：R3-E accepted plan 对这些行为、数值、partial 字段和 LLM-facing 下一步指令有逐项直接授权。Web egress/resource policy 同样有明确授权。审查没有把“固定数值”本身等同于过度设计。

## Findings

### F-01 — 高 — Host 用参数字段名黑名单重定义 LLM-safe contract，合法工具调用被整体降级

状态：**未修复**。

#### 过度设计的语义 / contract

`accepted_result_projection` 新增了一套递归参数名 policy：只要任一 key 含 `api_key`、`token`、`secret`、`password`，以 `path` 结尾或含 `path_`，就把整个 accepted tool query 改成 `LIMITED_SIGNAL / arguments_summary_unsafe`。这不是读取 producer 已提供的安全投影，而是在所有工具共享的下游 LLM projection 中，用字符串启发式重新决定哪些业务参数“安全”。

该规则同时成为 RunInput、Memory、CompactMaterial 与 Tool Trace 的共享 LLM-facing contract，而不是局部日志防护。

#### 正确 owner

- `TOOL_CALL_REQUESTED` producer / ToolRuntime 应拥有“原始 accepted 参数”与“LLM-safe replay 参数”的产生、脱敏、digest 和持久化。
- 每个工具或 framework tool 的 typed semantic-query contract 应拥有业务可读 query。`fetch_more` 的 cursor/scope token 属 Host 内部治理信息，应由 ToolRuntime 直接产生不含这些标识的业务中性 query，而不是交给下游猜测。
- `accepted_result_projection` 只能校验并消费上述 owner atom；它不应拥有跨工具敏感字段 taxonomy。

#### 直接证据

1. 参数名黑名单及整体拒绝行为位于 `dayu/host/accepted_result_projection.py:518-576`；命中任一嵌套 key 后直接返回 `arguments_summary_unsafe`，没有字段级安全投影。
2. 真实 ordinary ToolRuntime 在 `dayu/host/tool_runtime.py:6731-6739` 和 `:6841-6849` 构造 `ToolAcceptCall` 时传入原始 `call.arguments`，没有填写 `semantic_query_text`。因此生产调用通常都会走 arguments fallback，而不是测试中手写的 semantic query。
3. ordinary producer 在 `dayu/host/tool_runtime.py:4357-4365` 强制 arguments payload digest 等于原始 normalized digest；`dayu/host/tool_runtime.py:6404-6423` 直接把原参数复制到 `{"arguments": ...}`。相反，wait producer 已在 `dayu/host/waiting.py:2336-2342` 使用 `llm_safe_replay_arguments`，说明安全投影能力已有 owner 实现，但 ordinary producer 没有复用。
4. 合法现有工具字段会确定命中该 policy：Doc tools 的公开 schema 使用 `file_path`，见 `dayu/tools/doc_tools.py:2821-2836`、`:2892-2908`、`:2926-2938`；framework `fetch_more` 使用必填 `scope_token`，见 `dayu/host/tool_runtime.py:5965-5990`。诊断调用当前 helper 得到 `file_path=True`、`scope_token=True`、`ticker=False`。
5. `fetch_more` 不是理论路径：`tests/host/test_phase6_toolruntime_integration.py:383-464` 证明含 `scope_token` 的调用作为普通工具走同一个 accept/EventLog 路径。
6. `tests/host/test_accepted_result_projection.py:751-796` 用 `api_key` 固化了整体 limited-signal 行为，但没有覆盖合法 `file_path` / `scope_token` 的误伤。`:941-969` 又证明同一 projection 进入 RunInput、Memory、Tool Trace 与 CompactMaterial。
7. 生产消费者直接复用该 LLM material：`dayu/host/durable/memory.py:420-430`、`dayu/host/run_input.py:3178-3182`、`dayu/host/compact_material.py:2579-2599`。

#### 设计真源 / accepted plan 缺口

- `docs/host/design.md:1613` 明确要求 producer 持久化已脱敏的 LLM-safe 参数投影，并明确其 `arguments_payload_digest` **不要求**等于原始 `normalized_arguments_digest`。这把安全参数的 owner 放在 producer，而不是 projection。
- 同一设计表 `docs/host/design.md:1629` 又写两者必须相等，和 `:1613` 直接矛盾。项目约束要求 owner 不清楚时停止；实现没有停止，而是用下游 key blacklist 掩盖该矛盾。
- `docs/host/design.md:1615` 只授权在缺 semantic query 时消费 bounded arguments projection，或输出业务中性 unavailable 文案；同时禁止把 cursor / Host 内部账本字段渲染给 LLM。它没有授权用字段名片段建立通用安全策略。
- accepted P1-A plan `docs/host/wu-semantic-ownership-01-p1-a-plan.md:134-141` 只写“不可安全读取时”进入 typed limited signal，既没有定义上述 key taxonomy，也没有把已验证 safe atom 的 owner 移到 projection。其完成信号 `:141` 也没有列出 unsafe-key 测试。
- 后续 code-review controller 在 `docs/reviews/wu-semantic-ownership-01-p1-a-code-review-controller-adjudication.md:57-71` 反而声称 accepted plan “explicitly listed” unsafe argument key，并要求测试；原 plan 文本不支持该说法。`:84-90` 再把启发式记为 projection-owner residual，是实现后的追认，不是设计真源或 accepted plan 授权。

#### 当前失败方式 / 成本放大

- 所有没有 semantic query、但参数含 `file_path` / `scope_token` 的正常 accepted result 都失去业务 query，上下文中只剩“查询语义不可用；参数未安全展开”。这一损失同时扩散到 RunInput、Memory、Trace 与 CompactMaterial。
- 任一嵌套 key 命中会丢弃同一调用中的全部安全字段，行为取决于拼写而不是工具 schema/owner。例如 `file_path` 被默认视为不可读，即使它已经是 tool owner 明确投给 LLM 的定位参数。
- 该 blacklist 既会误伤，也无法证明覆盖所有敏感字段；ordinary producer 仍保存原参数，未命中的敏感别名可能继续进入 fallback。新增更多片段只会把局部启发式扩成通用 security framework 和长期兼容负担。
- 测试和 controller artifact 已把该局部 policy 固化为“正确 contract”，后续修回 producer owner 会被旧测试反向阻挡。

#### 推荐修正边界

1. 先在 `docs/host/design.md` 裁决 `:1613` 与 `:1629` 的 digest 冲突，冻结原始 digest与 safe-projection digest 的唯一关系；在此之前不要再扩展 key taxonomy。
2. ordinary ToolRuntime producer 复用/扩展现有 `llm_safe_replay_arguments` 或 typed per-tool safe projection，在写 `TOOL_CALL_REQUESTED` 时即产生可验证的 LLM-safe atom；不要在消费者层重新识别敏感字段。
3. 给 `fetch_more` 由 ToolRuntime owner 产生不含 cursor/scope token 的业务中性 semantic query。
4. 删除 `_contains_unsafe_argument_key`、`arguments_summary_unsafe` 这一字段名 policy 及固化它的测试；safe atom 缺失或 digest 不可验证时统一 fail closed / unavailable，不加兼容 alias。

#### 验证点

- ordinary 与 wait producer 对同一安全投影/digest contract 一致；原始敏感参数不会进入 LLM-safe atom。
- 合法 `file_path` 调用保留 owner 允许的 bounded query；字段名本身不触发全量拒绝。
- `fetch_more` 的 RunInput/Memory/Trace/CompactMaterial 都有业务中性可读 query，且不含 cursor/scope token。
- 构造未列入旧 blacklist 的敏感字段时，仍由 producer typed redaction 保证不泄漏，而不是靠补充字符串片段。
- cross-consumer test 继续证明四个消费者只消费同一 projection，但不再固化字段名 taxonomy。

### F-02 — 中 — Host 把未知 `OpaqueEvidenceRef` 默认升格为业务来源

状态：**未修复**。

#### 过度设计的语义 / contract

新 projection 维护七项 internal ref denylist；凡 `ref_kind` 不在 denylist 中，就默认把不透明 `ref_kind/ref_id` 拼成 `kind:id`，并作为“业务来源”进入 LLM material。该规则无 producer schema、无显式 allowlist/typed contract，却给所有未来 ref kind 定义了用户可见语义。

#### 正确 owner

业务可读 source/locator 必须由 accepted-evidence producer 的显式 typed contract 产生和校验。`OpaqueEvidenceRef` 只拥有内部 provenance identity；Host projection 不应从不透明字符串反推业务分类。

#### 直接证据

1. denylist 位于 `dayu/host/accepted_result_projection.py:61-71`；`dayu/host/accepted_result_projection.py:644-691` 对不在 denylist 的任何 ref 返回 `f"{ref_kind}:{ref_id}"`。`:712-735` 将该 source 直接放入 LLM material。
2. 类型 owner 自身明确相反语义：`dayu/host/evidence.py:80-102` 将 `OpaqueEvidenceRef` 定义为“Host 不解析语义的 evidence ref”，只校验非空文本和 digest。
3. 测试自行发明 `filing:MSFT-10K` 分类并断言为业务来源：`tests/host/test_accepted_result_projection.py:87-142`、`:534-563`。内部 ref 测试只覆盖 `payload/event/digest` 三种 denylist 项，见 `:566-602`，没有证明 unknown kind 可公开。
4. 当前生产 ordinary/wait producer 都明确写空 `source_refs` / `locator_refs`：`dayu/host/tool_runtime.py:4925-4965`、`dayu/host/waiting.py:2005-2030`。所以测试中的 `filing` taxonomy 没有生产 producer contract 来源。
5. 同一 projection 已由 `tests/host/test_accepted_result_projection.py:941-969` 固化到 RunInput、Memory、Trace 与 CompactMaterial，不只是内部调试字段。

#### 设计真源 / accepted plan 缺口

- P1-A plan `docs/host/wu-semantic-ownership-01-p1-a-plan.md:69-76` 明确 envelope 不解析业务 source/locator 语义。
- 非目标 `docs/host/wu-semantic-ownership-01-p1-a-plan.md:110-118` 禁止把 source 分类扩成通用 provenance 平台。
- 最关键的 stop condition 在 `docs/host/wu-semantic-ownership-01-p1-a-plan.md:267-280`：若无法从 `OpaqueEvidenceRef` 判断业务可读分类且没有 producer contract，必须停止；同段还承认当前 producer refs 大多为空。
- `docs/host/design.md` / `docs/engine/design.md` 没有定义 `filing` 或“unknown kind 默认业务可读”的 ref schema。实现越过了 plan 的 stop condition。

#### 当前失败方式 / 成本放大

- production 目前只能给出 source unavailable，而测试却宣称存在 `filing:*` 业务来源；测试契约与真实 producer 能力脱节。
- 任何调用方一旦提供新的 opaque kind，即会未经 owner 审核进入 LLM 上下文。内部 ref 只要换一个未列入七项 denylist 的名字就会被误当财报来源。
- 七项 denylist 变成隐藏 schema。以后新增内部 ref kind 必须同步修改 projection 和所有消费者测试，否则会产生 LLM-visible leak；这正是本地最小设计把成本放大的方式。

#### 推荐修正边界

- 删除 unknown-kind 默认业务分类和七项 denylist 推断。现有 `OpaqueEvidenceRef` 一律只保留为内部 provenance；在没有 typed business-source atom 时投影统一为 unavailable。
- 若产品确需 `filing` 来源，先由具体 producer/公共契约新增显式业务 source 类型或业务可读 projection 字段，再由 accepted-result projection 机械消费；不要复用 opaque ref 的名字作为业务事实。
- 删除测试中手写 `filing:MSFT-10K` 作为生产 contract 的断言，增加“未知 opaque kind 不进入 LLM”的 fail-closed 测试。

#### 验证点

- 任意未知 `ref_kind`、内部 event/payload/digest ref 都不会出现在 RunInput、Memory、Trace 或 CompactMaterial。
- refs 为空时四个消费者仍得到同一 source-unavailable 文案。
- 只有显式 typed business-source producer atom 能产生可见来源，并有 producer、serialization、projection 与 cross-consumer owner 测试。

### F-03 — 中 — Doc 暴露计划外错误码 `source_budget_exceeded`，通用 catch 又把它扩到未裁决工具

状态：**未修复**。

#### 过度设计的语义 / contract

`SourceBudgetExceeded` 是 Documents 层内部 typed resource exception；Doc tool adapter 又新造公开错误码 `source_budget_exceeded`。该字符串通过 direct callable 和 process-backed failed envelope 对外可见，并由一个通用 catch 覆盖 `get_file_sections`、`read_file` 与 `read_file_section`。

#### 正确 owner

公开失败码的唯一 owner 是 `dayu.tools.doc_tools` 的 tool outcome projection，且必须服从 accepted R3-E stable failure-code contract。Documents processor 只拥有内部异常类型，不拥有公开工具错误码。

#### 直接证据

1. `dayu/tools/doc_tools.py:1163-1215` 捕获 `SourceBudgetExceeded` 并创建 `_DocBusinessFailure("source_budget_exceeded", ...)`。
2. direct callable 在 `dayu/tools/doc_tools.py:1048-1058` 把该字符串写入 `failed_outcome(error=...)`；process path 在 `dayu/tools/doc_tools.py:1369-1386` 把它写入 failed JSON envelope。它因此是公开工具 contract，不是内部日志标签。
3. 同一 catch 位于五工具共享路由之外层；`dayu/tools/doc_tools.py:1257-1293` 表明 `get_file_sections`、`read_file`、`read_file_section` 都传入 source budget。`get_file_sections` 在 `dayu/tools/doc_tools.py:1589-1617` 同样进入 bounded snapshot，因此也会继承该未裁决公开 code。
4. 测试 `tests/tools/test_doc_tools_provider.py:953-971` 只调用私有 `_read_file_business` 并断言内部 `SourceBudgetExceeded`，没有断言 direct/process tool outcome 的公开 error code。
5. 实现 artifact `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s4-implementation-codex.md:52-56` 把 `source_budget_exceeded` 记录为已实现；code review `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s4-code-review-ds.md:62-71` 甚至声称上述私有 helper 测试验证了异常到公开 code 的映射，和测试代码不符。

#### 设计真源 / accepted plan 缺口

- R3-E plan `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md:155-164` 明确授权内部 `BoundedSourceSnapshot` / `SourceBudgetExceeded`，但这只是 Documents resource owner contract。
- 同一 accepted plan 的 stable failure codes 在 `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md:223-227` 只授权 Doc 公开码 `source_too_large`，并限定用于单一显式 read/section source。全文没有 `source_budget_exceeded`。
- plan 没有冻结 `get_file_sections` 命中 source byte cap 时的公开失败码；实现不应让共享 catch 自动创造 contract。

#### 当前失败方式 / 成本放大

- 按 accepted plan 编写的 Host/LLM/tool caller 期待 `source_too_large`，实际收到 `source_budget_exceeded`，稳定错误分支和下一步动作会失配。
- `get_file_sections` 被动继承同一新码，扩大了 plan 未裁决的用户可见面；以后修回 owner contract 会诱发错误码兼容分支，而项目明确禁止为旧实现保留兼容逻辑。
- review artifact 把未验证的公开映射写成“测试已证明”，会使总控误判 contract 已闭合。

#### 推荐修正边界

- 保留 Documents 内部 `SourceBudgetExceeded`；在 Doc tool owner 中只对 `read_file` / `read_file_section` 映射 accepted code `source_too_large`。
- 对 `get_file_sections` 先由 Doc tool contract owner 明确裁决 oversize 行为；在计划/设计未补齐前，不要通过通用 catch 默认为新公开 code。
- 删除 `source_budget_exceeded` 公开字符串，不增加兼容 alias；修正声称已有映射测试的 review/control 记录。

#### 验证点

- direct callable 与 process-backed path 对 read/read-section 都精确返回 `source_too_large`。
- end-to-end tool outcome 测试断言公开 code，而不只断言私有 helper 异常。
- `get_file_sections` 的 oversize 行为有 owner 文档和对应 tool-boundary 测试后再成为 contract。
- 全仓不再出现公开 `source_budget_exceeded` 字符串；search 仍按授权返回 `source_limit` partial success。

## 工具安全专项审计

### 结论

当前范围并非“没有工具安全代码”：

1. **发现一项未授权的 tool-security-like policy**：F-01 的 Host 参数名安全 blacklist。它由 `2a841134c` 范围内提交引入，直接影响共享 LLM-facing material。
2. **存在但有明确授权的局部工具安全实现**，不报告为 finding：
   - Web URL/DNS/private-network/custom-port policy 位于 `dayu/tools/web/web_egress_policy.py:1-4`、`:252-367`；R3-E plan `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md:106-119` 逐项授权。
   - Web wire/decoded/browser/diagnostic budgets 位于 `dayu/tools/web/web_resource_budget.py:18-44`、`:88-139`；accepted plan `:166-204` 冻结全部字段与默认值。
   - public direct Playwright 的 `browser_egress_policy_unavailable` 位于 `dayu/tools/web/web_playwright_backend.py:1385-1391`、`:1570-1575`；accepted plan `:118`、`:204` 明确要求该 fail-closed 行为。
   - Doc source/directory budgets 与 partial outputs 位于 `dayu/tools/doc_tools.py:87-88`、`:118-150`、`:698-705`、`:846-854`，由 accepted plan `:155-164`、`:214-227` 明确授权。
3. R3-E plan `:526-547` 明确拒绝 repository-wide tool-security framework，并 deferred Fins file authority、upload symlink policy、Fins remote egress、generic browser sandbox 与 Doc generic file authority。当前 diff 中未发现这些 deferred 项被实现。
4. 对 `dayu/fins`、`dayu/cli`、`dayu/service`、`dayu/wechat` 的新增行扫描未发现 allowlist/denylist/file-authority/egress/browser/SSRF/remote-byte/generic security policy。CLI upload suffix allowlist 主体早于本范围；本 WU 只改动错误常量，不算本 WU 新增安全 contract。

### 文档 / 总控一致性

- `docs/reviews/wu-semantic-ownership-01-tool-security-artifact-code-audit.md:28-43` 通过有限关键词扫描得出“WU to date 未加入 tool-security code”。F-01 的实现提交 `2a841134c` 早于该 audit artifact 提交 `efa93109`，但实现使用的是普通字段片段与 `unsafe`，被 `:35` 所述扫描漏掉；该全局结论对当时的 Host 代码已不成立。
- 当前 HEAD 后续又按 R3-E accepted plan 合法加入 Web/Doc safety code，因此上述旧 artifact 更不能作为当前 HEAD 的“零工具安全代码”证明。应区分“计划授权的局部 safety owner”和“F-01 的未授权通用 key policy”。
- `docs/host/issues-implementation-control.md:207` 的 R3-D 行写有“No tool-security code was added; tool-security remains unimplemented”。这最多能描述该 slice 的文件扫描，不能再作为整个 WU 当前状态；否则会同时漏掉 F-01，并与后续 R3-E accepted implementation 冲突。

## 已知候选与相邻候选裁决

| 候选 | 直接证据与授权 | 裁决 |
| --- | --- | --- |
| `DocResourceBudget.max_source_bytes=32 MiB` / `max_directory_entries=10,000` | 代码 `dayu/tools/doc_tools.py:87-88,118-150,585-610`；R3-E plan `:155-164,214-220` 精确冻结数值、owner、partial schema 与 LLM-facing 说明 | **不报告**；是用户可见行为，但有 accepted plan 明确授权 |
| `BoundedSourceSnapshot` 超限抛 `SourceBudgetExceeded` | 代码 `dayu/documents/processors/bounded_source.py:276-321`；R3-E plan `:157-160` 明确要求读取 `limit+1` byte 后 typed fail | **不报告**；内部资源 owner 合理。只报告 F-03 的额外公开错误码 |
| `list_files/search_files` 的 `directory_entry_limit/source_limit` partial contract | LLM descriptions `dayu/tools/doc_tools.py:698-705,846-854`；R3-E plan `:161-163,217-221` 明确冻结 partial 字段和模型下一步 | **不报告**；不是无需求 partial scan |
| Web custom-port/private-network/egress fail-closed 与资源 budgets | 代码见工具安全专项；R3-E plan `:106-119,166-204,526-547` 逐项授权并限制为 Web 局部 owner | **不报告**；未发现 repository-wide generic policy 抽象 |
| Fins SEC stream/non-stream staging 双路径 | `dayu/fins/pipelines/sec_download_filing_workflow.py:429-490`、`dayu/fins/pipelines/sec_pipeline.py:1629-1649`；P3-F plan `docs/host/wu-semantic-ownership-01-p3-f-fins-source-provenance-plan.md:218-245` 明确要求两路径及测试 | **不报告**；虽是分支和测试 contract，但有计划授权 |
| Fins/CLI/Service/WeChat 的 cap、schema、state、compat/security 候选 | 专项 added-line 扫描；HKEX 100 为范围前 provider 行为，XBRL identity cap 只截内部诊断，source-meta 512 为透明 cache，CLI upload JSON schema 与 WeChat unavailable stub 均有对应 accepted plan | **0 个材料 finding**；没有把内部预算/缓存误报成产品 contract |
| Engine / Runtime 新增 cap、policy、compat shim、额外状态机 | 对范围内 `dayu/engine`、`dayu/runtime` 新增行按 cap/budget/policy/schema/state/compat/security 词族扫描，并与 `docs/engine/design.md`、Host owner plan 交叉核对 | **0 个材料 finding**；未发现无授权用户可见 contract |

## 范围与 Git 记法纠正

- 用户最终确认的唯一范围基线：`b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`。
- 实际执行命令：`git diff b1a0631f397967e7530b676a90ef7467d83a1817^ HEAD`。
- 首提交：`b1a0631f397967e7530b676a90ef7467d83a1817`（包含在范围内）。
- 基线 parent：`3410d7422655c56bdf13c643f77c27f40b9d4550`。
- 审查时 HEAD：`01bbf74c3c408b1b8eaafae20b5a9c68cb733c3f`。
- 分支：`phaseflow/host-issues-control`。
- 统计：`1317 files changed, 191967 insertions(+), 19116 deletions(-)`；顶层覆盖 `dayu/` 210、`tests/` 193、`docs/` 900、`utils/` 5，另含约束/README/pyproject 文件。
- 本范围用于包含 “WU-CLI-SMOKE-01 dayu-cli usability smoke PR-172” 之后的第一个 change 及其后全部代码；PR-172 之前的改动不在本审查中。
- 用户后续范围修正已覆盖先前的 main/merge-base 口径。本 artifact 不以 `HEAD..main`、`main...HEAD` 或 merge-base 推导 inclusion，也没有反向审查 main 提交。

## 审查真源、方法与覆盖

### 真源优先级

1. 项目约束：`AGENTS.md`，尤其 semantic owner、LLM-facing、无兼容 shim、最小设计与工具 schema 规则。
2. 设计真源：`docs/host/design.md`、`docs/engine/design.md`。
3. 总控：`docs/host/issues-implementation-control.md`；附加总控：`docs/phaseflow-umbrella-optimization-control.md`。
4. 对具体 WU 行为，只把 accepted plan 的明确冻结项视为授权；implementation/review artifact 只能证明“曾实现/曾被审查”，不能反向创造设计真源。

### 证据门

只有同时满足以下条件才报告：

- 行为由本范围新增或改变；
- 有直接文件/行号证明它改变公开工具错误、LLM-facing material、durable projection、Memory/Trace/Compact/RunInput 或测试 contract；
- 设计真源/accepted plan 未授权该具体语义，或明确要求由另一个 owner 产生；
- 有当前可达失败、已固化测试成本或明确的跨消费者传播，不以未来猜测代替影响。

### 并行覆盖

- `/root/host_engine_runtime_audit`：Host / Engine / Runtime，提交 F-01、F-02 候选及工具安全矛盾证据。
- `/root/web_docs_tools_audit`：Web / Documents / Tools，提交 F-03 候选并否决已授权 Doc/Web budget 候选。
- `/root/fins_cli_service_audit`：Fins / CLI / Service / WeChat，0 个材料 finding，并完成该范围工具安全新增行扫描。
- 主审重新读取生产代码、设计/计划、测试和 artifact 行号，独立裁决所有候选；子审结论未直接当作 finding 证据。

## 验证

- 审查开始前 `git status --short` 为空；除本 Markdown artifact 外未修改代码。
- focused regression：

  ```text
  pytest -q \
    tests/host/test_accepted_result_projection.py::test_projection_unsafe_argument_keys_return_limited_signal \
    tests/host/test_accepted_result_projection.py::test_projection_uses_semantic_query_status_result_and_business_source \
    tests/host/test_accepted_result_projection.py::test_projection_filters_internal_source_refs \
    tests/host/test_phase6_toolruntime_integration.py::test_fetch_more_uses_same_toolruntime_accept_eventlog_path \
    tests/tools/test_doc_tools_provider.py::test_read_file_source_limit_plus_one_raises_typed_resource_failure
  ```

  结果：`5 passed in 0.64s`。这些通过结果证明当前测试确实固化了被审查路径；不表示 findings 已修复。

- 只读 helper diagnostic：`file_path -> True`、`scope_token -> True`、`ticker -> False`，验证 F-01 对合法现有字段的确定性命中。
- `git diff --check b1a0631f^ HEAD` 返回范围内既有 review artifact 的 EOF 空行/尾随空格。它们属于 style/hygiene，按用户要求未报告 finding、未修改；这也不是本 artifact 引入的问题。
- 未运行全量 pytest/pyright：本任务是只读专项 contract review，没有代码修改；focused tests 足以验证三个 finding 的可达/固化路径。全量正确性与性能回归不在本专项结论的证明范围。

## Open Questions

1. `docs/host/design.md:1613` 与 `:1629` 对 safe arguments digest 是否必须等于 raw normalized digest 相互矛盾。F-01 的实现修复前必须由 Host durable contract owner 先裁决；不得继续用 projection blacklist 绕过。
2. R3-E accepted plan 没有冻结 `get_file_sections` 命中 source byte cap 的公开失败码。应由 Doc tool owner 决定复用 `source_too_large` 还是采用另一种已设计 outcome；在裁决前不能保留 `source_budget_exceeded` 作为事实默认值。
3. accepted evidence 当前没有生产级 business-source producer atom。F-02 应先回到 unavailable；若要公开 filing/source，需另行设计 typed producer contract，不能从 `OpaqueEvidenceRef` 猜测。

## Residual Risk

- 本审查是“无设计真源的过度设计 / 本地最小设计陷阱”专项，不是对 1,317 个文件做全类别 correctness/security/style 复审；非本主题缺陷可能仍存在。
- Web R3-E safety code按 accepted plan 做了语义所有权核对，但本次没有执行独立网络渗透、真实 DNS rebinding 或浏览器 sandbox 验证；结论仅为“不是无需求过度设计”。
- F-02 当前生产 refs 为空，因此现时主要损害是虚假的测试/public projection contract；unknown ref 真正进入生产后的泄漏面取决于未来 producer，但默认公开规则本身已由当前代码和测试确定。
- 该 artifact 不修改生产代码、测试、README 或总控；三个 finding 均保持未修复。
