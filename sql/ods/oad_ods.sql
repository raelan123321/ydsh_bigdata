use ydsh_ods;

-- ods_user 预期1000行
load data local inpath '/data/ods_user.csv' into table ydsh_ods.ods_user;
select count(*) as ods_user_count from ydsh_ods.ods_user;

-- ods_product 预期600行
load data local inpath '/data/ods_product.csv' into table ydsh_ods.ods_product;
select count(*) as ods_product_count from ydsh_ods.ods_product;

-- ods_store 预期60行
load data local inpath '/data/ods_store.csv' into table ydsh_ods.ods_store;
select count(*) as ods_store_count from ydsh_ods.ods_store;

-- ods_order 预期15600行
load data local inpath '/data/ods_order.csv' into table ydsh_ods.ods_order;
select count(*) as ods_order_count from ydsh_ods.ods_order;

-- ods_order_item 预期37549行
load data local inpath '/data/ods_order_item.csv' into table ydsh_ods.ods_order_item;
select count(*) as ods_order_item_count from ydsh_ods.ods_order_item;

-- ods_user_behavior 预期60000行
load data local inpath '/data/ods_user_behavior.csv' into table ydsh_ods.ods_user_behavior;
select count(*) as ods_user_behavior_count from ydsh_ods.ods_user_behavior;
