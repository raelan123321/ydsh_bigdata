-- ============================================================
-- 步骤 8（扩展）：探索性分析补充维度（提交清单要求：品类/区域/门店分布）
-- 依赖：06_load_partition.sql 已完成，dwd.dwd_order 已加载数据
-- ============================================================

-- 一、区域销售分布（关联用户维度表的省份）
select u.province, sum(o.pay_amount) as sales,
       count(distinct o.order_id) as orders
from dwd.dwd_order o
join dwd.dim_user u on o.user_id = u.user_id
group by u.province
order by sales desc;

-- 二、门店销售分布（关联 ODS 门店表取门店名称）
select s.store_name, sum(o.pay_amount) as sales,
       count(distinct o.order_id) as orders
from dwd.dwd_order o
join ydsh_ods.ods_store s on o.store_id = s.store_id
group by s.store_name
order by sales desc;

-- 三、窗口函数：用户累计消费（按时间递增累加，任务书子任务7要求）
select user_id, order_date, pay_amount,
       sum(pay_amount) over (partition by user_id order by order_date) as cum_amount,
       row_number() over (partition by user_id order by pay_amount desc) as spend_rank
from dwd.dwd_order;

-- 验证通过标准：能输出省份/门店维度的销售额排名，以及每个用户的累计消费序列
