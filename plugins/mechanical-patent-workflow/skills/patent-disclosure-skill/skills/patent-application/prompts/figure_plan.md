# 申请文件 · 图型决策

权要写完后、画附图之前：按核定保护对象及实际披露选图型，写入产出目录 `figures/figure_plan.yaml`。不覆盖交底原计划。机械产品（发明或实用新型）优先继承可信结构图及同源CAD视图；“装置”“模块”词面不能决定画软件框图。

合同：`references/schemas/application_figure_plan.schema.yaml`。

## 决策（按权要原文，可多选）

| 权要语言 | `kind` |
|----------|--------|
| 「包括以下步骤」/「步骤一…」 | `flowchart` |
| 已确认软件系统及其逻辑模块／处理器 | `block_diagram` |
| 内部、内设、腔体、剖视 | `section` |
| 可拆卸、分解、依次套设、从…拆出 | `exploded` |
| 第一/第二状态、锁定/触发、切换至 | `multi_state` |
| 机械产品交底合格线稿／核验后的CAD投影 | 保留 `lineart`或实际结构图类型，再按披露目的补缺 |
| 点名场景图 | `source_image` |

方法独权按实际步骤规划流程图，确有软件系统对象时规划框图；机械产品及混合案件的机械部分按整机、局部、剖视、爆炸和状态图规划。未知对象记待确认，不默认算法图。不要为凑套图编造内部结构。

剖视 / 爆炸 / 多状态：优先用交底 `relates_to` 已标明的入文线稿升格。交底没有对应图则 `source: pending`，记问题清单，禁止编内部结构。

每条写清 `reason` 和 `covers`（可见件号或模块名）。

```bash
python skills/patent-application/tools/plan_figures.py \
  --claims <产出>/权利要求书.md \
  --type invention --subject-kind mechanical_product \
  --disclosure-plan <交底>/figure_plan.yaml \
  --out <产出>/figures/figure_plan.yaml
```

方法／软件系统将 `--subject-kind`改为对应值；混合对象用 `mixed`并人工核对各图用途。机械产品无可信图源时保留 `pending`结构图，列缺口，不用流程图替代。看 `APPLICATION_FIG_PLAN:`，再按 `figures.md`处理；最终图号以具体实施方式首次实质引用次序确定，按[CAD规则](../../../../mechanical-patent-drawings/references/cad-figures.md#附图编号与正文引用)同步。
