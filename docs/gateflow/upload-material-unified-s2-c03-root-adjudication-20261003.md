# S2 US2-C03 总控裁决：必填构造参数的既有测试调用迁移

## 状态与直接依据

US2-C03：**accepted / 未修复**。同一个统一修复 WU、同一 S2，HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`，唯一 workspace `/Users/leo/workspace/dayu-agent-r`，唯一分支 `codex/upload-material-oracle`。不增加 slice/gate、业务范围或新验收规则，不改原计划和冻结任务/白名单的字节。

当前 runner `upload-material-unified-s2-final-completion-sol-20261003-01` 首次 full pyright 实际 PID 32504、exit 1、127 errors；总控读取了 `workspace/tmp/upload-material-unified-s2-final-completion-sol-20261003-01/types-01/{actual-exit.json,stdout.txt}`，逐项核对四个文件中报错构造调用与生产 SEC/CN required `material_upload_state_repository` 签名。报告中四个文件目前字节均与本轮 input-sha256.json 相符，没有在授权前修改。

动机成立：这是已接受 required repository 接口的直接调用迁移。装配负责显式提供同一工作区的实际材料状态仓储；测试不能倒逼生产接口保留默认参数或 fallback。

## 本轮最窄白名单补充

本记录独立补充 allowed-files.json，以下四件从保护输入转为获准测试候选。首核 SHA 如下，最终审计保留原冻结文件，明确依据本补充排除这四件的预期合法变更；其余保护输入继续逐字校验。

- `tests/fins/test_cn_download_workflow.py`：`590a4b694bd56868b6ddd17dd4dd3db4ca1834b956f713e6e57269423accbdef`。
- `tests/fins/test_processor_read_consistency.py`：`135f77414ae6006dc81b52eb5df34a61cc393b345aa03fb92635c5892302fa59`。
- `tests/fins/test_sec_pipeline_download.py`：`2856675842d4f2bbf85fa3fdf9b063baa9a37cd7a2b81b8dc62f96dbef7d7a4e`。
- `tests/fins/test_sec_pipeline_download_stream.py`：`dc2f9a18dc3dd6a7e8514a91c51aa7330e6e44bda2fa48a9e20863f69a76331d`。

只允许补齐真实 SEC/CN 构造调用的显式 `material_upload_state_repository` 和必要仓储导入、装配 docstring。优先复用已有 runtime/repository_set；否则同一 workspace 的真实 FsMaterialUploadStateRepository，不能 fake、optional/default、pyright ignore 或修改原 download/read 业务断言、期望值、跳过测试。全部现存构造调用均须迁移，不只 pyright 报错行；没有报错的新业务变化不属于本补充。

四个文件加入受影响测试选择，运行对应现有测试，最终 full pyright 必须为 0。原有要求和 V7–V14 验收继续有效。本项经实施、同版 MiMo/ds-flash 审查与总控复核后才能登记已修复；不因这份批准直接记 pass。

## 当前执行

托管 session 32721 在途，不重派、不终态核收。当前 runner 按已交接的 root 新裁决文件读取约定，在下一独立目标后或最终报告前读取本记录并同轮继续。其余已授权代码和验证持续推进；该常规必填构造迁移无需用户再次确认，不把它升级为业务审批。
