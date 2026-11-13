## 变更类型
<!-- feat / fix / docs / refactor / chore -->

## 对应子任务
<!-- 子任务编号与名称 -->

## 变更说明
<!-- 做了什么、为什么这么做 -->

## 口径影响
<!-- 是否修改指标口径？若修改，写明影响范围与数值变化 -->

## 验证方式
- [ ] SQL 在 Hive 实跑通过
- [ ] 结果与独立 SQL 交叉比对
- [ ] Python 脚本 `--source csv` 与 `--source hive` 均可运行
- [ ] 文档数字与 `output/week3/实跑结果记录.md` 一致

## 自审清单
- [ ] 无硬编码密钥
- [ ] 脚本可重复执行（drop if exists）
- [ ] 注释写明业务口径
- [ ] 已知问题已转 Issue

## 关联 Issue
Closes #
