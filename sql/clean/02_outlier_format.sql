-- ============================================================
-- 步骤 2：异常值与格式标准化（手册 3.2）
-- 目标：处理负金额、超大金额、异常年龄，统一日期与手机号格式
-- ============================================================

-- 金额异常处理（示例：按 P99 阈值）
select percentile(pay_amount, 0.99) from ydsh_ods.ods_order;

-- 日期统一为 yyyy-MM-dd
select regexp_replace(register_date, '/', '-') from ydsh_ods.ods_user;

-- 手机号去分隔符
select regexp_replace(phone, '-', '') from ydsh_ods.ods_user;

-- 验证通过标准：金额无负值、无超大值；日期格式统一
