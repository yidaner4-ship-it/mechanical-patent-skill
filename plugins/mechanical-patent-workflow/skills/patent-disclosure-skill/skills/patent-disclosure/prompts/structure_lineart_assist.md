# 机械结构线稿与正式标引

用于机械产品发明、实用新型，先读 `image_gen.md`。现行画法、纸面样式及验收统一引用[CAD取图与附图验收](../../../../mechanical-patent-drawings/references/cad-figures.md)，不另设相反的锚点或图外规则。外观仍用 `design_lineart_assist.md`。

## 选择图源

运行 `tools/image_gen.py --case-dir "outputs/{案件}"`：`existing_lineart` 直接保留已核图形；`cad_prepare` 从同源 CAD 取图；`needs_structure_sources` 补可信来源或明确未完成范围。CAD 矢量可直接保持原有零件层并叠标，不强制转栅格裁窗。只有栅格材料确需分件维护时才按 `structure_lineart_compose.md`。生成式示意必须有明确用途和事实依据，不能替代真实机械结构图。

## Brief 与标号

读取 `structure_schema`、`figure_plan`，跨图统一 `parts` 与 `features` 标号。填写 `structure_lineart_brief.yaml`：

- `enabled: true`，`patent_type` 保持 `invention` 或 `utility_model`，`subject_kind: mechanical_product`。
- `parts_legend` 可包含已登记子特征，`visible_part_ids` 为该视实际可辨认的标号，不含制图符号或 `uncertain`。
- `callout_mode: overlay`；`source_paths` 指向真实图源。没有图源不表示可以生成关键技术事实。

```bash
python skills/patent-disclosure/tools/structure_lineart_gate.py --case-dir "outputs/{案件}" --prepare-jobs
```

门禁只检数据及来源关系，不能证明线端实际正确。

## 真实锚点与纸面尺寸

实际查看已确认轮廓或 CAD 投影，填写 `structure_callout_anchors.yaml`，详见 `references/schemas/structure_callout_anchors.schema.yaml`：

- `anchor` 按真实目标登记 `target_kind: part|edge|face|hole|slot|gap|flow_path`、母件、可见几何依据和 `anchor_confirmed`。边指向该特征的真实边；宽面主要件可以按统一规则指向实体面中部；间隙指向两实体间实际空间。不得一律吸附到最近墨线。
- `label_placement: external|internal`；内部特征可在附近合适的图内留白，外引须满足整组主体之外的末端、字框和净距要求。不得一律把所有数字推到图外。
- `marker_type: ordinary|primary_arrow`；主要件三角箭头与短 S 读取已确认样式配置；箭底出线与箭轴顺接。几何要求明确时提供 `arrow_axis`（从箭尖指向箭底），保持真实锚点并相应重排数字。脚本逐根记录纸面实际弧长、名义长度及 `length_exception_reason`；差异提示只供复核，不是合格阈值。短 S 起排长度、顺滑和避让按最终图幅逐根核对，不以数值或一次反曲替代目视验收。
- `paper_width_mm` 表示最终含标引和留白的图体宽度；根据母版实际拟嵌入尺寸填写。缺少时只出 `preview_missing_paper_size` 预览，不视为定稿。SVG 后续缩放时须重新核查字号、线宽、箭头及短 S 纸面尺度。

```bash
python skills/patent-disclosure/tools/structure_callout_overlay.py --case-dir "outputs/{案件}" --anchors "outputs/{案件}/structure_callout_anchors.yaml"
```

脚本保留 YAML 的锚点，不自动改变几何归属；有 `base_svg_path` 时注入标号层并保留原始轮廓。旧 `--no-autolayout` 仅兼容，不再决定是否全局吸线。可选排布工具只提供图外数字候选，人工确认后回写；不能改变已核锚点或图内方式。

## 叠标后核查与回写

实际读取叠标后的 SVG/PNG，并逐次对照 `parts/features` 名称核线端、目标部位、同号跨图归属、整支箭头、S 全长、末端、完整字框及邻线净距。改一个标号后连查相邻线和同号其他视图。只为纠标号时修改锚点后重叠标，不重生轮廓。

最多两轮局部校正后仍无新增依据的，记录具体待核位置并完成其余部分，不硬标、不靠删去必需披露掩盖问题。最终图条目记录 `kind: lineart` 与真实 `source_kind/source_ref`、核验状态，入文图号及母图关系与正文同步。仅出 `contour_only` 或仍有未核关键标号时明确交付范围，不能宣称附图已经完整验收。
