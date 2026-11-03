-- ============================================================
-- 步骤 6（下）：DWD 层订单事实表（手册 3.6）
-- 目标：以订单事实表为核心，按日期分区，ORC 存储
-- ============================================================

-- 订单事实表（分区表）
create table dwd.dwd_order (
  order_id string, user_id string, store_id string,
  order_timestamp string, pay_amount double, discount_amount double,
  order_status string, channel string
) partitioned by (order_date string) stored as orc;

-- 验证通过标准：事实表含度量字段（pay_amount / discount_amount）
