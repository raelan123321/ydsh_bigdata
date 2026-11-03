-- ============================================================
-- 步骤 6（上）：DWD 层维度表（手册 3.6）
-- 目标：构建星型模型的维度表，ORC 存储
-- ============================================================

-- 维度表（示例）
create table dwd.dim_user (
  user_id string, user_name string, gender string, age int,
  city string, province string, member_level string
) stored as orc;

create table dwd.dim_product (
  product_id string, product_name string, category string,
  sub_category string, brand string, price double
) stored as orc;

-- 验证通过标准：事实表含度量字段，维度表含描述属性
