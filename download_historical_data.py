import yfinance as yf
import pandas as pd
import os
from datetime import datetime

TICKERS = {
    '7203.T': 'トヨタ自動車', '6758.T': 'ソニーグループ', '9984.T': 'ソフトバンクグループ',
    '9432.T': '日本電信電話', '8306.T': '三菱UFJFG', '6861.T': 'キーエンス',
    '6098.T': 'リクルートHD', '4063.T': '信越化学工業', '8035.T': '東京エレクトロン',
    '7974.T': '任天堂', '8001.T': '伊藤忠商事', '7267.T': 'ホンダ',
    '8316.T': '三井住友FG', '6902.T': 'デンソー', '4502.T': '武田薬品工業',
    '6954.T': 'ファナック', '6501.T': '日立製作所', '8411.T': 'みずほFG',
    '6367.T': 'ダイキン工業', '4568.T': '第一三共', '8031.T': '三井物産',
    '6594.T': 'ニデック', '3382.T': 'セブン＆アイ・HD', '6702.T': '富士通',
    '8058.T': '三菱商事', '2914.T': '日本たばこ産業', '9433.T': 'KDDI',
    '7741.T': 'HOYA', '6981.T': '村田製作所', '4519.T': '中外製薬',
    '6920.T': 'レーザーテック', '7182.T': 'ゆうちょ銀行', '9983.T': 'ファーストリテイリング',
    '4661.T': 'オリエンタルランド', '6503.T': '三菱電機', '4523.T': 'エーザイ',
    '8766.T': '東京海上HD', '6752.T': 'パナソニックHD', '4543.T': 'テルモ',
    '4005.T': '住友化学', '6146.T': 'ディスコ', '4901.T': '富士フイルムHD',
    '7269.T': 'スズキ', '5108.T': 'ブリヂストン', '8053.T': '住友商事',
    '9022.T': 'JR東海', '8002.T': '丸紅', '4507.T': '塩野義製薬',
    '8591.T': 'オリックス', '7751.T': 'キヤノン', '6723.T': 'ルネサスエレクトロニクス',
    '9020.T': 'JR東日本', '8725.T': 'MS&AD', '4911.T': '資生堂',
    '1925.T': '大和ハウス工業', '4528.T': '小野薬品工業', '7011.T': '三菱重工業',
    '8802.T': '三菱地所', '6301.T': '小松製作所', '8801.T': '三井不動産',
    '6762.T': 'TDK', '9735.T': 'セコム', '7201.T': '日産自動車',
    '2502.T': 'アサヒグループHD', '5401.T': '日本製鉄', '2802.T': '味の素',
    '9434.T': 'ソフトバンク', '4307.T': '野村総合研究所', '4578.T': '大塚HD',
    '1928.T': '積水ハウス', '8604.T': '野村HD', '6273.T': 'SMC',
    '4452.T': '花王', '4689.T': 'LINEヤフー', '8630.T': 'SOMPOHD',
    '3407.T': '旭化成', '6971.T': '京セラ', '6869.T': 'シスメックス',
    '9021.T': 'JR西日本', '3402.T': '東レ', '7270.T': 'SUBARU',
    '6701.T': 'NEC', '5802.T': '住友電気工業', '2503.T': 'キリンHD',
    '4188.T': '三菱ケミカルG', '5020.T': 'ENEOS', '9101.T': '日本郵船',
    '9104.T': '商船三井', '9107.T': '川崎汽船', '4503.T': 'アステラス製薬',
    '6645.T': 'オムロン', '7202.T': 'いすゞ自動車', '8308.T': 'りそなHD',
    '8309.T': '三井住友トラストHD', '9202.T': 'ANA HD', '9201.T': '日本航空',
    '7733.T': 'オリンパス', '4385.T': 'メルカリ', '2413.T': 'エムスリー',
    '6857.T': 'アドバンテスト'
}

# 過去10年分をローカルに落とすためのスクリプト
# これによりアプリ起動時の yfinance アクセス負荷が激減し、スプレッドシートへの依存も最小限で済む

DATA_FILE = "stock_historical.csv"

def download_historical():
    print("Downloading 10 years of historical data for 100 tickers...")
    all_data = []
    
    # yfinance は一括DLすると列名がMultiIndexになるので展開
    tickers = list(TICKERS.keys())
    # 2016-01-01 -> 2026-03-31 までの過去データ
    # ユーザーリクエストに合わせて 2026-03-31 固定とするため end="2026-04-01"
    df = yf.download(tickers, period="10y", end="2026-04-01", group_by="ticker", auto_adjust=False)
    
    for ticker in tickers:
        try:
            if ticker in df.columns.get_level_values(0):
                single_df = df[ticker].copy()
            else:
                single_df = df.copy() # 要素が1つの場合など
            
            single_df = single_df.dropna(subset=['Close'])
            if single_df.empty:
                continue
                
            single_df['Ticker'] = ticker
            single_df.reset_index(inplace=True) # Date column になる
            all_data.append(single_df[['Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume']])
            
        except Exception as e:
            print(f"Error extracting {ticker}: {e}")
            
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        # Date順、Ticker順にソートして保存
        final_df = final_df.sort_values(by=['Date', 'Ticker'])
        final_df.to_csv(DATA_FILE, index=False)
        print(f"Successfully saved {len(final_df)} rows to {DATA_FILE}")
    else:
        print("No data collected.")

if __name__ == "__main__":
    download_historical()
