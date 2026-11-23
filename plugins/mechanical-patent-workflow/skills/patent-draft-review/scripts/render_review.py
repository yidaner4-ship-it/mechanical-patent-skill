#!/usr/bin/env python3
"""Render supplied review records, not perform or approve a patent review.

Independent implementation. MIT License.
Copyright (c) 2026 Mechanical Patent Toolkit contributors.
"""

import argparse
import html
import json
from pathlib import Path
import sys


def _escaped(value):
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    return html.escape(text, quote=True)


def _first(record, names, fallback="未提供"):
    for name in names:
        if name in record:
            return record[name]
    return fallback


def render_report(data):
    """Return static HTML, retaining every input field as escaped visible JSON."""
    if not isinstance(data, (dict, list)):
        raise ValueError("JSON 顶层必须为对象或数组")
    root = data if isinstance(data, dict) else {}
    title = _first(root, ("title", "case_title"), "专利稿审阅记录")
    issues = data if isinstance(data, list) else _first(
        root, ("issues", "findings", "problems"), []
    )
    rows = []
    if isinstance(issues, list):
        for index, item in enumerate(issues, 1):
            record = item if isinstance(item, dict) else {"record": item}
            label = _first(record, ("id", "issue_id"), str(index))
            fields = (
                ("程度", ("severity", "priority")),
                ("位置", ("location", "where")),
                ("证据", ("evidence", "source")),
                ("影响", ("impact", "reason")),
                ("建议", ("recommendation", "suggestion")),
                ("状态", ("status", "disposition")),
                ("复核", ("recheck", "verification")),
            )
            values = "".join(
                "<dt>" + heading + "</dt><dd>" + _escaped(_first(record, names))
                + "</dd>" for heading, names in fields
            )
            rows.append(
                '<article class="issue" id="issue-' + str(index) + '"><h3>'
                + _escaped(label) + "</h3><dl>" + values
                + '</dl><details open><summary>完整条目（含其他字段）</summary><pre>'
                + _escaped(item) + "</pre></details></article>"
            )
    else:
        rows.append("<p>问题字段不是数组；原值保留在全部输入记录中，未据此推定审核状态。</p>")
    if not rows:
        rows.append("<p>未提供问题条目；这不表示已完成审阅或不存在问题。</p>")
    status = _first(root, ("review_status", "status"))
    # All dynamic values pass through html.escape; no input enters script or CSS.
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>""" + _escaped(title) + """</title><style>
body{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1.2rem;color:#20252a;line-height:1.6}
h1{font-size:1.7rem}h2{margin-top:2rem}h3{margin-top:0}.notice{border-left:4px solid #926a12;background:#fff7df;padding:1rem}
.issue{border:1px solid #ccd2d7;border-radius:6px;margin:1rem 0;padding:1rem}dl{display:grid;grid-template-columns:5em 1fr;gap:.4rem}dt{font-weight:600}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f7;padding:1rem;border:1px solid #dde1e4}summary{cursor:pointer}footer{border-top:1px solid #ccd2d7;margin-top:2rem;padding-top:1rem}
@media print{body{max-width:none;margin:0}.issue{break-inside:avoid}summary{display:none}}
</style></head><body><h1>""" + _escaped(title) + """</h1>
<p class="notice">本页仅呈现提供的审核记录；报告生成不等于完成独立审阅、目视核图、问题整改或审查通过。</p>
<p><strong>提供的审核状态：</strong>""" + _escaped(status) + """</p>
<h2>问题记录</h2>""" + "".join(rows) + """
<h2>全部输入记录（完整保留）</h2><p>以下包含所有已提供字段；未填写或未知字段未被推定为通过。</p>
<pre id="complete-input">""" + _escaped(data) + """</pre>
<footer>独立公开兼容实现。所有判断、状态及证据均以实际审阅和复核记录为准。</footer>
</body></html>
"""


def _invalid_constant(value):
    raise ValueError("JSON 不允许非有限数值")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "--json", "-i", required=True, dest="input")
    parser.add_argument("--output", "--out", "-o", required=True, dest="output")
    args = parser.parse_args(argv)
    try:
        if args.input != "-" and args.output != "-":
            if Path(args.input).resolve() == Path(args.output).resolve():
                raise ValueError("输入和输出不能是同一文件")
        if args.input == "-":
            source = sys.stdin.read()
        else:
            source = Path(args.input).read_text(encoding="utf-8-sig")
        data = json.loads(source, parse_constant=_invalid_constant)
        result = render_report(data)
        if args.output == "-":
            sys.stdout.write(result)
        else:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(result, encoding="utf-8")
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        # Error messages deliberately avoid echoing source data or local paths.
        message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else "读取、解析或写入失败"
        print("报告未生成：" + message, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
