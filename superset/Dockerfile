FROM apache/superset:3.1.0

USER root

# 安装 Hive（pyhive）与 MySQL 驱动：pure-sasl（纯 Python）替代 sasl，无需编译工具链、无需 apt
# 注意：不能用 pyhive[hive] extra（会拉取需要 C++ 编译的 sasl 包）
RUN pip install --no-cache-dir pyhive==0.7.0 thrift thrift-sasl pure-sasl pymysql \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY superset_config.py /app/superset_config.py
ENV SUPERSET_CONFIG_PATH=/app/superset_config.py

USER superset
