-- ===================== 步骤8：缺失值处理 =====================
-- 需求说明：
-- 1.年龄：null、负数、大于120，使用合法年龄均值填充（均值：41.23427331887202）
-- 2.邮箱：缺失保留，标记为'未知'
-- 3.上架日期：缺失，补默认日期'2020-01-01'

-- 创建DWD层数据库，指定路径解决权限问题
create database if not exists ydsh_dwd
location '/opt/hive/ydsh_dwd';

-- 创建DWD清洗用户表
create table if not exists ydsh_dwd.dwd_user(
user_id string comment '用户编号',
age int comment '年龄，已清洗：空值、异常值用均值填充',
email string comment '邮箱，缺失标记为未知',
shelf_date string comment '上架日期，缺失补默认日期'
) comment 'DWD层-清洗后用户表'
row format delimited fields terminated by ',';

-- 清洗数据写入DWD表
insert overwrite table ydsh_dwd.dwd_user
select
    user_id,
    case when age is null or age < 0 or age > 120 then cast(41.23 as int) else age end as age,
    case when email is null or email = '' then '未知' else email end as email,
    '2020-01-01' as shelf_date
from ydsh_ods.ods_user;

-- 校验SQL：验证清洗结果，查询无返回数据就代表age清洗合格
select * from ydsh_dwd.dwd_user where age is null or age <0 or age >120;
