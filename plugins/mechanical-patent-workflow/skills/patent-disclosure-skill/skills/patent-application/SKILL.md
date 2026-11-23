---
name: patent-application
description: 申请文件：把已有交底写成权利要求书、说明书、摘要与附图，也支持已有稿迭代。按保护对象核材料并区分阶段成果与正式定稿；问题单不替代整改和验收。已有稿另存新时间戳目录。须显式触发。
metadata:
  source_user_invocable: 'False'
---

# 申请文件

## 本机运行环境

在目标机器为本技能创建并验证独立Python环境后运行工具；虚拟环境与CAD隔离环境不随包复制。依赖与安装见整包INSTALL.md，使用目标机器实际解释器。

## 用途

把已有交底写成权利要求书、说明书、摘要与说明书附图（四件套：Markdown + Word + 黑白图）。内容歧义不阻塞主文件，缺口写入问题清单。

## 何时用

须用户点名（申请文件 / 申请底稿 / 申报材料 / 权利要求书 / 五书 / `/申请底稿` / `/patent-apply`）。首次起草定位同案交底材料目录；给出具体文件时从其父目录与已确认材料接入。已有稿迭代直接沿用当前底稿和可用依据，不因缺少标准格式目录而空停。案卷调度视为已点名。

## 输入

同案有效交底（Markdown或Word）、原图／模型、核定补充及已有稿。专利类型与保护对象分别核定；机械产品不论发明或实用新型，按结构、关系、图页计划及可信线稿核材料；方法／软件系统按正文、流程／框图核材料；外观沿用外观材料要求。已有资料可内部整理为工具所需schema，不要求用户重做。缺关键技术事实不编造，先完成有依据部分并标明未完成范围。发明人／申请人未填非阻塞。

## 步骤

0. 机械结构类发明或实用新型，先 **`Read`** [申晟机械结构专利撰写风格](../../../mechanical-patent-drawings/references/shensheng-drafting-style.md)，再进入下列首次起草或已有稿迭代分支。该参考的机械行文约定优先于通用模板中的方法步骤、软件系统示例；材料支持、保护范围和本轮修改范围仍按本案要求核对。
   同时按[接入与定稿收尾](../../../mechanical-patent-drawings/references/drafting-and-review.md#接入与定稿收尾)记录核定材料、程序阶段和底稿，并在首次成稿及迭代末尾执行其适用收尾。

1. **`Read`** `prompts/guardrails.md` → `intake.md`。首次起草和改稿均先定位用户指定或本案已确认的 Word 母版，按[用户模板套版](../../../mechanical-patent-drawings/references/drafting-and-review.md#用户模板套版)制作拟交付文件。
2. 已有申请产出上改稿（未要求整案重写）：**`Read`** `iteration_context.md` → `iteration.md`；不重做首次材料门禁，完成本轮修改后仍回共用收尾。
3. 跑 `tools/material_gate.py --case-dir <交底目录> --type <核定类型> --subject-kind <核定对象>`；退出码2先核缺件／误分类，能内部整理则补齐，不能补齐则完成其余有依据部分，不宣称整套定稿。
4. 发明 / 实用新型：`claim_strategy.md` → `claims_builder.md` → `figure_plan.md` → `figures.md` → `specification_builder.md` → `numeral_register.md` → `consistency.md`
5. 外观：先 `Read` `references/design_view_cnipa.md`，只走 `design_application.md`；跑本包 `check_design_views.py`
6. 用 `tools/emit_application_docx.py` 输出 Word。有用户指定或本案已确认的母版时，通用脚本的 Word 作为内容中间稿，在母版副本制成正式 Word。机械案回[共用收尾](../../../mechanical-patent-drawings/references/drafting-and-review.md#共用收尾)，完成适用的定稿检索、[独立质检](../../../shensheng-patent-qa/SKILL.md)、整改、渲染及隐私清理；其他案件执行其适用检查。最后读 `issues.md`，在问题清单及同一条交付回复中说明实际完成状态和待确认项。

整仓路径：`python skills/patent-application/tools/…`。

## 护栏

- 细则 `prompts/guardrails.md`。通用 Word 与附图生成使用本包 `tools/`，用户母版套版按第1步处理。

## 产出物

`outputs/patent-application/{案件标识}_{时间戳}/`：四件套（Markdown + Word + 黑白图）+ 旁路 `问题清单.md`（外观另有 `视图检查清单.md`）。对话末块标题 **交付后请确认**。
