# 申请文件 · 材料门禁

检查材料是否足以进入相应成文分支，不代表技术支持、检索或定稿验收通过。已有稿迭代不重走首次门禁。

```bash
python skills/patent-application/tools/material_gate.py --case-dir <交底目录> --type <核定类型> --subject-kind <核定对象>
```

可用 `--disclosure` 指定实际交底文件。`--type invention|utility_model|design`传本案已确定类型；`--subject-kind mechanical_product|method|software_system|mixed|unknown`另记技术形态。不能因为存在结构schema把发明改成实用新型。

以退出码和 `APPLICATION_GATE:` 为准。PowerShell 红字不是失败。

| 退出码 | 动作 |
|--------|------|
| 0 | 继续 |
| 2 | 核实缺失项和分类；已有资料可内部整理则补齐，否则完成有依据部分，明确未完成范围 |
| 1 | 修正路径后再跑 |

| 类型 | 必须存在 |
|------|----------|
| 方法／软件系统 | 交底书 `.md` 或 `.docx`，按实际披露规划流程／框图 |
| 机械产品（发明或实用新型） | 交底 + 结构台账 + 图页计划 + 可核对的结构线稿；缺图不得以算法图替代 |
| 外观 | 交底 + `appearance_schema` + `figure_plan` + 入文线稿 + 入文实拍 |

材料缺口不等于可随意编造；申请稿实际完成状态按[共用收尾](../../../../mechanical-patent-drawings/references/drafting-and-review.md#共用收尾)登记。
