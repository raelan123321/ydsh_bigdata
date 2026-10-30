# -*- coding: utf-8 -*-
# 数据质量预评估表 生成脚本（统计型：质量总览 + 明细问题清单）
try:
    import openpyxl
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "openpyxl>=3.1.0"])
    import openpyxl

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import CellIsRule
from openpyxl.utils import get_column_letter

def xl_color(css_hex: str) -> str:
    value = css_hex.removeprefix("#").upper()
    if len(value) != 6:
        raise ValueError(f"Expected #RRGGBB, got: {css_hex}")
    return "FF" + value

XL_PRIMARY = xl_color("#4472C4")
XL_LIGHT = xl_color("#D9E2F3")
XL_BORDER = xl_color("#BFBFBF")
RED_FILL = PatternFill("solid", start_color=xl_color("#FFC7CE"))
RED_FONT = Font(color=xl_color("#9C0006"))
YELLOW_FILL = PatternFill("solid", start_color=xl_color("#FFEB9C"))
YELLOW_FONT = Font(color=xl_color("#9C6500"))
GREEN_FILL = PatternFill("solid", start_color=xl_color("#C6EFCE"))
GREEN_FONT = Font(color=xl_color("#006100"))

thin = Side(style="thin", color=XL_BORDER)
border_all = Border(left=thin, right=thin, top=thin, bottom=thin)

wb = openpyxl.Workbook()
wb.properties.title = "数据质量预评估表"

# ============ Sheet 1: 质量总览 ============
ws = wb.active
ws.title = "质量总览"

# 锚点：第1行标题、第2行表头、第3~8行数据、第9行合计、第11行说明
ws.merge_cells("A1:J1")
ws["A1"] = "云购生活新零售 · 第1周数据质量预评估表（五维度扫描）"
ws["A1"].font = Font(bold=True, size=14, color="FFFFFF")
ws["A1"].fill = PatternFill("solid", start_color=XL_PRIMARY)
ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[1].height = 28

headers = ["表名", "总行数", "完整性问题数", "唯一性问题数", "有效性问题数", "一致性问题数", "准确性问题数", "问题总数", "主要问题", "建议处理策略"]
for i, h in enumerate(headers, start=1):
    c = ws.cell(row=2, column=i, value=h)
    c.font = Font(bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", start_color=XL_PRIMARY)
    c.alignment = Alignment(horizontal="center", vertical="center", wrapText=True)
    c.border = border_all

overview = [
    ("ods_user", 1000, "邮箱缺失193、性别非法414、手机号格式错误102、年龄缺失51/非法27", "缺失值填充（年龄均值41）+ 枚举与格式统一", (342, 0, 543, 0, 100)),
    ("ods_product", 600, "上架日期缺失11、价格负数20", "缺失补默认日期，负数价格修正", (11, 0, 20, 0, 0)),
    ("ods_store", 60, "未发现问题，整体质量良好", "无需处理，直接进入下层数据加工", (0, 0, 0, 0, 0)),
    ("ods_order", 15600, "主键重复586、折扣为负769、金额≤0共310、状态枚举混乱1175、日期格式混用1902", "ROW_NUMBER()去重 + 金额校验 + 枚举映射 + 日期统一", (0, 586, 3229, 0, 1902)),
    ("ods_order_item", 37549, "数量≤0共718、单价负数798", "过滤非法数量与负数单价", (0, 0, 1516, 0, 0)),
    ("ods_user_behavior", 60000, "行为类型中英混用3672、行为时间格式错误6088", "枚举统一为 pv/fav/cart/buy + 时间格式统一", (0, 0, 3672, 0, 6088)),
]

# 数据区 3~8 行：维度列为静态扫描结果（快照报告，无公式）
for r, (name, total, issues, action, dims) in enumerate(overview, start=3):
    ws.cell(row=r, column=1, value=name)
    ws.cell(row=r, column=2, value=total)
    for ci, v in zip(range(3, 8), dims):
        ws.cell(row=r, column=ci, value=v)
    ws.cell(row=r, column=8, value=sum(dims))
    ws.cell(row=r, column=9, value=issues)
    ws.cell(row=r, column=10, value=action)
    for ci in range(1, 11):
        cell = ws.cell(row=r, column=ci)
        cell.border = border_all
        if ci in (2, 3, 4, 5, 6, 7, 8):
            cell.alignment = Alignment(horizontal="right", vertical="center")
            cell.number_format = "#,##0"
        else:
            cell.alignment = Alignment(horizontal="left", vertical="center", wrapText=True)
        if r % 2 == 1:
            cell.fill = PatternFill("solid", start_color=XL_LIGHT)

# 合计行 第9行（静态快照值）
totals = [sum(x[i] for x in overview) for i in range(1, 2)]  # 总行数合计
dim_totals = [sum(x[4][j] for x in overview) for j in range(5)]
ws.cell(row=9, column=1, value="合计")
ws.cell(row=9, column=2, value=sum(x[1] for x in overview))
for j, v in enumerate(dim_totals):
    ws.cell(row=9, column=3 + j, value=v)
ws.cell(row=9, column=8, value=sum(dim_totals))
for ci in range(1, 11):
    cell = ws.cell(row=9, column=ci)
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill("solid", start_color=xl_color("#2F5597"))
    cell.border = border_all
    cell.alignment = Alignment(horizontal="right" if ci in range(2, 9) else "left", vertical="center")

ws["A11"] = "扫描说明：Python 对 6 张源 CSV 全量扫描（114,815 行数据，与 Hive ODS 层导入数据一致）；扫描日期：2026-10-30。占比与明细见「明细问题清单」表。"
ws["A11"].font = Font(size=10, italic=True, color="666666")

# 条件格式：问题总数列
ws.conditional_formatting.add("H3:H8", CellIsRule(operator="greaterThanOrEqual", formula=["1000"], fill=RED_FILL, font=RED_FONT))
ws.conditional_formatting.add("H3:H8", CellIsRule(operator="greaterThan", formula=["0"], fill=YELLOW_FILL, font=YELLOW_FONT))

widths = {"A": 18, "B": 10, "C": 12, "D": 12, "E": 12, "F": 12, "G": 12, "H": 10, "I": 46, "J": 40}
for col, w in widths.items():
    ws.column_dimensions[col].width = w
ws.freeze_panes = "A3"

# ============ Sheet 2: 明细问题清单 ============
wd = wb.create_sheet("明细问题清单")
dhead = ["序号", "表名", "质量维度", "检查项", "问题数量", "表总行数", "占比", "建议处理策略", "优先级"]
for i, h in enumerate(dhead, start=1):
    c = wd.cell(row=1, column=i, value=h)
    c.font = Font(bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", start_color=XL_PRIMARY)
    c.alignment = Alignment(horizontal="center", vertical="center", wrapText=True)
    c.border = border_all

issues = [
    ("ods_user", "完整性", "gender 性别空值", 84, 1000, "空值归入“未知”或按注册行为推断填充", "中"),
    ("ods_user", "完整性", "age 年龄空值", 51, 1000, "合法年龄均值(41)填充", "高"),
    ("ods_user", "完整性", "member_level 会员等级空值", 14, 1000, "标记“普通会员”或“未知”", "低"),
    ("ods_user", "完整性", "email 邮箱空值", 193, 1000, "保留空值并统一标记为“未知”", "中"),
    ("ods_user", "唯一性", "user_id 主键重复", 0, 1000, "无需处理", "低"),
    ("ods_user", "有效性", "年龄非法（≤0 或 ≥120）", 27, 1000, "边界清洗后按均值填充", "中"),
    ("ods_user", "有效性", "性别取值异常（非男/女/未知）", 414, 1000, "枚举映射并回查源数据口径", "中"),
    ("ods_user", "有效性", "手机号非 1 开头 11 位规范", 102, 1000, "标记待核实，不参与分析", "中"),
    ("ods_user", "准确性", "注册日期含“2023/06/21”式非标准格式", 100, 1000, "统一为 YYYY-MM-DD", "中"),
    ("ods_product", "完整性", "launch_date 上架日期空值", 11, 600, "补默认日期 2020-01-01", "低"),
    ("ods_product", "有效性", "price 价格负数", 20, 600, "按类目成本修正或过滤", "中"),
    ("ods_product", "唯一性", "product_id 主键重复", 0, 600, "无需处理", "低"),
    ("ods_store", "唯一性", "store_id 主键重复", 0, 60, "无需处理", "低"),
    ("ods_store", "完整性", "关键字段空值（店名/开店日期/面积）", 0, 60, "无需处理", "低"),
    ("ods_store", "有效性", "area 面积 ≤0", 0, 60, "无需处理", "低"),
    ("ods_order", "唯一性", "order_id 主键重复（主键重复但字段不同）", 586, 15600, "ROW_NUMBER() 窗口函数按时间保留一条", "高"),
    ("ods_order", "完整性", "关键字段空值（金额/支付/状态等）", 0, 15600, "无需处理", "低"),
    ("ods_order", "有效性", "pay_amount 实付金额 ≤0", 310, 15600, "剔除或按订单明细重算", "高"),
    ("ods_order", "有效性", "discount_amount 折扣金额为负", 769, 15600, "负数折扣置 0 或回查业务规则", "高"),
    ("ods_order", "有效性", "折扣金额 > 应付金额", 324, 15600, "业务规则校验后修正", "中"),
    ("ods_order", "有效性", "pay_type 枚举中英混用（alipay/wechat/微信）", 651, 15600, "映射为标准中文枚举", "中"),
    ("ods_order", "有效性", "order_status 枚举混乱（数字码/英文/变体）", 1175, 15600, "映射为标准状态枚举", "高"),
    ("ods_order", "一致性", "user_id 外键不在用户表", 0, 15600, "无需处理", "低"),
    ("ods_order", "一致性", "store_id 外键不在门店表", 0, 15600, "无需处理", "低"),
    ("ods_order", "准确性", "order_date 含“2024/09/10”式非标准格式", 1902, 15600, "统一为 YYYY-MM-DD", "高"),
    ("ods_order_item", "唯一性", "item_id 主键重复", 0, 37549, "无需处理", "低"),
    ("ods_order_item", "有效性", "quantity 购买数量 ≤0", 718, 37549, "过滤非法数量记录", "中"),
    ("ods_order_item", "有效性", "unit_price 单价为负", 798, 37549, "过滤或按订单金额反推修正", "中"),
    ("ods_order_item", "一致性", "order_id 外键不在订单表", 0, 37549, "无需处理", "低"),
    ("ods_order_item", "一致性", "product_id 外键不在商品表", 0, 37549, "无需处理", "低"),
    ("ods_user_behavior", "唯一性", "behavior_id 主键重复", 0, 60000, "无需处理", "低"),
    ("ods_user_behavior", "有效性", "behavior_type 枚举中英混用（购买/加购/浏览/收藏 vs buy/cart/pv/fav）", 3672, 60000, "统一映射为 pv/fav/cart/buy 四类", "高"),
    ("ods_user_behavior", "准确性", "behavior_time 非标准时间格式", 6088, 60000, "统一为 YYYY-MM-DD HH:mm:ss", "中"),
    ("ods_user_behavior", "一致性", "user_id 外键不在用户表", 0, 60000, "无需处理", "低"),
    ("ods_user_behavior", "一致性", "product_id 外键不在商品表", 0, 60000, "无需处理", "低"),
]

# 数据区：第 2 行起，共 len(issues) 行
for r, (tbl, dim, item, cnt, total, action, prio) in enumerate(issues, start=2):
    wd.cell(row=r, column=1, value=r - 1)
    wd.cell(row=r, column=2, value=tbl)
    wd.cell(row=r, column=3, value=dim)
    wd.cell(row=r, column=4, value=item)
    wd.cell(row=r, column=5, value=cnt)
    wd.cell(row=r, column=6, value=total)
    ratio = cnt / total if total else 0
    wd.cell(row=r, column=7, value=round(ratio, 4))
    wd.cell(row=r, column=7).number_format = "0.00%"
    wd.cell(row=r, column=8, value=action)
    wd.cell(row=r, column=9, value=prio)
    for ci in range(1, 10):
        cell = wd.cell(row=r, column=ci)
        cell.border = border_all
        if ci in (1, 5, 6, 9):
            cell.alignment = Alignment(horizontal="center", vertical="center")
            if ci in (5, 6):
                cell.number_format = "#,##0"
        elif ci == 7:
            cell.alignment = Alignment(horizontal="right", vertical="center")
        else:
            cell.alignment = Alignment(horizontal="left", vertical="center", wrapText=True)

last = len(issues) + 1
wd.conditional_formatting.add(f"I2:I{last}", CellIsRule(operator="equal", formula=['"高"'], fill=RED_FILL, font=RED_FONT))
wd.conditional_formatting.add(f"I2:I{last}", CellIsRule(operator="equal", formula=['"中"'], fill=YELLOW_FILL, font=YELLOW_FONT))
wd.conditional_formatting.add(f"I2:I{last}", CellIsRule(operator="equal", formula=['"低"'], fill=GREEN_FILL, font=GREEN_FONT))

dw = {"A": 6, "B": 18, "C": 10, "D": 42, "E": 10, "F": 10, "G": 10, "H": 38, "I": 8}
for col, w in dw.items():
    wd.column_dimensions[col].width = w
wd.freeze_panes = "A2"
wd.auto_filter.ref = f"A1:I{last}"

out = r"E:/ydsh_bigdate/交付物/数据质量预评估表.xlsx"
wb.save(out)
print("saved:", out)
