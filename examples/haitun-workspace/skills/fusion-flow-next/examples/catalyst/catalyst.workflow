-- 光催化全水解（overall water splitting，OWS）Co-scientist 数据流。
--
-- 来源优先级：
--   1. 飞书白板“光催化全水解agent进展”的登录态原始节点数据；
--      本次实际读取到 82 个节点，其中 40 个图形/文字节点、42 条连接线。
--   2. coscientist-ows-entry.zip 中的技能说明和 streaming scheduler；
--      它只用于补充执行器、候选池、GPU 和批处理等白板未展开的实现语义。
--   3. 会话 019f7d37-a6af-77d0-88d5-b7bdc3085d90；
--      该会话只补充 grammar / validator / lowering / runtime 的职责边界，
--      没有提供 OWS 专属节点或连线。
--
-- 白板到本文件的转换规则：
--   * 白板中的 subagent 方框被建模为 Agent，紧随其后的业务方框被建模为 Step；
--     两者之间的箭头用 step_executor(Step) == Agent 表达。
--   * 圆柱、平行四边形和过程输出均按 Artifact 建模。
--   * “通过 / 不通过”不是块级 if/else，而是两个互斥的结果 Artifact。
--   * 白板的三个空白外框 o2:83、o2:98、o2:106 只是视觉分组，不是运行步骤。
--   * 白板文字节点 a10:7、a10:8 只是边标签，分别对应“通过”和“不通过”。
--   * 连接线 c2:187 的终点没有吸附到具体节点，但几何上接入推荐输入总线；
--     结合附件中推荐器会读取 candidate registry 的事实，本文件把它解释为
--     “候选催化剂池反馈给四个推荐步骤”。这是唯一需要几何和附件共同补全的边。
--
-- 语法和运行时边界：
--   * 本文件使用 WorkflowStrict.g4 可解析的 .workflow 表面语法。
--   * “==”表示关系成立，不是命令式赋值；源码先后顺序也不代表执行顺序。
--   * consumes / produces 表达数据关系，真正的并发、分支触发、持久化更新和停止行为
--     仍需 validator、lowering 与 runtime 落实。
--   * if(formula, then_term, else_term) 只能产生一个值，不能包住 Step；因此这里不用 if
--     伪造白板路由，而是用不同的结果 Artifact 表达各条数据支路。
--   * member_of、parallelism、independent、batch_size、exclusive_lease
--     来自外部 operator catalog；
--     grammar 能解析这些调用，但执行前仍需相应的 validator/runtime 支持。

-- Workflow source 只声明本文件使用的具体 identity，不在本地定义 concept 或 operator。
-- Workflow、Step、StepGroup、Artifact、Resource、Agent、Program、Tool、
-- Instruction 等 concept 均由外部 Workflow ontology/catalog 提供；
-- 其中 Agent 和 Program 是 Executor 的子概念，因而可以作为 step_executor 的值。
--
-- 下列白板分组和执行补充元数据算子也必须预先注册在外部 operator catalog：
--   step_instruction(Step) -> Instruction
--   member_of(Step, StepGroup) -> Bool
--   parallelism(StepGroup) -> Integer
--   independent(Step) -> Bool
--   batch_size(Step) -> Integer
--   exclusive_lease(Step, Resource) -> Bool

-- 顶层工作流。
const coscientist_ows:Workflow;

-- 两个虚线视觉分组：
--   catalyst_recommendation_subagent_group 对应 a2:5 / o2:98；
--   crystal_generation_evaluation_subagent_group 对应 a2:6 / o2:106。
const catalyst_recommendation_subagent_group:StepGroup;
const crystal_generation_evaluation_subagent_group:StepGroup;

-- Prepare the workflow output root, scheduler files, registry, pools, and slot directories.
const prepare_workflow_step:Step;

-- Four independent recommendation branches from o2:93, o2:95, o2:96, and o2:97.
const recommend_1_step:Step;
const recommend_2_step:Step;
const recommend_3_step:Step;
const recommend_4_step:Step;

-- Crystal generation/evaluation chain from o2:107 -> o2:110 -> o2:108.
const mattergen_step:Step;
const mattersim_step:Step;

-- Catalytic performance proof gate and downstream synthesis route-design chain:
--   performance_proof_step checks candidate folders under tmp/candidates before
--   they enter pools/candidates;
--   o2:116 synthesis route design subagent runs after MatterSim outputs;
--   synthesis_route_feasibility_analysis_step runs after the 96-well cumulative
--   synthesis route is produced.
const performance_proof_step:Step;
const synthesis_route_design_step:Step;
const synthesis_route_feasibility_analysis_step:Step;

-- 结束节点。
const shutdown_step:Step;

-- Readable StepName identities used by step_name relations.
const prepare_workflow:StepName;
const recommend_1:StepName;
const recommend_2:StepName;
const recommend_3:StepName;
const recommend_4:StepName;
const performance_proof:StepName;
const mattergen:StepName;
const mattersim:StepName;
const synthesis_route_design:StepName;
const synthesis_route_feasibility_analysis:StepName;
const shutdown:StepName;

-- 白板左侧 o2:83 分组中的五类持久输入：
--   o2:84“全水解知识库”；
--   o2:86“实验室规则库”；
--   o2:87“机器人化学家Skills”；
--   o2:88“成功路线库”；
--   o2:85“历史结果”，内部包含成功催化剂、失败催化剂及原因、
--   当前累计合成路线和原液瓶情况。
const overall_water_splitting_knowledge_base:Artifact;
const laboratory_rule_base:Artifact;
const robot_chemist_skill_library:Artifact;
const successful_route_library:Artifact;
const historical_results:Artifact;

-- Runtime output root name provided by the workflow caller.
const result_directory_name:Artifact;

-- Artifacts initialized by prepare_workflow_step.
const workflow_run_context:Artifact;
const scheduler_state:Artifact;
const prepare_workflow_step_result:Artifact;

-- Candidate knowledge cache. Stage steps may update this artifact
-- opportunistically while doing their original stage work, except recommendation
-- steps, which write captured recommendation knowledge under
-- <output_root>/tmp/knowledge first. The path is <output_root>/pools/knowledge.
const candidate_knowledge_base:Artifact;

-- Candidate pool handle initialized by prepare_workflow_step.
-- The path is <output_root>/pools/candidates. Recommendation steps may read
-- this pool but must not write to it directly. performance_proof_step moves
-- candidate folders judged as possible_catalytic_performance into this pool.
-- mattergen_step moves successfully sampled candidate folders out of this pool;
-- failed or interrupted MatterGen candidates remain here for retry.
const candidate_catalyst_pool:Artifact;

-- Failure directories initialized by prepare_workflow_step.
-- The paths are <output_root>/fail and <output_root>/fail/candidates.
-- performance_proof_step moves candidate folders judged as
-- no_catalytic_performance into fail/candidates.
const fail_directory:Artifact;
const fail_candidates_directory:Artifact;

-- tmp/candidates directory initialized by prepare_workflow_step.
-- The path is <output_root>/tmp/candidates. Recommendation steps sync-copy
-- their slot-local ows_Sn_Ck result directories here. performance_proof_step
-- removes each judged candidate folder from tmp/candidates after routing it.
const tmp_candidates_directory:Artifact;

-- tmp/knowledge directory initialized by prepare_workflow_step.
-- The path is <output_root>/tmp/knowledge. During recommendation, if knowledge
-- capture is triggered and knowledge is obtained for one subagent result, the
-- recommendation step creates <output_root>/tmp/knowledge/slot_n/ows_Sn_Ck and
-- writes one JSON file with only these fields: candidate_knowledge_id,
-- knowledge, source. The source field records the source stage, subagent, and
-- catalyst recommendation id.
const tmp_knowledge_directory:Artifact;

-- Slot workspaces initialized by prepare_workflow_step under
-- <output_root>/02-ows-catalyst-recommender/slot_n.
const recommender_slot_1_directory:Artifact;
const recommender_slot_2_directory:Artifact;
const recommender_slot_3_directory:Artifact;
const recommender_slot_4_directory:Artifact;

-- Slot-local recommendation result directories under
-- <output_root>/02-ows-catalyst-recommender/slot_n/ows_Sn_Ck.
const recommendation_slot_1_results:Artifact;
const recommendation_slot_2_results:Artifact;
const recommendation_slot_3_results:Artifact;
const recommendation_slot_4_results:Artifact;

-- o2:110：MatterGen 生成、MatterSim 消费的候选催化剂结构池。
-- The path is <output_root>/pools/structures. It contains candidate folders
-- moved from <output_root>/pools/candidates only after MatterGen sampling is
-- complete and generated structures have been verified, with references to
-- their MatterGen stage workspaces. Recommendation steps read this pool for
-- deduplication. MatterGen result files are written under
-- mattergen_stage_directory.
const candidate_catalyst_structure_pool:Artifact;

-- MatterGen stage workspace initialized by prepare_workflow_step.
-- The path is <output_root>/04-mattergen-structure-sampler. Runtime writes
-- MatterGen result files here and resumes interrupted runs by reading existing
-- files before continuing.
const mattergen_stage_directory:Artifact;

-- MatterSim stage workspace initialized by prepare_workflow_step.
-- The path is <output_root>/05-mattersim-structure-evaluator. MatterSim writes
-- batch workspaces under streaming/batches/<batch_id>.
const mattersim_stage_directory:Artifact;

-- Stage08 round-parallel synthesis workspace initialized by
-- prepare_workflow_step. The path is
-- <output_root>/08-round-parallel-synthesis-advisor.
const round_parallel_synthesis_stage_directory:Artifact;

-- MatterSim outputs:
--   1. o2:113 novel and stable catalysts, stored under
--      <output_root>/pools/novel_and_stable_catalysts;
--   2. o2:114 non-novel or unstable catalysts.
const novel_and_stable_catalysts:Artifact;
const non_novel_or_unstable_catalysts:Artifact;

-- Catalytic performance proof results from tmp/candidates routing.
-- They correspond to folders moved to pools/candidates or fail/candidates.
const performance_proven_catalysts:Artifact;
const performance_rejected_catalysts:Artifact;

-- Main synthesis route-design outputs:
--   * route updates that can be merged into the total route;
--   * o2:118 catalysts that cannot join the total synthesis route.
const synthesis_route_update:Artifact;
const catalysts_unable_to_join_total_route:Artifact;

-- Stage08 round-parallel synthesis artifacts. The round files live under
-- <output_root>/08-round-parallel-synthesis-advisor/rounds/<round_id>. The
-- cumulative files and parameter CSVs live directly under
-- <output_root>/08-round-parallel-synthesis-advisor.
const synthesis_input_summary:Artifact;
const round_parallel_synthesis_route:Artifact;
const round_parallel_synthesis_index:Artifact;
const cumulative_synthesis_parameter_csv_files:Artifact;
const source_liquid_inventory:Artifact;
const source_liquid_preparation_methods:Artifact;
const cumulative_synthesis_route:Artifact;
const chemskills_execution_spec:Artifact;

-- Written only when SOURCE_LIQUID_PREPARATION_METHODS.json reports that the
-- cumulative 96-well route is complete.
const source_liquid_bottle_preparation:Artifact;

-- Stage09 synthesis-route safety and feasibility artifacts. The files live
-- under <output_root>/09-synthesis-safety-feasibility-judge/rounds/<round_id>.
const synthesis_safety_feasibility_judgment:Artifact;
const synthesis_safety_feasibility_judgment_audit:Artifact;

-- o2:122 的完成结果及 o2:121 的关闭结果。
const completed_96_well_plate_synthesis_route:Artifact;
const workflow_closed:Artifact;

-- 白板中的四个 subagent 方框 o2:89、o2:90、o2:91、o2:92。
const recommender_1_agent:Agent;
const recommender_2_agent:Agent;
const recommender_3_agent:Agent;
const recommender_4_agent:Agent;

-- 白板和附件共同确定的其他执行主体。
const crystal_generation_evaluation_agent:Agent;
const performance_prover_agent:Agent;
const synthesis_route_designer_agent:Agent;
const synthesis_safety_feasibility_judge_agent:Agent;
const main_coordinator_agent:Agent;

-- Program executor for workflow preparation.
const prepare_workflow_program:Program;

-- ==================== prepare_workflow_step ：开始instruction========================
-- Instruction body: ./instructions/prepare-workflow.md
-- ==================== prepare_workflow_step ：结束instruction========================
const call_prepare_workflow_step_script_instruction:Instruction;

-- ==================== recommend_1_step/recommend_2_step/recommend_3_step/recommend_4_step ：开始instruction========================
-- Instruction body: ./instructions/recommend-candidate.md
-- ==================== recommend_1_step/recommend_2_step/recommend_3_step/recommend_4_step ：结束instruction========================
const recommend_candidate_to_slot_and_tmp_directory_instruction:Instruction;

-- ==================== performance_proof_step ：开始instruction========================
-- Instruction body: ./instructions/prove-performance.md
-- ==================== performance_proof_step ：结束instruction========================
const prove_tmp_candidate_performance_and_route_candidate_instruction:Instruction;

-- ==================== mattergen_step ：开始instruction========================
-- Instruction body: ./instructions/sample-structure.md
-- ==================== mattergen_step ：结束instruction========================
const sample_candidate_structure_and_move_from_candidates_instruction:Instruction;

-- ==================== mattersim_step ：开始instruction========================
-- Instruction body: ./instructions/evaluate-structures.md
-- ==================== mattersim_step ：结束instruction========================
const evaluate_candidate_structures_and_route_candidates_instruction:Instruction;

-- ==================== synthesis_route_design_step ：开始instruction========================
-- Instruction body: ./instructions/design-synthesis-route.md
-- ==================== synthesis_route_design_step ：结束instruction========================
const design_round_parallel_synthesis_route_instruction:Instruction;

-- ==================== synthesis_route_feasibility_analysis_step ：开始instruction========================
-- Instruction body: ./instructions/analyze-route-feasibility.md
-- ==================== synthesis_route_feasibility_analysis_step ：结束instruction========================
const analyze_synthesis_route_safety_feasibility_instruction:Instruction;

-- ==================== shutdown_step ：开始instruction========================
-- Instruction body: ./instructions/shutdown-workflow.md
-- ==================== shutdown_step ：结束instruction========================
const close_workflow_after_cumulative_96_route_instruction:Instruction;

-- 白板明确出现及 workflow 补充使用的技能/能力。
const web_search_tool:Tool;
const mattergen_skill:Tool;
const mattersim_skill:Tool;
const catalytic_performance_prover_skill:Tool;
const round_parallel_synthesis_advisor_skill:Tool;
const synthesis_safety_feasibility_judge_skill:Tool;

-- 附件确认 MatterGen 与 MatterSim 都需要 GPU。
-- gpu_device 是外部 catalog 预置的 Resource identity，规范单位为“设备个数”；
-- source 中这里只引用该 identity，不新建 gpu 这种未注册的资源类型或单位。
const gpu_device:Resource;

workflow coscientist_ows {
    -- 顶层输入：左侧五个数据源。
    input_workflow(
        coscientist_ows,
        overall_water_splitting_knowledge_base
    ) == True;
    input_workflow(coscientist_ows, laboratory_rule_base) == True;
    input_workflow(coscientist_ows, robot_chemist_skill_library) == True;
    input_workflow(coscientist_ows, successful_route_library) == True;
    input_workflow(coscientist_ows, historical_results) == True;
    input_workflow(coscientist_ows, result_directory_name) == True;

    -- 备选知识库和历史结果都是跨轮次持久状态，因此既可以有初始内容，
    -- 也会在本轮被追加后作为输出保留。
    input_workflow(coscientist_ows, candidate_knowledge_base) == True;
    output_workflow(coscientist_ows, candidate_knowledge_base) == True;
    output_workflow(coscientist_ows, historical_results) == True;

    -- 对外最终结果：完成 96 孔板合成路线，产出合成路线安全/可行性分析，
    -- 并确认所有 subagent 已关闭。
    output_workflow(
        coscientist_ows,
        completed_96_well_plate_synthesis_route
    ) == True;
    output_workflow(
        coscientist_ows,
        synthesis_safety_feasibility_judgment
    ) == True;
    output_workflow(
        coscientist_ows,
        synthesis_safety_feasibility_judgment_audit
    ) == True;
    output_workflow(coscientist_ows, workflow_closed) == True;

    -- Stable Step identities are mapped to readable StepName values.
    step_name(prepare_workflow_step) == prepare_workflow;
    step_name(recommend_1_step) == recommend_1;
    step_name(recommend_2_step) == recommend_2;
    step_name(recommend_3_step) == recommend_3;
    step_name(recommend_4_step) == recommend_4;
    step_name(performance_proof_step) == performance_proof;
    step_name(mattergen_step) == mattergen;
    step_name(mattersim_step) == mattersim;
    step_name(synthesis_route_design_step) == synthesis_route_design;
    step_name(synthesis_route_feasibility_analysis_step) == synthesis_route_feasibility_analysis;
    step_name(shutdown_step) == shutdown;

    -- prepare_workflow_step calls workflow相关/scripts/prepare_workflow_step.py.
    -- It creates the output root, entry files, scheduler registry,
    -- <output_root>/04-mattergen-structure-sampler,
    -- <output_root>/05-mattersim-structure-evaluator/streaming/batches,
    -- <output_root>/08-round-parallel-synthesis-advisor/rounds,
    -- <output_root>/08-round-parallel-synthesis-advisor/synthesis-routes,
    -- <output_root>/pools/candidates, <output_root>/pools/knowledge,
    -- <output_root>/pools/structures,
    -- <output_root>/pools/novel_and_stable_catalysts,
    -- <output_root>/fail, <output_root>/fail/candidates,
    -- <output_root>/tmp/candidates, <output_root>/tmp/knowledge, and Stage02
    -- slot directories before any recommender reads the candidate pool.
    step_instruction(
        prepare_workflow_step
    ) == "./instructions/prepare-workflow.md";
    step_executor(prepare_workflow_step) == prepare_workflow_program;
    consumes(prepare_workflow_step, result_directory_name) == True;
    produces(prepare_workflow_step, workflow_run_context) == True;
    produces(prepare_workflow_step, scheduler_state) == True;
    produces(prepare_workflow_step, mattergen_stage_directory) == True;
    produces(prepare_workflow_step, mattersim_stage_directory) == True;
    produces(
        prepare_workflow_step,
        round_parallel_synthesis_stage_directory
    ) == True;
    produces(prepare_workflow_step, candidate_knowledge_base) == True;
    produces(prepare_workflow_step, candidate_catalyst_pool) == True;
    produces(prepare_workflow_step, candidate_catalyst_structure_pool) == True;
    produces(prepare_workflow_step, novel_and_stable_catalysts) == True;
    produces(prepare_workflow_step, fail_directory) == True;
    produces(prepare_workflow_step, fail_candidates_directory) == True;
    produces(prepare_workflow_step, tmp_candidates_directory) == True;
    produces(prepare_workflow_step, tmp_knowledge_directory) == True;
    produces(prepare_workflow_step, recommender_slot_1_directory) == True;
    produces(prepare_workflow_step, recommender_slot_2_directory) == True;
    produces(prepare_workflow_step, recommender_slot_3_directory) == True;
    produces(prepare_workflow_step, recommender_slot_4_directory) == True;
    produces(prepare_workflow_step, prepare_workflow_step_result) == True;

    -- The recommendation area contains four parallel independent branches.
    -- parallelism=4 is the number of recommendation workers.
    member_of(
        recommend_1_step,
        catalyst_recommendation_subagent_group
    ) == True;
    member_of(
        recommend_2_step,
        catalyst_recommendation_subagent_group
    ) == True;
    member_of(
        recommend_3_step,
        catalyst_recommendation_subagent_group
    ) == True;
    member_of(
        recommend_4_step,
        catalyst_recommendation_subagent_group
    ) == True;
    parallelism(catalyst_recommendation_subagent_group) == 4;
    independent(recommend_1_step) == True;
    independent(recommend_2_step) == True;
    independent(recommend_3_step) == True;
    independent(recommend_4_step) == True;

    -- 晶体生成评测区只包含 MatterGen 与 MatterSim 两个执行步骤；
    -- 中间的候选催化剂结构池是 Artifact，不是 Step。
    member_of(
        mattergen_step,
        crystal_generation_evaluation_subagent_group
    ) == True;
    member_of(
        mattersim_step,
        crystal_generation_evaluation_subagent_group
    ) == True;

    -- 执行器映射：白板 subagent -> 对应业务 Step。
    step_instruction(
        recommend_1_step
    ) == "./instructions/recommend-candidate.md";
    step_instruction(
        recommend_2_step
    ) == "./instructions/recommend-candidate.md";
    step_instruction(
        recommend_3_step
    ) == "./instructions/recommend-candidate.md";
    step_instruction(
        recommend_4_step
    ) == "./instructions/recommend-candidate.md";
    step_executor(recommend_1_step) == recommender_1_agent;
    step_executor(recommend_2_step) == recommender_2_agent;
    step_executor(recommend_3_step) == recommender_3_agent;
    step_executor(recommend_4_step) == recommender_4_agent;

    step_instruction(
        mattergen_step
    ) == "./instructions/sample-structure.md";
    step_executor(mattergen_step) == crystal_generation_evaluation_agent;
    step_instruction(
        mattersim_step
    ) == "./instructions/evaluate-structures.md";
    step_executor(mattersim_step) == crystal_generation_evaluation_agent;
    step_instruction(
        performance_proof_step
    ) == "./instructions/prove-performance.md";
    step_executor(performance_proof_step) == performance_prover_agent;
    step_executor(
        synthesis_route_design_step
    ) == synthesis_route_designer_agent;
    step_instruction(
        synthesis_route_design_step
    ) == "./instructions/design-synthesis-route.md";
    step_instruction(
        synthesis_route_feasibility_analysis_step
    ) == "./instructions/analyze-route-feasibility.md";
    step_executor(
        synthesis_route_feasibility_analysis_step
    ) == synthesis_safety_feasibility_judge_agent;
    step_instruction(
        shutdown_step
    ) == "./instructions/shutdown-workflow.md";
    step_executor(shutdown_step) == main_coordinator_agent;

    -- 白板明确出现“联网搜索”，但没有给出 Model、Engine、ApiBase 等配置；
    -- 因此只声明允许使用的工具，不伪造 agent_config。
    allowed_tool(recommender_1_agent, web_search_tool) == True;
    allowed_tool(recommender_2_agent, web_search_tool) == True;
    allowed_tool(recommender_3_agent, web_search_tool) == True;
    allowed_tool(recommender_4_agent, web_search_tool) == True;
    allowed_tool(
        crystal_generation_evaluation_agent,
        web_search_tool
    ) == True;
    allowed_tool(
        synthesis_route_designer_agent,
        web_search_tool
    ) == True;
    allowed_tool(
        synthesis_route_designer_agent,
        round_parallel_synthesis_advisor_skill
    ) == True;
    allowed_tool(
        performance_prover_agent,
        catalytic_performance_prover_skill
    ) == True;
    allowed_tool(
        synthesis_safety_feasibility_judge_agent,
        synthesis_safety_feasibility_judge_skill
    ) == True;
    allowed_tool(
        crystal_generation_evaluation_agent,
        mattergen_skill
    ) == True;
    allowed_tool(
        crystal_generation_evaluation_agent,
        mattersim_skill
    ) == True;

    -- 附件补充的实现参数，不把它们画成额外业务节点：
    --   * MatterSim 以 8 个 sampled candidate 为一个 micro-batch；
    --   * 两个技能各需要 1 块 GPU；
    --   * MatterGen ideally runs one subprocess per confirmed GPU ID, and each
    --     subprocess owns one GPU ID while sampling;
    --   * MatterSim 以 8 个 sampled candidate 为一个 micro-batch，并同样需要
    --     排他 GPU。
    batch_size(mattersim_step) == 8;
    resource_requirement(mattergen_step, gpu_device) == 1;
    resource_requirement(mattersim_step, gpu_device) == 1;
    exclusive_lease(mattergen_step, gpu_device) == True;
    exclusive_lease(mattersim_step, gpu_device) == True;

    -- 左侧知识/规则/历史分组馈入四个推荐器。
    -- candidate_knowledge_base 对应顶部橙色反馈线；
    -- candidate_catalyst_pool 对应未吸附终点的 c2:187，并用于去重和协调在途候选。
    consumes_multi(recommend_1_step) == [
        overall_water_splitting_knowledge_base,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        historical_results,
        workflow_run_context,
        scheduler_state,
        candidate_knowledge_base,
        candidate_catalyst_pool,
        candidate_catalyst_structure_pool,
        novel_and_stable_catalysts,
        fail_candidates_directory,
        tmp_candidates_directory,
        tmp_knowledge_directory,
        recommender_slot_1_directory
    ];
    consumes_multi(recommend_2_step) == [
        overall_water_splitting_knowledge_base,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        historical_results,
        workflow_run_context,
        scheduler_state,
        candidate_knowledge_base,
        candidate_catalyst_pool,
        candidate_catalyst_structure_pool,
        novel_and_stable_catalysts,
        fail_candidates_directory,
        tmp_candidates_directory,
        tmp_knowledge_directory,
        recommender_slot_2_directory
    ];
    consumes_multi(recommend_3_step) == [
        overall_water_splitting_knowledge_base,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        historical_results,
        workflow_run_context,
        scheduler_state,
        candidate_knowledge_base,
        candidate_catalyst_pool,
        candidate_catalyst_structure_pool,
        novel_and_stable_catalysts,
        fail_candidates_directory,
        tmp_candidates_directory,
        tmp_knowledge_directory,
        recommender_slot_3_directory
    ];
    consumes_multi(recommend_4_step) == [
        overall_water_splitting_knowledge_base,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        historical_results,
        workflow_run_context,
        scheduler_state,
        candidate_knowledge_base,
        candidate_catalyst_pool,
        candidate_catalyst_structure_pool,
        novel_and_stable_catalysts,
        fail_candidates_directory,
        tmp_candidates_directory,
        tmp_knowledge_directory,
        recommender_slot_4_directory
    ];

    -- Recommendation steps write primary slot-local results under
    -- <output_root>/02-ows-catalyst-recommender/slot_n/ows_Sn_Ck. Each result
    -- contains CANDIDATE_PAYLOAD.json and REASONING.md. Each completed
    -- ows_Sn_Ck directory is sync-copied to <output_root>/tmp/candidates for
    -- later checks. If recommendation-time knowledge capture is triggered and
    -- obtains knowledge, the same slot/result structure is created under
    -- <output_root>/tmp/knowledge with one JSON file containing only
    -- candidate_knowledge_id, knowledge, and source. Later proof artifacts may
    -- be placed in the same result directory by downstream steps.
    -- Recommendation steps may read candidate_catalyst_pool,
    -- candidate_catalyst_structure_pool, novel_and_stable_catalysts,
    -- fail_candidates_directory, and candidate_knowledge_base but must not write
    -- under <output_root>/pools.
    -- The grammar has no optional_produces relation, so this declares the
    -- allowed tmp/knowledge write without making knowledge capture required.
    produces(recommend_1_step, recommendation_slot_1_results) == True;
    produces(recommend_1_step, tmp_candidates_directory) == True;
    produces(recommend_1_step, tmp_knowledge_directory) == True;
    produces(recommend_2_step, recommendation_slot_2_results) == True;
    produces(recommend_2_step, tmp_candidates_directory) == True;
    produces(recommend_2_step, tmp_knowledge_directory) == True;
    produces(recommend_3_step, recommendation_slot_3_results) == True;
    produces(recommend_3_step, tmp_candidates_directory) == True;
    produces(recommend_3_step, tmp_knowledge_directory) == True;
    produces(recommend_4_step, recommendation_slot_4_results) == True;
    produces(recommend_4_step, tmp_candidates_directory) == True;
    produces(recommend_4_step, tmp_knowledge_directory) == True;

    -- performance_proof_step is executed by performance_prover_agent according
    -- to prove_tmp_candidate_performance_and_route_candidate_instruction. The
    -- agent uses stage08-catalytic-performance-prover, writes the proof
    -- Markdown and audit JSON inside each candidate folder, routes judged
    -- folders to pools/candidates or fail/candidates, and removes judged
    -- folders from tmp/candidates.
    consumes_multi(performance_proof_step) == [
        tmp_candidates_directory,
        candidate_catalyst_pool,
        fail_candidates_directory
    ];
    produces(performance_proof_step, tmp_candidates_directory) == True;
    produces(performance_proof_step, candidate_catalyst_pool) == True;
    produces(performance_proof_step, fail_candidates_directory) == True;
    produces(performance_proof_step, performance_proven_catalysts) == True;
    produces(performance_proof_step, performance_rejected_catalysts) == True;

    -- 晶体生成评测主链：
    --   证明通过后的候选催化剂池 -> MatterGen -> 候选催化剂结构池 -> MatterSim。
    -- When MatterGen sampling is complete, the candidate folder is moved out
    -- of candidate_catalyst_pool and into candidate_catalyst_structure_pool.
    consumes(mattergen_step, candidate_catalyst_pool) == True;
    consumes(mattergen_step, mattergen_stage_directory) == True;
    produces(mattergen_step, candidate_catalyst_pool) == True;
    produces(mattergen_step, mattergen_stage_directory) == True;
    produces(
        mattergen_step,
        candidate_catalyst_structure_pool
    ) == True;
    consumes(
        mattersim_step,
        candidate_catalyst_structure_pool
    ) == True;
    consumes(mattersim_step, mattersim_stage_directory) == True;
    consumes(mattersim_step, novel_and_stable_catalysts) == True;
    consumes(mattersim_step, fail_candidates_directory) == True;
    consumes(
        mattersim_step,
        overall_water_splitting_knowledge_base
    ) == True;

    -- MatterSim produces candidate classifications and routes judged candidate
    -- folders out of the structure pool.
    -- 对每个候选，novel_and_stable 与 non_novel_or_unstable 两类结果互斥。
    -- novel_and_stable_catalysts 已包含进入合成路线设计所需的评测证据；
    -- 附件中的 evaluation summary 在白板层级合并进该 Artifact，不另造白板节点。
    produces(mattersim_step, candidate_catalyst_structure_pool) == True;
    produces(mattersim_step, mattersim_stage_directory) == True;
    produces(mattersim_step, novel_and_stable_catalysts) == True;
    produces(mattersim_step, fail_candidates_directory) == True;
    produces(
        mattersim_step,
        non_novel_or_unstable_catalysts
    ) == True;

    -- “通过”支路进入合成路线设计。
    -- 节点文字明确区分“没有总路线时新建设计”和“已有总路线时补入”；
    -- 因此 historical_results 是白板文字隐含的必要输入，它提供当前累计路线与原液瓶状态。
    consumes_multi(synthesis_route_design_step) == [
        novel_and_stable_catalysts,
        round_parallel_synthesis_stage_directory,
        historical_results,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        fail_candidates_directory
    ];
    -- 对每个候选，synthesis_route_update 与
    -- catalysts_unable_to_join_total_route 两类结果同样互斥。
    produces(
        synthesis_route_design_step,
        synthesis_route_update
    ) == True;
    produces(
        synthesis_route_design_step,
        catalysts_unable_to_join_total_route
    ) == True;
    produces(
        synthesis_route_design_step,
        round_parallel_synthesis_stage_directory
    ) == True;
    produces(synthesis_route_design_step, novel_and_stable_catalysts) == True;
    produces(synthesis_route_design_step, fail_candidates_directory) == True;
    produces(synthesis_route_design_step, synthesis_input_summary) == True;
    produces(synthesis_route_design_step, round_parallel_synthesis_route) == True;
    produces(synthesis_route_design_step, round_parallel_synthesis_index) == True;
    produces(
        synthesis_route_design_step,
        cumulative_synthesis_parameter_csv_files
    ) == True;
    produces(synthesis_route_design_step, source_liquid_inventory) == True;
    produces(synthesis_route_design_step, source_liquid_preparation_methods) == True;
    produces(synthesis_route_design_step, cumulative_synthesis_route) == True;
    produces(synthesis_route_design_step, chemskills_execution_spec) == True;
    -- The grammar has no optional_produces relation, so this declares the
    -- final 96-well source-liquid preparation Markdown as a possible Stage08
    -- output even though it is written only when the cumulative route is
    -- complete.
    produces(synthesis_route_design_step, source_liquid_bottle_preparation) == True;
    -- The Stage08 route step produces this artifact only when the cumulative
    -- route reaches 96 wells and the Stage08 completion contract is satisfied.
    produces(
        synthesis_route_design_step,
        completed_96_well_plate_synthesis_route
    ) == True;

    -- 合成路线可行性分析在 Stage08 产出 96 wells 累计路线后运行，输出
    -- Stage09 judgment Markdown 和 audit JSON。
    consumes_multi(synthesis_route_feasibility_analysis_step) == [
        cumulative_synthesis_route,
        completed_96_well_plate_synthesis_route
    ];
    produces(
        synthesis_route_feasibility_analysis_step,
        synthesis_safety_feasibility_judgment
    ) == True;
    produces(
        synthesis_route_feasibility_analysis_step,
        synthesis_safety_feasibility_judgment_audit
    ) == True;

    -- shutdown_step 读取 cumulative_synthesis_route，并按
    -- close_workflow_after_cumulative_96_route_instruction 判断其中是否已经
    -- 包含 96 个催化剂的合成路线，同时等待合成路线可行性分析结果产出；未完成时，
    -- Stage08 累计文件和各池状态继续供前序 step 消费。
    consumes(shutdown_step, cumulative_synthesis_route) == True;
    consumes(shutdown_step, synthesis_safety_feasibility_judgment) == True;
    consumes(shutdown_step, synthesis_safety_feasibility_judgment_audit) == True;
    consumes(
        shutdown_step,
        completed_96_well_plate_synthesis_route
    ) == True;
    produces(shutdown_step, workflow_closed) == True;

    -- The scheduler init boundary is now represented by prepare_workflow_step.
    -- next-action/register/claim/complete/release, Z-scheme aggregation, and
    -- novelty still need separate workflow modeling before they can be treated
    -- as first-class steps.
}
