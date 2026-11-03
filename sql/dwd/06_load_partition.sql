-- ============================================================
-- 步骤 7：分区表数据加载（手册 3.7）
-- 目标：按日期分区加载数据，验证分区裁剪效果
-- ============================================================

insert overwrite table dwd.dwd_order partition (order_date)
select order_id, user_id, store_id, order_timestamp, pay_amount,
       discount_amount, order_status, channel, substr(order_date,1,10) as order_date
from dwd_order_tmp;

-- 验证通过标准：show partitions dwd.dwd_order; 能看到按天分区，查询带分区条件生效
