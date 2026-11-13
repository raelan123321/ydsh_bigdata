-- =====================================================================
-- 第3周 子任务1：KPI 指标结果表
-- 交付物 2 要求：核心指标统计结果（可直接读取的结果表，而非临时查询）
-- 5 项 KPI：GMV / 订单量 / 客单价 AOV / 活跃用户数 / 复购率
--
-- 口径说明（这是本脚本最重要的部分，答辩必问）
--   有效订单 = order_status in ('已完成','已支付') 且 pay_amount is not null
--     · 已取消 / 待支付 / 退款中 不计入任何销售类指标
--     · 状态为纯数字码(1/2/3/4)的订单语义不可考，归入"其他"，一并排除
--   GMV      = 有效订单 pay_amount 之和
--   订单量   = 有效订单去重数
--   AOV      = GMV / 订单量
--   活跃用户 = 有效订单中的去重用户数
--   复购率   = 有效订单数 >= 2 的用户数 / 有效订单用户数
-- =====================================================================

create database if not exists ads location '/opt/hive/warehouse/ads';

drop table if exists ads.ads_kpi_summary;
create table ads.ads_kpi_summary (
  kpi_name   string comment '指标名称',
  kpi_value  double comment '指标值',
  kpi_unit   string comment '单位',
  calc_desc  string comment '计算口径说明',
  stat_scope string comment '统计范围',
  calc_time  string comment '计算时间'
) stored as orc;

insert overwrite table ads.ads_kpi_summary
select 'GMV' as kpi_name,
       round(sum(t.gmv), 2) as kpi_value,
       '元' as kpi_unit,
       '有效订单(已完成/已支付)实付金额之和' as calc_desc,
       '2024-01-01 ~ 2024-12-31' as stat_scope,
       from_unixtime(unix_timestamp()) as calc_time
from (select sum(pay_amount) as gmv from dwd.dwd_order_norm
      where order_status in ('已完成', '已支付') and pay_amount is not null) t
union all
select '订单量', count(distinct order_id), '单',
       '有效订单去重计数', '2024-01-01 ~ 2024-12-31', from_unixtime(unix_timestamp())
from dwd.dwd_order_norm
where order_status in ('已完成', '已支付') and pay_amount is not null
union all
select '客单价AOV',
       round(sum(pay_amount) / count(distinct order_id), 2), '元',
       'GMV / 订单量', '2024-01-01 ~ 2024-12-31', from_unixtime(unix_timestamp())
from dwd.dwd_order_norm
where order_status in ('已完成', '已支付') and pay_amount is not null
union all
select '活跃用户数', count(distinct user_id), '人',
       '有效订单中的去重用户数', '2024-01-01 ~ 2024-12-31', from_unixtime(unix_timestamp())
from dwd.dwd_order_norm
where order_status in ('已完成', '已支付') and pay_amount is not null
union all
select '复购率',
       round(sum(case when freq >= 2 then 1 else 0 end) / count(*) * 100, 2), '%',
       '有效订单数>=2的用户数 / 有效订单用户数', '2024-01-01 ~ 2024-12-31', from_unixtime(unix_timestamp())
from (select user_id, count(distinct order_id) as freq
      from dwd.dwd_order_norm
      where order_status in ('已完成', '已支付') and pay_amount is not null
      group by user_id) u;

-- ---------------------------------------------------------------------
-- 辅助结果表：KPI 月度趋势（供前端趋势图与同比分析使用）
-- ---------------------------------------------------------------------
drop table if exists ads.ads_kpi_month;
create table ads.ads_kpi_month (
  month      string,
  gmv        double,
  order_cnt  bigint,
  aov        double,
  user_cnt   bigint,
  repurchase_rate double comment '当月复购率(%)'
) stored as orc;

insert overwrite table ads.ads_kpi_month
select m.month, m.gmv, m.order_cnt, m.aov, m.user_cnt,
       round(coalesce(r.repurchase_rate, 0), 2)
from dws.dws_sales_month m
left join (
    select substr(order_date, 1, 7) as month,
           sum(case when freq >= 2 then 1 else 0 end) / count(*) * 100 as repurchase_rate
    from (
        select user_id, substr(order_date, 1, 7) as order_date,
               count(distinct order_id) as freq
        from dwd.dwd_order_norm
        where order_status in ('已完成', '已支付') and pay_amount is not null
        group by user_id, substr(order_date, 1, 7)
    ) x
    group by substr(order_date, 1, 7)
) r on m.month = r.month;

-- ---------------------------------------------------------------------
-- 验证通过标准
-- ---------------------------------------------------------------------
select * from ads.ads_kpi_summary;
select * from ads.ads_kpi_month order by month;
