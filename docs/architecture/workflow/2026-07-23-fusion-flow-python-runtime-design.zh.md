# FusionFlow Python 执行运行时设计

> 状态：待评审
> 日期：2026-07-23
> 目标 PR：独立于 Workflow Graph PR
> 目标包：`src/psi_agent/fusion_flow/`

## 1. 背景与目标

现有 `examples/haitun-workspace/skills/fusion-flow/runtime/` 是一套 TypeScript
执行运行时。`flow.agent`、`flow.if`、`flow.parallel`、`flow.retry` 等函数不是
静态工作流图本身，而是执行时原语：函数一旦被调用，就会立即执行回调、调用
Agent、启动子进程或更新运行记录。

本 PR 的目标是把这套公开能力逐项迁移到 Python，并保留足够的兼容语义，使后续
图执行器可以把图节点编译为这些 Python 执行原语的调用。

迁移时的行为真源按以下优先级认定：

1. `core/src/types.ts` 的当前公开类型；
2. `core/src/flow.ts` 和 `core/src/run.ts` 的当前实现；
3. `core/test/` 的回归测试；
4. examples 和 README 仅作补充，和源码冲突时不反向覆盖源码。

本 PR 不负责：

- 解析声明式图；
- 根据图决定执行顺序；
- 判断一个有环图能否终止；
- 把 Workflow Core IR 自动编译成执行计划；
- 直接修改 Haitun 的现有 TypeScript skill 入口；
- 搬运旧 CLI 的 provider 选择、交互询问和进程退出逻辑。

## 2. 与其他模块的边界

三层必须分离：

```text
WorkflowGraph（静态声明）
        |
        | 未来：planner
        v
ExecutionPlan（一次运行的计划）
        |
        | dispatcher 通过 Core IR/catalog 解析 executor_id 的类型
        +-- agent   -> fusion_flow -> Agent/session runner
        +-- program -> fusion_flow -> Python callable / subprocess
        +-- human   -> 图执行器暂停 / 审批 / 外部事件 / 恢复
```

`WorkflowGraph` 描述“有哪些步骤、Artifact 和关系”；`fusion_flow` 描述“一个具体
操作现在怎么执行”。本 PR 中的 `ExecutionTrace` 是某次运行产生的动态事实，不是
静态图，也不反向充当工作流定义。

未来的图执行器应同时依赖 `workflow_graph` 和 `fusion_flow`，而两者互不依赖。
其中 human executor 不是某个 `flow.*` callable。读图与计划层应把它降解为“暂停运行、
等待审批或外部事件、收到结果后恢复”；本 PR 不伪造一个自动执行 human 节点的函数。
Human/Agent/Program 分类来自 `executor_id` 指向的 Core IR/catalog concept，不在运行时
或静态图中再增加一份 `executor_kind`。

## 3. 为什么放在 `src/psi_agent/`

本设计把运行时放在可安装的 `psi_agent` Python 包中，目的是让普通 Python 代码
可以稳定地 `from psi_agent.fusion_flow import flow, run`，而不依赖示例 workspace
被加入 `sys.path`。

这与当前 `fusion-flow-next` 编译器原型“暂留在示例 skill 内”的布局不同。两者服务
的边界也不同：

- `fusion_flow_next`：未激活的语法、检查器与 Core IR 原型；
- `psi_agent.fusion_flow`：可由 Python 程序直接调用的执行库。

这个布局会让 psi-agent 核心发行物多一个通用运行时模块，是一项需要明确接受的
架构选择；相关争议单独记录在待讨论文档中。

## 4. 建议的最小模块结构

```text
src/psi_agent/fusion_flow/
├── __init__.py       # 稳定公开 API
├── model.py          # 运行、步骤、trace、binding 的不可变/可序列化模型
├── runtime.py        # RuntimeContext、持久化、动态作用域、服务注册
└── flow.py           # Flow 类及 flow 单例，执行原语
```

`Agent` 和 runner 协议放在 `model.py`，`run()` 生命周期放在 `runtime.py`。不提前
增加 `planner.py`、`executor.py`、`store.py` 或 backend 抽象。未来真正出现第二种
实现时再拆分。

## 5. Python 公开 API

Python 采用 Ruff 可接受的 `snake_case` 命名；`if` 是 Python 关键字，因此必须命名
为 `if_`。不同时维护一套 camelCase 别名，避免双倍文档和测试面。

| TypeScript | Python | 语义 |
| --- | --- | --- |
| `flow.agent` | `flow.agent` | 校验配置并创建具名 Agent handle，不执行 |
| `flow.session` | `flow.session` | 使用 Agent handle 发起一次独立调用 |
| `flow.service` | `flow.service` | 注册具名服务 |
| `flow.call` | `flow.call` | 调用服务 |
| `flow.parallel` | `flow.parallel` | all/first/any 并行 |
| `flow.if` | `flow.if_` | 严格布尔二分支 |
| `flow.ifElse` | `flow.if_else` | 按顺序选择首个真分支 |
| `flow.forEach` | `flow.for_each` | 顺序遍历副作用 |
| `flow.parallelForEach` | `flow.parallel_for_each` | 并行遍历副作用 |
| `flow.evaluate` | `flow.evaluate` | 动态表达式/选择/评分 |
| `flow.loopUntil` | `flow.loop_until` | 先执行再判断 |
| `flow.loopWhile` | `flow.loop_while` | 先判断再执行 |
| `flow.choice` | `flow.choice` | 从候选项中选择 |
| `flow.map` | `flow.map` | 顺序映射 |
| `flow.pmap` | `flow.pmap` | 并行映射，结果保持输入顺序 |
| `flow.filter` | `flow.filter` | 顺序过滤 |
| `flow.pfilter` | `flow.pfilter` | 并行过滤，结果保持输入顺序 |
| `flow.reduce` | `flow.reduce` | 顺序归约 |
| `flow.pipeline` | `flow.pipeline` | 值依次通过多个步骤 |
| `flow.retry` | `flow.retry` | 指数退避重试 |
| `flow.evaluateStatic` | `flow.evaluate_static` | 通过判别式 `StaticRule` 做静态求值 |
| `flow.use` | `flow.use` | 按服务名调用服务 |
| `flow.block` | `flow.block` | 执行匿名/内联块 |
| `flow.defineBlock` | `flow.define_block` | 定义具名块 |
| `flow.runBlock` | `flow.run_block` | 执行具名块 |
| `flow.repeat` | `flow.repeat` | 固定次数重复 |
| `flow.input` | `flow.input` | 读取输入 binding |
| `flow.output` | `flow.output` | 写入输出 binding |
| `flow.exec` | `flow.exec` | 显式 `name` + `argv` 的无 shell 子进程执行 |

包级别同时保留：

- `Agent`：可调用包装器；可从当前 `run()` 继承 runner，也可通过
  `Agent(config, runner=...)` 脱离运行上下文调用；
- `run`：建立一次运行的动态上下文；
- `assert_safe_name`：名称与路径安全检查；
- `aggregate_tokens`：按 `user` / `internal` 分组汇总 token，并保留扁平总计；
- `format_token_count`：格式化 token 数；
- `gc_runs`：清理历史运行目录。

`RunContext.input()`、`RunContext.save()` 和 `RunContext.flow` 也保留。
`RunContext.flow` 返回包级同一个 `flow` 对象；输入输出的委托方向是
`flow.input()` → 当前 `RunContext.input()`、`flow.output()` → 当前
`RunContext.save()`，因此落盘与查重逻辑只有一套。

旧 `pickEngine`、CLI provider 选择和交互式提示不进入本包。Agent 调用通过注入的
异步 `SessionRunner` 完成。

## 6. 核心模型

### 6.1 Run

一次 `run()` 至少记录：

- `run_id`；
- 动态节点状态：兼容 `running | ok | error`，并扩展 `cancelled`；
- `started_at`、`finished_at`、`duration_ms`；
- 输入、输出、bindings；
- 根级 `ExecutionTrace`；
- token 汇总：`user`、`internal` 两组以及二者合计；
- 可选的 `resume_from_run_id`；
- 错误摘要。

`run()` 的公开结果保留旧合同：`status` 为 `ok | error`。普通业务异常默认被记录为
`error` 并由结果返回；`throw_on_error=True` 时才重新抛出。取消异常永远传播，
不得被转换成普通失败；持久化 trace 可以用扩展状态 `cancelled` 记录清理事实。

### 6.2 ExecutionTrace

每个执行原语产生一个 trace 节点：

- 稳定 `trace_id`；
- `kind` 与用户标签；
- `status`；
- 起止时间和真实 duration；
- 输入/输出摘要；
- 子节点；
- token、重试、所选分支等元数据；
- 错误或取消原因。

当前父节点使用 `contextvars.ContextVar` 保存。并行子任务继承同一个父节点，但
各自建立独立子上下文。向共享 trace 树和 bindings 写入时通过 AnyIO 锁串行化。

### 6.3 Binding

binding 是一次运行内的具名值。规则：

1. 名称先通过 `assert_safe_name`；
2. 同一次当前运行默认只写一次；
3. 名称预留、调用序号和写值是一个事务；
4. 缓存命中或 binding 完整落盘后才推进调用序号；失败重试复用原序号；
5. 恢复目录中的旧 binding 是缓存输入。缓存未命中时允许覆盖一次；同一当前运行
   第二次显式写同名仍拒绝；
6. 序列化失败必须明确报错，不能静默丢值。

## 7. Agent 与 SessionRunner

`SessionRunner` 是一个最小异步 callable 协议。这里沿用旧函数名中的 session，
但它表示一次独立 Agent invocation，不承诺聊天历史或会话复用。运行时只关心：

- agent 标识与配置；
- 用户输入；
- 本次调用的 context；
- 可选参数；
- 返回文本、结构化结果和 token 使用量。

它不直接实例化 `SessionAgent`。现有 `SessionAgent` 是带持久对话、tool loop 和
workspace 生命周期的应用层对象，并不等价于一个轻量函数。后续可以提供基于
psi-agent socket 协议的 adapter，但本 PR 用注入方式保持运行时独立、可测试。

`flow.agent` 只创建 handle，本身不检查 runner；真正执行 handle 的
`flow.session` 在未配置 runner 时立即抛出明确配置错误。若未来要把它接到
psi-agent 的有状态 Session，必须由独立 adapter 明确规定 history 和 identity，
不能由本包暗中推断。

包级 `Agent(config, runner=...)` 是显式的无状态直调入口，可在 `run()` 外调用；
不传 runner 时继续通过当前运行的 `flow.session` 执行并生成 trace/binding。
runner 仍拥有 provider/engine 选择权，FusionFlow 不嵌入 provider。

## 8. 执行语义

### 8.1 parallel

- `all`：等待全部成功，返回值保持输入任务顺序；
- `first`：第一个完成的任务决定结果；其余任务被取消并完成清理；
- `any=n`：按完成顺序收集前 `n` 个结果，达到数量后取消其余任务；
- 任一模式都使用 AnyIO task group；
- `n` 必须是整数且满足 `1 <= n <= len(tasks)`；
- 空任务列表只允许 `all`，结果为空列表；
- 任务失败、取消与“还未选中”在 trace 中分开表示。

第一版保留旧实现的错误传播：任一已完成任务失败，`any=n` 整体失败并取消其余
任务。只修复 `n` 越界、非整数和空任务导致永久等待的问题。“收集前 n 个成功”
可以成为后续新 mode，但不能静默改变旧 `any`。

`first` 暂按旧实现理解为“第一个 settle”，即最先失败也会使整体失败。是否改成
“第一个成功”留在待讨论项。

旧 `Promise.all` 在一个分支失败后可能让兄弟任务继续后台写入。Python 版建议在
向调用者报告失败前取消并等待兄弟任务清理。这是为避免幽灵写入而做的明确安全
偏差，不宣称与旧副作用时序完全一致，需在书面设计评审时确认。

Python 无法安全强杀一个不让出控制权或主动吞掉取消的任意 callable。首版合同要求
用户 callback 是 cancellation-cooperative；运行时使用结构化取消并等待受控的
runner、subprocess 和兄弟任务完成清理，不承诺固定宽限时间，也不会把仍可写 binding
的任务 detached 到 run 结束之后。

### 8.2 条件与选择

- `if_` 和 `if_else` 的条件必须返回真正的 `bool`，不接受 Python truthy 值；
- `if_else` 按声明顺序求条件，执行第一个为真的分支；
- trace 明确记录所选分支下标；
- `choice` 拒绝空候选和重复候选；
- 数字范围必须满足 `minimum <= maximum`。

`evaluate_static(question, rule, binding_name=...)` 的 `rule` 是判别联合
`RegexRule | ContainsRule | EqualsRule | RangeRule | PredicateRule`，而不是一组可同时
出现的可选关键字。每种规则只携带自身需要的数据；`PredicateRule.fn` 是零参数
callable。binding 的 JSON 同时包含 `value` 与 `rule` 字段，便于审计。

### 8.3 循环与重试

- `loop_until`：先执行 body，再检查 condition；
- `loop_while`：先检查 condition，再执行 body；
- `repeat`：执行固定非负次数；
- 所有最大次数必须是整数并且在合法范围；
- 为逐项迁移，达到循环上限时先保留旧行为：记录 warning 后正常返回；
- `retry` 默认最多 3 次尝试，初始延迟 200ms，倍率 2，最大延迟 8s；
- AnyIO 取消异常和明确的永久错误不重试；
- sleep 使用 `anyio.sleep()`。

### 8.4 集合操作

- `for_each` / `parallel_for_each` 是副作用原语，返回 `None`；
- `map` / `filter` / `reduce` 顺序执行；
- `pmap` / `pfilter` 并行执行，但输出按输入下标重组；
- `pipeline(value, steps)` 把上一步结果传给下一步，不把首参数解释为 label。

### 8.5 service 与 block

服务和 `define_block` 定义在当前运行上下文中注册，重复名字立即失败。内联
`block(label, fn)` 不注册，label 可以重复。`use` 保留为 `call` 的服务名入口，
因为旧代码同时暴露了二者。

服务/块恢复是否可复用，不能只依赖参数 JSON 的插入顺序；至少使用规范化输入和
实现身份生成摘要。函数体身份在 Python 中难以稳定计算，因此第一版宁可少复用，
也不错误复用。

### 8.6 input 与 output

旧 `flow.input` 会解析 CLI 的 `--input.<name>=...`。本包不移植旧 CLI parser，
而由 `run(inputs={...})` 注入同一份覆盖映射；未提供覆盖时使用调用处 default。
每个 input 仍写入 `input/`，同名重复读取仍按旧合同拒绝。`flow.output` 仍写
`bindings/`，不伪造一个尚不存在的 `outputs/` 协议。

### 8.7 exec

- 使用 `anyio.open_process()`；
- 调用签名显式包含操作 `name` 和 `argv`；`name` 用作 trace label 与默认 binding 前缀；
- `argv` 逐项传入，绝不经 shell；
- 支持 `stdin`、`cwd`、显式环境变量覆盖、timeout；
- timeout、stdout/stderr 消费和 stdin 发送从进程启动起并发，避免双向 PIPE 死锁；
- 默认 stdout 上限 4 MiB；`0` 或正无穷关闭限制，stderr 始终完整消费；
- stdout 首次越界时立即杀进程，返回保留前缀并将本次主动终止视为截断成功；
- 截断 binding 在正文后追加 `[truncated at ...]`，避免下游把残缺内容当完整结果；
- timeout 或取消时杀进程并等待回收；
- 退出码非零时操作失败，不能先提交成功 binding；
- `cwd` 是调用者显式选择的子进程工作目录，不强制位于 runs 根目录；恢复路径仍必须
  位于配置的 runs 根目录内。

旧 TS 类型文档描述的是“干净环境，仅保留 `PATH` 后应用覆盖”，Python 首版有意采用
“继承当前环境，再应用显式 overrides”的语义，以符合普通 subprocess 调用预期。
这是已记录的兼容性差异；如果要完全隔离，应作为后续显式选项。

## 9. 持久化与恢复

默认运行目录保留为当前工作目录下的 `runs/<run_id>/`，同时允许通过
`run(..., runs_dir=...)` 显式指定。所有 IO 使用 `anyio.Path`。`run_id`、binding、
service、block 等所有参与路径的名称都经过统一安全检查。

建议落盘：

```text
runs/<run_id>/
├── program.py
├── input/
├── bindings/
├── trace/
├── progress.jsonl
├── execution-graph.json
└── meta.json
```

`program.py` 对应旧版的 `program.ts`。显式 `program_path` 优先；未提供时运行时
会从 Python `sys.argv[0]` 尽力复制 `.py` 入口脚本。动态定义、REPL 或打包环境无法
可靠取得源码时不伪造源码，默认快照失败只记录 warning 和缺失状态。

文件使用“临时文件 + 同目录替换”写入，避免取消或崩溃留下半个 JSON。

持久化分为两类：

- binding、最终 `execution-graph.json` 和 `meta.json` 是关键业务状态，写入失败会使
  本次运行失败；
- `progress.jsonl` 和 `trace/*.json` 是增量诊断信息，采用 best-effort 写入，失败时
  记录日志但不把已成功的业务操作反转成失败。与旧 TS 一致，首版只为包含 provider
  调用细节的 `session`、`evaluate` 写独立 trace 文件；其余节点仍完整进入最终 graph。

`progress.jsonl` 对每个 trace 节点写一对精简事件：开始记录
`ts/event/id/type/label`，结束记录再带 `status/durationMs`；`event` 分别为
`node_start` 和 `node_end`。它不是完整 trace 快照。

最终 graph/meta 仍会汇总完整内存 trace，因此单节点诊断文件缺失不改变运行结果。

为忠实迁移，`resume_from_run_id` 指向既有 run：载入该目录的 cache，并在同一
`run_id/run_dir` 上重新执行顶层程序，再原子更新 graph/meta。旧 TS 只有
`session`、`call` 会按稳定 binding 名与输入摘要尝试复用；`evaluate`、`exec`、
静态判断和任意 Python callable 都会重新执行。Python 首版保留这一边界，但不会像
旧实现那样提前消耗调用序号：缓存命中或新结果完整落盘后才提交序号；失败重试仍
探测原 binding。旧恢复 binding 不计为当前运行已写入，因此未命中时会原子覆盖，
而不是无条件跳到新的序号。

因此 resume 不是“整条工作流幂等重放”，也不是进程级 checkpoint。尤其
`choice/evaluate` 可能重新选择分支，`exec` 可能再次产生外部副作用。是否应由未来
planner 生成显式 replay policy，或扩展运行时缓存范围，作为待讨论项保留。

## 10. 与 TS 的兼容策略

迁移遵循三类处理：

1. **语义保留**：公开函数、参数含义、结果顺序、默认重试退避等；
2. **Python 化但可映射**：snake_case、`if_`、dataclass、AnyIO、显式 runner 注入；
3. **安全修复并记录**：会导致死锁、错误复用、路径逃逸、取消泄漏、失败值提前提交
   的行为不照搬。

不会为了“逐行一样”复制 TypeScript 的内部类层次、Promise 辅助器或 Node CLI
provider 栈。兼容目标是可观察语义和公开能力，不是文本结构。

## 11. 测试策略

### 11.1 API 对照测试

- 29 个 `flow.*` 方法全部存在；
- 包级稳定入口（含 `Agent`、`TokenSummary`、`run` 与辅助函数）全部存在；
- 每个 TS 名称都有唯一 Python 映射；
- 公开签名和文档一致。

### 11.2 行为测试

- parallel 三种模式、顺序、失败、取消、非法 `n`；
- 条件严格 bool、分支下标；
- loop 先后顺序、上限 warning 后返回的兼容行为；
- retry 退避、永久异常和取消传播；
- pmap/pfilter 输出顺序；
- binding 原子重复检查；
- service/block 重名与调用；
- exec stdout/stderr、非零码、timeout、取消和截断；
- trace duration、父子关系和并发安全；
- run 的默认错误结果与 `throw_on_error`。

### 11.3 持久化与安全测试

- JSON 原子写；
- 不安全名称和 `resume_from_run_id` 路径逃逸；
- 失败操作不写成功 binding；
- 恢复只在 `session`、`call` 上复用输入摘要匹配的结果，其他原语重新执行；
- `gc_runs` 不删除根目录外内容。

## 12. 验收标准

- 所有旧公开执行能力都有明确 Python 对应；
- 核心实现只使用 AnyIO，不直接使用 `asyncio`、`pathlib`、`subprocess.run`；
- 取消能传播，子任务和子进程都被清理；
- Ruff、ty、目标测试通过；
- README/AGENTS 和中文讨论文档同步；
- 不连接现有 TypeScript skill，不提前实现图 planner/executor；
- 后续执行器可以通过稳定公开 API 调用这些原语。
