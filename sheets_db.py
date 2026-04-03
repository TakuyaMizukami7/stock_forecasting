import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import os
import json
from dotenv import load_dotenv

load_dotenv()

def get_credentials():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    # Check Streamlit secrets if running in Streamlit environment
    try:
        import streamlit as st
        if "gcp_service_account" in st.secrets:
            # Convert AttrDict to generic dict for credentials parsing
            creds_dict = dict(st.secrets["gcp_service_account"])
            return Credentials.from_service_account_info(creds_dict, scopes=scopes)
    except ImportError:
        pass
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error reading st.secrets: {e}")

    # Fallback 1: Local JSON file (specified in `.env` or defaulting to `credentials.json`)
    json_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    if os.path.exists(json_path):
        return Credentials.from_service_account_file(json_path, scopes=scopes)
        
    # Fallback 2: JSON string in `.env` (useful for simple deployment)
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw_json:
        try:
            creds_info = json.loads(raw_json)
            return Credentials.from_service_account_info(creds_info, scopes=scopes)
        except json.JSONDecodeError as e:
            print(f"Error parsing GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
            
    return None

def get_client():
    creds = get_credentials()
    if creds:
        try:
            return gspread.authorize(creds)
        except Exception as e:
            print(f"Google API authorization failed: {e}")
            return None
    return None

def get_sheet():
    client = get_client()
    if not client:
        return None
        
    # Look for Spreadsheet ID or URL from environment/secrets
    sheet_id_or_url = os.getenv("SPREADSHEET_ID")
    
    if not sheet_id_or_url:
        try:
            import streamlit as st
            sheet_id_or_url = st.secrets.get("SPREADSHEET_ID")
        except Exception:
            pass
            
    if not sheet_id_or_url:
        print("SPREADSHEET_ID is not configured in environment or secrets.")
        return None
        
    try:
        if "spreadsheets.google.com" in sheet_id_or_url:
            sheet = client.open_by_url(sheet_id_or_url)
        else:
            sheet = client.open_by_key(sheet_id_or_url)
        
        expected_headers = ['更新日時', '銘柄コード', '企業名', '現在価格', '予測トレンド', '自信度(%)']
        
        # 明示的に Predictions シートを使う
        try:
            worksheet = sheet.worksheet("Predictions")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title="Predictions", rows="1000", cols="10")
            worksheet.insert_row(expected_headers, 1)
            return worksheet
        
        # Ensure headers exist
        try:
            headers = worksheet.row_values(1)
        except Exception:
            headers = []
            
        if not headers or headers[0] != expected_headers[0]:
            worksheet.insert_row(expected_headers, 1)
            
        return worksheet
    except Exception as e:
        print(f"Spreadsheet connection error: {e}")
        return None

def save_prediction(ticker, company_name, current_price, prediction_val, confidence):
    worksheet = get_sheet()
    if not worksheet:
        print("未設定または認証エラーのため、Googleスプレッドシートへの保存をスキップしました。")
        return False
        
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 予測値のフォーマット
    if prediction_val == 1:
        trend = "上昇"
    elif prediction_val == -1:
        trend = "下落"
    else:
        trend = "ステイ"
        
    row_data = [
        now_str,
        ticker,
        company_name,
        f"{current_price:,.1f}",
        trend,
        f"{confidence:.1f}"
    ]
    
    try:
        # UPSERT logic using gspread
        # Get all records to find the row index
        records = worksheet.get_all_records()
        df = pd.DataFrame(records)
        
        if not df.empty and '銘柄コード' in df.columns:
            matches = df[df['銘柄コード'] == ticker]
            if not matches.empty:
                row_idx = int(matches.index[0]) + 2 # Header is row 1
                # Update the existing row
                cell_range = f"A{row_idx}:F{row_idx}"
                worksheet.update([row_data], cell_range)
                return True
                
        # If not found or empty dataset, append as a new row
        worksheet.append_row(row_data)
        return True
    except Exception as e:
        print(f"Spreadsheet save error: {e}")
        return False

def get_all_predictions():
    worksheet = get_sheet()
    if not worksheet:
        return None
        
    try:
        records = worksheet.get_all_records()
        if not records:
            return pd.DataFrame(columns=['更新日時', '銘柄コード', '企業名', '現在価格', '予測トレンド', '自信度(%)'])
            
        df = pd.DataFrame(records)
        
        # '更新日時'でソート (最新が上に来るように)
        if '更新日時' in df.columns:
            df = df.sort_values(by='更新日時', ascending=False).reset_index(drop=True)
            
        return df
    except Exception as e:
        print(f"Spreadsheet read error: {e}")
        return None

# --- Stock Data Sync Functions ---
def get_daily_stock_data():
    """
    スプレッドシートの StockData シートから全レコード（日次更新分等）を取得し、DataFrameとして返す。
    """
    client = get_client()
    if not client: return pd.DataFrame()
    sheet_id_or_url = os.getenv("SPREADSHEET_ID")
    try:
        if "spreadsheets.google.com" in sheet_id_or_url:
            sheet = client.open_by_url(sheet_id_or_url)
        else:
            sheet = client.open_by_key(sheet_id_or_url)
            
        # Historical_ prefixをもつシートを探す
        worksheets = sheet.worksheets()
        ranges = [f"{ws.title}!A:K" for ws in worksheets if ws.title.startswith('Historical_')]
        
        if not ranges:
            return pd.DataFrame(columns=["Date", "Ticker", "Open", "High", "Low", "Close", "Volume"])
            
        data_list = []
        # gspread APIのURL長制限を考慮し、50シートずつチャンクでバッチ取得する
        for i in range(0, len(ranges), 50):
            chunk = ranges[i:i+50]
            results = sheet.values_batch_get(chunk)
            for sheet_title, value_range in zip(chunk, results.get('valueRanges', [])):
                ticker = sheet_title.split('!')[0].replace('Historical_', '')
                if not ticker.endswith('.T'):
                    ticker += '.T'
                values = value_range.get('values', [])
                if len(values) > 1:
                    headers = values[0]
                    df = pd.DataFrame(values[1:], columns=headers)
                    df['Ticker'] = ticker
                    data_list.append(df)
                    
        if not data_list:
            return pd.DataFrame(columns=["Date", "Ticker", "Open", "High", "Low", "Close", "Volume"])
            
        df_all = pd.concat(data_list, ignore_index=True)
        # 必要な列のみ抽出
        req_cols = ['Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume']
        available_cols = [c for c in req_cols if c in df_all.columns]
        df_all = df_all[available_cols]
        return df_all
    except Exception as e:
        print(f"Error fetching StockData: {e}")
        return pd.DataFrame()

def append_daily_stock_data(df_new):
    """
    取得した不足分のDataFrame（新しい日付のデータ）をStockDataの末尾に追記する。
    """
    if df_new.empty: return False
    client = get_client()
    if not client: return False
    sheet_id_or_url = os.getenv("SPREADSHEET_ID")
    try:
        if "spreadsheets.google.com" in sheet_id_or_url:
            sheet = client.open_by_url(sheet_id_or_url)
        else:
            sheet = client.open_by_key(sheet_id_or_url)
            
        ws = sheet.worksheet("StockData")
        
        df_new = df_new.copy()
        if pd.api.types.is_datetime64_any_dtype(df_new['Date']):
            df_new['Date'] = df_new['Date'].dt.strftime('%Y-%m-%d')
            
        cols = ["Date", "Ticker", "Open", "High", "Low", "Close", "Volume"]
        # NaN  등을 処理
        df_new[cols] = df_new[cols].fillna(0)
        values = df_new[cols].values.tolist()
        ws.append_rows(values)
        return True
    except Exception as e:
        print(f"Error appending StockData: {e}")
        return False
