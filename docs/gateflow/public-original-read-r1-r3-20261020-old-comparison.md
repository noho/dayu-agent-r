# OLD 代码对照与根因限定

按用户补充线索，实际只读 `/Users/leo/workspace/dayu-agent`（OLD）当前 HEAD `76037b242d0b14a77281d7bc610429296123c5cb`；工作树干净。读取其 AGENTS 后仅查相关公开阅读链，不修改 OLD、不读取其业务数据、不执行 OLD runtime。保存精确文件快照/摘要于 `workspace/tmp/public-original-read-r1-r3-20261020/old-comparison/`，receipt.json 列出版本与文件。

- R2：OLD `dayu/fins/processors/sec_form_section_common.py:1133` 同样定义 `_COVER_PAGE_MAX_CHARS = 5000`；1165–1166 无 TOC 时直接切片返回，1333 调入。静默裁剪不是本重构新引入的机制。
- R3：OLD `dayu/fins/tools/service.py:1761` 的 `_create_processor` 从 `get_primary_source`（1778）构造阅读 processor；`read_section`（310 起）仅收 ticker/document_id/ref。同样缺少公开按资产名+实际字节版本绑定的原文路径。未用同一 TSM 原件运行 OLD，不能声称它的选件结果必然相同。
- R1：OLD `dayu/fins/processors/sec_xbrl_query.py:487–501` 的真实 `_query_facts_rows` 分支跳过 text block 与 numeric_value is None；不能因下游 service_helpers 存在文本清洗分支，推定真实 SEC 查询可返回非数值事实。OLD `dayu/engine/processors/bs_processor.py:572,745,1151` 等也以 get_text(separator=" ",strip=True)/空白归一化生成便利阅读/表格；不承诺保留原始物理节点、属性或 namespace。

当前可下的结论：三项限制至少在 OLD 对应代码链已有，不能统称为重构新增回归。重构版与 OLD 在样本/安装/入口/表现是否完全相同，尚无同输入运行对照证据；不扩大本任务去重现 OLD 的业务运行。已确认修复目标仍成立：在既有 storage snapshot/processor/read runtime 内补齐原文契约、删除任意静默裁剪，保留便利阅读能力及业务判断边界。

本对照为根因说明与审核依据，不代替本轮开发树公开 API 验收或 merge 后 live 复验。剩余 OLD 动态对照属于 assigned to later work unit；owner 为后续提出 OLD 差异调查的任务，当前无必要先扩大范围。
