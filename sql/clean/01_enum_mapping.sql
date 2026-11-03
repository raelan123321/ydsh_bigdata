-- ============================================================
-- 步骤 1：枚举字段标准化（手册 3.1）
-- 目标：将 gender、member_level、order_status 等枚举字段统一为规范中文取值
-- ============================================================

-- 扫描取值分布
select gender, count(*) from ydsh_ods.ods_user group by gender;
select order_status, count(*) from ydsh_ods.ods_order group by order_status;
select pay_type, count(*) from ydsh_ods.ods_order group by pay_type;

-- 统一映射
select user_id, user_name,
  case when gender in ('男','M','male','Male') then '男'
       when gender in ('女','F','female','Female') then '女'
       else '未知' end as gender,
  case when member_level in ('金卡会员','gold','Gold') then '金卡会员'
       when member_level in ('银卡会员','silver','Silver') then '银卡会员'
       else '普通会员' end as member_level
from ydsh_ods.ods_user;

-- 验证通过标准：清洗后各枚举字段的 distinct 取值仅剩规范值
