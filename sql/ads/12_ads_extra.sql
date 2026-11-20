-- =====================================================================
-- 第4周补充：ADS 层区域表与渠道表（供 Superset 区域地图 / 渠道饼图消费）
--   1) ads.ads_region    省级销售额与订单数（地图数据集）
--   2) ads.ads_channel   渠道销售额占比（饼图数据集）
-- 口径：有效订单 = order_status in ('已完成','已支付') 且 pay_amount 非空
-- =====================================================================

drop table if exists ads.ads_region;
create table ads.ads_region stored as orc as
select st.province                                      as province,
       round(sum(o.pay_amount), 2)                      as sales,
       count(distinct o.order_id)                       as cnt
from dwd.dwd_order_norm o
join dwd.dim_store st on o.store_id = st.store_id
where o.order_status in ('已完成', '已支付')
  and o.pay_amount is not null
group by st.province;

drop table if exists ads.ads_channel;
create table ads.ads_channel stored as orc as
select channel                                as channel,
       round(sum(pay_amount), 2)              as sales,
       count(*)                               as cnt
from dwd.dwd_order_norm
where order_status in ('已完成', '已支付')
  and pay_amount is not null
group by channel;

-- 验证通过标准
select * from ads.ads_region order by sales desc;
select * from ads.ads_channel order by sales desc;
