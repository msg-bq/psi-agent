-- 鍏夊偓鍖栧叏姘磋В锛坥verall water splitting锛孫WS锛塁o-scientist 鏁版嵁娴併€?
--
-- 鏉ユ簮浼樺厛绾э細
--   1. 椋炰功鐧芥澘鈥滃厜鍌寲鍏ㄦ按瑙gent杩涘睍鈥濈殑鐧诲綍鎬佸師濮嬭妭鐐规暟鎹紱
--      鏈瀹為檯璇诲彇鍒?82 涓妭鐐癸紝鍏朵腑 40 涓浘褰?鏂囧瓧鑺傜偣銆?2 鏉¤繛鎺ョ嚎銆?
--   2. coscientist-ows-entry.zip 涓殑鎶€鑳借鏄庡拰 streaming scheduler锛?
--      瀹冨彧鐢ㄤ簬琛ュ厖鎵ц鍣ㄣ€佸€欓€夋睜銆丟PU 鍜屾壒澶勭悊绛夌櫧鏉挎湭灞曞紑鐨勫疄鐜拌涔夈€?
--   3. 浼氳瘽 019f7d37-a6af-77d0-88d5-b7bdc3085d90锛?
--      璇ヤ細璇濆彧琛ュ厖 grammar / validator / lowering / runtime 鐨勮亴璐ｈ竟鐣岋紝
--      娌℃湁鎻愪緵 OWS 涓撳睘鑺傜偣鎴栬繛绾裤€?
--
-- 鐧芥澘鍒版湰鏂囦欢鐨勮浆鎹㈣鍒欙細
--   * 鐧芥澘涓殑 subagent 鏂规琚缓妯′负 Agent锛岀揣闅忓叾鍚庣殑涓氬姟鏂规琚缓妯′负 Step锛?
--     涓よ€呬箣闂寸殑绠ご鐢?step_executor(Step) == Agent 琛ㄨ揪銆?
--   * 鍦嗘煴銆佸钩琛屽洓杈瑰舰鍜岃繃绋嬭緭鍑哄潎鎸?Artifact 寤烘ā銆?
--   * 鈥滈€氳繃 / 涓嶉€氳繃鈥濅笉鏄潡绾?if/else锛岃€屾槸涓や釜浜掓枼鐨勭粨鏋?Artifact銆?
--   * 鐧芥澘鐨勪笁涓┖鐧藉妗?o2:83銆乷2:98銆乷2:106 鍙槸瑙嗚鍒嗙粍锛屼笉鏄繍琛屾楠ゃ€?
--   * 鐧芥澘鏂囧瓧鑺傜偣 a10:7銆乤10:8 鍙槸杈规爣绛撅紝鍒嗗埆瀵瑰簲鈥滈€氳繃鈥濆拰鈥滀笉閫氳繃鈥濄€?
--   * 杩炴帴绾?c2:187 鐨勭粓鐐规病鏈夊惛闄勫埌鍏蜂綋鑺傜偣锛屼絾鍑犱綍涓婃帴鍏ユ帹鑽愯緭鍏ユ€荤嚎锛?
--     缁撳悎闄勪欢涓帹鑽愬櫒浼氳鍙?candidate registry 鐨勪簨瀹烇紝鏈枃浠舵妸瀹冭В閲婁负
--     鈥滃€欓€夊偓鍖栧墏姹犲弽棣堢粰鍥涗釜鎺ㄨ崘姝ラ鈥濄€傝繖鏄敮涓€闇€瑕佸嚑浣曞拰闄勪欢鍏卞悓琛ュ叏鐨勮竟銆?
--
-- 璇硶鍜岃繍琛屾椂杈圭晫锛?
--   * 鏈枃浠朵娇鐢?WorkflowStrict.g4 鍙В鏋愮殑 .workflow 琛ㄩ潰璇硶銆?
--   * 鈥?=鈥濊〃绀哄叧绯绘垚绔嬶紝涓嶆槸鍛戒护寮忚祴鍊硷紱婧愮爜鍏堝悗椤哄簭涔熶笉浠ｈ〃鎵ц椤哄簭銆?
--   * consumes / produces 琛ㄨ揪鏁版嵁鍏崇郴锛岀湡姝ｇ殑骞跺彂銆佸垎鏀Е鍙戙€佹寔涔呭寲鏇存柊鍜屽仠姝㈣涓?
--     浠嶉渶 validator銆乴owering 涓?runtime 钀藉疄銆?
--   * if(formula, then_term, else_term) 鍙兘浜х敓涓€涓€硷紝涓嶈兘鍖呬綇 Step锛涘洜姝よ繖閲屼笉鐢?if
--     浼€犵櫧鏉胯矾鐢憋紝鑰屾槸鐢ㄤ笉鍚岀殑缁撴灉 Artifact 琛ㄨ揪鍚勬潯鏁版嵁鏀矾銆?
--   * member_of銆乸arallelism銆乮ndependent銆乥atch_size銆乪xclusive_lease
--     鏉ヨ嚜澶栭儴 operator catalog锛?
--     grammar 鑳借В鏋愯繖浜涜皟鐢紝浣嗘墽琛屽墠浠嶉渶鐩稿簲鐨?validator/runtime 鏀寔銆?

-- Workflow source 鍙０鏄庢湰鏂囦欢浣跨敤鐨勫叿浣?identity锛屼笉鍦ㄦ湰鍦板畾涔?concept 鎴?operator銆?
-- Workflow銆丼tep銆丼tepGroup銆丄rtifact銆丷esource銆丄gent銆丳rogram銆乀ool銆?
-- Instruction 绛?concept 鍧囩敱澶栭儴 Workflow ontology/catalog 鎻愪緵锛?
-- 鍏朵腑 Agent 鍜?Program 鏄?Executor 鐨勫瓙姒傚康锛屽洜鑰屽彲浠ヤ綔涓?step_executor 鐨勫€笺€?
--
-- 涓嬪垪鐧芥澘鍒嗙粍鍜屾墽琛岃ˉ鍏呭厓鏁版嵁绠楀瓙涔熷繀椤婚鍏堟敞鍐屽湪澶栭儴 operator catalog锛?
--   step_instruction(Step) -> Instruction
--   member_of(Step, StepGroup) -> Bool
--   parallelism(StepGroup) -> Integer
--   independent(Step) -> Bool
--   batch_size(Step) -> Integer
--   exclusive_lease(Step, Resource) -> Bool

-- 椤跺眰宸ヤ綔娴併€?
const coscientist_ows:Workflow;

-- 涓や釜铏氱嚎瑙嗚鍒嗙粍锛?
--   catalyst_recommendation_subagent_group 瀵瑰簲 a2:5 / o2:98锛?
--   crystal_generation_evaluation_subagent_group 瀵瑰簲 a2:6 / o2:106銆?
const catalyst_recommendation_subagent_group:StepGroup;
const crystal_generation_evaluation_subagent_group:StepGroup;

-- Prepare the workflow output root, scheduler files, registry, pools, and slot directories.
const prepare_workflow_step:Step;

-- Four independent recommendation branches from o2:93, o2:95, o2:96, and o2:97.
const recommend_1_step:Step;
const recommend_2_step:Step;
const recommend_3_step:Step;
const recommend_4_step:Step;
const merge_recommendation_outputs_step:Step;

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

-- 缁撴潫鑺傜偣銆?
const shutdown_step:Step;

-- Readable StepName identities used by step_name relations.
const prepare_workflow:StepName;
const recommend_1:StepName;
const recommend_2:StepName;
const recommend_3:StepName;
const recommend_4:StepName;
const merge_recommendation_outputs:StepName;
const performance_proof:StepName;
const mattergen:StepName;
const mattersim:StepName;
const synthesis_route_design:StepName;
const synthesis_route_feasibility_analysis:StepName;
const shutdown:StepName;

-- 鐧芥澘宸︿晶 o2:83 鍒嗙粍涓殑浜旂被鎸佷箙杈撳叆锛?
--   o2:84鈥滃叏姘磋В鐭ヨ瘑搴撯€濓紱
--   o2:86鈥滃疄楠屽瑙勫垯搴撯€濓紱
--   o2:87鈥滄満鍣ㄤ汉鍖栧瀹禨kills鈥濓紱
--   o2:88鈥滄垚鍔熻矾绾垮簱鈥濓紱
--   o2:85鈥滃巻鍙茬粨鏋溾€濓紝鍐呴儴鍖呭惈鎴愬姛鍌寲鍓傘€佸け璐ュ偓鍖栧墏鍙婂師鍥犮€?
--   褰撳墠绱鍚堟垚璺嚎鍜屽師娑茬摱鎯呭喌銆?
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

-- Single-assignment versions of the mutable directories and pools. The
-- *_initial artifacts are created by prepare_workflow_step; the unqualified
-- names are reserved for each directory or pool's final workflow state.
const mattergen_stage_directory_initial:Artifact;
const mattersim_stage_directory_initial:Artifact;
const round_parallel_synthesis_stage_directory_initial:Artifact;
const candidate_catalyst_pool_initial:Artifact;
const candidate_catalyst_structure_pool_initial:Artifact;
const novel_and_stable_catalysts_initial:Artifact;
const fail_candidates_directory_initial:Artifact;
const tmp_candidates_directory_initial:Artifact;
const tmp_knowledge_directory_initial:Artifact;

-- Independent recommendation deltas and their explicit fan-in result.
const tmp_candidates_directory_from_recommend_1:Artifact;
const tmp_candidates_directory_from_recommend_2:Artifact;
const tmp_candidates_directory_from_recommend_3:Artifact;
const tmp_candidates_directory_from_recommend_4:Artifact;
const tmp_knowledge_directory_from_recommend_1:Artifact;
const tmp_knowledge_directory_from_recommend_2:Artifact;
const tmp_knowledge_directory_from_recommend_3:Artifact;
const tmp_knowledge_directory_from_recommend_4:Artifact;
const tmp_candidates_directory_after_recommendations:Artifact;

-- Stage-to-stage versions before the final shared artifact names are emitted.
const candidate_catalyst_pool_after_performance_proof:Artifact;
const fail_candidates_directory_after_performance_proof:Artifact;
const candidate_catalyst_structure_pool_after_mattergen:Artifact;
const novel_and_stable_catalysts_after_mattersim:Artifact;
const fail_candidates_directory_after_mattersim:Artifact;

-- Candidate knowledge cache. Stage steps may update this artifact
-- opportunistically while doing their original stage work, except recommendation
-- steps, which write captured recommendation knowledge under
-- <output_root>/tmp/knowledge first. The path is <output_root>/pools/knowledge.
const candidate_knowledge_base_initial:Artifact;
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

-- tmp/knowledge directory states. prepare_workflow_step creates the initial
-- directory, every recommender emits a per-slot delta, and the merge step
-- produces this final artifact. A captured delta contains the knowledge file;
-- an empty delta contains a captured=false manifest and no knowledge file.
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

-- o2:110锛歁atterGen 鐢熸垚銆丮atterSim 娑堣垂鐨勫€欓€夊偓鍖栧墏缁撴瀯姹犮€?
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

-- o2:122 鐨勫畬鎴愮粨鏋滃強 o2:121 鐨勫叧闂粨鏋溿€?
const completed_96_well_plate_synthesis_route:Artifact;
const workflow_closed:Artifact;

-- 鐧芥澘涓殑鍥涗釜 subagent 鏂规 o2:89銆乷2:90銆乷2:91銆乷2:92銆?
const recommender_1_agent:Agent;
const recommender_2_agent:Agent;
const recommender_3_agent:Agent;
const recommender_4_agent:Agent;

-- 鐧芥澘鍜岄檮浠跺叡鍚岀‘瀹氱殑鍏朵粬鎵ц涓讳綋銆?
const crystal_generation_evaluation_agent:Agent;
const performance_prover_agent:Agent;
const synthesis_route_designer_agent:Agent;
const synthesis_safety_feasibility_judge_agent:Agent;
const main_coordinator_agent:Agent;

-- Program executors for workflow preparation and recommendation fan-in.
const prepare_workflow_program:Program;
const merge_recommendation_outputs_program:Program;

-- ==================== prepare_workflow_step 锛氬紑濮媔nstruction========================
-- Instruction body: ./instructions/prepare-workflow.md
-- ==================== prepare_workflow_step 锛氱粨鏉焛nstruction========================
const call_prepare_workflow_step_script_instruction:Instruction;

-- ==================== recommend_1_step/recommend_2_step/recommend_3_step/recommend_4_step 锛氬紑濮媔nstruction========================
-- Instruction body: ./instructions/recommend-candidate.md
-- ==================== recommend_1_step/recommend_2_step/recommend_3_step/recommend_4_step 锛氱粨鏉焛nstruction========================
const recommend_candidate_to_slot_and_tmp_directory_instruction:Instruction;

-- ==================== performance_proof_step 锛氬紑濮媔nstruction========================
-- Instruction body: ./instructions/prove-performance.md
-- ==================== performance_proof_step 锛氱粨鏉焛nstruction========================
const prove_tmp_candidate_performance_and_route_candidate_instruction:Instruction;

-- ==================== mattergen_step 锛氬紑濮媔nstruction========================
-- Instruction body: ./instructions/sample-structure.md
-- ==================== mattergen_step 锛氱粨鏉焛nstruction========================
const sample_candidate_structure_and_move_from_candidates_instruction:Instruction;

-- ==================== mattersim_step 锛氬紑濮媔nstruction========================
-- Instruction body: ./instructions/evaluate-structures.md
-- ==================== mattersim_step 锛氱粨鏉焛nstruction========================
const evaluate_candidate_structures_and_route_candidates_instruction:Instruction;

-- ==================== synthesis_route_design_step 锛氬紑濮媔nstruction========================
-- Instruction body: ./instructions/design-synthesis-route.md
-- ==================== synthesis_route_design_step 锛氱粨鏉焛nstruction========================
const design_round_parallel_synthesis_route_instruction:Instruction;

-- ==================== synthesis_route_feasibility_analysis_step 锛氬紑濮媔nstruction========================
-- Instruction body: ./instructions/analyze-route-feasibility.md
-- ==================== synthesis_route_feasibility_analysis_step 锛氱粨鏉焛nstruction========================
const analyze_synthesis_route_safety_feasibility_instruction:Instruction;

-- ==================== shutdown_step 锛氬紑濮媔nstruction========================
-- Instruction body: ./instructions/shutdown-workflow.md
-- ==================== shutdown_step 锛氱粨鏉焛nstruction========================
const close_workflow_after_cumulative_96_route_instruction:Instruction;

-- 鐧芥澘鏄庣‘鍑虹幇鍙?workflow 琛ュ厖浣跨敤鐨勬妧鑳?鑳藉姏銆?
const web_search_tool:Tool;
const mattergen_skill:Tool;
const mattersim_skill:Tool;
const catalytic_performance_prover_skill:Tool;
const round_parallel_synthesis_advisor_skill:Tool;
const synthesis_safety_feasibility_judge_skill:Tool;

-- 闄勪欢纭 MatterGen 涓?MatterSim 閮介渶瑕?GPU銆?
-- gpu_device 鏄閮?catalog 棰勭疆鐨?Resource identity锛岃鑼冨崟浣嶄负鈥滆澶囦釜鏁扳€濓紱
-- source 涓繖閲屽彧寮曠敤璇?identity锛屼笉鏂板缓 gpu 杩欑鏈敞鍐岀殑璧勬簮绫诲瀷鎴栧崟浣嶃€?
const gpu_device:Resource;

workflow coscientist_ows {
    -- 椤跺眰杈撳叆锛氬乏渚т簲涓暟鎹簮銆?
    input_workflow(coscientist_ows) == [
        overall_water_splitting_knowledge_base,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        historical_results,
        result_directory_name,
        candidate_knowledge_base_initial
    ];

    -- 澶囬€夌煡璇嗗簱鍜屽巻鍙茬粨鏋滈兘鏄法杞鎸佷箙鐘舵€侊紝鍥犳鏃㈠彲浠ユ湁鍒濆鍐呭锛?
    -- 涔熶細鍦ㄦ湰杞杩藉姞鍚庝綔涓鸿緭鍑轰繚鐣欍€?
    output_workflow(coscientist_ows) == [
        candidate_knowledge_base,
        historical_results,
        completed_96_well_plate_synthesis_route,
        synthesis_safety_feasibility_judgment,
        synthesis_safety_feasibility_judgment_audit,
        workflow_closed
    ];

    -- 瀵瑰鏈€缁堢粨鏋滐細瀹屾垚 96 瀛旀澘鍚堟垚璺嚎锛屼骇鍑哄悎鎴愯矾绾垮畨鍏?鍙鎬у垎鏋愶紝
    -- 骞剁‘璁ゆ墍鏈?subagent 宸插叧闂€?

    -- Stable Step identities are mapped to readable StepName values.
    step_name(prepare_workflow_step) == prepare_workflow;
    step_name(recommend_1_step) == recommend_1;
    step_name(recommend_2_step) == recommend_2;
    step_name(recommend_3_step) == recommend_3;
    step_name(recommend_4_step) == recommend_4;
    step_name(merge_recommendation_outputs_step) == merge_recommendation_outputs;
    step_name(performance_proof_step) == performance_proof;
    step_name(mattergen_step) == mattergen;
    step_name(mattersim_step) == mattersim;
    step_name(synthesis_route_design_step) == synthesis_route_design;
    step_name(synthesis_route_feasibility_analysis_step) == synthesis_route_feasibility_analysis;
    step_name(shutdown_step) == shutdown;

    -- prepare_workflow_step calls workflow鐩稿叧/scripts/prepare_workflow_step.py.
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
    consumes(prepare_workflow_step) == [
        result_directory_name,
        candidate_knowledge_base_initial
    ];
    produces(prepare_workflow_step) == [
        workflow_run_context,
        scheduler_state,
        mattergen_stage_directory_initial,
        mattersim_stage_directory_initial,
        round_parallel_synthesis_stage_directory_initial,
        candidate_knowledge_base,
        candidate_catalyst_pool_initial,
        candidate_catalyst_structure_pool_initial,
        novel_and_stable_catalysts_initial,
        fail_directory,
        fail_candidates_directory_initial,
        tmp_candidates_directory_initial,
        tmp_knowledge_directory_initial,
        recommender_slot_1_directory,
        recommender_slot_2_directory,
        recommender_slot_3_directory,
        recommender_slot_4_directory,
        prepare_workflow_step_result
    ];

    -- 鎵ц鍣ㄦ槧灏勶細鐧芥澘 subagent -> 瀵瑰簲涓氬姟 Step銆?
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
        merge_recommendation_outputs_step
    ) == "./instructions/merge-recommendation-outputs.md";
    step_executor(
        merge_recommendation_outputs_step
    ) == merge_recommendation_outputs_program;

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

    -- 宸︿晶鐭ヨ瘑/瑙勫垯/鍘嗗彶鍒嗙粍棣堝叆鍥涗釜鎺ㄨ崘鍣ㄣ€?
    -- candidate_knowledge_base 瀵瑰簲椤堕儴姗欒壊鍙嶉绾匡紱
    -- candidate_catalyst_pool 瀵瑰簲鏈惛闄勭粓鐐圭殑 c2:187锛屽苟鐢ㄤ簬鍘婚噸鍜屽崗璋冨湪閫斿€欓€夈€?
    consumes(recommend_1_step) == [
        overall_water_splitting_knowledge_base,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        historical_results,
        workflow_run_context,
        scheduler_state,
        candidate_knowledge_base,
        candidate_catalyst_pool_initial,
        candidate_catalyst_structure_pool_initial,
        novel_and_stable_catalysts_initial,
        fail_candidates_directory_initial,
        tmp_candidates_directory_initial,
        tmp_knowledge_directory_initial,
        recommender_slot_1_directory
    ];
    consumes(recommend_2_step) == [
        overall_water_splitting_knowledge_base,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        historical_results,
        workflow_run_context,
        scheduler_state,
        candidate_knowledge_base,
        candidate_catalyst_pool_initial,
        candidate_catalyst_structure_pool_initial,
        novel_and_stable_catalysts_initial,
        fail_candidates_directory_initial,
        tmp_candidates_directory_initial,
        tmp_knowledge_directory_initial,
        recommender_slot_2_directory
    ];
    consumes(recommend_3_step) == [
        overall_water_splitting_knowledge_base,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        historical_results,
        workflow_run_context,
        scheduler_state,
        candidate_knowledge_base,
        candidate_catalyst_pool_initial,
        candidate_catalyst_structure_pool_initial,
        novel_and_stable_catalysts_initial,
        fail_candidates_directory_initial,
        tmp_candidates_directory_initial,
        tmp_knowledge_directory_initial,
        recommender_slot_3_directory
    ];
    consumes(recommend_4_step) == [
        overall_water_splitting_knowledge_base,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        historical_results,
        workflow_run_context,
        scheduler_state,
        candidate_knowledge_base,
        candidate_catalyst_pool_initial,
        candidate_catalyst_structure_pool_initial,
        novel_and_stable_catalysts_initial,
        fail_candidates_directory_initial,
        tmp_candidates_directory_initial,
        tmp_knowledge_directory_initial,
        recommender_slot_4_directory
    ];

    -- Recommendation steps write primary slot-local results under
    -- <output_root>/02-ows-catalyst-recommender/slot_n/ows_Sn_Ck. Each result
    -- contains CANDIDATE_PAYLOAD.json and REASONING.md. Each completed
    -- ows_Sn_Ck directory is sync-copied to <output_root>/tmp/candidates for
    -- later checks. Every recommendation step emits its per-slot knowledge
    -- delta. Captured deltas include the knowledge file; uncaptured deltas
    -- include an explicit captured=false manifest and no knowledge file.
    -- Later proof artifacts may be placed in the same result directory by
    -- downstream steps.
    -- Recommendation steps may read candidate_catalyst_pool,
    -- candidate_catalyst_structure_pool, novel_and_stable_catalysts,
    -- fail_candidates_directory, and candidate_knowledge_base but must not write
    -- under <output_root>/pools.
    -- Knowledge capture remains optional, but emitting the corresponding
    -- knowledge delta artifact is required for every recommendation branch.
    produces(recommend_1_step) == [
        recommendation_slot_1_results,
        tmp_candidates_directory_from_recommend_1,
        tmp_knowledge_directory_from_recommend_1
    ];
    produces(recommend_2_step) == [
        recommendation_slot_2_results,
        tmp_candidates_directory_from_recommend_2,
        tmp_knowledge_directory_from_recommend_2
    ];
    produces(recommend_3_step) == [
        recommendation_slot_3_results,
        tmp_candidates_directory_from_recommend_3,
        tmp_knowledge_directory_from_recommend_3
    ];
    produces(recommend_4_step) == [
        recommendation_slot_4_results,
        tmp_candidates_directory_from_recommend_4,
        tmp_knowledge_directory_from_recommend_4
    ];

    -- Merge the four independent recommendation deltas into the initialized
    -- tmp directories before performance proof reads the candidate set.
    consumes(merge_recommendation_outputs_step) == [
        tmp_candidates_directory_initial,
        tmp_knowledge_directory_initial,
        tmp_candidates_directory_from_recommend_1,
        tmp_candidates_directory_from_recommend_2,
        tmp_candidates_directory_from_recommend_3,
        tmp_candidates_directory_from_recommend_4,
        tmp_knowledge_directory_from_recommend_1,
        tmp_knowledge_directory_from_recommend_2,
        tmp_knowledge_directory_from_recommend_3,
        tmp_knowledge_directory_from_recommend_4
    ];
    produces(merge_recommendation_outputs_step) == [
        tmp_candidates_directory_after_recommendations,
        tmp_knowledge_directory
    ];

    -- performance_proof_step is executed by performance_prover_agent according
    -- to prove_tmp_candidate_performance_and_route_candidate_instruction. The
    -- agent uses stage08-catalytic-performance-prover, writes the proof
    -- Markdown and audit JSON inside each candidate folder, routes judged
    -- folders to pools/candidates or fail/candidates, and removes judged
    -- folders from tmp/candidates.
    consumes(performance_proof_step) == [
        tmp_candidates_directory_after_recommendations,
        candidate_catalyst_pool_initial,
        fail_candidates_directory_initial
    ];
    produces(performance_proof_step) == [
        tmp_candidates_directory,
        candidate_catalyst_pool_after_performance_proof,
        fail_candidates_directory_after_performance_proof,
        performance_proven_catalysts,
        performance_rejected_catalysts
    ];

    -- 鏅朵綋鐢熸垚璇勬祴涓婚摼锛?
    --   璇佹槑閫氳繃鍚庣殑鍊欓€夊偓鍖栧墏姹?-> MatterGen -> 鍊欓€夊偓鍖栧墏缁撴瀯姹?-> MatterSim銆?
    -- When MatterGen sampling is complete, the candidate folder is moved out
    -- of candidate_catalyst_pool and into candidate_catalyst_structure_pool.
    consumes(mattergen_step) == [
        candidate_catalyst_pool_after_performance_proof,
        mattergen_stage_directory_initial,
        candidate_catalyst_structure_pool_initial
    ];
    produces(mattergen_step) == [
        candidate_catalyst_pool,
        mattergen_stage_directory,
        candidate_catalyst_structure_pool_after_mattergen
    ];
    consumes(mattersim_step) == [
        candidate_catalyst_structure_pool_after_mattergen,
        mattersim_stage_directory_initial,
        novel_and_stable_catalysts_initial,
        fail_candidates_directory_after_performance_proof,
        overall_water_splitting_knowledge_base
    ];

    -- MatterSim produces candidate classifications and routes judged candidate
    -- folders out of the structure pool.
    -- 瀵规瘡涓€欓€夛紝novel_and_stable 涓?non_novel_or_unstable 涓ょ被缁撴灉浜掓枼銆?
    -- novel_and_stable_catalysts 宸插寘鍚繘鍏ュ悎鎴愯矾绾胯璁℃墍闇€鐨勮瘎娴嬭瘉鎹紱
    -- 闄勪欢涓殑 evaluation summary 鍦ㄧ櫧鏉垮眰绾у悎骞惰繘璇?Artifact锛屼笉鍙﹂€犵櫧鏉胯妭鐐广€?
    produces(mattersim_step) == [
        candidate_catalyst_structure_pool,
        mattersim_stage_directory,
        novel_and_stable_catalysts_after_mattersim,
        fail_candidates_directory_after_mattersim,
        non_novel_or_unstable_catalysts
    ];

    -- 鈥滈€氳繃鈥濇敮璺繘鍏ュ悎鎴愯矾绾胯璁°€?
    -- 鑺傜偣鏂囧瓧鏄庣‘鍖哄垎鈥滄病鏈夋€昏矾绾挎椂鏂板缓璁捐鈥濆拰鈥滃凡鏈夋€昏矾绾挎椂琛ュ叆鈥濓紱
    -- 鍥犳 historical_results 鏄櫧鏉挎枃瀛楅殣鍚殑蹇呰杈撳叆锛屽畠鎻愪緵褰撳墠绱璺嚎涓庡師娑茬摱鐘舵€併€?
    consumes(synthesis_route_design_step) == [
        novel_and_stable_catalysts_after_mattersim,
        round_parallel_synthesis_stage_directory_initial,
        historical_results,
        laboratory_rule_base,
        robot_chemist_skill_library,
        successful_route_library,
        fail_candidates_directory_after_mattersim
    ];
    -- 瀵规瘡涓€欓€夛紝synthesis_route_update 涓?
    -- catalysts_unable_to_join_total_route 涓ょ被缁撴灉鍚屾牱浜掓枼銆?
    produces(synthesis_route_design_step) == [
        synthesis_route_update,
        catalysts_unable_to_join_total_route,
        round_parallel_synthesis_stage_directory,
        novel_and_stable_catalysts,
        fail_candidates_directory,
        synthesis_input_summary,
        round_parallel_synthesis_route,
        round_parallel_synthesis_index,
        cumulative_synthesis_parameter_csv_files,
        source_liquid_inventory,
        source_liquid_preparation_methods,
        cumulative_synthesis_route,
        chemskills_execution_spec,
        source_liquid_bottle_preparation,
        completed_96_well_plate_synthesis_route
    ];
    -- The grammar has no optional_produces relation, so this declares the
    -- final 96-well source-liquid preparation Markdown as a possible Stage08
    -- output even though it is written only when the cumulative route is
    -- complete.
    -- The Stage08 route step produces this artifact only when the cumulative
    -- route reaches 96 wells and the Stage08 completion contract is satisfied.

    -- 鍚堟垚璺嚎鍙鎬у垎鏋愬湪 Stage08 浜у嚭 96 wells 绱璺嚎鍚庤繍琛岋紝杈撳嚭
    -- Stage09 judgment Markdown 鍜?audit JSON銆?
    consumes(synthesis_route_feasibility_analysis_step) == [
        cumulative_synthesis_route,
        completed_96_well_plate_synthesis_route
    ];
    produces(synthesis_route_feasibility_analysis_step) == [
        synthesis_safety_feasibility_judgment,
        synthesis_safety_feasibility_judgment_audit
    ];

    -- shutdown_step 璇诲彇 cumulative_synthesis_route锛屽苟鎸?
    -- close_workflow_after_cumulative_96_route_instruction 鍒ゆ柇鍏朵腑鏄惁宸茬粡
    -- 鍖呭惈 96 涓偓鍖栧墏鐨勫悎鎴愯矾绾匡紝鍚屾椂绛夊緟鍚堟垚璺嚎鍙鎬у垎鏋愮粨鏋滀骇鍑猴紱鏈畬鎴愭椂锛?
    -- Stage08 绱鏂囦欢鍜屽悇姹犵姸鎬佺户缁緵鍓嶅簭 step 娑堣垂銆?
    consumes(shutdown_step) == [
        cumulative_synthesis_route,
        synthesis_safety_feasibility_judgment,
        synthesis_safety_feasibility_judgment_audit,
        completed_96_well_plate_synthesis_route
    ];
    produces(shutdown_step) == [workflow_closed];

    -- The scheduler init boundary is now represented by prepare_workflow_step.
    -- next-action/register/claim/complete/release, Z-scheme aggregation, and
    -- novelty still need separate workflow modeling before they can be treated
    -- as first-class steps.
}
