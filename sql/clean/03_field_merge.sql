-- ============================================================
-- 步骤 3：字段拆分合并（手册 3.3）
-- 目标：合并订单日期与时间为完整时间戳，为后续时间序列分析做准备
-- ============================================================

create table dwd_order_tmp as
select order_id, user_id, store_id,
       concat(order_date, ' ', order_time) as order_timestamp,
       pay_amount, discount_amount, pay_type, order_status, channel
from dwd_order;

-- 验证通过标准：order_timestamp 为 yyyy-MM-dd HH:mm:ss 格式，无空值
