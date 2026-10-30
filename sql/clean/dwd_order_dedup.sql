-- ===================== 步骤9：重复值检测与去重 =====================
-- 需求说明（依据《数据质量预评估表》）：
-- ods_order 中存在 order_id 主键重复（主键重复但字段不同），
-- 与整行重复不同，需用 ROW_NUMBER() 窗口函数按业务规则保留一条。
-- 保留策略：按 order_date、order_time 升序，保留最早下单的一条记录。

-- 1. 去重前行数（预期 15600）
select count(*) as before_cnt from ydsh_ods.ods_order;

-- 2. 主键重复统计（重复的 order_id 组数）
select count(*) as dup_groups
from (
    select order_id
    from ydsh_ods.ods_order
    group by order_id
    having count(*) > 1
) t;

-- 3. 去重：创建 DWD 层订单表（ydsh_dwd 库已由缺失值清洗脚本创建）
create table if not exists ydsh_dwd.dwd_order as
select order_id, user_id, store_id, order_date, order_time,
       pay_amount, discount_amount, pay_type, order_status, channel
from (
    select *,
           row_number() over (
               partition by order_id
               order by order_date asc, order_time asc
           ) as rn
    from ydsh_ods.ods_order
) t
where rn = 1;

-- 4. 去重后校验
-- 4.1 行数应等于源表 distinct order_id 数量（15600 - 去除的重复行）
select count(*) as after_cnt from ydsh_dwd.dwd_order;
select count(distinct order_id) as expect_cnt from ydsh_ods.ods_order;

-- 4.2 order_id 应不再重复（查询无返回数据即合格）
select order_id
from ydsh_dwd.dwd_order
group by order_id
having count(*) > 1;
