# 申请文件 · 录入

执行前 **`Read`** `prompts/guardrails.md`。

## 触发

申请文件、申请底稿、申报材料、权利要求书、说明书五部分、把交底改成申请、`/申请底稿`、`/patent-apply`。

已有申请四件套上改独权、附图、说明书、点名补图：走 `iteration_context.md`，不要从门禁空写。

## 同案材料与底稿

首次起草定位有效交底材料目录（常见 `outputs/{案件标识}/`）。给的是文件则取其父目录并核对该文件，已有Word／模型可内部整理。迭代沿用用户指定底稿及上一版计划的 `case_dir`；缺标准目录不要求用户重做。确无材料时询问缺口，不凭空成文。

机械案按[接入与定稿收尾](../../../../mechanical-patent-drawings/references/drafting-and-review.md#接入与定稿收尾)分别确认 `patent_type`、`subject_kind`、程序阶段、工作与原始基线及核定材料。`subject_kind` 使用 `mechanical_product|method|software_system|mixed|unknown`，不由“装置”一词或schema反推专利类型。

不要把仓库 `examples/*/knowledge/` 当成交底产出。

## 下一步

1. 首次起草读 `material_gate.md`，运行 `tools/material_gate.py --case-dir <目录> --type <核定类型> --subject-kind <核定对象>`；已有稿修改直接进迭代
2. `ok=0` → 核实缺件／分类并内部整理可用材料，无法补齐的说明未完成范围，继续有依据部分
3. `ok=1` 后：`invention` / `utility_model` → `claim_strategy.md`；`design` → `design_application.md`
