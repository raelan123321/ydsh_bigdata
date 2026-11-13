-- =====================================================================
-- 第3周 子任务1 前置：DWD 层补强
-- 1) dim_store    门店维度表（第2周缺失，ADS 门店/区域分析、NL2SQL 均依赖）
-- 2) dwd_order_item 订单明细清洗表（品类分析的数据来源）
-- 3) dwd_order_norm 订单事实表标准化视图表（状态/渠道枚举标准化）
--
-- 背景：第2周 dwd.dwd_order 只做了去重、金额置空与时间戳合并，
--       order_status / channel 仍保留源系统原样写法
--       （状态 12 种：已完成/完成/已支付/已付款/待支付/已取消/cancelled/退款中/1/2/3/4，
--         渠道 6 种：APP/app/门店/小程序/PC官网/pc），
--       直接用于 KPI 会导致口径错误，故在 DWD 层补齐标准化。
-- =====================================================================

create database if not exists dwd location '/opt/hive/warehouse/dwd';

-- ---------------------------------------------------------------------
-- 1) 门店维度表
-- ---------------------------------------------------------------------
drop table if exists dwd.dim_store;
create table dwd.dim_store (
  store_id   string comment '门店ID',
  store_name string comment '门店名称',
  province   string comment '省份',
  city       string comment '城市',
  district   string comment '区县',
  address    string comment '详细地址',
  open_date  string comment '开业日期',
  area       int    comment '营业面积(㎡)',
  manager    string comment '店长'
) stored as orc;

insert overwrite table dwd.dim_store
select store_id,
       trim(store_name),
       trim(province),
       trim(city),
       trim(district),
       trim(address),
       open_date,
       area,
       trim(manager)
from ydsh_ods.ods_store;

-- ---------------------------------------------------------------------
-- 2) 订单明细清洗表
--    异常：quantity 出现 0 / -2 / 99；unit_price 出现负数
--    口径：数量限定 1~20，单价 > 0，折扣率 0~1，仅保留已落事实表的订单（天然去重）
--    item_amount = quantity * unit_price * (1 - discount)
-- ---------------------------------------------------------------------
drop table if exists dwd.dwd_order_item;
create table dwd.dwd_order_item (
  item_id     string comment '明细ID',
  order_id    string comment '订单ID',
  product_id  string comment '商品ID',
  quantity    int    comment '数量',
  unit_price  double comment '单价',
  discount    double comment '折扣率',
  item_amount double comment '明细金额',
  order_date  string comment '订单日期(冗余,便于按天汇总)'
) stored as orc;

insert overwrite table dwd.dwd_order_item
select i.item_id,
       i.order_id,
       i.product_id,
       i.quantity,
       i.unit_price,
       i.discount,
       round(i.quantity * i.unit_price * (1 - i.discount), 2) as item_amount,
       o.order_date
from ydsh_ods.ods_order_item i
join dwd.dwd_order o on i.order_id = o.order_id
where i.quantity between 1 and 20
  and i.unit_price > 0
  and i.unit_price <= 100000
  and i.discount between 0 and 1;

-- ---------------------------------------------------------------------
-- 3) 订单事实表标准化
--    状态映射：文本别名归一；4 个纯数字码（1/2/3/4）无法从数据本身推断语义
--              （各码金额分布与业务状态无相关性，见 07_eda 侦察），
--              统一归入 '其他'，KPI 计算时排除，占总量 5%
--    渠道映射：APP/app -> APP；PC官网/pc -> PC官网；门店、小程序保持
-- ---------------------------------------------------------------------
drop table if exists dwd.dwd_order_norm;
create table dwd.dwd_order_norm (
  order_id        string,
  user_id         string,
  store_id        string,
  order_timestamp string,
  pay_amount      double,
  discount_amount double,
  raw_status      string comment '源系统原始状态',
  order_status    string comment '标准化状态',
  raw_channel     string comment '源系统原始渠道',
  channel         string comment '标准化渠道',
  order_date      string
) stored as orc;

insert overwrite table dwd.dwd_order_norm
select order_id, user_id, store_id, order_timestamp, pay_amount, discount_amount,
       order_status as raw_status,
       case when order_status in ('已完成', '完成')        then '已完成'
            when order_status in ('已支付', '已付款')      then '已支付'
            when order_status = '待支付'                  then '待支付'
            when order_status in ('已取消', 'cancelled')   then '已取消'
            when order_status = '退款中'                  then '退款中'
            else '其他' end as order_status,
       channel as raw_channel,
       case when upper(trim(channel)) in ('APP')          then 'APP'
            when upper(trim(channel)) in ('PC官网', 'PC')  then 'PC官网'
            when trim(channel) = '门店'                   then '门店'
            when trim(channel) = '小程序'                  then '小程序'
            else '其他' end as channel,
       order_date
from dwd.dwd_order;

-- ---------------------------------------------------------------------
-- 验证通过标准
-- ---------------------------------------------------------------------
-- 门店维度 60 行，无空省份
select 'dim_store' as tbl, count(*) as cnt from dwd.dim_store
union all select 'order_item', count(*) from dwd.dwd_order_item
union all select 'order_norm', count(*) from dwd.dwd_order_norm;

-- 标准化后状态应只剩 6 个值，渠道只剩 5 个值
select order_status, count(*) as cnt from dwd.dwd_order_norm group by order_status order by cnt desc;
select channel, count(*) as cnt from dwd.dwd_order_norm group by channel order by cnt desc;

-- 明细清洗后不应再出现异常数量/单价
select count(*) as dirty_item_left from dwd.dwd_order_item
where quantity not between 1 and 20 or unit_price <= 0 or discount not between 0 and 1;
