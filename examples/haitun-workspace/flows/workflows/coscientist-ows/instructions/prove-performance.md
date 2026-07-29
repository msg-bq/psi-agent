根据 `skills/stage08-catalytic-performance-prover`，由
`coscientist-ows-entry/scripts/program.py` 的 performance 操作确定性处理每个尚未判断的
`<output_root>/tmp/candidates/slot_n/ows_Sn_Ck` 文件夹：读取
`CANDIDATE_PAYLOAD.json`，构造一个只包含该候选名称和化学式的单记录
`retained_records` 输入；使用 `stage08-catalytic-performance-prover` 运行
`LLM_proof/run_llm_proof.py`；在候选文件夹中写入
`CATALYTIC_PERFORMANCE_PROOF.md` 以及相邻的 audit JSON；将判断为可能具有
催化性能的文件夹移动到
`<output_root>/pools/candidates/slot_n/ows_Sn_Ck`；将判断为无催化性能的
文件夹移动到 `<output_root>/fail/candidates/slot_n/ows_Sn_Ck`；并从
`<output_root>/tmp/candidates` 移除每个已经判断过的文件夹。

运行约束：

- 不得读取或回显 `LLM_PROOF_API_KEY` 的值，只能检查该环境变量是否存在。
- 复用启动 psi-agent 的当前 Python 解释器，不得安装依赖或切换解释器。
- 使用候选的实际 `slot_n/<folder>` 路径作为身份，不使用可能重复或与目录不一致的
  `candidate_id`。
- 在调用外部模型前拒绝任何已有的 pool/fail 目标目录，不得覆盖已有结果。
- 单记录 `retained_records` 输入必须写为 UTF-8 无 BOM。
