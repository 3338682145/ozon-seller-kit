-- ClickHouse facts: immutable observations, ReplacingMergeTree dedupe by version.
-- Query dedup with argMax(*,row_version) or FINAL; eventual dedup is NOT instant.
CREATE DATABASE IF NOT EXISTS default;

CREATE TABLE IF NOT EXISTS fact_product_daily (
 record_key String,
 source LowCardinality(String),
 observed_at DateTime64(3, 'UTC'),
 calculated_at DateTime64(3, 'UTC'),
 data_type LowCardinality(String),
 dataset_version LowCardinality(String),
 algorithm_version LowCardinality(String),
 ozon_id String,
 keyword String,
 position Nullable(Int32),
 is_advert Nullable(Bool),
 price_rub Nullable(Decimal(18,4)),
 gross_units Nullable(Decimal(18,4)),
 gmv_rub Nullable(Decimal(22,4)),
 net_units_est Nullable(Decimal(18,4)),
 net_gmv_est Nullable(Decimal(22,4)),
 metric_value Nullable(Decimal(18,4)),
 payload String,
 row_version UInt64 DEFAULT toUnixTimestamp64Milli(calculated_at)
) ENGINE = ReplacingMergeTree(row_version)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (source, dataset_version, record_key)
TTL observed_at + INTERVAL 730 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fact_price_history (
 record_key String,
 source LowCardinality(String),
 observed_at DateTime64(3, 'UTC'),
 calculated_at DateTime64(3, 'UTC'),
 data_type LowCardinality(String),
 dataset_version LowCardinality(String),
 algorithm_version LowCardinality(String),
 ozon_id String,
 keyword String,
 position Nullable(Int32),
 is_advert Nullable(Bool),
 price_rub Nullable(Decimal(18,4)),
 gross_units Nullable(Decimal(18,4)),
 gmv_rub Nullable(Decimal(22,4)),
 net_units_est Nullable(Decimal(18,4)),
 net_gmv_est Nullable(Decimal(22,4)),
 metric_value Nullable(Decimal(18,4)),
 payload String,
 row_version UInt64 DEFAULT toUnixTimestamp64Milli(calculated_at)
) ENGINE = ReplacingMergeTree(row_version)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (source, dataset_version, record_key)
TTL observed_at + INTERVAL 730 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fact_sales_daily (
 record_key String,
 source LowCardinality(String),
 observed_at DateTime64(3, 'UTC'),
 calculated_at DateTime64(3, 'UTC'),
 data_type LowCardinality(String),
 dataset_version LowCardinality(String),
 algorithm_version LowCardinality(String),
 ozon_id String,
 keyword String,
 position Nullable(Int32),
 is_advert Nullable(Bool),
 price_rub Nullable(Decimal(18,4)),
 gross_units Nullable(Decimal(18,4)),
 gmv_rub Nullable(Decimal(22,4)),
 net_units_est Nullable(Decimal(18,4)),
 net_gmv_est Nullable(Decimal(22,4)),
 metric_value Nullable(Decimal(18,4)),
 payload String,
 row_version UInt64 DEFAULT toUnixTimestamp64Milli(calculated_at)
) ENGINE = ReplacingMergeTree(row_version)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (source, dataset_version, record_key)
TTL observed_at + INTERVAL 730 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fact_inventory_history (
 record_key String,
 source LowCardinality(String),
 observed_at DateTime64(3, 'UTC'),
 calculated_at DateTime64(3, 'UTC'),
 data_type LowCardinality(String),
 dataset_version LowCardinality(String),
 algorithm_version LowCardinality(String),
 ozon_id String,
 keyword String,
 position Nullable(Int32),
 is_advert Nullable(Bool),
 price_rub Nullable(Decimal(18,4)),
 gross_units Nullable(Decimal(18,4)),
 gmv_rub Nullable(Decimal(22,4)),
 net_units_est Nullable(Decimal(18,4)),
 net_gmv_est Nullable(Decimal(22,4)),
 metric_value Nullable(Decimal(18,4)),
 payload String,
 row_version UInt64 DEFAULT toUnixTimestamp64Milli(calculated_at)
) ENGINE = ReplacingMergeTree(row_version)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (source, dataset_version, record_key)
TTL observed_at + INTERVAL 730 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fact_keyword_daily (
 record_key String,
 source LowCardinality(String),
 observed_at DateTime64(3, 'UTC'),
 calculated_at DateTime64(3, 'UTC'),
 data_type LowCardinality(String),
 dataset_version LowCardinality(String),
 algorithm_version LowCardinality(String),
 ozon_id String,
 keyword String,
 position Nullable(Int32),
 is_advert Nullable(Bool),
 price_rub Nullable(Decimal(18,4)),
 gross_units Nullable(Decimal(18,4)),
 gmv_rub Nullable(Decimal(22,4)),
 net_units_est Nullable(Decimal(18,4)),
 net_gmv_est Nullable(Decimal(22,4)),
 metric_value Nullable(Decimal(18,4)),
 payload String,
 row_version UInt64 DEFAULT toUnixTimestamp64Milli(calculated_at)
) ENGINE = ReplacingMergeTree(row_version)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (source, dataset_version, record_key)
TTL observed_at + INTERVAL 730 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fact_serp_observation (
 record_key String,
 source LowCardinality(String),
 observed_at DateTime64(3, 'UTC'),
 calculated_at DateTime64(3, 'UTC'),
 data_type LowCardinality(String),
 dataset_version LowCardinality(String),
 algorithm_version LowCardinality(String),
 ozon_id String,
 keyword String,
 position Nullable(Int32),
 is_advert Nullable(Bool),
 price_rub Nullable(Decimal(18,4)),
 gross_units Nullable(Decimal(18,4)),
 gmv_rub Nullable(Decimal(22,4)),
 net_units_est Nullable(Decimal(18,4)),
 net_gmv_est Nullable(Decimal(22,4)),
 metric_value Nullable(Decimal(18,4)),
 payload String,
 row_version UInt64 DEFAULT toUnixTimestamp64Milli(calculated_at)
) ENGINE = ReplacingMergeTree(row_version)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (source, dataset_version, record_key)
TTL observed_at + INTERVAL 730 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fact_keyword_sku_daily (
 record_key String,
 source LowCardinality(String),
 observed_at DateTime64(3, 'UTC'),
 calculated_at DateTime64(3, 'UTC'),
 data_type LowCardinality(String),
 dataset_version LowCardinality(String),
 algorithm_version LowCardinality(String),
 ozon_id String,
 keyword String,
 position Nullable(Int32),
 is_advert Nullable(Bool),
 price_rub Nullable(Decimal(18,4)),
 gross_units Nullable(Decimal(18,4)),
 gmv_rub Nullable(Decimal(22,4)),
 net_units_est Nullable(Decimal(18,4)),
 net_gmv_est Nullable(Decimal(22,4)),
 metric_value Nullable(Decimal(18,4)),
 payload String,
 row_version UInt64 DEFAULT toUnixTimestamp64Milli(calculated_at)
) ENGINE = ReplacingMergeTree(row_version)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (source, dataset_version, record_key)
TTL observed_at + INTERVAL 730 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fact_reviews_daily (
 record_key String,
 source LowCardinality(String),
 observed_at DateTime64(3, 'UTC'),
 calculated_at DateTime64(3, 'UTC'),
 data_type LowCardinality(String),
 dataset_version LowCardinality(String),
 algorithm_version LowCardinality(String),
 ozon_id String,
 keyword String,
 position Nullable(Int32),
 is_advert Nullable(Bool),
 price_rub Nullable(Decimal(18,4)),
 gross_units Nullable(Decimal(18,4)),
 gmv_rub Nullable(Decimal(22,4)),
 net_units_est Nullable(Decimal(18,4)),
 net_gmv_est Nullable(Decimal(22,4)),
 metric_value Nullable(Decimal(18,4)),
 payload String,
 row_version UInt64 DEFAULT toUnixTimestamp64Milli(calculated_at)
) ENGINE = ReplacingMergeTree(row_version)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (source, dataset_version, record_key)
TTL observed_at + INTERVAL 730 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fact_category_daily (
 record_key String,
 source LowCardinality(String),
 observed_at DateTime64(3, 'UTC'),
 calculated_at DateTime64(3, 'UTC'),
 data_type LowCardinality(String),
 dataset_version LowCardinality(String),
 algorithm_version LowCardinality(String),
 ozon_id String,
 keyword String,
 position Nullable(Int32),
 is_advert Nullable(Bool),
 price_rub Nullable(Decimal(18,4)),
 gross_units Nullable(Decimal(18,4)),
 gmv_rub Nullable(Decimal(22,4)),
 net_units_est Nullable(Decimal(18,4)),
 net_gmv_est Nullable(Decimal(22,4)),
 metric_value Nullable(Decimal(18,4)),
 payload String,
 row_version UInt64 DEFAULT toUnixTimestamp64Milli(calculated_at)
) ENGINE = ReplacingMergeTree(row_version)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (source, dataset_version, record_key)
TTL observed_at + INTERVAL 730 DAY
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS fact_collection_metrics (
 record_key String,
 source LowCardinality(String),
 observed_at DateTime64(3, 'UTC'),
 calculated_at DateTime64(3, 'UTC'),
 data_type LowCardinality(String),
 dataset_version LowCardinality(String),
 algorithm_version LowCardinality(String),
 ozon_id String,
 keyword String,
 position Nullable(Int32),
 is_advert Nullable(Bool),
 price_rub Nullable(Decimal(18,4)),
 gross_units Nullable(Decimal(18,4)),
 gmv_rub Nullable(Decimal(22,4)),
 net_units_est Nullable(Decimal(18,4)),
 net_gmv_est Nullable(Decimal(22,4)),
 metric_value Nullable(Decimal(18,4)),
 payload String,
 row_version UInt64 DEFAULT toUnixTimestamp64Milli(calculated_at)
) ENGINE = ReplacingMergeTree(row_version)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (source, dataset_version, record_key)
TTL observed_at + INTERVAL 90 DAY
SETTINGS index_granularity = 8192;
