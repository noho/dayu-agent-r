# Plan Review — UF-FIX01 correction 独立裁决（AgentDS）

- **目标**：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-correction-20260813.md`
- **输入边界**：仅 7 个列名文件；未做搜索、子 agent 或读取未列文件。
- **裁决结论**：**PASS**

## 四项独立裁决

1. **tri-state owner — 成立**。直接证据：`_fs_identity.py` 的
   `_identity_directory_for_read` docstring 明确「目录不存在时仍返回确定性 locator」
   （`_fs_identity.py:299`），实现只在 `exists() or is_symlink()` 时读 descriptor
   （`_fs_identity.py:316`），absent 从不抛 `FileNotFoundError`。correction 对 accepted
   plan 错误假设的判定属实；新增 `_identity_directory_if_present_for_read`（identity
   owner）与 `_ticker_dir_if_present_for_read`（infra 委托）分层正确，不泄漏给
   CLI/pipeline。
2. **lazy create_directories=False — 成立**。直接证据：`sec_pipeline.py:526` 与
   `cn_pipeline.py:363` 在 `or` 链前无条件调用
   `build_fs_repository_set(workspace_root=...)`，全注入时仍构造 eager set；
   `_fs_storage_infra.py:419` `create_directories` 参数已存在且
   `_fs_storage_infra.py:452` 以此门控 mkdir，`_should_manage_batch_state`
   （`_fs_storage_infra.py:1370`）同样尊重该 flag。correction 方案可行。
3. **非空 source fixture — 成立**。直接证据：`_fs_storage_infra.py:937-939`
   `_validate_complete_source_files` 对 `files` 非 list 或为空抛 ValueError，空
   `files=[]` fixture 会在 snapshot 断言前于 commit validation 失败。改用真实业务文件
   的 correction 正确。
4. **goal/non-goal/UF-FIX09 drift — 无漂移**。accepted plan §7 已把
   `_fs_identity.py`、`_fs_storage_infra.py` 列入修改文件，§6.3/§6.4 已规定 tri-state
   helper 与 SEC/CN lazy fallback set；correction §4/§5 未新增目标、协议或
   non-goal，未触碰 converter 与 UF-FIX09 范围。correction 是已接受计划的
   code-fact 修正，非 goal/owner/architecture change。

## Findings

### 1-未修复-中-tri-state helper 沿用未验证的 factory 参数
- **位置**: correction §4（lazy fallback set 依赖 `build_fs_repository_set(create_directories=False)`）
- **问题类型**: 契约缺失
- **直接证据**: 本次 7 文件限界内无法核对 `_fs_repository_factory.py` 是否确有该参数
  （accepted plan Q2 声称 Controller 已核验；`_FsStorageInfra` 侧参数已确认存在）。
- **影响**: 若 factory 未透传，S1 lazy 断言仍会失败。
- **建议改法**: 实现首个 commit 前以一次直接读取确认 factory 签名；不需要修改 plan。
- **严重程度（低/中/高/严重）**: 中

## Open questions

无阻断性 open question。

## Residual risks

- `FsFinsIngestionJobStore` jobs 目录 lazy 化仍属 accepted plan S1 范围，correction
  未覆盖，交由 S1 实现与 owner tests 验证。
- 建议在 S1 owner tests 中保留「已注入全部 repositories 时不构造 eager set」断言，
  防止 `or` 链退化为无意义构造。

## 结论

**PASS** — correction 的五项失败根因与修正方案均有直接代码证据支持，无目标漂移、
无 UF-FIX09 越界，可作为 S1 重实现的依据。
