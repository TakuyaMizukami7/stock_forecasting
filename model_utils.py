import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

# 1. データ取得
import os
from sheets_db import get_daily_stock_data, append_daily_stock_data

def sync_local_csv_with_sheets(data_file="stock_historical.csv"):
    """起動時などに呼ばれ、スプレッドシートの全データをCSVに同期する機能"""
    try:
        df_daily = get_daily_stock_data()
        if df_daily.empty or 'Date' not in df_daily.columns:
            return False
            
        df_daily['Date'] = pd.to_datetime(df_daily['Date']).dt.normalize()
        
        if os.path.exists(data_file):
            df_hist_all = pd.read_csv(data_file)
            df_hist_all['Date'] = pd.to_datetime(df_hist_all['Date']).dt.normalize()
        else:
            df_hist_all = pd.DataFrame(columns=['Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume'])
            
        # 結合して重複排除 (DateとTickerが同じなら後から来たデータを優先)
        df_combined = pd.concat([df_hist_all, df_daily], ignore_index=True)
        df_combined = df_combined.drop_duplicates(subset=['Date', 'Ticker'], keep='last')
        
        # 保存
        df_combined = df_combined.sort_values(by=['Ticker', 'Date'])
        df_combined.to_csv(data_file, index=False)
        return True
    except Exception as e:
        print(f"Sync error: {e}")
        return False

def fetch_latest_data_manual(ticker, data_file="stock_historical.csv"):
    """指定銘柄の最新データを手動で取得し、CSVにマージする"""
    try:
        # yfinanceから多めに取得して最新状況を確保
        new_data = yf.download(ticker, period="1mo", progress=False)
        if new_data is None or new_data.empty:
            return False, "データが見つかりませんでした。"
            
        # MultiIndex 解除
        if isinstance(new_data.columns, pd.MultiIndex):
            try:
                if ticker in new_data.columns.get_level_values(1):
                    new_data = new_data.xs(ticker, axis=1, level=1)
                else:
                    new_data.columns = new_data.columns.droplevel(1)
            except Exception:
                pass
                
        if 'Close' not in new_data.columns:
            return False, "有効な価格データがありません。"

        df_new = new_data[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        df_new['Ticker'] = ticker
        df_new.reset_index(inplace=True)
        if 'index' in df_new.columns:
            df_new.rename(columns={'index': 'Date'}, inplace=True)
        df_new['Date'] = pd.to_datetime(df_new['Date']).dt.normalize()
        # 邪魔なtzを取り除く (tz-naiveにする)
        df_new['Date'] = df_new['Date'].dt.tz_localize(None)

        if os.path.exists(data_file):
            df_hist_all = pd.read_csv(data_file)
            df_hist_all['Date'] = pd.to_datetime(df_hist_all['Date']).dt.normalize()
        else:
            df_hist_all = pd.DataFrame(columns=['Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume'])
            
        # 重複排除しながら結合。手動取得データ(後)が優先される
        df_combined = pd.concat([df_hist_all, df_new], ignore_index=True)
        df_combined = df_combined.drop_duplicates(subset=['Date', 'Ticker'], keep='last')
        df_combined = df_combined.sort_values(by=['Ticker', 'Date'])
        df_combined.to_csv(data_file, index=False)
        
        return True, "最新データを取得し反映しました。"
    except Exception as e:
        return False, f"エラーが発生しました: {e}"

def get_stock_data(ticker, period="10y", start=None, end=None):
    """ローカルのCSVファイルからデータを読み込みます。欠落している場合は yfinance から取得します。"""
    try:
        data_file = "stock_historical.csv"
        df_hist = pd.DataFrame()
        
        # 1. ローカルCSVからの読み込み
        if os.path.exists(data_file):
            try:
                df_hist_all = pd.read_csv(data_file)
                df_hist = df_hist_all[df_hist_all['Ticker'] == ticker].copy()
            except Exception as e:
                print(f"CSV読み込みエラー: {e}")

        # 2. データが空の場合に yfinance から取得 (フォールバック)
        if df_hist.empty:
            print(f"  [フォールバック] {ticker} のデータを yfinance から取得中 ({period})...")
            try:
                df_yf = yf.download(ticker, period=period, progress=False)
                if not df_yf.empty:
                    # MultiIndex 解除
                    if isinstance(df_yf.columns, pd.MultiIndex):
                        try:
                            # Tickerレベルが存在する場合は抽出、そうでなければ単にドロップ
                            if ticker in df_yf.columns.get_level_values(1):
                                df_yf = df_yf.xs(ticker, axis=1, level=1)
                            else:
                                df_yf.columns = df_yf.columns.droplevel(1)
                        except Exception:
                            pass
                    
                    df_yf.reset_index(inplace=True)
                    if 'index' in df_yf.columns:
                        df_yf.rename(columns={'index': 'Date'}, inplace=True)
                    df_yf['Ticker'] = ticker
                    df_yf['Date'] = pd.to_datetime(df_yf['Date']).dt.tz_localize(None)
                    
                    # 必要な列のみ選択
                    cols = ['Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume']
                    df_yf = df_yf[[c for c in cols if c in df_yf.columns]]

                    # キャッシュとしてCSVに保存
                    if os.path.exists(data_file):
                        df_all = pd.read_csv(data_file)
                        df_combined = pd.concat([df_all, df_yf], ignore_index=True)
                        df_combined['Date'] = pd.to_datetime(df_combined['Date']).dt.tz_localize(None)
                        df_combined = df_combined.drop_duplicates(subset=['Date', 'Ticker'], keep='last')
                        df_combined.to_csv(data_file, index=False)
                    else:
                        df_yf.to_csv(data_file, index=False)
                    
                    df_hist = df_yf.copy()
            except Exception as e:
                print(f"yfinance フォールバックエラー: {e}")

        if df_hist.empty:
            return None
            
        # 以降は共通の処理
        df_hist['Date'] = pd.to_datetime(df_hist['Date'])
        # tz-awareな場合は統一のためにnaiveにする
        if df_hist['Date'].dt.tz is not None:
            df_hist['Date'] = df_hist['Date'].dt.tz_localize(None)
            
        df_hist.set_index('Date', inplace=True)
        df_hist.drop(columns=['Ticker'], inplace=True, errors='ignore')
        df_hist = df_hist.sort_index()

        if df_hist.empty or 'Close' not in df_hist.columns:
            return None
            
        if start:
            df_hist = df_hist[df_hist.index >= pd.to_datetime(start)]
        if end:
            df_hist = df_hist[df_hist.index <= pd.to_datetime(end)]
            
        return df_hist
    except Exception as e:
        print(f"データ取得エラー: {e}")
        return None

# 特徴量計算用ヘルパー
def add_technical_indicators(df):
    close = df['Close']
    
    # 既存指標
    df['SMA5'] = close.rolling(window=5).mean()
    df['SMA20'] = close.rolling(window=20).mean()
    df['Return'] = close.pct_change()
    
    # ボリンジャーバンド (20日, ±2σ)
    std20 = close.rolling(window=20).std()
    df['BB_Upper'] = df['SMA20'] + (std20 * 2)
    df['BB_Lower'] = df['SMA20'] - (std20 * 2)
    
    # MACD (12日EMA - 26日EMA) & シグナル (9日EMA)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # RSI (14日)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['RSI14'] = 100 - (100 / (1 + rs))
    
    # ヒストリカル・ボラティリティ (20日リターンの標準偏差)
    df['Volatility'] = df['Return'].rolling(window=20).std()
    
    return df

# 2. 特徴量作成と予測
def predict_stock(data):
    df = data.copy()
    
    # 特徴量追加
    df = add_technical_indicators(df)
    
    # 目的変数作成: 30日後の終値 / 現在の終値
    df['Future_Close'] = df['Close'].shift(-30)
    
    def get_label(current, future):
        if pd.isna(future) or current == 0: return np.nan
        ratio = future / current
        if ratio >= 1.10: return 1 # 上昇
        if ratio <= 0.90: return -1 # 下落
        return 0 # ステイ

    df['Target'] = df.apply(lambda x: get_label(x['Close'], x['Future_Close']), axis=1)
    
    # 特徴量リスト
    feature_cols = ['SMA5', 'SMA20', 'Return', 'BB_Upper', 'BB_Lower', 'MACD', 'MACD_Signal', 'RSI14', 'Volatility']
    
    # NaNを落とす
    data_for_model = df.dropna(subset=feature_cols)
    train_data = data_for_model.dropna(subset=['Target'])
    
    if len(train_data) < 50:
        return None, "データ不足により予測不可", None
        
    X = train_data[feature_cols]
    y = train_data['Target']
    
    # ハイパーパラメータ調整した RandomForest
    model = RandomForestClassifier(
        n_estimators=200, 
        max_depth=10, 
        min_samples_split=5, 
        random_state=42
    )
    model.fit(X, y)
    
    # 最新データの予測
    latest_features = data_for_model.iloc[[-1]][feature_cols]
    prediction = model.predict(latest_features)[0]
    
    # 予測確率の抽出 (クラスごとの確率)
    proba = model.predict_proba(latest_features)[0]
    classes = model.classes_
    predicted_idx = list(classes).index(prediction)
    confidence = proba[predicted_idx] * 100
    
    return prediction, confidence, df

# 3. モデルの精度検証 (時系列での分割テスト)
def evaluate_model(ticker, period="5y", start=None, end=None):
    """
    指定銘柄の過去データを取得し直近20%をテスト用データとして
    Accuracy (正解率) を検証して返す。
    """
    data = get_stock_data(ticker, period=period, start=start, end=end)
    if data is None or data.empty:
        return None
        
    df = data.copy()
    df = add_technical_indicators(df)
    
    df['Future_Close'] = df['Close'].shift(-30)
    
    def get_label(current, future):
        if pd.isna(future) or current == 0: return np.nan
        ratio = future / current
        if ratio >= 1.10: return 1
        if ratio <= 0.90: return -1
        return 0
        
    df['Target'] = df.apply(lambda x: get_label(x['Close'], x['Future_Close']), axis=1)
    
    feature_cols = ['SMA5', 'SMA20', 'Return', 'BB_Upper', 'BB_Lower', 'MACD', 'MACD_Signal', 'RSI14', 'Volatility']
    
    # NaNを落とす (Future_Closeが取れない直近30日もこれで落ちる)
    data_for_model = df.dropna(subset=feature_cols + ['Target'])
    
    if len(data_for_model) < 100:
        return None
        
    X = data_for_model[feature_cols]
    y = data_for_model['Target']
    
    # 時系列分割 (過去80%を学習、直近20%をテスト)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    model = RandomForestClassifier(n_estimators=200, max_depth=10, min_samples_split=5, random_state=42)
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    return accuracy


