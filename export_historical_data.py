"""
export_historical_data.py
全100社の過去10年分の株価データ＋テクニカル指標を
Google Spreadsheetの各シートに一括インポートするスクリプト。

実行方法:
  python export_historical_data.py          # 全100社を処理
  python export_historical_data.py 7203.T   # 指定銘柄のみ処理
"""
import sys
import time
import os
import pandas as pd
from dotenv import load_dotenv
import gspread

from model_utils import get_stock_data, add_technical_indicators
from sheets_db import get_client

load_dotenv()

# ========== 対象100社リスト (app.py と同一) ==========
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


def get_spreadsheet():
    """Spreadsheetオブジェクトを返す"""
    client = get_client()
    if not client:
        raise RuntimeError("Google APIへの接続設定が見つかりません。credentials.json または .env を確認してください。")

    sheet_id_or_url = os.getenv("SPREADSHEET_ID")
    if not sheet_id_or_url:
        raise RuntimeError("SPREADSHEET_ID が .env に設定されていません。")

    if "spreadsheets.google.com" in sheet_id_or_url:
        return client.open_by_url(sheet_id_or_url)
    else:
        return client.open_by_key(sheet_id_or_url)


def export_one(spreadsheet, ticker: str, company_name: str):
    """1社分のデータをSpreadsheetの専用シートにインポートする"""
    print(f"\n[{company_name} ({ticker})] 処理開始...")

    # 1. データ取得とテクニカル指標の計算
    data = get_stock_data(ticker, period="10y")
    if data is None or data.empty:
        print(f"  ⚠ データ取得失敗。スキップします。")
        return False

    df = data.copy()
    df = add_technical_indicators(df)

    # NaN処理・日付を文字列化
    df = df.fillna("")
    df = df.reset_index()
    if 'Date' in df.columns:
        df['Date'] = df['Date'].apply(
            lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x)
        )
    else:
        df.rename(columns={'index': 'Date'}, inplace=True)
        df['Date'] = df['Date'].apply(
            lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x)
        )

    # float を小数点2桁に丸める
    for col in df.select_dtypes(include=['float64', 'float32']).columns:
        df[col] = df[col].apply(lambda x: round(x, 2) if x != "" else "")

    header = df.columns.tolist()
    values = df.values.tolist()
    data_to_upload = [header] + values

    # 2. シートの取得または新規作成
    sheet_name = f"Historical_{ticker.split('.')[0]}"
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        print(f"  既存シート '{sheet_name}' をクリアして上書きします...")
        worksheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        print(f"  新規シート '{sheet_name}' を作成します...")
        worksheet = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=len(data_to_upload) + 10,
            cols=max(len(header), 20)
        )

    # 3. 一括アップロード
    print(f"  アップロード中... ({len(df)} 行)")
    worksheet.update(data_to_upload, "A1")
    print(f"  ✅ 完了！")
    return True


def main():
    print("=" * 60)
    print("株価歴史データ 一括インポートスクリプト")
    print("=" * 60)

    # 処理対象の決定（引数があれば指定銘柄のみ）
    if len(sys.argv) > 1:
        ticker_arg = sys.argv[1]
        if ticker_arg in TICKERS:
            targets = {ticker_arg: TICKERS[ticker_arg]}
        else:
            print(f"⚠ '{ticker_arg}' はリストにありません。リストの100社を確認してください。")
            return
    else:
        targets = TICKERS

    print(f"\n対象銘柄: {len(targets)} 社")
    for t, n in targets.items():
        print(f"  - {n} ({t})")

    # Spreadsheet接続 (1回だけ行う)
    print("\nGoogle Spreadsheetに接続中...")
    try:
        spreadsheet = get_spreadsheet()
        print(f"  接続成功: '{spreadsheet.title}'")
    except Exception as e:
        print(f"  接続失敗: {e}")
        return

    # 各銘柄を順番にインポート
    success_count = 0
    fail_count = 0
    for i, (ticker, company_name) in enumerate(targets.items(), 1):
        print(f"\n--- ({i}/{len(targets)}) ---")
        try:
            ok = export_one(spreadsheet, ticker, company_name)
            if ok:
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            fail_count += 1

        # API レートリミット対策 (最後の銘柄以外は少し待機)
        if i < len(targets):
            time.sleep(2)

    print("\n" + "=" * 60)
    print(f"インポート完了！  成功: {success_count} 社 / 失敗: {fail_count} 社")
    print("=" * 60)


if __name__ == "__main__":
    main()
