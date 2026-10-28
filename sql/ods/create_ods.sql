-- 创建ods数据库
create database if not exists ydsh_ods;
use ydsh_ods;

-- ods_user 用户表
create table if not exists ydsh_ods.ods_user (
    user_id string,
    user_name string,
    gender string,
    age int,
    city string,
    province string,
    register_date string,
    member_level string,
    phone string,
    email string
)
row format delimited fields terminated by ','
tblproperties('skip.header.line.count'='1');

-- ods_product 商品表
create table if not exists ydsh_ods.ods_product (
    product_id string,
    product_name string,
    category string,
    price decimal(10,2),
    stock int,
    brand string,
    create_time string
)
row format delimited fields terminated by ','
tblproperties('skip.header.line.count'='1');

-- ods_store 门店表
create table if not exists ydsh_ods.ods_store (
    store_id string,
    store_name string,
    city string,
    province string,
    manager string,
    contact string,
    open_date string
)
row format delimited fields terminated by ','
tblproperties('skip.header.line.count'='1');

-- ods_order 订单表
create table if not exists ydsh_ods.ods_order (
    order_id string,
    user_id string,
    store_id string,
    order_date string,
    order_time string,
    pay_amount decimal(10,2),
    discount_amount decimal(10,2),
    pay_type string,
    order_status string,
    channel string
)
row format delimited fields terminated by ','
tblproperties('skip.header.line.count'='1');

-- ods_order_item 订单明细表
create table if not exists ydsh_ods.ods_order_item (
    item_id string,
    order_id string,
    product_id string,
    buy_num int,
    item_price decimal(10,2),
    subtotal decimal(10,2)
)
row format delimited fields terminated by ','
tblproperties('skip.header.line.count'='1');

-- ods_user_behavior 用户行为表
create table if not exists ydsh_ods.ods_user_behavior (
    behavior_id string,
    user_id string,
    product_id string,
    behavior_type string,
    behavior_time string
)
row format delimited fields terminated by ','
tblproperties('skip.header.line.count'='1');
