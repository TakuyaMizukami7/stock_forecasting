import os
import time
import gspread
from dotenv import load_dotenv
from sheets_db import get_client

load_dotenv()

def cleanup_sheets():
    print("Google Spreadsheetに接続中...")
    client = get_client()
    if not client:
        print("接続エラー")
        return

    sheet_id = os.getenv("SPREADSHEET_ID")
    if not sheet_id:
        print("SPREADSHEET_IDがありません")
        return

    try:
        spreadsheet = client.open_by_key(sheet_id)
        worksheets = spreadsheet.worksheets()
        
        hist_sheets = [ws for ws in worksheets if ws.title.startswith("Historical_")]
        print(f"対象シート {len(hist_sheets)}件 を見つけました。直近1週間分(7行)を残して削除します。")
        
        for i, ws in enumerate(hist_sheets, 1):
            print(f"[{i}/{len(hist_sheets)}] {ws.title} を処理中...")
            try:
                # すべてのデータを取得
                all_values = ws.get_all_values()
                if len(all_values) <= 8: # ヘッダー1行 + 7行以内なら何もしない
                    print(f"  -> データが少ないためスキップします ({len(all_values)}行)")
                    time.sleep(1)
                    continue
                
                # ヘッダー + 下から7行を残す
                header = all_values[0]
                tail_data = all_values[-7:]
                
                new_values = [header] + tail_data
                
                # パフォーマンスのため、シートをクリアして上書き
                ws.clear()
                ws.update(new_values, "A1")
                print(f"  -> {len(new_values)}行に縮小しました。")
                
            except Exception as e:
                print(f"  ❌ エラー: {e}")
            
            # API制限回避
            time.sleep(1.5)
            
        print("\n🎉 すべてのクリーンアップが完了しました！")
    except Exception as e:
        print(f"全体エラー: {e}")

if __name__ == "__main__":
    cleanup_sheets()
