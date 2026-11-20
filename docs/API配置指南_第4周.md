# 第 4 周 API 配置指南（密钥安全管理）

> 对应任务书子任务 4~5：API 密钥与数据库密码通过环境变量注入，避免硬编码

## 一、密钥清单

| 变量 | 用途 | 默认值 | 风险等级 |
|------|------|--------|----------|
| MYSQL_ROOT_PASSWORD | metastore 元数据库 root 密码 | root（演示环境） | 高 |
| HIVE_DB_PASSWORD | Hive→MySQL metastore 密码 | hive | 高 |
| SUPERSET_SECRET_KEY | Superset 会话/加密密钥 | please_change_this_secret | 高 |
| CLICKHOUSE_PASSWORD | ClickHouse 密码 | clickhouse | 中 |
| LLM_API_KEY | DeepSeek/Qwen 等 OpenAI 协议 Key | （空=规则兜底） | 高 |
| LLM_BASE_URL / LLM_MODEL | LLM 服务地址与模型 | api.deepseek.com / deepseek-chat | 低 |

## 二、注入方式（compose 只写 `${VAR}` 引用）

- 真实值只存本地 `.env`（已被 .gitignore 排除，永不入库）
- 模板入库：`.env.example`（所有人复制后填写）
- 生成强随机 Superset 密钥：
  `python -c "import secrets; print(secrets.token_hex(32))"`

## 三、密钥管理原则

1. **最小权限**：Superset 连 Hive 使用只读账号；业务库不用 root（演示环境除外，生产必须建专用账号）
2. **不入库**：`.gitignore` 中排除 `.env`、`*.env`、`**/.env`；提交前 `git status` 复查
3. **轮换**：LLM_API_KEY 每 90 天轮换；泄露立即在服务商控制台吊销重发
4. **日志脱敏**：应用日志不打印完整连接串，报错信息剔除密码段
5. **容器内传递**：密钥只经 `environment` 环境变量进入容器，不写进镜像层

## 四、各服务连接串参考

| 服务 | 连接串 |
|------|--------|
| Superset → Hive | `hive://hive@hive-server:10000/default` |
| Superset → MySQL | `mysql+pymysql://root:${MYSQL_ROOT_PASSWORD}@mysql:3306/ydsh_ads` |
| Streamlit → Hive | 环境变量 `HIVE_HOST=hive-server`、`HIVE_PORT=10000`（NL2SQL 读取） |
| NL2SQL → LLM | `LLM_API_KEY` + `LLM_BASE_URL`（OpenAI 兼容协议） |

> ⚠️ 注意：容器之间必须用**服务名**（hive-server / mysql），不能用 localhost。

## 五、验证清单

- [ ] `git ls-files | grep -i env` 只出现 `.env.example`
- [ ] `docker exec app env | grep LLM_API_KEY` 有值而镜像内无明文文件
- [ ] Superset SECRET_KEY 已替换为随机串
- [ ] 大屏 API 不需要任何密钥（纯只读 JSON）
