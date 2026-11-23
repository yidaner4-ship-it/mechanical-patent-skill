# 机械结构事实与附图计划

用于机械产品发明和实用新型；申请类型保持本案核定值，不以“结构”推断为实用新型。成文前在案件目录写 `structure_schema.yaml` 与 `figure_plan.yaml`，已有时更新，不要求用户另行制作内部格式。

## 核对与登记

1. 读取本案原文、真实 CAD 和可信原图，联读总装、爆炸、局部及剖视；用户已要求按模型取图或撰写时，按 `project_scan.md` 直接进行可用的只读解析，不重复确认。
2. `parts` 登记物理部件，`id/name` 全案统一。可分离的真实零件可以独立登记；不为画图把一体轮廓随意拆成零件。
3. `features` 登记需要指认的孔、槽、筋、齿、面、开口、间隙及功能区，字段为 `id/name/parent_part_id/kind/source/visible_in`。`id` 是标号，与 `parts.id` 共享唯一编号空间，沿用本案复合号体系。子特征无须成为拼装零件层。剖切线、剖切箭头等放 `annotations`，不混入结构件或子特征。
4. 图源可辨认或用户确认的事实才写为确定结构；关键新补充记录来源并回写有效底稿。看不清或资料没有的进入 `uncertain`，不得为关单或补图编造。
5. `relations` 写真实连接及位置，可用 `seen_in` 关联图；总装、局部、爆炸及剖视用 `figure_plan.relates_to` 维护母图关系。跨图同一实体沿用同号。

## 图源判定

对每张候选图实际识图，写 `role/kind/source_kind/source_ref/covers/relevance/quality/score/use_in_disclosure/reason`。`covers` 可以同时列部件与已登记子特征标号。

原始 CAD 或截图先为 `kind: cad`、不直接入文。经同源几何核验、清理及正式布标的 CAD 投影可提升为 `kind: lineart`，同时保留 `source_kind: cad`、非空 `source_ref`、`geometry_verified: true`、`drawing_ready: true`。只认事实与成品质量，不全面排斥 CAD，也不把来源当合格证。

运行 `image_gen.py`：合格原图直接使用；`cad_prepare` 处理真实几何；`needs_structure_sources` 说明待核。机械图不自动转为生成式重画。矢量 CAD 可直接保留零件层并叠标；栅格素材确需分件维护时再按 `structure_lineart_compose.md` 处理。

按 `structure_lineart_assist.md` 补正式标引；图内/图外、边/面/间隙落点及短 S 采用机械附图的统一规则。`patent_type` 沿用核定类型，机械产品另写 `subject_kind: mechanical_product`。

## 成文前与改后核对

```bash
python skills/patent-disclosure/tools/check_source_parts.py --case-dir outputs/{案件标识} --write
```

确定的未登记号、未知母件和无依据结构先修复；缺事实时保留其余可完成工作并明确未完成范围。`uncertain` 不得进入确定的欲保护点。图源或主题变化后重评图计划；仅 `use_in_disclosure: true` 的合格图分配图号并入文。编号、画法及逐段覆盖以[CAD取图与附图验收](../../../../mechanical-patent-drawings/references/cad-figures.md)为准。
