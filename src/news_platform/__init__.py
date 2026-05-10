"""News platform package — 與交易機器人 (event_relay) 完全解耦。

- 寫入獨立的 MySQL DB（`NEWSPF_MYSQL_*` 環境變數）
- **禁止** import `event_relay`、不寫入 `t_relay_events`
- 第一階段只爬 TW 社會新聞；之後再擴政治／娛樂／財經，與其他國家頁
"""
