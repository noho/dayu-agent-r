# S2 回归发现 US2-T01：仓储 provider 测试夹具须迁移到严格材料契约

## 即时登记

状态：accepted / 未修复；属于当前 S2 的 owner 级测试迁移，不新增业务规则或 slice。总控在 S2 实施者在途期间读取了 `workspace/tmp/upload-material-unified-s2-implement-sol-20261002-01/storage-coverage-01/stdout.txt`：实际 pytest exit 1，104 passed、5 failed，失败均在 `tests/fins/test_fins_storage_provider.py`。完整 failed 票据保留，不记成通过。

五个失败用例：

- `test_snapshot_explicit_source_kind_ignores_other_kind_with_same_document_id`
- `test_complete_filing_and_material_commit_share_one_source_truth`
- `test_read_runtime_citation_projects_provider_owned_source_types`
- `test_read_runtime_citation_inventory_uses_complete_published_sources`
- `test_list_documents_meta_less_corpus_coexists_with_healthy_alias_corpus`

真实 traceback 指向 `create_source_document` → `_upsert_source_document` → `validate_material_source_primary`，材料旧夹具的文件声明没有提供已承诺的完整 Docling 主源/角色。总控已读失败输出及该测试文件的相关 source 创建调用；这不是根据覆盖率推断产品故障。当前完整 S2 尚在实施，最终 amended required 合同也必须由合法 producer/夹具明确提供真实布尔值。

## 裁决与最窄授权

项目 AGENTS.md 要求测试跟随 owner 边界迁移，不得为旧 fixture 在产品增加兼容/default/fallback。计划 §6.6 的完整仓储/读回与 V14 回归同样要求合法完整源。因此，完成 S2 时额外允许修改 **`tests/fins/test_fins_storage_provider.py` 单文件**，仅迁移上述失效材料 fixture 及其共享构建 helper，以真实 blob 存储、精确文件声明/Docling role/primary 和显式 amended 事实构建当前契约。保持这些测试原本关于 namespace、来源、citation 和 meta-less corpus 的业务断言。

禁止放宽 `validate_material_source_primary`、删掉测试、xfail/skip、用 mock 替代真实仓储、增加旧库兼容或默认 amended。这是同一 S2 implementation 的测试白名单补充；不修改已冻结计划字节。待当前 runner 取得终态后，在下一次同 gate 集中收尾的冻结白名单中加入该单文件，将本 finding 交 gpt-6-sol 修复，MiMo/ds-flash 审查并由总控核实最终测试证据后才标已修复。

## 证据与风险

证据根 `workspace/tmp/upload-material-unified-s2-implement-sol-20261002-01/storage-coverage-01/` 包括实际 command/stdout/stderr/exit，不能以其它 2011 passed 套件排除该失败。本项未修复前不得通过 S2。最终逐修改产品文件覆盖及 full pyright 仍须核实；当前 71.31% 的完整性 owner 覆盖不构成通过。
