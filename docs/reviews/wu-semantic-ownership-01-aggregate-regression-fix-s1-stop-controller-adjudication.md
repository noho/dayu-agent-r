# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix Slice 1 stop Controller adjudication

## 1. 裁决

- 时间：`2026-07-18 17:20:23 +0800`。
- Gate：Slice 1 implementation continuation；不是新 WU、不是新 slice，也不改变 accepted plan 的语义目标或文件 allowlist。
- AgentCodex stop：`VALID / CORRECTLY STOPPED`。真实 compactor smoke 发现同一已授权测试文件中的第二处 stale current-schema oracle；在未获得补充精确授权前停止，符合原 authorization §4。
- Controller verdict：`PLAN_EVIDENCE_CLARIFICATION / TEST-OWNER FIX AUTHORIZED / NOT_PRODUCTION_DEFECT`。

## 2. 直接证据与 semantic owner

- Production owner `dayu/host/compact_payload.py::_input_snapshot_refs_json_vnext` 只发布 `input_snapshot_refs.current_input_ref`。
- fresh real compact artifact 同源发布 `current_input_ref`，不发布 `current_user_input_ref`；manifest/request-digest/artifact 的新唯一关联已经成功。
- 失败仅发生在 `tests/host/test_public_compact_smoke.py` 的 existing continuity oracle 读取 `_CURRENT_USER_INPUT_REF_FIELD = "current_user_input_ref"`，报 `KeyError`。
- 因此 root cause 是 test oracle 未随 current compact schema owner 迁移，不是 production schema 缺字段，也不需要 production fallback、兼容 alias 或历史 schema 分支。

Accepted plan §2.4 与 §4.1 要求对定位后的 current artifact 保持 first/second-run continuity assertion。该要求拥有 continuity 业务断言，不拥有 stale 字段拼写；把 oracle 改为 owner-published `current_input_ref` 是完成原计划、不是扩 scope。

## 3. 补充精确授权

AgentCodex 在同一任务 follow-up 中获准：

1. 只在已经授权的 `tests/host/test_public_compact_smoke.py` 中把 `_CURRENT_USER_INPUT_REF_FIELD` 及对应局部变量/断言迁移为 `current_input_ref`；必须保留“字段存在、类型为非空文本”的 continuity assertion。
2. 不得修改 production、其它测试、README、workflow、config、design/control 或既有 review artifacts；原三个 test mutable paths与固定 implementation artifact allowlist不变。
3. 更新同一 implementation artifact，记录本 Controller 裁决、修复 diff、fresh real-smoke结果及原 stop 后尚未运行的全部 mandatory gates。
4. 从受影响 focused/real smokes开始 fresh重跑，再完整执行 accepted plan §4.1、§6 与原 authorization §4；不能用 stop 前结果替代最终门禁。
5. 若修复后出现 production defect、额外 schema 冲突、额外 path需求或任何新的 stop condition，仍须立即停止。

## 4. 保持不变的边界

- Slice 2/3、code review、commit、push、PR、aggregate deepreview 与 closeout仍未授权。
- Topic 8/9 no-code决定不变；不实现统一 tool authorization framework。
- Issues 142、151、175、177、178及 Web/WeChat/render tracker owner不变，不得偷带 deferred能力。
- `AR-F06 = RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；`AR-F07 = PENDING_RELEASE_BLOCKER`。

## 5. Next entry

AgentCodex same-task implementation follow-up；完成全部 fresh validation 后停在 Controller validation。
