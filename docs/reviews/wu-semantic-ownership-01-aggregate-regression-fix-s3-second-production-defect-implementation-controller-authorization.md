# WU-SEMANTIC-OWNERSHIP-01 Slice 3 第二个 Production Defect Implementation Controller Authorization

## Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` continuation；不是新 WU。
- Implementation base：accepted plan commit
  `9ad5711e20dd35d5a0cdc0cf79067333ff3b3daf`。
- Fixed plan SHA-256：
  `552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04`。
- Accepted-plan commit validation：
  `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-accepted-plan-commit-controller-validation.md`。

## Authorized scope

先关闭 `S3-STOP-F02`，然后继续同一个 Slice 3 implementation；不得开启新 slice 或新 WU。

本次相对现有working tree唯一允许新增production diff的路径：

```text
dayu/fins/processors/sec_form_section_common.py
```

现有 Docling production delta受保护，不得回滚、重写或单独提交：

```text
dayu/documents/processors/docling_processor.py
```

允许继续修改的测试路径仅为：

```text
tests/documents/test_processors.py
tests/fins/test_sec_pipeline_download.py
tests/fins/test_processor_read_consistency.py
tests/fins/test_fins_ingestion_tools.py
tests/host/test_effective_execution_config.py
tests/runtime/test_argparse_exit.py
```

`dayu/fins/README.md` 只有在先读取其更新约束且实现形成稳定用户/维护者可见语义时才允许按触发规则更新。
其它 production、tests、README、design、control、review 与 utility paths 不得修改。

## Mandatory owner contract

`sec_form_section_common.py` 是本缺陷唯一publication decision owner：

1. 使用owner-private typed state精确表示 `BUILDING`、`VIRTUAL_PUBLISHED`、
   `BASE_FALLBACK_PUBLISHED`；唯一transition owner原子发布最终状态。
2. 原始marker验证顺序固定为：base duplicate、dangling、marker duplicate/multi-section/tree/
   bidirectional contradiction；任一矛盾fail closed。只有无矛盾但marker缺失或不完整时whole-base fallback。
3. complete mapping发布完整virtual state；zero-table允许virtual publication；不得把未映射table猜给首个、最近、
   标题或位置章节。
4. 删除 `_filter_table_refs_by_availability()` 的silent filtering与
   `_assign_unmapped_tables_by_position()`；`_remap_tables_to_deepest_virtual_sections()`只能消费同一
   owner-local candidate mapping，并受最终双向校验。
5. 首次refresh就是publication/failure入口；10-K/10-Q第二次postprocess/refresh必须幂等消费同一terminal。
   五个public consumers统一由typed mode读取，不得各自反推状态。
6. Fallback时base section/table identity、title、read/search行为完整一致；complete virtual时同样由一次发布的
   candidate state提供。不得修改`DocumentProcessor` marker contract、`SecProcessor`或两个form-common guards。

## Verification and stop conditions

- 先使已存在的S3-STOP-F02最小public node变绿，再完成accepted plan中的完整六类matrix。
- Fresh回归Docling caption 8-node matrix；不得为了测试通过改写受保护Docling语义。
- 运行六个授权测试文件、canonical suite、AR-F06 exact node、219/219 changed production coverage、full
  pyright、scoped Ruff、build、README触发检查、source/propagation/security scans与plan列出的真实smoke。
- Gemini是低budget测试账号；quota结果固定为
  `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，不得追加真实调用或修改配置、模型、key、
  retry、quota、budget。
- Config与Host internal SQLite/EventLog属于trusted local domain；只在Tool Trace、audit、public、
  LLM-facing、logs/outputs/diff/reviews执行secret明文零泄露检查，不设计新的secret基础设施或统一权限框架。
- 如需要第二个新增production path、公共schema、兼容分支、fallback猜测或deferred Issue能力，立即STOP并报告。

## Handoff

AgentCodex完成后新建 implementation continuation artifact；不得覆盖此前stop artifact，不得stage/commit，
不得自行进入code review。下一gate是Controller独立验证。
