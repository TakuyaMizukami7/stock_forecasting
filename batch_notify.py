import schedule
import time
import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv
from model_utils import get_stock_data, predict_stock

# .envファイルから環境変数を読み込む
load_dotenv()

# 監視対象の銘柄コードリスト
WATCH_TICKERS = ['7203.T', '6758.T', '9984.T']

# LINE API設定
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.getenv("LINE_USER_ID")
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

def send_to_line(message):
    """
    LINE Messaging API を用いて直接メッセージをPUSH送信する。
    """
    if not LINE_ACCESS_TOKEN or not LINE_USER_ID:
        print("エラー: .env に LINE_ACCESS_TOKEN または LINE_USER_ID が設定されていません。")
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    
    payload = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }
    
    try:
        response = requests.post(LINE_API_URL, headers=headers, json=payload)
        
        if response.status_code == 200:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LINE通知送信成功")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LINE通知送信失敗: ステータスコード {response.status_code}, {response.text}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 送信エラー: {e}")

def job():
    print(f"--- 定期実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    messages = ["【今日の株価予測サマリー】"]
    
    for ticker in WATCH_TICKERS:
        print(f"{ticker} のデータを取得中...")
        data = get_stock_data(ticker, period="2y")
        
        if data is None or data.empty:
            messages.append(f"{ticker}: データ取得失敗")
            continue
            
        prediction, _ = predict_stock(data)
        latest_close = data['Close'].iloc[-1]
        
        if prediction == 1:
            trend = "📈 上昇予想 (10%以上)"
        elif prediction == -1:
            trend = "📉 下落予想 (10%以上)"
        else:
            trend = "➡️ ステイ予想"
            
        messages.append(f"■ {ticker}\n現在値: {latest_close:,.1f} 円\n予測: {trend}")
        
    final_message = "\n\n".join(messages)
    send_to_line(final_message)

if __name__ == "__main__":
    # テストのために即座に1回実行
    print("テスト実行を行います...")
    job()
    
    # 毎日12:00に実行する設定
    print("毎日12:00のスケジュールを登録しました。待機します...")
    schedule.every().day.at("12:00").do(job)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

