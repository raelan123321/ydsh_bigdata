-- =====================================================================
-- 第3周 子任务1：DWS 汇总层（按天 / 周 / 月 / 品类 / 门店 / 渠道 六张汇总表）
--
-- 设计原则
--   1) 只做"轻度汇总"，不跨主题、不做复杂计算，保持可复用
--   2) 粒度统一为"统计周期 + 一个分析维度"，供 ADS 与后续 NL2SQL 直接查询
--   3) 全部基于 dwd.dwd_order_norm（状态已标准化），KPI 口径只认有效订单：
--      有效订单 = order_status in ('已完成','已支付') 且 pay_amount is not null
-- =====================================================================

create database if not exists dws location '/opt/hive/warehouse/dws';

-- ---------------------------------------------------------------------
-- 1) 按天汇总（ADS 销售日报与预测建模的数据源）
-- ---------------------------------------------------------------------
drop table if exists dws.dws_sales_day;
create table dws.dws_sales_day (
  order_date  string comment '订单日期',
  order_cnt   bigint comment '有效订单量',
  gmv         double comment '成交总额',
  aov         double comment '客单价',
  user_cnt    bigint comment '下单用户数',
  avg_discount double comment '平均优惠金额'
) stored as orc;

insert overwrite table dws.dws_sales_day
select order_date,
       count(distinct order_id)               as order_cnt,
       round(sum(pay_amount), 2)              as gmv,
       round(sum(pay_amount) / count(distinct order_id), 2) as aov,
       count(distinct user_id)                as user_cnt,
       round(avg(discount_amount), 2)         as avg_discount
from dwd.dwd_order_norm
where order_status in ('已完成', '已支付')
  and pay_amount is not null
group by order_date;

-- ---------------------------------------------------------------------
-- 2) 按周汇总
-- ---------------------------------------------------------------------
drop table if exists dws.dws_sales_week;
create table dws.dws_sales_week (
  week_start string comment '周一日期',
  year_week  string comment '年-周',
  order_cnt  bigint,
  gmv        double,
  user_cnt   bigint
) stored as orc;

insert overwrite table dws.dws_sales_week
select date_sub(next_day(order_date, 'MO'), 7)          as week_start,
       concat(year(order_date), '-', lpad(weekofyear(order_date), 2, '0')) as year_week,
       count(distinct order_id),
       round(sum(pay_amount), 2),
       count(distinct user_id)
from dwd.dwd_order_norm
where order_status in ('已完成', '已支付')
  and pay_amount is not null
group by date_sub(next_day(order_date, 'MO'), 7),
         concat(year(order_date), '-', lpad(weekofyear(order_date), 2, '0'));

-- ---------------------------------------------------------------------
-- 3) 按月汇总
-- ---------------------------------------------------------------------
drop table if exists dws.dws_sales_month;
create table dws.dws_sales_month (
  month     string comment 'yyyy-MM',
  order_cnt bigint,
  gmv       double,
  aov       double,
  user_cnt  bigint
) stored as orc;

insert overwrite table dws.dws_sales_month
select substr(order_date, 1, 7) as month,
       count(distinct order_id),
       round(sum(pay_amount), 2),
       round(sum(pay_amount) / count(distinct order_id), 2),
       count(distinct user_id)
from dwd.dwd_order_norm
where order_status in ('已完成', '已支付')
  and pay_amount is not null
group by substr(order_date, 1, 7);

-- ---------------------------------------------------------------------
-- 4) 品类 × 天 汇总
--    品类来自 dim_product，金额来自明细表（quantity*unit_price*(1-discount)），
--    避免手册"事实表直接 join 商品维度"造成的多明细重复计费问题
-- ---------------------------------------------------------------------
drop table if exists dws.dws_category_day;
create table dws.dws_category_day (
  order_date string comment '订单日期',
  category   string comment '商品大类',
  sales      double comment '品类销售额',
  qty        bigint comment '销售件数',
  order_cnt  bigint comment '涉及订单数'
) stored as orc;

insert overwrite table dws.dws_category_day
select i.order_date,
       p.category,
       round(sum(i.item_amount), 2) as sales,
       sum(i.quantity)              as qty,
       count(distinct i.order_id)   as order_cnt
from dwd.dwd_order_item i
join dwd.dim_product p on i.product_id = p.product_id
join dwd.dwd_order_norm o on i.order_id = o.order_id
where o.order_status in ('已完成', '已支付')
  and i.order_date is not null
group by i.order_date, p.category;

-- ---------------------------------------------------------------------
-- 5) 门店 × 天 汇总
-- ---------------------------------------------------------------------
drop table if exists dws.dws_store_day;
create table dws.dws_store_day (
  order_date string,
  store_id   string,
  store_name string,
  province   string,
  city       string,
  sales      double,
  order_cnt  bigint,
  user_cnt   bigint
) stored as orc;

insert overwrite table dws.dws_store_day
select o.order_date,
       o.store_id,
       s.store_name,
       s.province,
       s.city,
       round(sum(o.pay_amount), 2) as sales,
       count(distinct o.order_id)  as order_cnt,
       count(distinct o.user_id)   as user_cnt
from dwd.dwd_order_norm o
left join dwd.dim_store s on o.store_id = s.store_id
where o.order_status in ('已完成', '已支付')
  and o.pay_amount is not null
group by o.order_date, o.store_id, s.store_name, s.province, s.city;

-- ---------------------------------------------------------------------
-- 6) 渠道 × 天 汇总
-- ---------------------------------------------------------------------
drop table if exists dws.dws_channel_day;
create table dws.dws_channel_day (
  order_date string,
  channel    string,
  sales      double,
  order_cnt  bigint,
  user_cnt   bigint
) stored as orc;

insert overwrite table dws.dws_channel_day
select order_date,
       channel,
       round(sum(pay_amount), 2),
       count(distinct order_id),
       count(distinct user_id)
from dwd.dwd_order_norm
where order_status in ('已完成', '已支付')
  and pay_amount is not null
group by order_date, channel;

-- ---------------------------------------------------------------------
-- 验证通过标准
-- ---------------------------------------------------------------------
select 'dws_sales_day' as tbl, count(*) as cnt from dws.dws_sales_day
union all select 'dws_sales_week',  count(*) from dws.dws_sales_week
union all select 'dws_sales_month', count(*) from dws.dws_sales_month
union all select 'dws_category_day',count(*) from dws.dws_category_day
union all select 'dws_store_day',   count(*) from dws.dws_store_day
union all select 'dws_channel_day', count(*) from dws.dws_channel_day;

-- 按月看趋势（12 行左右，验证分布合理性）
select * from dws.dws_sales_month order by month;
