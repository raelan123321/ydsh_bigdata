#!/bin/bash
# Hive 容器幂等启动脚本
# 原生 apache/hive entrypoint 每次启动都无条件执行 schematool -initSchema，
# 元数据库已存在时会抛 "FUNCTION 'NUCLEUS_ASCII' already exists" 并退出 1，
# 导致容器重启即挂（表现为 compose 里 hive-server 反复 Error）。
# 这里改为：仅在元数据库不存在时初始化，之后直接启动服务。
set -x

: ${DB_DRIVER:=derby}

# 命名卷在部分 Docker Desktop 环境下不会继承镜像目录属主（落成 root:root），
# 导致 hive 用户无法写 Derby；以 root 启动时先纠正属主
if [ "$(id -u)" = "0" ]; then
  chown -R hive:hive /opt/hive/metastore_db /opt/hive/data/warehouse /opt/hive/warehouse 2>/dev/null || true
fi

export HIVE_CONF_DIR=$HIVE_HOME/conf
if [ -d "${HIVE_CUSTOM_CONF_DIR:-}" ]; then
  find "${HIVE_CUSTOM_CONF_DIR}" -type f -exec \
    ln -sfn {} "${HIVE_CONF_DIR}"/ \;
  export HADOOP_CONF_DIR=$HIVE_CONF_DIR
  export TEZ_CONF_DIR=$HIVE_CONF_DIR
fi

export HADOOP_CLIENT_OPTS="$HADOOP_CLIENT_OPTS -Xmx1G $SERVICE_OPTS"

# 幂等初始化：Derby 库目录（metastore_db/data/seg0）已存在则跳过
DERBY_DB_DIR="${DERBY_DB_DIR:-${HIVE_HOME}/metastore_db/data}"
if [ ! -d "${DERBY_DB_DIR}/seg0" ]; then
  echo ">>> 首次启动，初始化 Hive 元数据库 (${DB_DRIVER})"
  ${HIVE_HOME}/bin/schematool -dbType ${DB_DRIVER} -initSchema || {
    echo "!!! 元数据库初始化失败"; exit 1; }
else
  echo ">>> 元数据库已存在，跳过初始化"
fi

if [ "${SERVICE_NAME}" == "hiveserver2" ]; then
  export HADOOP_CLASSPATH=$TEZ_HOME/*:$TEZ_HOME/lib/*:$HADOOP_CLASSPATH
elif [ "${SERVICE_NAME}" == "metastore" ]; then
  export METASTORE_PORT=${METASTORE_PORT:-9083}
fi

exec ${HIVE_HOME}/bin/hive --skiphadoopversion --skiphbasecp --service ${SERVICE_NAME}
