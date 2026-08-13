# FusionFlow 声明式反馈循环设计

> **状态**: Draft
>
> **目标分支**: `agent/workflow-runtime-reliability`
>
> **跟踪 Issue**: [#88](https://github.com/msg-bq/psi-agent/issues/88)
>
> **范围**: 定义反馈状态的 `n -> n+1` 语义、同步提交、最终状态可见性和 `TerminalStep` 终止契约。本文先固定语言与后端契约, 不声称当前 runtime 已实现循环执行。

## 目标

FusionFlow 是声明式 Step-Artifact 数据流语言。反馈循环继续使用现有的 `consumes` / `produces` 图关系表达, 不引入命令式 `for` 或 `while`。

```fusionflow
consumes(update_a) == [state_a, state_b];
produces(update_a) == [state_a];

consumes(update_b) == [state_a, state_b];
produces(update_b) == [state_b];
```

上述关系在合法反馈区域内唯一解释为:

```text
state_a[n + 1] = update_a(state_a[n], state_b[n])
state_b[n + 1] = update_b(state_a[n], state_b[n])
```

同一个 Artifact 表示一条按 epoch 版本化的状态流。源码不为了运行时版本增加 `state_a_next` 等普通 Artifact。

## 反馈状态识别

每个反馈状态必须同时满足:

1. 位于 Step-Artifact 二部图的循环区域内。
2. 具有一个不依赖该循环区域的初始化来源。
3. 具有恰好一个环内 producer, 作为下一状态 writer。

合法初始化来源是:

- `input_workflow` 提供的初值;
- 环外 initializer 提供的初值;
- resume 时已完整提交的 checkpoint。

`consumes` 只声明依赖, 不能提供初值。

对一个循环区域, 所有同时满足“有独立初值”和“有唯一环内 next writer”的 Artifact 都进入同一个同步反馈状态集合。后端不在多个候选 feedback cut 之间猜测作者意图。

若状态集合为空、存在多个 next writer, 或把反馈写入解释为跨 epoch 后单轮依赖仍有环, checker 必须拒绝该图。

## 同步 epoch 语义

每个 epoch 使用不可变的 current snapshot:

```text
current = state_vector[n]
staged  = empty state_vector[n + 1]
```

规则如下:

1. 本轮所有 feedback `consumes` 都读取同一份 `state_vector[n]`。
2. feedback `produces` 只写入 staged `state_vector[n + 1]`。
3. staged 状态不能在同一轮通过普通 `consumes` 被读取。
4. 所有 next state 与终止判断成功完成后, 才在 epoch barrier 原子提交整个状态向量。
5. 任一必需 writer 或终止判断失败时, 本轮状态向量不得部分提交。

这对应同步 Jacobi 更新, 而不是依赖调度先后的异步或 Gauss-Seidel 更新。

同一 epoch 读取 staged `n+1` 的显式语法不在本设计范围, 继续由 #88 跟踪。

## 最终状态可见性

反馈区域对外表现为一个复合数据流节点:

- 中间 epoch 只对循环内部、checkpoint 和 trace 可见;
- 环外 consumer 不会被中间状态唤醒;
- `output_workflow` 和环外 consumer 只在循环成功终止后读取最终已提交状态。

## 终止概念

catalog 增加两个子类型概念:

```text
TerminalStep <: Step
BoolArtifact <: Artifact
```

不增加 `termination_signal(...)` operator。`TerminalStep` 的类型已经声明其控制角色。

`TerminalStep` 仍是普通数据流 Step:

- 使用 `consumes(...)` 读取本轮业务数据;
- 由自己的 executor / instruction 完成业务判断;
- 每个 epoch 恰好运行一次;
- 唯一逻辑结果是严格 Boolean。

### 显式结果

```fusionflow
const delta: Artifact;
const done: BoolArtifact;
const check_convergence: TerminalStep;

consumes(check_convergence) == [delta];
produces(check_convergence) == [done];
```

显式 `produces` 必须恰好是长度为 1 的列表, 唯一元素必须属于 `BoolArtifact`。

### 隐式结果

```fusionflow
const delta: Artifact;
const check_convergence: TerminalStep;

consumes(check_convergence) == [delta];
```

省略 `produces` 时, compiler 为该 `TerminalStep` 创建一个不可从源码引用的内部 `BoolArtifact` 结果。显式形式与隐式形式具有相同的控制语义。

### 封闭输出契约

`TerminalStep` 不能产生第二个输出或任何普通 Artifact。

诊断报告、评分、差值、验证结果等业务数据必须由普通 Step 产生; `TerminalStep` 只消费这些数据并作最终 Boolean 分类。

运行值只接受严格 `true` 或 `false`, 不接受字符串、数字或一般 truthy / falsy 转换。

## 循环归属

`TerminalStep` 不接收额外的循环定位参数。后端通过其 input dependency ancestry 反向定位所属 feedback component:

- 唯一到达一个 feedback component: 合法;
- 到达零个 feedback component: 静态错误;
- 到达多个独立 feedback component: 静态归属歧义;
- 一个 feedback component 没有 `TerminalStep` 或有多个 `TerminalStep`: 静态错误。

循环归属只是静态图分析, 不会把 feedback state 作为隐藏参数传给 `TerminalStep`。

## barrier 与终止顺序

每个 epoch 的后端顺序为:

1. 从 current snapshot 执行本轮数据流。
2. 收集完整 staged next-state vector。
3. 执行并读取 `TerminalStep` 的严格 Boolean 结果。
4. 若所有必需结果成功, 原子提交完整 next-state vector。
5. 根据 Boolean 决定继续或成功终止。

| TerminalStep 结果 | 后端行为 |
|---|---|
| `false` | 提交完整 `state[n+1]`, 开始下一 epoch |
| `true` | 提交完整 `state[n+1]`, 成功终止, 对外发布最终状态 |
| 非 Boolean | 不提交本轮, 报运行时契约错误 |
| Step 失败 | 不提交本轮, 按 Step 失败 / retry 策略处理 |

`true` 指“本轮产生的新状态是最终状态”, 因此必须先提交 `state[n+1]`, 不能返回 `state[n]`。

## Loop Engineering 示例

```fusionflow
const engineering_state: Artifact;
const candidate: Artifact;
const verification: Artifact;
const done: BoolArtifact;

const engineer: Step;
const verify: Step;
const advance: Step;
const terminal: TerminalStep;

workflow loop_engineering {
  input_workflow(loop_engineering) == [engineering_state];

  consumes(engineer) == [engineering_state];
  produces(engineer) == [candidate];

  consumes(verify) == [candidate];
  produces(verify) == [verification];

  consumes(advance) == [engineering_state, candidate, verification];
  produces(advance) == [engineering_state];

  consumes(terminal) == [verification];
  produces(terminal) == [done];

  output_workflow(loop_engineering) == [engineering_state];
}
```

`verification` 由普通 Step 产生, 因而可保留完整测试证据。`terminal` 只把验证结果归类为是否结束。

## ReAct 示例

```fusionflow
const react_state: Artifact;
const decision: Artifact;
const observation: Artifact;
const done: BoolArtifact;

const reason_once: Step;
const act_once: Step;
const update_state: Step;
const final_decision: TerminalStep;

workflow react_loop {
  input_workflow(react_loop) == [react_state];

  consumes(reason_once) == [react_state];
  produces(reason_once) == [decision];

  consumes(act_once) == [decision];
  produces(act_once) == [observation];

  consumes(update_state) == [react_state, decision, observation];
  produces(update_state) == [react_state];

  consumes(final_decision) == [decision];
  produces(final_decision) == [done];

  output_workflow(react_loop) == [react_state];
}
```

该图只在 `act_once` 对 `Final` decision 保证无副作用 no-op 时才完整表达 ReAct。lazy conditional activation 和动态 tool dispatch 的执行契约仍需后续设计, 不能由 `TerminalStep` 代替。

## 必需静态诊断

第一阶段至少应提供以下稳定诊断:

- `MISSING_INITIAL_STATE`
- `MULTIPLE_NEXT_WRITERS`
- `RESIDUAL_EPOCH_CYCLE`
- `MISSING_TERMINAL_STEP`
- `MULTIPLE_TERMINAL_STEPS`
- `TERMINAL_LOOP_NOT_FOUND`
- `AMBIGUOUS_TERMINAL_LOOP`
- `INVALID_TERMINAL_OUTPUT_COUNT`
- `INVALID_TERMINAL_OUTPUT_TYPE`

诊断应列出 loop component、feedback state、初始化来源、current readers、next writer、TerminalStep 和 commit group, 让作者明确看到 `n` 与 `n+1` 的解释。

## Runtime 持久化要求

可恢复执行不能继续使用“每个 Step 只运行一次”的身份模型。至少需要:

- 稳定 `loop_id`;
- `epoch` 纳入 invocation identity;
- committed current-state vector;
- inflight epoch 与 staged outputs;
- epoch barrier 的原子 commit;
- resume 时校验完整 checkpoint 与 workflow definition digest。

外部副作用无法仅靠 checkpoint 获得 exactly-once。Program 和 Agent tool invocation 仍须使用稳定 idempotency key, 或明确保持 at-least-once 语义。

## 非目标

本设计不包含:

- `for` / `while` 命令式语法;
- 默认固定点终止;
- `termination_signal(...)` operator;
- 同一 epoch 显式读取 staged `n+1`;
- nested loop / multi-rate loop;
- lazy `if` / branch activation;
- exactly-once 外部副作用保证;
- 跨机器调度与故障接管。

## 实现阶段

- [ ] 在 catalog / type checker 中加入 `TerminalStep <: Step` 和 `BoolArtifact <: Artifact`。
- [ ] 支持 TerminalStep 显式或隐式唯一 BoolArtifact 输出并实施封闭输出校验。
- [ ] 分析反馈 component、初始化来源、唯一 next writer 与单轮 DAG。
- [ ] 生成 current / staged 双缓冲 epoch execution unit。
- [ ] 实施完整状态向量 barrier 与最终状态可见性。
- [ ] 把 `loop_id` / `epoch` / staged state 纳入 checkpoint 和 invocation identity。
- [ ] 增加 Loop Engineering 与 ReAct 的 parser、checker、planner、runtime、resume 测试。
- [ ] 更新 Workflow README、SKILL 和根 `AGENTS.md` 的行为约定。

