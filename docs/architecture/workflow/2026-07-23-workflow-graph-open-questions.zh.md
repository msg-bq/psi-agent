# Workflow Graph 初版：待讨论点与潜在矛盾

> 本文集中记录图 PR 已发现但不应在初版静态模型中擅自定案的问题。

## 1. 第一原则：图允许有环，但“允许”有三种不同含义

### 1.1 结构允许

`WorkflowGraph` 可以包含 directed cycle，model validator 不拒绝。这满足：

- round-trip 保存；
- lineage 展示；
- SCC 识别；
- 发现 feedback 候选；
- 后续分析器给出诊断。

### 1.2 静态可分析

有环图仍可分析：

- strongly connected components；
- condensation DAG；
- 无输入边的 source components；
- 有无 workflow input/seed；
- 哪些 Artifact/Step 处于同一 feedback component；
- 哪些 output 在图论上不可达。

但是“有 seed”也只是一项必要线索，不足以证明可执行或终止。

### 1.3 动态可执行

真正执行一个环至少需要定义：

- Artifact 是单值、版本序列、事件还是 token；
- workflow input 是 version 0 还是永久可读常量；
- Step 一次成功后能否再次 activation；
- 新 Artifact version 是否重新触发消费者；
- 一次 activation 读取最新版本、固定快照还是指定版本；
- 多个环内 Step 的 commit 是逐步还是 barrier；
- attempt 和 iteration 的编号关系；
- side effect 是否允许重复；
- 失败后回滚哪些 pending values；
- termination 是最大轮数、收敛、condition、事件耗尽还是外部取消。

初版不回答这些问题，因此：

> cycle-valid 不等于 schedule-ready，更不等于 termination-proven。

## 2. 旧文档中的 “DAG” 用词需要修正

7 月 13 日旧设计稿曾把基础 consumes/produces 数据流称作 DAG。用户已经明确：
新设计不是 DAG，允许有环。

建议以后统一措辞：

- 原始模型：directed WorkflowGraph；
- SCC 缩点后：condensation DAG；
- 无环子集：acyclic workflow；
- 不再用 DAG 指代全部 WorkflowGraph。

旧的单调运行草案是：

- Step 初始 pending；
- consumes 全部 available 后可执行；
- 成功后把 produces 加入单调增长的 available；
- 一个静态 Step 只成功一次。

该模型可以执行无环部分，也能保存某些带回边结构，但不能产生迭代语义。若不新增
activation/version，它遇到无 seed 环会永远没有 ready Step，遇到 seed 环也通常只
把每个 Step 执行一次。

## 3. Graph、Core IR 和 runtime state 的所有权

### 3.1 Core IR 拥有什么

- 作者声明的 identity；
- typed constants；
- compound/conditional terms；
- assertions 和 formulas；
- 原始 List 顺序与 multiplicity；
- Agent config、instruction 等非图事实。

### 3.2 WorkflowGraph 拥有什么

- Step/Artifact identity；
- Step 到具体 Executor identity 的映射，但不复制 Executor concept 类型；
- consumes/produces/foreach 关系；
- 少量已闭合的 static policies；
- 为依赖分析准备的规范化视图。

### 3.3 Runtime 拥有什么

- Artifact values 和 versions；
- ready/blocked/running/succeeded/failed/cancelled；
- activation、attempt、foreach slot；
- winner/branch decision；
- timeout/retry/backoff；
- event history 和 trace；
- resume/checkpoint；
- external side effects。

边界原则：如果一个字段只对一次 run 有意义，它不进入 `WorkflowGraph`。

## 4. 当前语法评审与仓库实现不一致

两个 PR 不能把当前 `fusion-flow-next` 当作已经闭合的唯一语法合同。

### 4.1 assertion equality

7 月 18 日评审：

- canonical 输出使用单 `=`；
- 可兼容读取 `==`；
- 二者都表示 assertion equality。

当前 G4：

- `==` 用于 assertion；
- `=` 被用于 formula comparison。

影响：

- 当前 Python Core IR 的 `Assertion` 不保存 token，projector 将缺省视为 canonical
  `=`；显式 adapter 可以接受 `=`/`==`；
- parser/checker 在上游必须决定 canonical lowering；
- Graph PR 不修改 G4；
- 不能宣称现有 BNF 与评审完全一致。

### 4.2 `*_multi`

评审合同：

- 只有 `consumes_multi(step) = {a, b}`；
- 是无序、重复报错、展开后消失的局部关系糖。

当前 G4/Core IR：

- 有 input/output/consumes/produces 四种 multi；
- RHS 是有序、可重复的 List。

Graph 中的边是关系集合。当前 multi List 只作为批量关系载体，源码顺序没有执行
含义；初版兼容 repository dialect 时显式擦除载体顺序并拒绝重复，但会保留全部
依赖关系。若未来某个新 construct 的 List 顺序成为业务语义，应：

- 保留在 Core IR；
- 或新增不同的 ordered construct；
- 不能给普通边偷偷加 position 破坏另一 dialect。

### 4.3 `if`

评审 C04 的 ordered first-match、overlap、default、持久化仍全部 OPEN。当前 G4
却固定了三参数 value-producing `if(condition, then, else)`。

影响：

- Graph PR 不增加 IfNode；
- 旧 `flow.if_` 的执行行为不代表新 DSL 已确认；
- value-level if、control branch、graph Region 必须区分；
- 当前数据边不能表达“未选择分支不会产生 Artifact”。
- Python `core_ir.py` 已有 `IfTerm`，但 TypeScript `src/core-ir.ts` 仍没有对应节点，
  且 parser lowering 未实现；仓库内部也尚未端到端闭合。

### 4.4 formula subset

评审包含 NOT/AND/OR/IMPLIES/IFF，并要求 unknown 不能当 false。当前 G4/Core IR
只覆盖 NOT/AND/OR 和 comparison 子集。

Graph projector 只处理已知 dependency assertions，不声称承接完整 formula。

### 4.5 workflow block 内容

旧设计希望尽量复用 declaration/statement/term/formula；当前 G4 的 workflow block
主要限制为 assertions，常量在文件级。

这属于实验性简化，不应反向写成用户已确认合同。

### 4.6 编译链仍未闭合

Python ANTLR lexer/parser 已生成、提交且可导入，但尚未接入 `parser.py` facade；
Python parser/checker 入口仍是 stub。TypeScript prototype 的 parser/checker/
generator 边界同样未形成可用端到端链。因此 Graph PR 接收 normalized Python
adapter，而不是假装已经有：

```text
FusionFlow text -> parser -> checked Core IR -> graph
```

真实 parser 接入应另 PR 完成。

## 5. Artifact 的类型和身份

### 5.1 是否携带 Concept/type reference

不携带的优点：

- Graph 保持执行依赖视图；
- 不复制 Core IR checker 的职责；
- 模型小且稳定。

携带的优点：

- planner 可以检查 operation input/output；
- graph 单独序列化后仍有 interface type；
- foreach 可以确认 source 是 List、item 是 element type。

初版暂不携带。后续若 executor 需要，应保存 Core IR `Concept` identity 引用，不把
Python runtime type 当语言类型。

### 5.2 一个 Artifact 是一个逻辑变量还是一个具体版本

无环、单次执行时两者看起来一样；有环后必须分开：

- static `artifact_id`：逻辑通道/声明；
- runtime `(artifact_id, version)`：一次 committed value；
- pending output：尚未可见的 attempt-local value。

在该合同未建立前，Graph 只保存 static identity。

### 5.3 input 同时有 producer

结构上它可表示 seed + feedback。运行时可能有三种解释：

1. input 只是 version 0，之后 producer 写 version 1..N；
2. input 和 producer 冲突，应静态拒绝；
3. input 是默认值，producer 存在时覆盖。

初版选择“允许保存、不可据此直接执行”。planner 必须在 cycle policy 明确后再接受。

### 5.4 多 producer

初版拒绝多 producer，因为普通 Artifact 没有：

- branch exclusivity；
- merge；
- last-writer-wins；
- version arbitration。

未来 `if` 应由一个控制 operation 统一产生结果 Artifact，而不是让两个分支普通 Step
各自成为同一 Artifact producer。显式 merge 也应是一个普通 Step。

## 6. Readiness、fan-out 与 join

已确认：

- consumes 是非破坏性读取；
- Artifact 可被多个 Step 读取；
- 多 consumes 是 all-ready；
- 源码书写顺序没有执行含义；
- ready 且无依赖关系的 Step 可以并发；
- 不承诺物理同时、FIFO 或公平。

因此初版不需要：

- ForkNode；
- ParallelNode；
- JoinAllNode。

仍开放：

- any-ready；
- first-completed/first-success；
- winner binding；
- loser cancellation；
- late arrival；
- all-failed；
- retry/replay 是否复用 winner；
- one-shot select 与 stream merge 的区别。

旧 Python/TS `flow.parallel(first/any)` 可以保留为 imperative API，但没有无损的静态
Graph 映射。

## 7. Foreach

### 7.1 已确认部分

- source 为有限、有序、允许重复的 List；
- 每个 index 是独立 slot；
- 重复值不会合并；
- item 是 invocation-local binding；
- 一个静态 Step，不静态复制多个 Step；
- 空 List 产生零 slot和空聚合结果；
- slot 无隐含顺序；
- 输出按 source index 对齐；
- source activation 时冻结；
- slot 与普通 attempt 共享 workflow max_concurrency。

### 7.2 Graph 初版表达

`ForeachEdge(source, step, item_binding)` 能无损表达：

- source；
- 单 Step body；
- local item identity。

它不能表达：

- slot status；
- 单 slot retry；
- partial failure；
- ordered result buffer；
- slot-local intermediate Artifact；
- multi-Step/nested body。

### 7.3 多输出 Step

如果 foreach Step produces A 和 B，合理候选是：

- A、B 分别形成 index-aligned List；
- 每个 slot 只有 A/B 都成功才算 slot 成功；
- 所有 slots 成功后一起 commit 两个 List。

但这尚未正式确认。另一个可能合同是允许每个输出独立 partial completion。初版只
保留静态 produces，不把聚合策略写入 Graph。

### 7.4 partial failure

需要决定：

- 一个 slot 失败是否取消其他 slots；
- 成功 slots 是否保留；
- retry 是 per-slot 还是整个 foreach；
- 耗尽后能否产生 partial List；
- partial List 如何保持 index 对齐；
- 空洞用 error、None、Result 还是不提交。

在决定前，最安全的未来默认可能是 all slots success 后原子提交，但本 PR不定案。

### 7.5 与旧 `forEach` 的矛盾

旧 `flow.for_each` 明确顺序执行、返回 `None`；声明式 foreach slots 没有隐含顺序，
可并行且需要 index-aligned outputs。二者不是同一抽象。

旧 `parallel_for_each` 更接近 slot 并行，但仍没有 Artifact commit 和 partial
failure 合同。图 executor 不应直接把所有 ForeachEdge lower 成旧 `for_each`。

## 8. Retry

已确认：

- `max_attempts=N` 是总 attempt 数，包含首次；
- `N >= 1`；
- 省略默认 1；
- retry 不复制静态 Step；
- attempt 是 runtime state；
- Step timeout 每个 attempt 重新计时；
- backoff 不计入 Step timeout，但计入 Workflow timeout；
- timeout attempt 不提交 outputs。

仍开放：

- 哪些错误可 retry；
- timeout 是否 retry；
- retry 是允许还是必须；
- backoff/jitter；
- partial output；
- side-effect idempotency；
- 耗尽后的 outcome。

所以 Graph 初版只保存 `max_attempts`，不引入完整 RetryPolicy。FusionFlow imperative
runtime 默认 3 attempts 和指数退避；从 Graph lower 时必须显式传 1，不能套 runtime
默认。

## 9. 条件、choice、Region 与普通 cycle

### 9.1 为什么暂不加 IfNode

条件分支需要同时闭合：

- condition 的求值时机；
- then/else body；
- 是否 ordered first-match；
- 未选分支 outputs；
- 两分支 yield 的 Artifact/type 一致性；
- branch decision 的持久化和 replay。

简单加一条 guard edge 会让下游 all-ready 永远等待未选分支。

### 9.2 未来 Region 的可能形态

当语法合同确认后，可考虑：

```text
IfOp
├── inputs
├── then_region -> yields
├── else_region -> yields
└── result artifacts
```

multi-Step foreach 和 structured while 也可能拥有 Region。但当前单 Step foreach 用
ForeachEdge 已足够，不应为了未来统一而先包一层空 Region。

### 9.3 数据环不是 while

普通 SCC 没有 condition、loop-carried values、iteration boundary 或 termination。
planner 不能“看到环就调用 `flow.loop_while`”。只有显式 structured-loop contract
才能 lower 成 loop primitive。

## 10. Executor、Agent config、Human task 与 residual

`StepNode.executor_id` 只指向具体 identity。它不是 Python 函数 identity 的同义词。
原始 Core IR 已确认 `Executor` 的三个直接子 concept：

```text
Executor
├── Human
├── Agent
└── Program
```

不在 Graph 增加 `executor_kind`；真正分派至少还需要原始 Core IR/catalog：

```text
executor_concept[executor_id] -> Human | Agent | Program
executor_config[executor_id] -> catalog-owned configuration
handlers[concept] -> runtime dispatcher
```

Agent 的 model、engine、api_base、tools、instruction、system prompt、max_turns 等
并不都属于 Graph topology。它们应继续留在 Core IR/catalog/residual，由 future
executor adapter 解析。

Program 也不等于一条 shell 字符串；它可以指向脚本、可执行程序或其他程序适配器。
Human Step 不是普通 Boolean 审批事件：它可以消费和产生任意 Artifact。future
runtime 必须持久化未完成的人类任务、释放 worker，并在人类提交结果后完成 Step；
等待期间的状态、correlation、权限、超时和重复提交处理都不进入本次静态图。

当前 unresolved：

- `agent_config` 默认值和多配置；
- system prompt 的声明式表示；
- Program executor 的 operation binding；
- Human executor 的 assignee/pool、通知、认领、权限、correlation 和提交协议；
- context schema；
- tool authorization；
- workspace/runDir；
- foreach/retry 是否共享 Agent state；
- session identity/resume。

Graph PR 不增加 SessionNode、HumanTaskNode 或 ProgramNode。三类执行者都复用普通
Step，差异只由 dispatcher 根据 executor identity 的 Core IR concept 决定。

## 11. residual 如何持久化和重新组合

当前 `GraphProjection.residual_assertions` 可以保留外部 Core IR objects，不适合 JSON。
候选方案：

1. 保存完整 Core IR，Graph 只是可重算的 cache；
2. 定义独立 `ProjectedWorkflow(graph, residual_dto)` schema；
3. Graph 只用于进程内分析，不独立持久化；
4. 后续 compiler 每个 backend 各自消费 Core IR，无需重新组合。

初版采用 1/3 的保守边界：`graph.to_dict()` 可序列化，但不是完整 executable
program。不要仅拿 Graph JSON 去执行。

## 12. 序列化版本与反序列化

当前只有一个生产者和没有外部消费者时，`to_dict()` 足够。加入 `from_dict()` 会
立刻需要决定：

- `schema_version`；
- unknown field；
- forward/backward compatibility；
- migration；
- canonical ordering；
- invalid legacy payload；
- dialect 信息是否属于 graph。

初版暂缓。若 PR 期间出现真实落盘消费者，应先加顶层 `schema_version=1`，再提供
严格 `from_dict()`；不要做宽松 Any-dict parser。

## 13. SCC 分析是否应在首 PR 中实现

支持理由：

- 用户特别关注 cycle；
- 能给出 blocked component 诊断；
- condensation DAG 对 planner 有用。

暂缓理由：

- 模型已经允许 cycle；
- 没有 runtime semantics 时 SCC 只能给结构诊断；
- analyzer 是独立纯函数，随时可加；
- 首 PR 目标是稳定 IR 和投影。

**暂定**：不在 model/projector 中加入 SCC。未来新增 `analyzer.py`，避免 Graph 对象
自己缓存派生状态。

## 14. 名称：WorkflowGraph 还是 DefinitionGraph

旧 runtime 也使用 execution graph 一词，容易混淆。

候选：

- `WorkflowGraph`：直观，但必须持续加 static/definition 限定；
- `WorkflowDefinitionGraph`：最准确，较长；
- `DefinitionGraph`：短，但脱离上下文泛化；
- `WorkflowDataflowGraph`：强调当前只含数据子图。

初版沿用 `WorkflowGraph`，公开文档始终写“静态声明图”；动态模型固定叫
`ExecutionTrace`，不复用 `WorkflowGraph` 类型。

## 15. 两条 PR 的组合边界

图 PR：

- 定义和投影静态图；
- 不执行；
- 不依赖 runtime。

Python 运行时 PR：

- 逐项迁移旧 `flow.*`；
- 直接执行 Python callback/Agent/subprocess；
- 产生动态 trace；
- 不读取静态图。

未来第三个模块 `workflow_runtime`：

- 读取 Graph；
- 结合原始 Core IR/value catalog；
- 形成 ExecutionPlan；
- 管理 Artifact versions、activations、slots；
- 调 operation，operation 可使用 `flow.session/call/exec`；
- 写 ExecutionTrace。

这样避免两个 PR 各自偷偷实现半个 scheduler。

## 16. PR 评审需要明确回答的问题

1. 是否确认原始 WorkflowGraph 允许环，只有 condensation graph 称 DAG？
2. 是否接受初版“cycle 可保存，但尚不可执行”的边界？
3. 是否接受运行时把 input+producer 视为未闭合反馈语义，而模型先允许保存？
4. Artifact 是否现在就需要 Concept/type reference？
5. 是否保留 repository List-multi 的显式顺序擦除关系投影，还是首版只支持评审 dialect？
6. 是否确认一个普通 Artifact 初版只允许一个 producer？
7. foreach 多输出是否应全部按 index 分别聚合为 List？
8. foreach 单 slot 失败时是否坚持 all-or-nothing？
9. 是否确认 retry 图层只保存 `max_attempts`，不保存 backoff/error filter？
10. 是否确认 `if`/choice/while/Region 全部不进入初版图？
11. 是否需要在首 PR 同时加 SCC analyzer？
12. `WorkflowGraph` 名称是否足够清楚，还是改为 `WorkflowDefinitionGraph`？
13. 是否需要首版即加入 `schema_version`/`from_dict()`？
14. Graph 和 residual 的长期持久化容器由哪个模块负责？
