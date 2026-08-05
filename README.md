# forex-alert-bot 外匯盯盤提醒機器人

24/5 自動監控外匯，出現訊號就推 Telegram。跑在 GitHub Actions 上，**免費、不用開電腦**。

## 策略
- 商品：EURUSD、GBPUSD、USDJPY、黃金（Gold）
- 訊號：EMA20 / EMA50 交叉（1 小時線）
- 止損：ATR(14) × 1.5 動態計算
- 止盈：風報比 1:2
- **純提醒**，不自動下單；你收到訊息自己下單

## 運作方式
GitHub Actions 每 15 分鐘（週一~週五）跑一次 `forex_alert_bot.py --once`，
偵測到 EMA 交叉就發 Telegram 訊息（進場 / 止損 / 止盈）。
`state.json` 記錄已提醒的 K 棒，避免同一根重複提醒。

## 設定
Telegram 憑證放在 GitHub Secrets（不進版控）：
- `TG_TOKEN`：Telegram Bot Token
- `TG_CHAT`：你的 Chat ID

## 本機測試
```bash
pip install -r requirements.txt
# 本機用 config.json 填 token/chat_id，或用環境變數
python forex_alert_bot.py --test    # 測 Telegram
python forex_alert_bot.py --once    # 檢查一次
python forex_alert_bot.py           # 常駐迴圈
```

## 調整
改 `config.json` 的 `symbols` / EMA 週期 / ATR 倍數 / 風報比即可。
