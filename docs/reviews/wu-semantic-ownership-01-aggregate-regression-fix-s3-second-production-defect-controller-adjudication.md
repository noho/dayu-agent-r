# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 第二个 Production Defect Controller 裁决

## 1. Verdict

`S3-STOP-F02 = ACCEPTED_CURRENT_FIX / PLAN_CORRECTION_REQUIRED / NOT_READY_FOR_CODE_REVIEW`。

这仍是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 aggregate regression fix Slice 3，
不是新 WU、不是新 feature / issue，也不是重新打开历史 sub-WU。

AgentCodex continuation artifact
`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-continuation-codex.md`
记录的第二个 production correctness defect 成立。Controller 已用 `.venv` 从公开
`TenKFormProcessor` 入口独立复现：合法最小 10-K HTML 含一张表格时，构造器在
`_refresh_virtual_section_state()` 抛出
`ValueError: 存在无法分配到最终虚拟章节的 table_ref: ['t_0001']`。

当前不得进入 code review。原因不是验证量不足，而是已出现超出已接受 production allowlist
的新 owner 缺陷；按已接受 plan 的 stop condition，必须先纠正 Slice 3 plan、完成双路完整
plan review / fix / re-review，再由 Controller 重新授权恢复实现。

## 2. Direct evidence and root cause

根因由同一公开调用链与同一数据事实直接闭合：

1. `DocumentProcessor.get_full_text_with_table_markers()` 明确约定：不支持 marker 注入的
   processor 返回空字符串，上层必须安全降级。
2. `SecProcessor.get_full_text_with_table_markers()` 正确履行该 contract，返回空字符串；
   不存在必须扩展 SecProcessor DOM marker 能力的设计依据。
3. `_assign_tables_to_virtual_sections()` 遇空 marker 文本立即返回，未建立任何虚拟章节表格映射。
4. 同一次 `_refresh_virtual_section_state()` 随后又要求 base table refs 与 virtual-section table
   refs 完全相等，因此任何“形成虚拟章节 + base 有表格 + marker capability 不可用”的状态必然失败。
5. Controller fresh command：

   ```text
   source .venv/bin/activate && pytest -q \
     tests/fins/test_processor_read_consistency.py::test_ten_k_public_processor_assigns_tables_without_marker_capability
   1 failed, 3 warnings
   ```

真实 AAPL fixture 与最小合法 HTML 命中同一失败，故不是测试夹具伪造状态。

## 3. Semantic-owner adjudication

唯一修复 owner 是 `dayu/fins/processors/sec_form_section_common.py` 的虚拟章节构建、刷新与
table ownership state machine，不是 `SecProcessor` marker producer、`list_tables()` 展示层、
下游 read runtime、测试夹具或 consumer。

纠正计划必须锁定以下语义：

- 虚拟章节 projection 是一个原子状态。只有能够为全部公开 base tables 建立完整、唯一、
  双向一致的 virtual-section ownership 时才可发布。
- marker capability 缺失，或 marker material 不能完整证明全部 base-table ownership 时，
  必须安全降级为底层 processor 的原始 sections / tables / read_section contract；不得把表格
  猜到第一个/最近章节，不得按顺序、标题、文本相似度、日志或偶然 `section_ref` 发明业务归属。
- marker capability 可用且映射完整时，继续由同一个 refresh owner 一次发布
  `_virtual_sections`、`_virtual_section_by_ref` 与 `_table_ref_to_virtual_ref`，并保持重复、悬挂、
  双向不一致 fail-closed 校验。
- `list_sections()`、`list_tables()`、`read_section()` 必须只消费已经发布的同一个状态；
  `list_tables()` 不得保留下游“最近一次/首章节”补偿来伪造缺失 mapping。
- `DocumentProcessor` marker contract 与 `SecProcessor` 的空字符串能力声明保持不变；本轮不新增
  DOM/raw HTML marker 实现、不修改 `sec_processor.py`、不引入新 capability schema 或 fallback helper。

该裁决选择原子回退而不是“把所有表格塞给首章节”，因为后者只能让集合校验通过，却会把未知
业务归属伪装成已知章节事实，违反 AGENTS.md 的唯一真源与禁止下游补偿约束。底层
`SecProcessor` 已拥有同源且双向一致的原始 section/table contract；回退复用该真源即可。

## 4. Corrected-plan scope authorization

只授权 AgentCodex 修改既有
`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，把 `S3-STOP-F02`
加入同一 Slice 3 correction：

- production allowlist 新增且仅新增
  `dayu/fins/processors/sec_form_section_common.py`；
- 保留已经授权的 `dayu/documents/processors/docling_processor.py`；
- test allowlist 保持既有六路径，不因本 finding 扩张；
- continuation artifact 与现有测试/代码 delta 保持受保护；
- 先完成原子 virtual-section fallback 的 owner-level public matrix，再继续九 owner coverage、
  canonical、219/219 coverage、build、scans、smokes 与 security gates；
- 新 stop conditions 至少覆盖：需要第三个 production path、需要改变 base marker contract、
  需要猜测表格业务归属、需要兼容分支/下游 fallback，或任何受保护路径漂移。

纠正计划至少要列出以下测试反例：

1. 真实 public `TenKFormProcessor` + marker unsupported + base table：构造成功并原子回退，
   list/read/table 双向一致；
2. marker supported + complete mapping：继续发布虚拟章节，映射精确且双向一致；
3. marker supported but incomplete：不发布半套虚拟章节，原子回退 base contract；
4. duplicate / dangling / contradictory mapping：仍 fail-closed，不被 fallback 吞掉；
5. 零表格文档：不因 marker unsupported 无意义地放弃合法虚拟章节；
6. 10-K / 10-Q 二次 postprocess refresh 在已回退状态下保持幂等，不重新触发失败或半状态。

## 5. Gate and retained decisions

- 当前 gate：`Slice 3 second production defect plan correction by AgentCodex`。
- next gate：AgentMiMo / AgentDS 并发完整 plan review。
- implementation、code review、aggregate、accepted commit、push、PR、closeout 均未授权。
- `S3-STOP-F01` 的 Docling 修复与 8-node caption matrix 保留在 worktree，状态是
  implementation-done / review-pending，不回滚、不单独 review/commit。
- `AR-F05` 仍 open；`AR-F06` 保持 retained/unfixed/unwaived；`AR-F07` 保持真实 Windows
  evidence release blocker。
- Config 与 Host internal SQLite/EventLog 继续是 trusted internal；Tool Trace、audit、public、
  LLM-facing、logs/outputs/diff/reviews 继续要求 secret 明文为零。
- Gemini quota 继续是 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`；不得追加
  真实请求或修改 config/model/key/retry/quota/budget。
- Issues 142/151/175/177/178、Topic 8/9、统一 tool authorization framework 与其它 deferred
  能力仍不进入本 correction。
