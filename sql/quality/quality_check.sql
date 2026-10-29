use ydsh_ods;

-- ======================================
-- 1. ods_user 用户表 质量检查
-- ======================================
-- 完整性：手机号空值数量
select count(*) as phone_null_cnt
from ods_user
where phone is null or phone = '';

-- 唯一性：user_id 重复条数
select count(*) as user_id_dup_cnt
from (select user_id from ods_user group by user_id having count(*) > 1) t;

-- 有效性：年龄非法（<=0 或者 >=120）条数
select count(*) as age_err_cnt
from ods_user
where age <= 0 or age >= 120;

-- 及时性：注册时间格式错误条数
select count(*) as register_date_err_cnt
from ods_user
where register_date not regexp '^(\\d{4}/\\d{2}/\\d{2} \\d{2}:\\d{2})$|^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})$';


-- ======================================
-- 2. ods_product 商品表 质量检查
-- ======================================
-- 完整性：商品名称空值
select count(*) as prod_name_null_cnt
from ods_product
where product_name is null or product_name = '';

-- 唯一性：product_id 重复条数
select count(*) as product_id_dup_cnt
from (select product_id from ods_product group by product_id having count(*) > 1) t;

-- 有效性：价格、库存负数条数
select count(*) as price_stock_err_cnt
from ods_product
where price < 0 or stock < 0;

-- 及时性：创建时间格式校验
select count(*) as create_time_err_cnt
from ods_product
where create_time not regexp '^(\\d{4}/\\d{2}/\\d{2} \\d{2}:\\d{2})$|^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})$';


-- ======================================
-- 3. ods_store 门店表 质量检查
-- ======================================
-- 完整性：门店名称空值
select count(*) as store_name_null_cnt
from ods_store
where store_name is null or store_name = '';

-- 唯一性：store_id 重复条数
select count(*) as store_id_dup_cnt
from (select store_id from ods_store group by store_id having count(*) > 1) t;

-- 有效性：城市为空的条数
select count(*) as city_null_cnt
from ods_store
where city is null or city = '';

-- 及时性：开业时间格式校验
select count(*) as open_date_err_cnt
from ods_store
where open_date not regexp '^(\\d{4}/\\d{2}/\\d{2} \\d{2}:\\d{2})$|^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})$';


-- ======================================
-- 4. ods_order 订单表 质量检查
-- ======================================
-- 完整性：支付金额空值
select count(*) as pay_amount_null_cnt
from ods_order
where pay_amount is null;

-- 唯一性：order_id 重复条数
select count(*) as order_id_dup_cnt
from (select order_id from ods_order group by order_id having count(*) > 1) t;

-- 有效性：订单状态为空条数
select count(*) as order_status_null_cnt
from ods_order
where order_status is null or order_status = '';

-- 及时性：订单时间格式校验
select count(*) as order_time_err_cnt
from ods_order
where order_time not regexp '^(\\d{4}/\\d{2}/\\d{2} \\d{2}:\\d{2})$|^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})$';

-- 一致性：无效user_id条数
select count(*) as order_user_err_cnt
from ods_order
where user_id not in (select user_id from ods_user);

-- 一致性：无效store_id条数
select count(*) as order_store_err_cnt
from ods_order
where store_id not in (select store_id from ods_store);


-- ======================================
-- 5. ods_order_item 订单明细表
-- ======================================
-- 完整性：商品ID空值
select count(*) as item_prod_null_cnt
from ods_order_item
where product_id is null or product_id = '';

-- 唯一性：item_id 重复条数
select count(*) as item_id_dup_cnt
from (select item_id from ods_order_item group by item_id having count(*) > 1) t;

-- 有效性：购买数量、单价≤0非法条数
select count(*) as item_num_price_err_cnt
from ods_order_item
where buy_num <= 0 or item_price <= 0;

-- 一致性：无效order_id条数
select count(*) as item_order_err_cnt
from ods_order_item
where order_id not in (select order_id from ods_order);


-- ======================================
-- 6. ods_user_behavior 用户行为表
-- ======================================
-- 完整性：行为类型空值
select count(*) as behavior_type_null_cnt
from ods_user_behavior
where behavior_type is null or behavior_type = '';

-- 唯一性：behavior_id 重复条数
select count(*) as behavior_id_dup_cnt
from (select behavior_id from ods_user_behavior group by behavior_id having count(*) > 1) t;

-- 有效性：行为类型不规范条数（不是4类标准值）
select count(*) as behavior_type_err_cnt
from ods_user_behavior
where lower(behavior_type) not in ('pv','cart','fav','buy','浏览','加购','收藏','购买');

-- 及时性：行为时间格式校验
select count(*) as behavior_time_err_cnt
from ods_user_behavior
where behavior_time not regexp '^(\\d{4}/\\d{2}/\\d{2} \\d{2}:\\d{2})$|^(\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2})$';

-- 一致性：无效user_id条数
select count(*) as beh_user_err_cnt
from ods_user_behavior
where user_id not in (select user_id from ods_user);

-- 一致性：无效product_id条数
select count(*) as beh_prod_err_cnt
from ods_user_behavior
where product_id not in (select product_id from ods_product);
