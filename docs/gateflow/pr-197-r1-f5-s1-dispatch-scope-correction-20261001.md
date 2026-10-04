# F5-S1 派发范围遗漏：总控更正

- finding：F5-S1-SETUP-A1，controller dispatch setup，非新业务/产品目标。
- 状态：accepted，白名单已更正，待本新派发启动；旧Sol64747已outer0终态，完整73JSONL/28commands/61current+originals/canary及报告核收，未改产品。
- 直接根因：root指定的allowed_write漏列 `dayu/fins/pipelines/cn_download_rebuild.py`。accepted202行plan §2明确此owner，§5要求rebuild结果 `uncertain_reports`/count必填，当前该函数§83短路HK与§135自身CN结果均由此产生。不能在adapter/default/单调用方补缺字段。
- 本轮真实证据：Sol独占tmp `workspace/tmp/pr197-f5-s1-implement-sol-20261001-01/blocker-repro.stdout` 在真实空Fs对CN/HK rebuild输出均缺必需字段，准确反映当前契约需迁移；实际函数与workflow import已root读取。无产品变更。
- 最小更正：在下一次整完整F5-S1派发允许原计划已列的 `cn_download_rebuild.py`，仅正常空查询/CN明确无unknown与HKtyped结果保持同源必填投影；不改CN财期规则、不扩用户scope，不修改acceptedplan字节。其余必要callers仍按已批准schema严格迁移。
- 旧freeze及原失败/blocked证据保全，不原地改旧freeze或让在途作者违反只读边界；取得旧outer终态后新的unique label/output/stderr/last/freeze启动，角色仍Sol。
- validation：root源码/ownercaller读取，待authorterminal后核完整真实探针/pyright日志；产品pytest/fullpyright/cov尚未执行，不假通过。
- residual：none新业务decision；完整F5-S1后续必需验证与双审继续。

## 同轮补齐已计划CLI消费者权限

root读取 `dayu/cli/output.py:_print_download_summary` 414–450：当前只列known document_rows/旧counts，不展示未知行。acceptedplan §2/§7明确CLI消费public typed unknown、用户要求列B未知，因此该既有CLI展示owner也列下一轮allowed_write，仅从public对象机械打印unknown/count/omission，不计算财期或重构typed状态。原 `tests/cli/test_output.py` 已白名单，覆盖随同完整S1。这是同一派发白名单遗漏批量纠正，不新增业务目标、不另切slice。
