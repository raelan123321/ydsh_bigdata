# 第 5 周 · Git 提交历史审查报告

> 审查日期：2026-11-23　仓库：github.com/raelan123321/ydsh_bigdata　对象：main 全量 51 次提交 + feature 分支

## 一、提交网络图与分支结构

```
* 6113405 fix: Hive 编排修复（幂等初始化/命名卷/0.0.0.0）
* 2a96f1f docs: README 更新至第4周
* 4886383 docs(w4): 交付清单
* 2b33943 docs(w4): 部署手册/API指南/周志/压测
* 987b286 feat(w4): 支撑脚本（导数/Superset REST/压测）
* 02904d5 feat(w4): Streamlit 智能问答
* 8c9e8c8 feat(w4): ECharts 数据大屏
* 26ced53 feat(w4): 编排扩展（Superset/ClickHouse/screen-api/app）
* c999a32 chore: 清理
*   eff0d7a merge: 第3周（PR 留痕见 docs/collaboration/）
|\
| * f5a9644 docs(交付物6): PR说明/CodeReview/Issue 与 PR 模板
| * c0acbf6 docs(交付物5): AI 智能洞察与反思
| * 99ec1df docs(交付物3): 预测建模分析报告
| * 6fde105 docs(交付物2): KPI 结果表
| * c85898f fix(子任务1): KPI 脚本重构（Tez 计数器上限）
| * 6731cf1 / 332f281 / 5f43369 fix: NL2SQL 与预测修正
| * a6af788 / 9a6b47a / 147a5f8 feat: AI洞察 / NL2SQL / 预测
| * c7fd182 / 262d796 feat: DWS / DWD 补强
|/
* 2cfcf92 …（第 1~2 周：环境/清洗/探索分析）
```

- 主干 `main` 线性清晰，第 3 周功能在 `feature/week3-dws-ads-nl2sql` 独立分支开发后经 merge 回主干，merge 提交注明 PR 位置。
- 分支命名 `feature/<周次>-<主题>`，符合规范；PR / CodeReview / Issue 记录归档于 `docs/collaboration/`。

## 二、约定式提交规范核查

| 类型 | 次数 | 用例 |
|---|---|---|
| feat | 20+ | 大屏、NL2SQL、DWS/ADS、编排扩展（含 `feat(w4)` `feat(子任务N)` 作用域） |
| fix | 8 | KPI 脚本重构、Hive 编排修复、中文别名修正 |
| docs | 15+ | 周志、交付清单、手册、README |
| chore / merge | 6 | 清理、分支合并 |

结论：**类型标注一致、作用域可追溯、单提交聚焦单一功能**，符合约定式提交规范。

## 三、敏感信息与卫生检查

- 全历史扫描未发现硬编码密码 / 密钥（第 4 周起密钥全部经 `.env` 注入，`.env.example` 仅含占位符）。
- `.gitignore` 覆盖交付压缩包、输出缓存等临时产物。
- 无 force-push 痕迹，主干历史未被改写。

## 四、审查结论与改进项

| 项 | 状态 |
|---|---|
| 主干历史清晰 | ✅ |
| 分支命名规范 | ✅ |
| 约定式提交 | ✅ |
| PR/Issue 留痕 | ✅（docs/collaboration/） |
| 无敏感信息泄露 | ✅ |
| 每功能独立分支 | ⚠️ 仅第 3 周使用分支；第 4 周单人直推主干（一人团队下可接受，多成员时应恢复分支流程） |
