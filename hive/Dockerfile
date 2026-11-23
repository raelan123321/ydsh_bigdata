FROM apache/hive:3.1.3

# 基础镜像以 hive 用户运行；COPY 进来的文件属 root，故先切 root 处理目录属主
USER root

# 预建元数据/仓库目录并交给 hive 用户：
# 命名卷首次挂载到已有内容的路径时，会连带继承该目录的属主，避免 Derby 无写权限
RUN mkdir -p /opt/hive/metastore_db /opt/hive/data/warehouse /opt/hive/warehouse \
    && chown -R hive:hive /opt/hive/metastore_db /opt/hive/data/warehouse /opt/hive/warehouse

# 幂等启动脚本：元数据库已存在时不再重复 initSchema
COPY --chmod=755 entrypoint-idempotent.sh /entrypoint-idempotent.sh

USER hive

ENTRYPOINT ["/entrypoint-idempotent.sh"]
