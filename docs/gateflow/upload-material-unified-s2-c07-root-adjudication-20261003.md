# S2 US2-C07 总控裁决：三个读取回归用例的真实材料夹具迁移

## 状态和直接依据

US2-C07：**accepted / 未修复**。同一个 WU/S2，HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`，唯一 workspace `/Users/leo/workspace/dayu-agent-r`、分支 `codex/upload-material-oracle`。不增加 slice/gate、业务范围或验收。

完整 35 模块 `final-wide-01` 实际结果 2633 pass、3 fail、3 skip。总控直接读取 `workspace/tmp/upload-material-unified-s2-final-completion-sol-20261003-01/final-wide-01/{command.json,stdout.txt,junit.xml}`：三项均在真实 create_source_document → create_material → validate_material_source_primary 失败，原因“材料主文件必须精确命中已声明的 Docling 文件”。读取旧测试构造，原材料只有 txt 原件、primary 指原件、缺 Docling role declaration；它们原本验证的是跨来源别名/过滤投影，并不验证接受原件作材料 primary。总控与精确 S1 HEAD 对照，validate_material_source_primary 函数字节未改变。因此应迁移夹具，不能放松生产校验。

## 最窄补充

C03/C04 对这两个文件此前只批准必填参数/调用迁移，不意味着已批准其余任意重构。当前明确新增授权：仅以下三项及它们的已有共用创建 helper 的材料分支，构造符合新 schema 的真实材料 fixture：

- `test_document_alias_across_source_kinds_is_rejected_as_ambiguous`（processor_read_consistency）；
- `test_storage_snapshot_resolves_explicit_kind_and_rejects_ambiguity`（read_runtime_semantic_ownership_guards）；
- `test_list_documents_projects_stable_document_type_and_filter_contract`（同文件）。

允许真实 Fs blob 保存原件和实际 DoclingDocument 序列化 JSON、显式 original/docling file_entries、exact Docling primary、strict amended 与必要 source schema 字段；复用唯一文件名映射规则。保留原 ID/alias、类型分类、财期/过滤/推荐/错误拒绝及缓存业务断言。filing helper 分支和其它原语义保持；不换 fake repository、mock完整性、给原 txt 贴 Docling 角色、删除/xfail 用例或加生产兼容分支。

总控现场已观察 helper 开始迁移为真实 Docling JSON；这只是候选增量，不证明此前窄授权包含该变更，不自动验收。保全其当前代码，按本最窄授权核对完成。当前候选 SHA：

- `tests/fins/test_processor_read_consistency.py`：`93d99118c8a66d94e848fb2707498c2f38edd4560685afb56414bde2d3de0484`。
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`：`26c8cd4e00bff7db35ae29853ab3cad37628b7f0d3fdae67a4c2a25e0c90976d`。

原冻结输入/白名单原件不改；补充仅扩大这两件已有候选中的上述夹具范围，不增文件数。必要受影响原用例及共用 helper 使用者实际回归、最终 pyright、完整最终测试结果与同版双审继续必需。若仅 fixture 或 tests 变化，按对应必要回归恢复 final-wide-01 的三个缺口，不能把旧失败全组记 pass；没有新的产品源码风险时不机械再跑全部宽回归。此前任何未经范围核实的候选改动，在最终 root 审计明确分类，不以新授权抹去执行时间线。

当前 runner 32721 在途，按约定读取本 root 新裁决并同轮收尾完整 S2。该 finding 等真实修复、同版双审和总控独立核收后才标已修复。
