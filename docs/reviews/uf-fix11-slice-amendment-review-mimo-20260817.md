# UF-FIX11 slice-boundary amendment review

## Review 元数据

- reviewed target: `docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md` + `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md` (§10 修订后)
- review scope: slice-boundary amendment 的可行性、原子性、完整性与可执行性
- review date: 2026-08-17 11:12:33
- reviewer: MiMo

## Assumptions tested

1. S1+S2 是否真是最小可绿原子边界
2. 是否遗漏文件/测试/producer/parser
3. 是否错误把可独立投影绑入
4. coverage/pyright/review/commit gate 是否可执行
5. 是否允许红色中间态或范围泄漏

## 当前 dirty diff 断点分析

读取 `git diff HEAD` 后确认：

| 文件 | 状态 | S1+S2 内容 |
| --- | --- | --- |
| `dayu/fins/domain/company_meta_contract.py` | 已修改 | CompanyNameIgnoredChange, CompanyMetaCommitOutcome, company_names_are_equivalent, merge_company_meta_for_commit 返回值变更 |
| `dayu/fins/pipelines/upload_company_meta.py` | 已修改 | requested_company_name 保留，name-only fresh intent 生成 |
| `dayu/fins/storage/repository_protocols.py` | 已修改 | commit_batch 签名变更 |
| `dayu/fins/storage/_fs_storage_infra.py` | 已修改 | commit_batch 返回 CompanyMetaCommitOutcome |
| `dayu/fins/storage/fs_batching_repository.py` | 已修改 | 透传 typed return |
| `dayu/fins/pipelines/filing_upload_publication.py` | **未修改** | SKIP metadata commit、warning projection 未实现 |
| `dayu/fins/pipelines/sec_upload_workflow.py` | **未修改** | SEC terminal producer warnings 未实现 |
| `dayu/fins/pipelines/cn_pipeline.py` | **未修改** | CN terminal producer warnings 未实现 |
| `dayu/fins/company_metadata_warning.py` | **不存在** | warning codec 未创建 |
| `dayu/fins/pipelines/docling_upload_service.py` | **未修改** | UploadOperationResult 未扩展 |
| `dayu/fins/ingestion_runtime.py` | **未修改** | typed warnings parser 未实现 |
| `dayu/fins/service_runtime.py` | **未修改** | SourceKind callsite 未更新 |

**断点结论**：当前 dirty diff 是 S1+S2 的 partial implementation，只完成 domain/storage contract 部分，publication/warning/producer/parser 完全未动。这是正确的 partial 状态，符合 amendment 声明。

## Findings

### 001-未修复-低-S1+S2 原子边界成立性验证

- **位置**: §10 原子 Slice S1+S2
- **问题类型**: 动机不成立（经验证后驳回）
- **当前写法**: 原 Slice 1/2 合并为不可拆分的原子 S1+S2
- **反例/失败场景**: 如果 domain producer 和 publication consumer 可以独立变绿，合并就是过度耦合
- **为什么有问题**: 需要验证是否真的不可拆分
- **直接证据**:
  1. Blocker 文件 `uf-fix11-s1-slice-boundary-blocker-20260817.md` 以 `639 passed, 1 failed` 证明：domain producer 一落地，canonical skip 就失败
  2. `_canonical_skip_requirements_are_met` 要求 `keep + no intent`，但 name-only fresh intent 是 `stage + preserve_published`
  3. 让 SKIP 携带 metadata-only commit 属于 publication owner 变更，不能在 Slice 1 内完成
  4. 修改测试期望会固化错误语义；丢弃 intent 会丢失用户输入
- **影响**: 无。原子边界由直接红测证据支撑
- **建议改法和验证点**: 无需修改；amendment 正确识别了真实 blocker
- **修复风险**: 低
- **严重程度**: 低

**结论**：S1+S2 原子边界成立。这不是人为制造的耦合，而是 domain producer 和 publication consumer 的真实语义依赖。

### 002-未修复-低-文件清单完整性验证

- **位置**: §9.1/§9.2/§10 Allowed files
- **问题类型**: 契约缺失（经验证后驳回）
- **当前写法**: 列出 15 个生产文件 + 14 个测试文件
- **反例/失败场景**: 遗漏关键文件导致实现中途发现必须扩大 scope
- **为什么有问题**: 需要验证清单是否覆盖所有必要改动
- **直接证据**:
  1. §9.1 列出 15 个生产文件，覆盖 domain/storage/pipeline/ingestion/service/direct/CLI/wait
  2. §9.2 列出 14 个测试文件，覆盖 owner/projection/protocol/fake
  3. §9.2 `commit_batch` 全量收敛清单明确列  dayu 3 定义 + test 7 文件/9 定义
  4. 当前 dirty diff 只修改了 5 个生产文件 + 10 个测试文件，剩余是 partial 状态
- **影响**: 无。清单完整且精确
- **建议改法和验证点**: 无需修改；§12.5 `rg -n "def commit_batch" dayu tests` 可验收
- **修复风险**: 低
- **严重程度**: 低

**结论**：文件清单完整。amendment 正确保留了原 plan 的精确文件清单，未扩大也未遗漏。

### 003-未修复-低-可独立投影绑入验证

- **位置**: §10 S1+S2 vs S3 边界
- **问题类型**: 过度耦合（经验证后驳回）
- **当前写法**: S1+S2 包含 SEC/CN terminal producer 和 parser，S3 只做 CLI/wait/direct projection
- **反例/失败场景**: 如果 producer/parser 可以独立于 domain/storage 变绿，就应该拆分
- **为什么有问题**: 需要验证 producer/parser 是否被错误绑入
- **直接证据**:
  1. §6.6 要求 SEC/CN filing terminal JSON 必须包含 `warnings` 数组
  2. §6.6 要求 `FinsUploadPipelineResult.from_pipeline_json` 新增 `source_kind` 参数
  3. 如果 producer 不输出 warnings，parser 就无法解析；如果 parser 不接受 warnings，producer 输出就会丢失
  4. producer 和 parser 是同一 schema 的两端，必须同时变更
  5. S3 只做 summary/durable/direct/CLI/tool 投影，不重新决定 parser schema
- **影响**: 无。producer/parser 绑入是真实依赖，不是过度耦合
- **建议改法和验证点**: 无需修改；S1+S2 是 producer+parser 的原子 schema slice
- **修复风险**: 低
- **严重程度**: 低

**结论**：producer/parser 绑入正确。这不是可独立投影的错误绑定，而是 schema 两端的真实原子依赖。

### 004-未修复-低-Validation gate 可执行性验证

- **位置**: §12 Validation plan
- **问题类型**: 不可直接实施（经验证后驳回）
- **当前写法**: 定义了 focused tests、coverage、pyright、static boundary checks
- **反例/失败场景**: gate 不可执行或门槛不可达
- **为什么有问题**: 需要验证 gate 是否真实可执行
- **直接证据**:
  1. §12.1 定义了完整的 pytest 命令，包含 blocker 测试
  2. §12.3 定义了 coverage 命令和 `>= 80%` 门槛
  3. §12.4 定义了 pyright 命令
  4. §12.5 定义了 `rg` 验收命令和人工检查清单
  5. 所有命令都是标准工具，可直接执行
- **影响**: 无。gate 完全可执行
- **建议改法和验证点**: 无需修改
- **修复风险**: 低
- **严重程度**: 低

**结论**：validation gate 完全可执行。命令明确、门槛清晰、工具标准。

### 005-未修复-低-红色中间态处置验证

- **位置**: amendment + §10 Completion / review / commit boundary
- **问题类型**: 状态机漏洞（经验证后驳回）
- **当前写法**: 当前 dirty diff 保留为 partial implementation，不单独接受/提交
- **反例/失败场景**: 红色中间态被误提交或误接受
- **为什么有问题**: 需要验证红色中间态是否被正确隔离
- **直接证据**:
  1. Amendment 明确声明 "当前原 Slice 1 dirty diff 原样保留为本原子 slice 的 partial implementation；它没有独立 acceptance，不得单独 stage/commit"
  2. §10 声明 "只有完整 review loop 通过后才允许一个 accepted S1+S2 slice commit"
  3. §10 声明 "禁止为原 Slice 1 domain/storage partial diff、原 Slice 2 publication diff 或任一红色/未验证中间态分别 stage/commit"
  4. Blocker 文件明确 "本轮不改测试期望、不越界实施 Slice 2、不创建 implementation acceptance artifact、不 stage/commit"
- **影响**: 无。红色中间态被正确隔离
- **建议改法和验证点**: 无需修改；amendment 和 plan 都明确禁止红色中间态的独立操作
- **修复风险**: 低
- **严重程度**: 低

**结论**：红色中间态处置正确。amendment 和 plan 都明确禁止红色中间态的独立接受/提交。

## Open questions

无。所有关键问题都已由直接证据回答。

## Residual risks

无。本 review 只验证 amendment 的可行性，不涉及实现风险。

## Final plan review conclusion

**pass**

UF-FIX11 slice-boundary amendment 通过 adversarial review。关键结论：

1. **S1+S2 原子边界成立**：由 blocker 红测 `639 passed, 1 failed` 直接证据支撑，不是人为制造的耦合
2. **文件清单完整**：§9.1/§9.2 精确覆盖所有必要改动，§9.2 `commit_batch` 全量收敛清单可验收
3. **producer/parser 绑入正确**：schema 两端的真实原子依赖，不是可独立投影的错误绑定
4. **Validation gate 可执行**：命令明确、门槛清晰、工具标准
5. **红色中间态处置正确**：amendment 和 plan 都明确禁止红色中间态的独立接受/提交

Amendment 是 code-generation-ready 的，可以交给 implementation agent 恢复实现。
