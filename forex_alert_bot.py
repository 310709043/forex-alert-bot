#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外匯盯盤提醒機器人
- 抓外匯小時線 (yfinance)
- 算 EMA(快/慢) 交叉 + ATR 動態止損, 風報比 1:2
- 出訊號就推 Telegram (進場/止損/止盈)
- 純提醒, 不自動下單

憑證來源:
  優先讀環境變數 TG_TOKEN / TG_CHAT (GitHub Actions 用 Secrets)
  否則讀同目錄 config.json (本機用)

用法:
  python3 forex_alert_bot.py --once   # 檢查一次 (排程用)
  python3 forex_alert_bot.py          # 常駐迴圈
  python3 forex_alert_bot.py --test   # 發測試訊息
"""
import json, os, time, argparse, datetime as dt
import requests

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, "state.json")

def load_cfg():
    path = os.path.join(BASE, "config.json")
    cfg = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    cfg.setdefault("symbols", ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "GC=F"])
    cfg.setdefault("interval", "1h")
    cfg.setdefault("fast_ema", 20); cfg.setdefault("slow_ema", 50)
    cfg.setdefault("atr_period", 14); cfg.setdefault("atr_mult_sl", 1.5)
    cfg.setdefault("risk_reward", 2.0); cfg.setdefault("check_every_min", 15)
    # 環境變數優先 (Actions Secrets)
    cfg["telegram_bot_token"] = os.environ.get("TG_TOKEN", cfg.get("telegram_bot_token", ""))
    cfg["telegram_chat_id"]   = os.environ.get("TG_CHAT",  cfg.get("telegram_chat_id", ""))
    return cfg

CFG = load_cfg()

NAME = {
    "EURUSD=X": "歐元/美元 EURUSD",
    "GBPUSD=X": "英鎊/美元 GBPUSD",
    "USDJPY=X": "美元/日圓 USDJPY",
    "GC=F": "黃金 Gold",
}

# ---------------- Telegram ----------------
def tg_send(text):
    url = "https://api.telegram.org/bot%s/sendMessage" % CFG["telegram_bot_token"]
    try:
        r = requests.post(url, data={
            "chat_id": CFG["telegram_chat_id"], "text": text, "parse_mode": "HTML",
        }, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print("Telegram 發送失敗:", e); return False

# ---------------- 狀態 ----------------
def load_state():
    if os.path.exists(STATE_PATH):
        try: return json.load(open(STATE_PATH, encoding="utf-8"))
        except Exception: return {}
    return {}

def save_state(s):
    json.dump(s, open(STATE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# ---------------- 指標 ----------------
def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def atr(df, n):
    import pandas as pd
    h, l, c = df["High"], df["Low"], df["Close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def digits_for(sym):
    return 2 if sym in ("USDJPY=X", "GC=F") else 5

# ---------------- 訊號 ----------------
def check_symbol(sym, state):
    import yfinance as yf, pandas as pd
    df = yf.download(sym, period="1mo", interval=CFG["interval"],
                     progress=False, auto_adjust=False)
    if df is None or len(df) < CFG["slow_ema"] + CFG["atr_period"] + 5:
        print(f"[{sym}] 資料不足, 跳過"); return
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df["ema_f"] = ema(df["Close"], CFG["fast_ema"])
    df["ema_s"] = ema(df["Close"], CFG["slow_ema"])
    df["atr"]   = atr(df, CFG["atr_period"])

    closed = df.iloc[:-1]                      # 丟掉未收盤的當前 K 棒
    last, prev = closed.iloc[-1], closed.iloc[-2]

    direction = 0
    if prev["ema_f"] <= prev["ema_s"] and last["ema_f"] > last["ema_s"]:
        direction = 1
    elif prev["ema_f"] >= prev["ema_s"] and last["ema_f"] < last["ema_s"]:
        direction = -1
    if direction == 0: return

    bar_id = str(closed.index[-1])
    if state.get(sym) == bar_id: return        # 這根 K 棒提醒過了

    d = digits_for(sym); entry = float(last["Close"]); a = float(last["atr"])
    sl_d = a * CFG["atr_mult_sl"]
    if direction > 0:
        sl, tp = entry - sl_d, entry + sl_d * CFG["risk_reward"]; emoji, word = "🟢", "做多 BUY"
    else:
        sl, tp = entry + sl_d, entry - sl_d * CFG["risk_reward"]; emoji, word = "🔴", "做空 SELL"

    msg = (f"{emoji} <b>{word} 訊號</b>\n"
           f"商品：{NAME.get(sym, sym)}（{CFG['interval']}）\n"
           f"進場約：<b>{entry:.{d}f}</b>\n止損：{sl:.{d}f}\n止盈：{tp:.{d}f}\n"
           f"風報比 1:{CFG['risk_reward']:g}｜EMA{CFG['fast_ema']}/{CFG['slow_ema']} 交叉\n"
           f"🕐 {dt.datetime.now(dt.timezone.utc).strftime('%m/%d %H:%M')} UTC\n"
           f"— 手動下單，止損記得掛上 —")
    if tg_send(msg):
        print(f"[{sym}] 已推送 {word} 訊號"); state[sym] = bar_id; save_state(state)

def run_once():
    state = load_state()
    for sym in CFG["symbols"]:
        try: check_symbol(sym, state)
        except Exception as e: print(f"[{sym}] 檢查出錯:", e)
    print(dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S"), "UTC 檢查完成")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    if not CFG["telegram_bot_token"] or not CFG["telegram_chat_id"]:
        print("缺少 Telegram 憑證 (TG_TOKEN / TG_CHAT 或 config.json)"); return

    if args.test:
        ok = tg_send("🔔 盯盤機器人測試：連線正常。")
        print("測試訊息", "已送出 ✅" if ok else "失敗 ❌"); return
    if args.once:
        run_once(); return

    print("盯盤機器人啟動，每", CFG["check_every_min"], "分鐘檢查一次。")
    tg_send("🟩 盯盤機器人已上線：" + "、".join(NAME.get(s, s) for s in CFG["symbols"]))
    while True:
        run_once(); time.sleep(CFG["check_every_min"] * 60)

if __name__ == "__main__":
    main()
