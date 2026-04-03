import os
import time
from model_utils import get_stock_data, predict_stock
from sheets_db import save_prediction

TICKERS = {
    '7203.T': 'トヨタ自動車',
    '6758.T': 'ソニーグループ',
    '9984.T': 'ソフトバンクグループ',
    '9432.T': '日本電信電話',
    '8306.T': '三菱UFJFG',
    '6861.T': 'キーエンス',
    '6098.T': 'リクルートHD',
    '4063.T': '信越化学工業',
    '8035.T': '東京エレクトロン',
    '7974.T': '任天堂',
    '8001.T': '伊藤忠商事',
    '7267.T': 'ホンダ',
    '8316.T': '三井住友FG',
    '6902.T': 'デンソー',
    '4502.T': '武田薬品工業',
    '6954.T': 'ファナック',
    '6501.T': '日立製作所',
    '8411.T': 'みずほFG',
    '6367.T': 'ダイキン工業',
    '4568.T': '第一三共'
}

def populate_database():
    print("=== スプレッドシートへの一括インポートを開始します ===")
    total = len(TICKERS)
    
    for i, (ticker, company_name) in enumerate(TICKERS.items()):
        print(f"[{i+1}/{total}] {company_name} ({ticker}) のデータを取得・予測中...")
        try:
            # データ取得
            data = get_stock_data(ticker)
            if data is None or data.empty:
                print(f"  -> ⚠ データ取得失敗: {ticker}")
                continue
                
            # 予測実行
            prediction, confidence, _ = predict_stock(data)
            
            if prediction is None:
                print(f"  -> ⚠ 予測失敗: {confidence}")
                continue
                
            # スプレッドシートに保存
            current_price = data['Close'].iloc[-1]
            success = save_prediction(ticker, company_name, current_price, prediction, confidence)
            
            if success:
                print(f"  -> ✅ 保存完了 (予測: {prediction}, 自信度: {confidence:.1f}%)")
            else:
                print(f"  -> ❌ スプレッドシート保存エラー")
                
            # APIのレート制限（Quotas）対策で少し待機
            time.sleep(1)
            
        except Exception as e:
            print(f"  -> ❌ エラー発生: {e}")
            
    print("=== インポート処理がすべて完了しました！ ===")

if __name__ == "__main__":
    populate_database()
