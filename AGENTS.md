# AGENTS.md

本文档面向后续开发者（人或 AI Agent），说明 psi-agent 的设计思路、代码结构、开发约定以及我们在开发过程中沉淀的最佳实践。

## 设计理念

psi-agent 是一个**微内核**式的 agent 框架。核心理念是：

1. **最小化核心**: 框架本身只提供通信协议、组件组合和 tool/Schedule 加载机制
2. **功能由 agent 包定义**: tools、system prompt 从 **agent** 目录加载（``Session.agent``；空则与 workspace 同根兼容）。用户 **workspace** 是打开目录（相对文件 IO），**定时任务 `schedules/` 例外地从 workspace 加载**（见坑 17）；**AppData** 是进程记忆区（todos / history / Gateway state）
3. **组件无状态**: AI 后端不保存任何状态；Session 只维护一个内存中的 history（落盘在 AppData）；Channel 不管理历史
4. **组合优于继承**: 三个独立组件通过 socket 任意组合
5. **一切异步**: 所有 IO 操作使用 `anyio`，永不使用 `asyncio` 原生 API 或 `pathlib`
6. **零抑制**: 不堆 `noqa`，不设 `per-file-ignores`。代码本身应符合规则
7. **显式单 choice 模型**: Session 和 AI 之间每 SSE chunk 保证恰好 1 个 choice。多 choice 作为错误处理，0 choice 静默跳过（心跳）
8. **zero `sys.exit`**: 所有 `run()` 方法必须可作为协程嵌入任意 event loop 中运行，不仅限于 tyro CLI 上下文。错误用 `raise`，禁止 `sys.exit(1)`
9. **`setup_logging` 第一行**: 每个组件的 `async def run(self)` 方法中，`setup_logging(verbose=self.verbose)` 必须是第一行可执行语句，先于任何 token 解析或参数校验
10. **参数透传**: Channel 请求中除 `messages` 外的不认识参数全部穿透到 AI 层，不丢失
11. **类型精确化**: 避免裸 `tuple`/`dict`。尽量用 `tuple[X, Y]` 或具体类型（如 `aiohttp.BaseConnector`）
12. **关键字参数风格统一**: `__init__` 参数顺序 ≡ 初始化赋值顺序。所有 connector 使用显式 `path=`/`ssl=` 等关键字
13. **可取消**: 所有 `run()` 协程必须可在外部被 cancel，`finally` 块清理资源（close socket / stop bot / shutdown updater）

## 架构决策记录

以下是设计过程中有意为之的关键决策：

**为什么用 Unix socket 而非 TCP？**
Socket 文件天然隔离——不同项目用不同文件路径，互不干扰。没有端口冲突，没有防火墙问题。本地组件通信不需要网络栈开销。

**为什么 AI 是 Server、Session 是 Client？**
AI 后端无状态，不保存任何信息。多个 Session 可以共享同一个 AI backend。如果反过来（Session 是 Server），每个 Session 都要自行配置上游 API，违反"组合"原则。

**为什么 Session history 持久化为 JSONL？**
JSONL 格式零依赖，逐行追加读写简单。现路径为 AppData ``{appdata}/histories/{session_id}.jsonl``（legacy ``{workspace}/histories/`` 双读），`session_id` 可由 CLI 传入以 resume。`SessionAgent.run()` 每次调用通过 ``async with self._conversation`` 进入上下文管理器——``Conversation`` 的 ``add / commit / rollback`` 实现回合级原子性。仅在回合成功完成（stop / tool_calls 全部执行 / unexpected finish / max rounds）时落盘；异常时 ``__aexit__`` 自动 ``rollback()`` 恢复内存到快照，磁盘不落地任何新消息。细节见 `session/AGENTS.md` / `gateway/AGENTS.md`。

**为什么拆 agent / workspace / AppData 三区？**
能力包（tools / system）与用户打开目录、进程记忆区解耦：同一 agent 可挂多个 workspace；定时任务 `schedules/` 跟着 **workspace** 走（同一 agent 挂不同 workspace 应有各自的提醒，见坑 17）；todos / history / Gateway `state/` 进 AppData（`platformdirs` / `--appdata` / `PSI_APPDATA`），避免写进用户项目树。路径助手在 ``psi_agent._appdata``（跨 Session/Gateway，避免循环导入）；**禁止**把 AppData 根塞进 Session ContextVar。分层细节见各层 `AGENTS.md`。

**为什么 socket 文件不自动 unlink？**
支持热换 Server。每个 `session.post()` 新建 TCP/Unix 连接，由 `UnixConnector` 按路径重新 connect。只要新的服务进程绑定到同一 socket 路径，客户端无需重启即可继续通信。auto-unlink 会破坏这个能力——socket 文件需要保留，由新进程手动接管。

**为什么 FusionMethod 的调用序号在命中缓存或成功落盘后才提交？**
调用序号属于可恢复状态。失败的 `session()` / `call()` 不得消耗序号，否则同一调用重试时可能误读下一条历史 binding。显式 `binding_name` 的旧恢复产物也不算本次运行已写入，因此 resume miss 后允许覆盖一次；本次运行再次写同名 binding 才报错。

**为什么 FusionMethod `parallel()` 不照搬 TypeScript 的 grace-period 脱离任务？**
Python 版本坚持 AnyIO 结构化并发：`first` / `any` 取消落后任务后仍等待它们完成清理。这样 `run()` 返回时 binding 与 trace 已封口，不会再被后台任务修改。任务若吞掉取消信号而永久运行，整个并行节点也会继续等待；这是资源与状态一致性的有意取舍。

**为什么 MethodGraph 的 `SelectNode` 是 eager 值选择？**
FusionMethod 的命名选择 `selected == if(condition, artifact_a, artifact_b)` 只决定下游读取哪个值。planner 会等待条件和两个候选 Artifact 全部可用，因此两个候选 producer 都会运行。它不是 lazy 分支、Step activation 或控制流 Region；不要据此跳过未选 Step。多级优先级用多个命名 Artifact 串联，禁止把嵌套 `if` 直接塞进 dataflow List。

**为什么 MethodGraph 同时有 Artifact 依赖和 `depends_on`？**
`ProducesEdge` / `ConsumesEdge` 表示值的来源与可用性；`StepNode.depends_on`
表示没有值传递时仍必须遵守的显式顺序约束。planner 将两类前驱合并为同一组
`Await`，执行器也会拒绝绕过任一前驱的手写计划。结构模型仍允许保存有环图，
包括显式顺序环；one-shot planner 在执行前统一拒绝 circular await。
`independent` 只是非约束 metadata，不能覆盖数据依赖或显式 `depends_on`。

**MethodGraph 的资源调度边界是什么？**
`.method` 只通过 `resource_requirement` 声明 Step 所需的资源种类和数量；容量或
具体实例 ID 由 runner 外部配置。执行器在同一个 admission 临界区中同时检查
`max_concurrency` 和全部资源需求，原子取出实例，并在成功、失败、超时或取消后
shielded release。`DispatchContext.resource_lease` 负责把具体实例传给 dispatcher，
但执行器不会自行绑定 GPU、设置环境变量或调用工具。allocator 是进程内对象；
跨进程/跨主机租约和 shared/exclusive 模式不在当前合同内。

**MethodGraph checkpoint 与 Human 跨回合等待的边界是什么？**
`ExecutionCheckpoint` 只保存已经物化的 Artifact 值，以及依赖闭包完整的已完成
Step / Select ID，并绑定非空 `method_id` 与 graph/plan 结构摘要。checkpoint 值只
接受 finite JSON；恢复时按 JSON 类型和值递归比较，因此 `true` 不等于 `1`。执行器
还会严格校验已完成 ID、输入和值集合，预先发布已完成事件并跳过这些操作；
`checkpoint_observer` 必须成功持久化后才允许依赖者继续。它不是任意缓存命中或
unbound graph/plan run-directory resume。

Session 在一个请求的完整 agent/tool loop 期间持有 `_lock`，因此 workspace tool
不能在 Human Step 内阻塞等待“下一条用户消息”，否则下一条消息无法进入同一
Session。G4 workspace adapter 必须先保存 checkpoint 和 Human request，返回到父
Session，通过既有 `clarify` 格式化问题并结束当前 turn；下一轮再用匹配的
`run_id` / `request_id` 恢复。人工等待期间不保留资源 lease，method/Step timeout
也在每个恢复阶段重新计时。该 adapter 属于 workspace，不把 Human 交互或持久化
塞进 `psi_agent.method_execution` 核心。

G4 workspace adapter 还会把每次运行已经物化的输入、中间、选择及最终 Artifact
逐个原子写入 method bundle 的 `runs/<run-id>/artifacts/*.md`。字符串保持原
Markdown，其他 finite JSON 值用 fenced `json` 表示。该目录是用户可见的运行历史，
不参与 checkpoint 恢复，也不跟 `.psi/fusion-method/runs/` 的 Human 私有状态混用；
纯 Agent/Program 运行仍不可 resume，但其中间 Artifact 不能因此丢失。
