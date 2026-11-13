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
--
-- 实现要点（踩坑记录）
--   最初把 5 个指标写成 5 路 UNION ALL、各扫一遍 dwd_order_norm，
--   在 Tez 上直接报 "Too many counters: 121 max=120" 而失败，
--   且 5 次全表扫描本身也很浪费。
--   现改为"单次扫描 -> 落基础汇总小表 -> 小表 UNION 展开 5 行"：
--   扫描次数由 5 次降为 2 次（订单口径 1 次 + 用户频次 1 次），计数器压力随之消失。
-- =====================================================================

create database if not exists ads location '/opt/hive/warehouse/ads';

-- ---------------------------------------------------------------------
-- 基础汇总 1：订单口径（GMV / 订单量 / 用户数），一次扫描
-- ---------------------------------------------------------------------
drop table if exists ads.ads_kpi_base;
create table ads.ads_kpi_base stored as orc as
select round(sum(pay_amount), 2)   as gmv,
       count(distinct order_id)    as order_cnt,
       count(distinct user_id)     as user_cnt
from dwd.dwd_order_norm
where order_status in ('已完成', '已支付')
  and pay_amount is not null;

-- ---------------------------------------------------------------------
-- 基础汇总 2：用户下单频次（复购率分子分母），一次扫描
-- ---------------------------------------------------------------------
drop table if exists ads.ads_kpi_base_user;
create table ads.ads_kpi_base_user stored as orc as
select count(*)                                   as total_user,
       sum(case when freq >= 2 then 1 else 0 end)  as repeat_user
from (
    select user_id, count(distinct order_id) as freq
    from dwd.dwd_order_norm
    where order_status in ('已完成', '已支付') and pay_amount is not null
    group by user_id
) t;

-- ---------------------------------------------------------------------
-- 结果表：5 行 KPI（从两张一行小表展开，不再扫事实表）
-- ---------------------------------------------------------------------
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
select 'GMV', gmv, '元', '有效订单(已完成/已支付)实付金额之和', '2024-01-01 ~ 2024-12-31', from_unixtime(unix_timestamp())
from ads.ads_kpi_base
union all
select '订单量', order_cnt, '单', '有效订单去重计数', '2024-01-01 ~ 2024-12-31', from_unixtime(unix_timestamp())
from ads.ads_kpi_base
union all
select '客单价AOV', round(gmv / order_cnt, 2), '元', 'GMV / 订单量', '2024-01-01 ~ 2024-12-31', from_unixtime(unix_timestamp())
from ads.ads_kpi_base
union all
select '活跃用户数', user_cnt, '人', '有效订单中的去重用户数', '2024-01-01 ~ 2024-12-31', from_unixtime(unix_timestamp())
from ads.ads_kpi_base
union all
select '复购率', round(repeat_user / total_user * 100, 2), '%', '有效订单数>=2的用户数 / 有效订单用户数', '2024-01-01 ~ 2024-12-31', from_unixtime(unix_timestamp())
from ads.ads_kpi_base_user;

-- ---------------------------------------------------------------------
-- 辅助结果表：KPI 月度趋势（供前端趋势图与同比分析使用）
-- ---------------------------------------------------------------------
drop table if exists ads.ads_kpi_month_user;
create table ads.ads_kpi_month_user stored as orc as
select month,
       count(*)                                   as user_cnt,
       sum(case when freq >= 2 then 1 else 0 end)  as repeat_user
from (
    select substr(order_date, 1, 7) as month, user_id, count(distinct order_id) as freq
    from dwd.dwd_order_norm
    where order_status in ('已完成', '已支付') and pay_amount is not null
    group by substr(order_date, 1, 7), user_id
) t
group by month;

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
       round(coalesce(u.repeat_user / u.user_cnt * 100, 0), 2) as repurchase_rate
from dws.dws_sales_month m
left join ads.ads_kpi_month_user u on m.month = u.month;

-- ---------------------------------------------------------------------
-- 验证通过标准
-- ---------------------------------------------------------------------
select * from ads.ads_kpi_summary;
select * from ads.ads_kpi_month order by month;
