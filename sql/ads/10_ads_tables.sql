-- =====================================================================
-- 第3周 子任务1：ADS 应用层（三张面向业务应用的结果表）
--   1) ads_sales_daily    销售日报（含环比、7日移动平均）
--   2) ads_category_top10 品类销售 Top10（含占比与累计占比）
--   3) ads_user_value     用户价值 RFM 分层
-- 说明：ADS 表为"可直接给报表/接口消费"的形态，指标一次算好、查询零加工
-- =====================================================================

create database if not exists ads location '/opt/hive/warehouse/ads';

-- ---------------------------------------------------------------------
-- 1) 销售日报
-- ---------------------------------------------------------------------
drop table if exists ads.ads_sales_daily;
create table ads.ads_sales_daily (
  order_date  string comment '日期',
  gmv         double comment 'GMV',
  order_cnt   bigint comment '订单量',
  aov         double comment '客单价',
  user_cnt    bigint comment '下单用户数',
  dod_rate    double comment 'GMV 日环比(%)',
  gmv_ma7     double comment 'GMV 7日移动平均'
) stored as orc;

insert overwrite table ads.ads_sales_daily
select order_date, gmv, order_cnt, aov, user_cnt,
       round((gmv - lag(gmv) over (order by order_date))
             / lag(gmv) over (order by order_date) * 100, 2)          as dod_rate,
       round(avg(gmv) over (order by order_date
                            rows between 6 preceding and current row), 2) as gmv_ma7
from dws.dws_sales_day;

-- ---------------------------------------------------------------------
-- 2) 品类销售 Top10（全年口径，含占比与累计占比，用于帕累托判断）
-- ---------------------------------------------------------------------
drop table if exists ads.ads_category_top10;
create table ads.ads_category_top10 (
  rk          int    comment '排名',
  category    string comment '商品大类',
  sales       double comment '销售额',
  qty         bigint comment '销售件数',
  order_cnt   bigint comment '订单数',
  sales_share double comment '销售额占比(%)',
  cum_share   double comment '累计占比(%)'
) stored as orc;

insert overwrite table ads.ads_category_top10
select rk, category, sales, qty, order_cnt, sales_share,
       round(sum(sales_share) over (order by rk rows between unbounded preceding and current row), 2) as cum_share
from (
    select row_number() over (order by sales desc) as rk,
           category, sales, qty, order_cnt,
           round(sales / sum(sales) over () * 100, 2) as sales_share
    from (
        select category,
               round(sum(sales), 2) as sales,
               sum(qty)             as qty,
               sum(order_cnt)       as order_cnt
        from dws.dws_category_day
        group by category
    ) c
) r
order by rk
limit 10;

-- ---------------------------------------------------------------------
-- 3) 用户价值 RFM 分层
--    R = 距最后一次下单天数（观察期末 2024-12-31 为基准）
--    F = 有效订单数；M = 累计消费金额
--    打分：ntile(5) 五等分，R 越小得分越高
--    分层：重要价值 / 重要保持 / 重要发展 / 一般价值 / 流失预警 / 一般保持 / 新客
-- ---------------------------------------------------------------------
drop table if exists ads.ads_user_value;
create table ads.ads_user_value (
  user_id       string,
  last_order_date string comment '最近下单日期',
  recency_days  int    comment 'R: 距今天数',
  frequency     bigint comment 'F: 有效订单数',
  monetary      double comment 'M: 累计消费',
  r_score       int,
  f_score       int,
  m_score       int,
  rfm_score     int    comment 'RFM 综合分',
  segment       string comment '价值分层'
) stored as orc;

insert overwrite table ads.ads_user_value
select user_id, last_order_date, recency_days, frequency, monetary,
       r_score, f_score, m_score,
       r_score + f_score + m_score as rfm_score,
       case when r_score >= 4 and f_score >= 4 and m_score >= 4 then '重要价值客户'
            when r_score <= 2 and f_score >= 4 and m_score >= 4 then '重要保持客户'
            when r_score >= 4 and f_score <= 2 and m_score <= 2 then '重要发展客户'
            when r_score <= 2 and f_score <= 2 and m_score <= 2 then '流失预警客户'
            when r_score >= 4 and f_score <= 2 then '新客'
            when r_score <= 2 then '一般保持客户'
            else '一般价值客户' end as segment
from (
    select user_id, last_order_date, recency_days, frequency, monetary,
           6 - ntile(5) over (order by recency_days asc) as r_score,
           ntile(5) over (order by frequency asc)    as f_score,
           ntile(5) over (order by monetary asc)     as m_score
    from (
        select user_id,
               max(order_date)             as last_order_date,
               datediff('2024-12-31', max(order_date)) as recency_days,
               count(distinct order_id)    as frequency,
               round(sum(pay_amount), 2)   as monetary
        from dwd.dwd_order_norm
        where order_status in ('已完成', '已支付')
          and pay_amount is not null
        group by user_id
    ) t
) s;

-- ---------------------------------------------------------------------
-- 验证通过标准
-- ---------------------------------------------------------------------
select 'ads_sales_daily' as tbl, count(*) as cnt from ads.ads_sales_daily
union all select 'ads_category_top10', count(*) from ads.ads_category_top10
union all select 'ads_user_value', count(*) from ads.ads_user_value;

select * from ads.ads_sales_daily order by order_date desc limit 5;
select * from ads.ads_category_top10 order by rk;
select segment, count(*) as user_cnt, round(sum(monetary), 2) as total_amount
from ads.ads_user_value group by segment order by user_cnt desc;
