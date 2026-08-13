# FusionFlow 声明式反馈循环设计

> **状态**: Draft implementation
>
> **目标分支**: `agent/workflow-runtime-reliability`
>
> **跟踪 Issue**: [#88](https://github.com/msg-bq/psi-agent/issues/88)
>
> **范围**: 定义并实现反馈状态的 `n -> n+1` 语义、同步提交、最终状态可见性和 `TerminalStep` 终止契约。

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

完整设计允许的初始化来源是:

- `input_workflow` 提供的初值;
- 环外 initializer 提供的初值;
- resume 时已完整提交的 checkpoint。

`consumes` 只声明依赖, 不能提供初值。

本 PR 的第一版后端只接受 `input_workflow` seed；resume 时可从该 loop
已经完成 barrier commit 的 checkpoint 接续。环外 initializer 因当前
Artifact 全局单 producer 约束尚不能无歧义表示，留在 #88 后续实现。

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

这个 BoolArtifact 是封闭的 loop control，不能作为 `output_workflow` 输出，
也不能被其他 Step 消费。需要对外呈现的完成状态应进入最终 feedback state，
或由终止后的普通 Step 从该最终状态提取。

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

## Loop Engineering

### 行为伪代码

下面的 `while` 只用于解释运行行为, 不进入 FusionFlow 源码:

```python
state = initial_engineering_state

while True:
    work = inspect_and_plan(state)
    candidate = engineer(state, work)
    verification = verify(state, work, candidate)

    next_state = advance(state, work, candidate, verification)
    done = check_complete(verification)  # strict bool, no other output

    # epoch barrier: next_state 和 done 都成功后才能提交
    state = commit(next_state)

    if done:
        return state
```

`candidate` 和 `verification` 是本轮真实业务 Artifact, 不是为了拼写 `state[n+1]` 而增加的冗余状态。由于普通 `consumes(state)` 只能读取 committed `state[n]`, verifier 需要通过 `candidate` 读取本轮待验证改动。

### 逐轮关系

```text
work[n]         = inspect_and_plan(state[n])
candidate[n]    = engineer(state[n], work[n])
verification[n] = verify(state[n], work[n], candidate[n])
state[n + 1]    = advance(state[n], work[n], candidate[n], verification[n])
done[n]         = check_complete(verification[n])
```

`advance_step` 与 `terminal_step` 读取同一份 `verification[n]`, 避免“终止判断通过, 但提交状态使用了另一套依据”。barrier 等待 `state[n+1]` 与 `done[n]` 都成功:

- `done[n] == false`: 提交 `state[n+1]`, 开始第 `n+1` 轮;
- `done[n] == true`: 提交 `state[n+1]`, 将它作为最终工程状态发布;
- 任一 Step 失败: 不提交本轮。

### FusionFlow 声明

该示例只增加 `TerminalStep` 和 `BoolArtifact` 两个 catalog concept。所有 operator 都来自现有 G4 工作流写法:

```fusionflow
const engineering_state: Artifact;
const discovered_work: Artifact;
const candidate_change: Artifact;
const verification: Artifact;
const done: BoolArtifact;

const inspect_step: Step;
const engineer_step: Step;
const verify_step: Step;
const advance_step: Step;
const terminal_step: TerminalStep;

const inspect_agent: Agent, Executor;
const engineer_agent: Agent, Executor;
const verify_agent: Agent, Executor;
const advance_agent: Agent, Executor;
const terminal_agent: Agent, Executor;

workflow loop_engineering {
  -- DATA FLOW
  input_workflow(loop_engineering) == [engineering_state];

  consumes(inspect_step) == [engineering_state];
  produces(inspect_step) == [discovered_work];

  consumes(engineer_step) == [engineering_state, discovered_work];
  produces(engineer_step) == [candidate_change];

  consumes(verify_step) ==
    [engineering_state, discovered_work, candidate_change];
  produces(verify_step) == [verification];

  consumes(advance_step) ==
    [engineering_state, discovered_work, candidate_change, verification];
  produces(advance_step) == [engineering_state];

  consumes(terminal_step) == [verification];
  produces(terminal_step) == [done];

  output_workflow(loop_engineering) == [engineering_state];

  -- EXECUTORS
  step_executor(inspect_step) == inspect_agent;
  step_executor(engineer_step) == engineer_agent;
  step_executor(verify_step) == verify_agent;
  step_executor(advance_step) == advance_agent;
  step_executor(terminal_step) == terminal_agent;

  -- STEP CONTRACTS
  step_name(inspect_step) == "Inspect and Plan";
  step_instruction(inspect_step) == "Inspect engineering_state and return concrete unresolved work, relevant evidence, priorities, and acceptance criteria as discovered_work.";

  step_name(engineer_step) == "Engineer Candidate";
  step_instruction(engineer_step) == "Use engineering_state and discovered_work to produce one candidate_change as an isolated patch or candidate workspace snapshot that can be verified before commit.";

  step_name(verify_step) == "Verify Candidate";
  step_instruction(verify_step) == "Verify candidate_change against the baseline and acceptance criteria in engineering_state and discovered_work. Return a structured verification with one acceptance verdict, test evidence, regressions, and remaining work.";

  step_name(advance_step) == "Advance Engineering State";
  step_instruction(advance_step) == "Produce the next engineering_state from engineering_state, discovered_work, candidate_change, and verification. Incorporate only verified progress and preserve all evidence and remaining work required by the next epoch.";

  step_name(terminal_step) == "Check Completion";
  step_instruction(terminal_step) == "Read verification and return exactly true iff its acceptance verdict says every required criterion passed; otherwise return exactly false. Produce no diagnostic or business data.";
}
```

这里显式声明 `done` 便于 trace。若不需要从源码引用它, 可以同时删除:

```fusionflow
const done: BoolArtifact;
produces(terminal_step) == [done];
```

compiler 随后为 `terminal_step` 合成唯一的内部 `BoolArtifact`。不能只删其中一行。

## ReAct Loop

### 标准行为伪代码

标准 ReAct 带有一个 `Action | Final` 分支:

```python
state = initial_react_state

while True:
    decision = reason_once(state)  # ToolCall(tool, args) | Final(answer)

    if decision is Final:
        next_state = append_final(state, decision.answer)
        done = True
    else:
        observation = dispatch_one_tool(decision.tool, decision.args)
        next_state = append_turn(state, decision, observation)
        done = False

    # epoch barrier
    state = commit(next_state)

    if done:
        return state.final_answer
```

这段伪代码说明 ReAct 的业务行为, 不是建议为 G4 新增 `while` 或命令式 `if`。

### 适合当前 eager 数据流的归一化形式

当前数据流不会因为 `TerminalStep` 返回 `true` 而回滚并跳过已经 ready 的普通 Step。因此 G4 示例必须把 action 归一化为一个总函数:

```python
decision = reason_once(state)
observation = dispatch_or_noop(decision)
next_state = append_decision_and_observation(state, decision, observation)
done = is_final(decision)

state = commit(next_state)  # next_state 与 done 都成功后
if done:
    return state.final_answer
```

其硬契约是:

```text
dispatch_or_noop(ToolCall) = 执行恰好一个指定工具并返回 observation
dispatch_or_noop(Final)    = 不执行任何工具, 返回无副作用 final observation
```

逐轮关系为:

```text
decision[n]     = reason_once(state[n])
observation[n]  = dispatch_or_noop(decision[n])
state[n + 1]    = update(state[n], decision[n], observation[n])
done[n]         = is_final(decision[n])
```

### FusionFlow 声明

```fusionflow
const react_state: Artifact;
const decision: Artifact;
const observation: Artifact;
const final_answer: Artifact;

const reason_step: Step;
const action_step: Step;
const update_step: Step;
const terminal_step: TerminalStep;
const extract_answer_step: Step;

const reason_agent: Agent, Executor;
const action_agent: Agent, Executor;
const update_agent: Agent, Executor;
const terminal_agent: Agent, Executor;
const answer_agent: Agent, Executor;

workflow react_loop {
  -- LOOP DATA FLOW
  input_workflow(react_loop) == [react_state];

  consumes(reason_step) == [react_state];
  produces(reason_step) == [decision];

  consumes(action_step) == [decision];
  produces(action_step) == [observation];

  consumes(update_step) == [react_state, decision, observation];
  produces(update_step) == [react_state];

  -- The BoolArtifact result is implicit.
  consumes(terminal_step) == [decision];

  -- This consumer runs only after successful loop termination.
  consumes(extract_answer_step) == [react_state];
  produces(extract_answer_step) == [final_answer];

  output_workflow(react_loop) == [final_answer];

  -- EXECUTORS
  step_executor(reason_step) == reason_agent;
  step_executor(action_step) == action_agent;
  step_executor(update_step) == update_agent;
  step_executor(terminal_step) == terminal_agent;
  step_executor(extract_answer_step) == answer_agent;

  -- STEP CONTRACTS
  step_name(reason_step) == "Reason Once";
  step_instruction(reason_step) == "Read react_state and return exactly one structured decision: either ToolCall with one tool name and arguments, or Final with one answer. Do not execute a tool.";

  step_name(action_step) == "Act Once Or No-op";
  step_instruction(action_step) == "Read decision. For ToolCall, execute exactly the selected allowed tool once and return its observation. For Final, execute no tool and return a side-effect-free final observation.";

  step_name(update_step) == "Update ReAct State";
  step_instruction(update_step) == "Append decision and observation to react_state and produce the next react_state. For Final, store the final answer and mark the state complete; for ToolCall, preserve everything required by the next reasoning epoch.";

  step_name(terminal_step) == "Detect Final Decision";
  step_instruction(terminal_step) == "Read decision and return exactly true for Final and exactly false for ToolCall. Produce no other output.";

  step_name(extract_answer_step) == "Extract Final Answer";
  step_instruction(extract_answer_step) == "Read the successfully terminated final react_state and return its stored final answer.";
}
```

该例故意使用 `TerminalStep` 的隐式输出形式, 因而没有声明 `done` 或书写 `produces(terminal_step)`。compiler 仍会创建唯一的内部 `BoolArtifact`。

`extract_answer_step` 不属于循环。它虽然消费同名 `react_state`, 但只有成功终止后才会被环外 completion readiness 唤醒, 因而读取的是最终 committed state。

### 这个例子完成了什么, 尚缺什么

新的反馈与终止语义已经能声明:

- `state[n] -> decision[n] -> observation[n] -> state[n+1]`;
- `Final` 的严格 Boolean 终止判断;
- `true` 时先提交包含 final answer 的 `state[n+1]`, 再发布结果;
- 中间 state 不泄漏给环外 consumer。

但 `TerminalStep` 只解决循环终止, 不自动提供以下能力:

- `ToolCall` 中 tool name 的结构类型与静态校验;
- 一个可观察的“动态派发恰好一次” runtime primitive;
- lazy branch activation, 即在 `Final` 时由 planner 根本不调度 action Step;
- 外部工具副作用的 exactly-once。

因此, 在 `action_step` 仍是当前黑盒 Agent executor 时, 该 G4 能表达 ReAct 的外层反馈结构, 但还不能证明 ReAct 已完全自举。达到自举标准至少还要让 `action_step` 的 one-action dispatch / Final no-op 成为可检查的 executor 契约, 而不是只写在自然语言 instruction 中。

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

## Runtime 持久化与恢复

实现不再使用“每个 Step 只运行一次”的身份模型，已经加入:

- 稳定 `loop_id`;
- `epoch` 纳入 invocation identity;
- committed current-state vector;
- epoch barrier 的原子 commit;
- resume 时校验完整 checkpoint 与 workflow definition digest;
- 初始 checkpoint 尚未进入 loop 时，仍严格校验 feedback input seed。

当前只支持从 epoch barrier 恢复。inflight epoch 与 staged outputs 会保留在
checkpoint schema 中用于校验，但不能从半轮状态续跑；遇到这种 checkpoint
会 fail closed。后续可在保证副作用重放契约后支持恢复未完成 epoch。

外部副作用无法仅靠 checkpoint 获得 exactly-once。Program 和 Agent tool invocation 仍须使用稳定 idempotency key, 或明确保持 at-least-once 语义。

## 第一版实现边界

本 PR 有意先收紧到可以准确执行和清楚诊断的子集:

- 每个 workflow 最多一个 feedback component;
- feedback seed 只来自 `input_workflow` 或已提交 checkpoint;
- 每个 feedback Artifact 恰好一个 next writer;
- 删除跨 epoch feedback 依赖后，本轮图必须是 DAG;
- feedback 不与 selector、`foreach` 或 Human Step 混用;
- `TerminalStep` 必须唯一归属于该 component;
- 环外 consumer 与 workflow output 只看到终止后的最终 committed state;
- resume 只发生在 epoch barrier;
- host 可用 `max_loop_epochs` 做安全上限，但它不是 FusionFlow 源码语法。

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

## 实现状态

- [x] 在 catalog / type checker 中加入 `TerminalStep <: Step` 和 `BoolArtifact <: Artifact`。
- [x] 支持 TerminalStep 显式或隐式唯一 BoolArtifact 输出并实施封闭输出校验。
- [x] 分析单个 feedback component、workflow input seed、唯一 next writer 与单轮 DAG。
- [x] 生成 current / staged 双缓冲 epoch execution unit。
- [x] 实施完整状态向量 barrier、终止后最终状态可见性与 Artifact 覆盖发布。
- [x] 把稳定 `loop_id` / `epoch` 纳入 checkpoint 和 invocation identity。
- [x] 增加真实 G4 编译、planner、同步 snapshot、严格 Boolean、barrier checkpoint 与恢复保护测试。
- [x] 提供 Loop Engineering 与归一化 ReAct 的完整 `.workflow` 示例。
- [x] 更新 Workflow README 与 SKILL 行为约定。
- [ ] 支持 inflight epoch / staged output 恢复与外部副作用幂等契约。
- [ ] 支持环外 initializer、多/嵌套 feedback component、selector/foreach/Human 组合。
