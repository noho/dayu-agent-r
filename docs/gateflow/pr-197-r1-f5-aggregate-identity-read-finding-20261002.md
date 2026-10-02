# F5-AG01：published source 读取绕过 ticker 身份校验

状态：accepted / 已修复（2026-10-02 同版双路复审及 root 核收通过）。严重度中。owner：dayu.fins.storage 的 published-read 根解析/共享core委托边界。destination：当前同一F5-S1 work unit的aggregate fix/re-review，不新WU/slice，不改用户财期裁决。

MiMo aggregate report docs/reviews/code-review-20261002-113431.md、managed55260 outer0，指出 `_get_source_meta_unguarded` / `_list_document_ids_unguarded` 从原 `_ticker_dir_for_read`变成 `_target_ticker_dir`：后者仅计算路径，漏 `_read_published_company_identity`。list/get/meta-view与locator/company/batch的错误语义分裂，坏descriptor可能被CN rebuild空结果掩盖。原acceptedplan§3承诺F4 published方法原行为不变。

root已读取真实两root函数与两wrapper及report/probe；当前code0d8de8cb，source输入77/validation11首末match。正在独立复现后裁决。MiMo-flash38354仍只读在途，未修改冻结产品/未aggregatepass。已有IV01–05仍为已修，无业务裁决重开。

必要修复方向若成立：owner published wrapper恢复原严格根解析，保持共享privatehelper、同guard/finally/actualstaging/Rawwholekind原语义；不在workflow/runtime/CLI加fallback，不收紧合法名字、不改schema。正式owner回归应覆盖坏ticker descriptor的三读入口、正常缺席/完整文档、locator及wholekind原异常类别；CN rebuild空命中不能变正常成功。精确改法交gpt-6-sol以真实源验证，root不代实施。

## Root 独立裁决

根因成立；不是财期业务裁决扩展。真实 FS staging 创建 A/B 后正式 commit，正常三个读入口成功；仅把 ticker descriptor 写成 `{}` 后，严格 `_ticker_dir_for_read` 抛 `CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")`，当前 list 返回 A/B、get 返回业务版本A、meta-view两条且无read_error。冻结77源码及11验证原件首末SHA不变。正常空目录的reviewer反例及已有实际文档的root反例共同证明读契约回归。基线3a的get经 persisted path → source root →严格ticker根，list亦严格ticker根，已从git show逐段保全。

独立证据：`workspace/tmp/pr197-f5-aggregate-20261002/root-validation/identity_read_probe.py`、`identity_read_probe_02.stdout`、`identity_read_probe_02.stderr`、`identity_read_probe.receipt.json`、`identity_base_contract.json`。首次临时入口未设repo PYTHONPATH导入tests失败exit1；补显式PYTHONPATH后全新根第二次exit0、stderr空，错误保留未覆盖。没有改生产源码/fixture、没有归入provider重试。

裁决 accepted，当前未修复；阻塞当前aggregate，不回滚已accepted code checkpoint。等MiMo-flash终态后将同版必要findings集中交Sol一次fix；不新增slice、不开始upload原队列、不绕Raw wholekind的独立unsafe_publication语义。

## 初审核收与保全

MiMo55260外层0、16231个合法LF事件、78调用与结果全部配对，当前校验文件实际读取一致，77源码/11验证原件首末无漂移。两个未引号echo导致zsh失败，后续对应helpers/测试来源实读恢复；一次coverage列表误当dict被末尾命令掩盖，下一调用逐件23条正确恢复。无关键取证缺口；stderr仅精确SDK非致命warning，报告header模型简写以terminal modelUsage为准，不开文案loop。report全46产品diff实读并对照基线，关键根解析与发布guard已root实核，接受其证据与唯一AG01 finding，不以作者自报代验。

已将独立复现源/输出/真实exit及git基线段、初审root receipt保全为正式`docs/gateflow/evidence/pr197-f5-aggregate-20261002/`。当前aggregate未通过；其余IV01–05已修状态保留。

目录纪律：可执行临时探针保留在`workspace/tmp/`；正式证据目录仅保其原字节文档档案`identity_read_probe.source.txt`（与实际执行源逐字同SHA），不提供docs下脚本入口。

## 最终修复状态（覆盖上方历史进度）

accepted / 已修复。唯一生产 delta 在 published-read owner 的两个 wrapper 恢复严格 `_ticker_dir_for_read`，共享 core/staging/whole-kind 语义不变。gpt-6-sol 完整交付及真实红→绿见 `pr-197-r1-f5-aggregate-fix-implementation-20261002.md`；root核收及新1747/fullpyright0/23生产覆盖≥80与独立44绿见 `pr-197-r1-f5-aggregate-fix-author-root-acceptance-20261002.md`。MiMo/MiMo-flash同版复审 `docs/reviews/code-review-20261002-130652.md` / `code-review-20261002-130446.md` 及root最终aggregate裁决验证已修；两路managed外层0，86输入/37验证原件全部samebytes。无未修accepted finding，不新WU/slice。最终真实CLI/后续upload队列仍未实施。
