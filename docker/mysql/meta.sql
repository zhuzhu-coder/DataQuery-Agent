SET NAMES utf8mb4;
CREATE DATABASE meta DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
GRANT ALL PRIVILEGES ON meta.* TO 'data_query_agent'@'%';

USE meta;

DROP TABLE IF EXISTS table_info;
CREATE TABLE table_info
(
    id          VARCHAR(64) PRIMARY KEY COMMENT '表编号',
    name        VARCHAR(128) COMMENT '表名称',
    role        VARCHAR(32) COMMENT '表类型(fact/dim)',
    description TEXT COMMENT '表描述'
);



DROP TABLE IF EXISTS column_info;
CREATE TABLE column_info
(
    id          VARCHAR(64) PRIMARY KEY COMMENT '列编号',
    name        VARCHAR(128) COMMENT '列名称',
    type        VARCHAR(64) COMMENT '数据类型',
    role        VARCHAR(32) COMMENT '列类型(primary_key,foreign_key,measure,dimension)',
    examples    JSON COMMENT '数据示例',
    description TEXT COMMENT '列描述',
    alias       JSON COMMENT '列别名',
    table_id    VARCHAR(64) COMMENT '所属表编号'
);

DROP TABLE IF EXISTS metric_info;
CREATE TABLE metric_info
(
    id               VARCHAR(64) PRIMARY KEY COMMENT '指标编码',
    name             VARCHAR(128) COMMENT '指标名称',
    description      TEXT COMMENT '指标描述',
    relevant_columns JSON COMMENT '关联的列',
    alias            JSON COMMENT '指标别名'
);


DROP TABLE IF EXISTS column_metric;
CREATE TABLE column_metric
(
    column_id VARCHAR(64) COMMENT '列编号',
    metric_id VARCHAR(64) COMMENT '指标编号',
    PRIMARY KEY (column_id, metric_id)
);


DROP TABLE IF EXISTS query_audit_log;
CREATE TABLE query_audit_log
(
    id            VARCHAR(64) PRIMARY KEY COMMENT '审计记录编号',
    request_id    VARCHAR(64) COMMENT '请求编号',
    query         TEXT COMMENT '用户自然语言问题',
    generated_sql TEXT COMMENT '模型生成 SQL',
    final_sql     TEXT COMMENT '安全改写后的最终 SQL',
    status        VARCHAR(32) COMMENT '状态 running/success/failed/rejected',
    error_message TEXT COMMENT '错误信息',
    row_count     INT COMMENT '返回行数',
    duration_ms   INT COMMENT '执行耗时毫秒',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'
);
