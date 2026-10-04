# F5-AG01 aggregate fix：总控作者核收

当前gate aggregate fix交付核收，仅供进入re-review；尚未aggregate/PR/finalcloseout pass。唯一主树/开发branch、HEAD0d8de8cb/mainfac32未动。Sol17484 outer0、112个合法LFJSONL事件、43条实际command_execution、turn.completed，当前校验实际cat结果及报告/last逐字match，stderr空；完整事件/failed命令/产物由root独立核。

根因与owner既有AG01不重开；只改storage两个publishedwrapper的strictticker根解析，仍用现有共享枚举/gethelper及原guard/finally。core 11增4删含必要异常/逻辑删除docstring，业务代码无下游fallback/兼容/schema或额外root规则；2tests真Fs/2README与边界一致。新增44参数用例：32三读/listall×2kind×4corruption、8locator/Rawwholekind/staging、2正常missing/complete/deleted、2CNemptyrebuild。原F5业务断言保留。root逐段actual5件diff检查并独立44pass/126selected外用例，真实managed90159 outer0、stderr0，77源码首末/currentSHA一致。原material/F5裁决不变。

作者原始红测36fail/8pass包含2错误删除控制预期；读真inspector并仅修test预期后34真实ownerfail/10pass，原红记录保留；修后44绿。首轮完整1747pass，但首轮pyright2新test参数具体Fs/protocol错配，改真实Fs共享core注入（不生产cast/shim），必要最终版本重验1747pass/3既有edgarwarnings、全量python -m pyright dayu/ tests/ utils/ 0errors/0warnings。root核完整22选择及参数仅输出/cache改、activation与真实exit/原stdoutstderrSHA、三最终验证77manifest首末及当前逐件一致。23生产实际coverage全部>=80（storagecore86.49，最低hk85.15），规范5件Gitdiff b748d0ab逐字与作者diff一致；普通diffcheck0。最新验证正式可Git移交在`evidence/pr197-f5-aggregate-fix-20261002/`，原stdout可逆base64 envelope保持SHA与EOF，不trim、不冒1703旧结果。

原75readonly/11旧验证原件全部unchanged；6官方Raw和acceptedplan/旧审查未动。三rootcontroller并行管理及root新artifact不归作者修改，作者不stage/reset覆盖。源码只有5授权路径差异；当前还无writerlease以外Agent写产品。

协议偏差单独记录：作者两次用了ps/rg查看模型进程，不符合sub-agents的进程查询纪律；root不采用这些查询作生命周期或实际模型证据，仅采用managed外层终态、原JSONL执行、实际校验与源/验证字节。模型实际字段未由event暴露，报告unknown合法，不以profile/PID补造。此辅助身份查找偏差未修改产品/造成必要取证缺失，不据此把正确产品证据清零或另开微型修复loop；后续prompt显式禁止ps/pgrep/kill-0，root当前无此操作。所有非零已解释/恢复：两红验证为有效反例和已纠正控制，一pyright首失败已实修再验证；无未恢复关键失败/error/结构损坏/伪造终态。

决策：author delivery accepted，AG01代码候选与回归已实现但最终状态仍待双路re-review；不以作者/root绿测试替代门禁。下一同版MiMo/MiMo-flash aggregate窄复审，重点精确修复delta+必要集成，不重复已同字节审面、22大套件或全type。gpt-6-sol作者角色保持；原17upload/XBRL/final真实CI+registry/readiness assigned后续新Agent，当前不实施。readonly整个产品已固定，任何新成立必要修复继续artifact登记，同完整WU，不为nit切slice。
