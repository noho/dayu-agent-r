# repo review fix - Codex

## 范围

- 修复来源：`docs/reviews/repo-review-20260529-204703.md`、`docs/reviews/repo-review-20260529-205643.md`
- Gate：`code-review-fix`
- 执行者：implementation/fix AgentCodex
- 日期：2026-05-29

## 已修复项

1. F1 EventLog 同 `event_id` INSERT 阶段 UNIQUE 冲突重新分类。
   - 证据：`append_event()` 原本只在 INSERT 前读取既有 row；INSERT 失败会被 transaction runner 归为通用 unique error。
   - 修复：INSERT 捕获 `sqlite3.IntegrityError` 后重新读取 `event_id`，同 digest 幂等返回，异 digest 抛 `HostEventIdentityConflictError`。

2. F2 Ollama `api_key_ref=null` 合法。
   - 证据：`models.json` 内 Ollama 为 `api_key_ref: null`，Service 原先强制要求非空。
   - 修复：`RunnerSpec.api_key_ref` 支持 `None`；Service header 渲染在 `api_key_ref=None` 时不要求 env，也不注入 Authorization。

3. F3 `HostDurableStore.close()` 拒绝活跃 transaction。
   - 证据：close 原先直接关闭 SQLite connection，可能触发隐式 rollback。
   - 修复：`HostTransactionRunner` 记录活跃 transaction，store close 发现活跃 transaction 时抛 `HostDurableError`。

4. F4 `ToolCallRequest.arguments` 构造期校验。
   - 证据：原先只校验 call id、name、index。
   - 修复：拒绝空白 key，并递归拒绝非有限 float、空白嵌套 object key 与非 JSON 兼容值。

5. F5 RunnerDone 不再静默覆盖更早完成原因。
   - 证据：ContentCompleted 与 Done 不一致时只打 warning，随后用 Done 覆盖。
   - 修复：不一致时保留先到的 ContentCompleted `finish_reason`，仍记录 Done 的 provider request id 与 warning。

6. F6 startup recovery 无 wakeup port 时输出 ERROR 诊断。
   - 证据：`dispatch_wakeup_port=None` 时 `ACCEPTED/QUEUED` promotion session 只进入结果对象，不会被唤醒。
   - 修复：存在待 promotion session 且无 wakeup port 时记录 `host.recovery.queue_promotion_wakeup_unavailable`。

7. F10 owner liveness pid 非正不再无限 inconclusive。
   - 证据：`StdlibPidLivenessProbe.collect(pid<=0)` 抛 `ValueError` 后被转成 `None` evidence，stale owner 走 inconclusive。
   - 修复：orphan classifier 读取到非正 pid 时直接产出 `owner_pid_missing` positive orphan proof。

8. F14 空 `ToolDefinition.name` 与空 `ToolBundle` 拒绝。
   - 证据：空 name 与空 bundle 原本可构造。
   - 修复：`ToolDefinition` 拒绝空白 name，`ToolBundle` 拒绝空 definitions。工具发现 no-tool 路径改用内部 sentinel，不向 Host construction 传空 bundle。

9. F15 `fallback_mode` 最终值二次验证。
   - 证据：`merge_agent_policy_config()` 只验证 default/profile，直接构造 run override 可绕过解析器。
   - 修复：对 `_select_value()` 选出的最终 `fallback_mode` 按来源上下文再次枚举校验。

10. F16 prompt 渲染不因非完整双花括号字面量失败。
    - 证据：渲染后额外用 `"{{" in rendered or "}}" in rendered` 拒绝残留，导致字面量被误判。
    - 修复：移除简单子串检查，仅保留完整 placeholder pattern 检查。

11. repo-review-20260529-205643 F05 删除 `pyproject.toml` 中不存在 `pytest.ini` 的误导注释。

## 裁定不改项

- Service 绝对路径配置逃逸验证：当前 `_resolve_project_path()` 明确支持绝对路径，配置来源是 package defaults 与 workspace config 这类受信任部署配置；现有 smoke / service 语义依赖绝对路径可用。本轮不强行收窄行为，避免把部署配置能力误改成安全沙箱策略。
- WAITING 超时取消、Service 生产入口迁移、execution profile 继承、memory rebuild 两阶段原子化、compaction budget estimator 二次校验、测试全局 conftest 重构、端到端压测：均为总控裁定暂不实施项，未混入本轮 bugfix。

## 测试与验证

- `source .venv/bin/activate && pytest ... -q`
  - 受影响测试集合共 163 个通过，覆盖 contracts、engine runner spec / finish reason、durable transaction / EventLog race、recovery、runtime assembly / scene prepare / tools discovery、service assembly、Host admission / public run / per-run tool selection。
- `source .venv/bin/activate && pyright`
  - 0 errors, 0 warnings, 0 informations。

## 残余风险

- EventLog 并发 UNIQUE 测试通过受控 interleaving 覆盖 INSERT 后重读分类分支；SQLite `BEGIN IMMEDIATE` 正常写事务会串行化多数真实 writer race。
- no-tool 仍是合法 Service 场景，但公共 `ToolBundle` 不再允许空集合；runtime tools discovery 内部用 no-tool sentinel 表达空发现结果，Host construction 不接收空业务 bundle。
