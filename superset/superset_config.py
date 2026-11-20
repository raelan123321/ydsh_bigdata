# Superset 自动化配置（仅演示环境）：关闭 CSRF 以支持 REST API 一键初始化
# 生产环境应删除本文件，保持 CSRF 开启并走登录会话
WTF_CSRF_ENABLED = False
WTF_CSRF_EXEMPT_LIST = ["*"]
