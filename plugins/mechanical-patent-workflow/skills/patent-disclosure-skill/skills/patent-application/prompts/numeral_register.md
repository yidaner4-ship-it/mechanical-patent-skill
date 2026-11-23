# 申请文件 · 件号 / 模块标记核对

机械产品（发明或实用新型）：与结构schema的 `parts`及可标引 `features`共用编号台账；子特征记录母件，不把剖切符号当零件。软件系统框图与系统权要不使用机械件号，其 `parts`可空；方法流程步骤不登记成机械parts。混合案件分别登记实际对象。

```bash
python skills/patent-application/tools/check_numeral_register.py \
  --register <产出>/件号登记表.yaml \
  --claims <产出>/权利要求书.md \
  --spec <产出>/说明书.md
```

机械产品加 `--schema`与 `--figure-plan`，不按发明／实用新型区分。无结构schema的方法／软件案不传结构参数。点名场景图按实际用途登记。

交付前再跑：

```bash
python skills/patent-application/tools/check_support.py --dir <产出>
```

`APPLICATION_NUMERALS: ok=0`先核实登记名、别名、句式前缀及实际对象；确定串号／漏号才改表或正文，误报记录依据。`check_support`归集结果到 `标号核对.md`，警告人工复核，不能为消除误报更改正确技术内容。逐处标号与图面检查继续执行。
