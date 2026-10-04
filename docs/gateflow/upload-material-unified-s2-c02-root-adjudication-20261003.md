# S2 US2-C02 总控裁决：显式传递该次提交的完整最终状态

## 状态、范围和直接依据

US2-C02：**accepted / 未修复**。本记录是同一个统一修复 WU、同一个 S2 implementation 的最窄接线补充，不新增 slice/gate、业务规则、持久 schema、用户可见 JSON 字段或验收标准。唯一 workspace `/Users/leo/workspace/dayu-agent-r`，分支 `codex/upload-material-oracle`，HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`；原计划 SHA `c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea` 保持不变。

直接证据来自同一条返回链，已由总控读取核对：

- 已接受计划 §6.2：storage 的 `commit_material_upload_batch(batch)` 在发布 guard 内形成并返回 `MaterialUploadPublishedState`。
- §6.7：`MaterialUploadPublicationOutcome` 必须含该次实际 `published_state` 和 `UploadOperationResult`；取消没有成功状态。D 仍唯一负责 staged write、最终取消检查和一次 capability 转交。
- §6.7 指定 D 的返回类型仍为 `UploadOperationResult`，明确新增了 source kind 和 published amended，却漏写完整最终状态从 D 返回到 executor 的通道。
- 当前 `dayu/fins/pipelines/docling_upload_service.py` 的 `UploadOperationResult`、`commit_prepared_upload_batch` 及 S2 实施报告 `upload-material-unified-s2-completion-report-20261002.md` 的直接路径印证该缺项。提交后另一次 read 不能证明它属于同一次 publication。

动机成立：必须保留已有计划所要求的实际 final，避免提交后读到后续版本或复制生命周期。语义 owner 是 storage 的 final 产生边界；D 负责原样传递，material publication executor 消费。

## 批准的最窄补充

在 `UploadOperationResult` 增加**显式必填、无默认值**的内部 typed 字段：

```python
material_published_state: MaterialUploadPublishedState | None
```

执行规则：

1. 材料 mutation 正常 commit 返回后，D 将 storage 返回的同一个完整 final 原样放入该字段；`published_amended` 从该 final 的严格材料事实投影。正常成功不能用 None，也不能重读或由 request 重建 final。
2. 材料 verified skip / 健康重删 no-op 的正常结果携带相应权威 guard 已验证的完整状态；不得假造 mutation commit。metadata-only、内容发布和删除仍按已有计划各自路径消费实际结果。
3. filing 和 cancelled 结果显式传 None。异常路径仍抛原 typed/operational 异常，不构造成功 final，不 retry/rollback 已转交的 capability。所有真实构造调用显式迁移；不加兼容默认、optional repository 或 shim。
4. material executor 直接取该字段构造 `MaterialUploadPublicationOutcome.published_state`，与 result 中的 final 保持同源；不能提交后 readback、共享可变 side-channel、回调、额外返回生命周期或 extra payload。
5. 仅内部 typed 交接携带完整状态；CLI/tool/LLM-facing JSON 保持已接受计划的字段和业务语义，不输出内部完整状态或 opaque revision。filing 原返回形状、业务规则和取消合同保持。

对应变更均在已有白名单中的 `docling_upload_service.py`、新 material publication owner、真实 caller 和相关测试。该补充落实已经批准的 final 成功信号，不引入新业务承诺，因此无需重新要求用户确认范围；原计划字节不改。本 finding 必须经实施、同版 MiMo/ds-flash review 和总控核实后才标已修复。

## 验证与后续执行

owner 级测试验证 storage 正常 final → D typed result → executor outcome 为同次事实，后续独立 publication 不能改变先前返回；filing/取消 None，材料正常结果不能缺 final；COMMITTED 后 release 异常不伪成功、不重读/重试/回滚；五旧 caller 及新增 executor 的 required 参数/构造全集保持。

当前 runner `upload-material-unified-s2-completion-sol-20261002-01` 仍在运行，不把 task blocked 当进程退出。总控不覆盖其报告或冻结输入。若其本轮读取到本记录，可按本记录继续完整 S2；否则待其真实终态核收后，把该明确裁决及完整剩余任务交接给 gpt-6-sol 集中续完，仍不增加 implementation slice 或提前送部分代码审查。

## 风险归属

该接线缺项属于当前 S2 必须修复；未修复前 S2 不得通过。不可观测公司历史仍按 US2-C01 已裁基准，原 US2-T01 与全部 V7–V14 验收保留。S3/XBRL、全 PR 审查及 WU 后 CLI CI/registry 的原归属不变。
