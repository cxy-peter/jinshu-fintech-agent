# features.csv 结构化输入（模拟）

仅用于复现软件流程，数值不代表任何机构。CSV SHA256：009dcad472d1d0d7a89f4a5d26cf48c433d76a8dd640f25590662bd79655e2d8

## 数据行

|name|event|status_filter|dedup_key|window|refresh|synthetic|
|---|---|---|---|---|---|---|
|successful_deposit_count_7d|FiatDeposit|success|transaction_id|7d|T+1|true|
|withdraw_sum_24h|ChainWithdraw|success|transaction_id|24h|realtime|true|