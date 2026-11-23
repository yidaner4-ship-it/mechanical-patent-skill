# 交底图源与线稿处理

机械产品（发明、实用新型）与外观共用来源打分，机械的画法及最终验收以[CAD取图与附图验收](../../../../mechanical-patent-drawings/references/cad-figures.md)为准。先运行：

```bash
python skills/patent-disclosure/tools/image_gen.py --case-dir "outputs/{案件标识}"
```

## 来源与合格性分开

- `kind` 表示当前图形状态：`lineart`、`cad`、`photo_clean`、`photo_scene`、`other`。`source_kind`、`source_ref` 保留真实来源。
- 机械 CAD 经同源几何核对、清理、黑白化及正式布标后可为合格线稿。须登记 `geometry_verified: true`、`drawing_ready: true`、非空 `source_ref`。未经处理 CAD 截图不能仅凭高分直接入文。
- 候选图实际识图后填写 `relevance`、`quality`（0–100）及 `score`。合格线稿 `score>=70`；分项存在时均须>=70，并验证文件存在。高分只用于筛选，不能代替几何、标号或图面验收。
- 实拍保持真实类别，不改标线稿。图像生成不能证明 CAD 投影、尺寸或资料未披露的内部结构。

## 规划结果

| mode | 后续处理 |
|---|---|
| `existing_lineart` | 使用合格原图或已核验的 CAD 衍生线稿，不重画轮廓；必要时补标并复核 |
| `cad_prepare` | 从真实 CAD 取轮廓、剖切或爆炸，清理和布标；不得转为生成式重画 |
| `needs_structure_sources` | 机械方案缺少可核的结构图源，补充可信资料或完成有据部分，明确未完成范围 |
| `img2img` / `txt2img` | 用于外观辅助或用户明确要求且有事实依据的示意；不得补造机械技术事实 |

机械计划应填写 `patent_type: invention|utility_model` 及 `subject_kind: mechanical_product`，类型与保护对象分别管理。存在合格线稿时直接采用；未合格的 CAD 保留为准备任务，不自动通过。`drafting_status` 与脚本运行成功分开。

## 入文与生成边界

机械正文只引用内容匹配、图文可核的线稿，包括经核验的 CAD 衍生图。将正式处理后的条目记为 `kind: lineart`、`source_kind: cad`，保留来源、核验状态和原始参考条目。

外观保持既有视图口径：先读 `references/design_view_cnipa.md`；正投影/立体角色、各视比例、禁尺寸线/中心线/阴影线及图内图号、画布和 DPI 按该参考核查。未过的 `quality<=69`。干净实拍 `photo_clean` 与合格线稿嵌入 Markdown 和 Word；CAD 原始图只作参考，不能因机械分支开放而自动成为合格外观视图。

确需生成式示意时，先有明确用途及本案可用事实，不生成未披露部件。已有参考图先图生图；无法使用时先记录可见细节再文生图，保留不确定范围。最终生成图仍须独立核对，不得以生成成功表示技术正确。

用户明确不要线稿或设置 `PATENT_SKILL_SKIP_LINEART=1` 时可跳过，并记录对交付范围的影响。
