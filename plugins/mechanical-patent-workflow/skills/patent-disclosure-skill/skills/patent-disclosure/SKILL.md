---
name: patent-disclosure
description: 中国专利交底书：发明/实用新型/外观设计的专利点挖掘、轻量查新与成文、保护型1+N专利布局。
metadata:
  source_user_invocable: 'False'
---

# 交底书编写

## 本机运行环境

在目标机器为本技能创建并验证独立Python环境后运行工具；虚拟环境与CAD隔离环境不随包复制。依赖与安装见整包INSTALL.md，使用目标机器实际解释器。

## 用途

挖专利点、轻量查新、写成发明 / 实用新型 / 外观设计交底书；首篇定稿后可走保护型 1+N 围栏。发明 / 实用新型 / 外观是**包内三个目录**，不是三个可触发技能。分步指令在本包 **`prompts/`**。

## 何时用

用户说专利挖掘、交底书、查新、实用新型、外观设计，或 `/patent-disclosure`、`/交底书`。未显式指定类型时**默认发明**。  
「专利布局 / 专利围栏 / 族树 / 做围栏」走本包旁路（首篇已定稿；用户点名可强开）。不要因写申请、读专利、对照表自动进入。

## 输入

发明人材料、项目目录、可选 `.tex`；拟申请类型与联系人在 `prompts/intake.md` 收敛，不全可推断并注明假设。查新范围与拟申请类型分开：发明/实用新型技术查新覆盖相关发明与实用新型及适用非专利资料，外观沿专用规则；工具参数见 `prompts/prior_art_search.md`。线稿、CAD、公式、Word 出图、PDF 转 md 用本包 `tools/`。

## 步骤

机械结构类发明或实用新型在首次成文及迭代改稿前，先 **`Read`** [申晟机械结构专利撰写风格](../../../mechanical-patent-drawings/references/shensheng-drafting-style.md)。交底采用其中的术语、结构叙述和图文衔接习惯，保留交底所需章节、证据表和待确认事实，不改成正式权利要求书。

同案材料接入及交底交付执行[接入与定稿收尾](../../../mechanical-patent-drawings/references/drafting-and-review.md#接入与定稿收尾)的适用部分。机械产品不因发明类型套算法主线；已授权按模型写稿／取图时直接使用可用CAD解析路径，图源及标引按机械权威规则，不重复询问是否解析。单纯交底不因此自动扩成申请五书或另做不适用的申请定稿检索。

机械结构类发明、实用新型在方案设计、挖点及迭代时，先读[工程价值、可专利性与必要性](references/engineering-value-and-patentability.md)。从真实需求与简洁基准出发，提前初检，比较改进收益和新增复杂度，并做删除、合并及常规替换检验。已有方案按适用范围回核，不为申请而追加无实际收益的结构；已有材料中的建议与已披露事实分别管理。

| 步骤 | 文件 |
|------|------|
| Step 1 | `prompts/intake.md` |
| Step 2 | `prompts/project_scan.md`；有 `.tex` 再 `Read prompts/tex_scan.md` |
| 机械方案设计与挖点前 | `references/engineering-value-and-patentability.md`；初检提前用于方案决策，Step 5复用并按变更补检 |
| Step 3–4 | `prompts/invention/` · `utility_model/` · `design/` 挖点 |
| 填表 / 线稿 | `prompts/fill_*`、`image_gen.md`、`*_lineart_*.md`；外观视图口径 `references/design_view_cnipa.md`；外观成文前 `tools/check_design_views.py`；结构案成文前 `tools/check_source_parts.py` |
| Step 5 | `prompts/prior_art_search.md`（轻量查新：3～4 个手段短语，公布模式每页 10 条，LLM 摘要精排） |
| Step 5.5 | 同文件「**D1 锁定与区别特征 Fk**」：主比对钉一篇最接近 + 逐特征表（可 D2 补行）+ **三态门禁**，落 `查新与区别定位_*.md`。三态都进 Step 6；**不过**仍成文但创造性降级 |
| Step 6 | `prompts/disclosure_preview.md` |
| Step 7 | 对应类型 `disclosure_builder.md` + `template_reference.md` |
| Step 8 | `prompts/disclosure_self_check.md` |
| 成稿后独立质检 | 实际 Word／正文及附图生成后，读[申晟专利独立质检](../../../shensheng-patent-qa/SKILL.md)，完成独立审阅、整改及复核后再交付；与起草自检分开 |
| 迭代 | `iteration_context.md` / `merger.md` / `correction_handler.md` |
| 旁路 · 保护型 1+N | 首篇定稿后 `prompts/fence/guardrails.md`；用户同意则 `decompose.md` → `design_around.md` → `matrix.md` → `plan.md`（family.yaml + 专利布局.md）→ `score.md`（立项后弱校验）→ 确认后 `dispatch.md` |
| 交付对话 | 定稿回复末块 `prompts/delivery_confirm.md`（标题固定 **交付后请确认**） |

查新：`prompts/prior_art_search.md`，脚本 `tools/crawl/cnipa_epub_search.py`（整仓路径 `skills/patent-disclosure/tools/crawl/cnipa_epub_search.py`）。

围栏：Step 8 之后只在交付回复 **`## 交付后请确认`** 第 3 条询问。口径见 `prompts/fence/guardrails.md`。立项说明直接写 `outputs/{案件}/fence/专利布局.md`（章节见 `prompts/fence/plan.md`），`family.yaml` 只供校验和分件。弱校验表 `references/scorecards/gbt42748_fence.yaml`。口头确认「按 C1、P1 写」后再分件。

```bash
python skills/patent-disclosure/tools/fence/check_layout.py --decompose outputs/{案件}/fence/decompose.yaml
python skills/patent-disclosure/tools/fence/check_layout.py --family outputs/{案件}/fence/family.yaml --matrix outputs/{案件}/fence/matrix.yaml
python skills/patent-disclosure/tools/fence/check_scorecard.py -i outputs/{案件}/fence/scorecard.yaml --case-dir outputs/{案件}
```

## 护栏

- 细则在各步 prompt；围栏先 `Read` `prompts/fence/guardrails.md`。
- 禁止假 D1，禁止空喊创新性强。未披露部件写入 `uncertain`，不进入权要或说明书。
- 候选数量按真实机会确定；不得以结构复杂、零件多或凑够专利点代替贡献。工程拟定和建议不得冒充既有实施事实，成文完成不等于可授权或实物验证通过。
- 未确认立项说明，不分件写多篇交底。

## 产出物

交底书 Markdown + Word，查新与区别定位稿，可选 schema / 线稿 / 公式图；围栏在 `outputs/{案件}/fence/`。对话末块标题 **交付后请确认**。
