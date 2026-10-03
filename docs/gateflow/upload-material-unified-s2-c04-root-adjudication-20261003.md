# S2 US2-C04 总控裁决：既有读取合同测试显式标注文档种类

## 状态与直接证据

US2-C04：**accepted / 未修复**，同一个 WU、同一个 S2、HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`，唯一 workspace `/Users/leo/workspace/dayu-agent-r`、分支 `codex/upload-material-oracle`。不增 slice/gate、业务规则或新验收。

总控读取本轮 `workspace/tmp/upload-material-unified-s2-final-completion-sol-20261003-01/types-02/{stdout.txt,actual-exit.json}`：actual PID 32665、exit 1，共 43 errors。其中两个保护文件中的 `_parse_source_document_meta` 测试调用缺显式 `source_kind`。同路径生产读取投影现在必须区分材料 strict amended 与原 filing 行为，不能靠 payload 猜来源或保留默认参数。直接阅读两个文件的原财期/布尔断言与生产签名、分支印证这一必要机械迁移。

## 最窄授权补充

保留本轮原 allowed-files.json、input-sha256.json 字节，额外允许以下两个测试候选从既有冻结输入迁移；总控已逐字验证授权前 SHA：

- `tests/fins/test_fiscal_normalization_contracts.py`：`71024259f3f0a84ae59cf74d74c526af4232496e2068f2936a6243538ff33c71`。
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`：`f0349754d63393215d83c986432ee05f7bd3f972d505f60013e8a9cc9a7fbce2`。

仅补齐 `_parse_source_document_meta(..., source_kind=SourceKind.FILING)` 等真实既有调用与必要 SourceKind import；这些既有用例验证 filing 的既有财期/字段行为，原断言和错误文案保持。若文件中存在明确材料用例，则按其真正来源显式 MATERIAL 并使用已接受 strict 合同，不猜业务事实或新增默认值。不允许 production compat/default、pyright ignore、删测试/xfail、修改其余读取/财期语义或扩大重构。

两个文件纳入受影响原测试，最终 full pyright 0。当前 runner 应读取本新增裁决并同轮完成；最终保护审计保留原输入，明列这两个授权变更和本记录依据，其余保护文件继续零漂移。必须等实施、同版双审和总控复核后才能回写已修复。此补充与 US2-C03 一并是 required 接口直接调用迁移，无需用户重新审批，也不提前送部分代码审查。
