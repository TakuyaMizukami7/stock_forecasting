"""
advanced_model.py
世界市場指標・ニュース感情スコア・ラグ特徴量を組み込んだ
LightGBM による 30日後株価予測モジュール。
"""

import pandas as pd
import numpy as np
import yfinance as yf
import feedparser
import urllib.parse
from datetime import datetime, timedelta

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

from sklearn.ensemble import RandomForestRegressor

from model_utils import get_stock_data, add_technical_indicators


# ─────────────────────────────────────────────
# ニュース感情分析用キーワード辞書
# ─────────────────────────────────────────────
POSITIVE_KEYWORDS = [
    "増収", "増益", "最高益", "最高値", "上昇", "成長", "好調", "好業績",
    "黒字", "増配", "自社株買い", "提携", "買収", "新製品", "受注",
    "上方修正", "復活", "回復", "強い", "拡大", "伸び", "高い",
    "profit", "growth", "record", "bullish", "upgrade", "beat",
    "revenue", "positive", "rise", "rally",
]
NEGATIVE_KEYWORDS = [
    "減収", "減益", "赤字", "損失", "下落", "不振", "悪化", "不正",
    "リコール", "訴訟", "下方修正", "リストラ", "閉鎖", "撤退", "借金",
    "破綻", "危機", "暴落", "弱い", "低下", "困難", "懸念",
    "loss", "decline", "bearish", "downgrade", "miss", "risk",
    "negative", "drop", "fall", "concern", "lawsuit",
]


# ─────────────────────────────────────────────
# 1. ニュース感情スコア取得
# ─────────────────────────────────────────────
def get_news_sentiment(company_name: str) -> float:
    """
    Google News RSS から企業名で検索した最新ニュースを取得し、
    ポジティブ/ネガティブキーワードの出現頻度から感情スコアを計算。
    Returns: float in [-1.0, 1.0]  (正=良い, 負=悪い)
    """
    try:
        query = urllib.parse.quote(company_name)
        url = f"https://news.google.com/rss/search?q={query}&hl=ja&gl=JP&ceid=JP:ja"
        feed = feedparser.parse(url)
        entries = feed.entries[:20]  # 最新20件

        if not entries:
            return 0.0

        pos_count, neg_count = 0, 0
        for entry in entries:
            text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
            pos_count += sum(1 for kw in POSITIVE_KEYWORDS if kw.lower() in text)
            neg_count += sum(1 for kw in NEGATIVE_KEYWORDS if kw.lower() in text)

        total = pos_count + neg_count
        if total == 0:
            return 0.0

        # [-1, 1] に正規化
        score = (pos_count - neg_count) / total
        return round(score, 4)

    except Exception as e:
        print(f"  ニュース感情スコア取得エラー: {e}")
        return 0.0


# ─────────────────────────────────────────────
# 2. 世界市場特徴量の取得
# ─────────────────────────────────────────────
MARKET_SYMBOLS = {
    "SP500": "^GSPC",    # S&P 500
    "VIX": "^VIX",       # VIX 恐怖指数
    "USDJPY": "JPY=X",   # USD/JPY
    "Bond10Y": "^TNX",   # 米10年国債利回り
    "Nikkei": "^N225",   # 日経平均
}


_market_features_cache = {}

def get_market_features(period: str = "10y") -> pd.DataFrame:
    """
    世界市場指標を取得し、日次リターン・ラグ特徴量を付与した DataFrame を返す。
    インデックスは Date (日付)。
    """
    global _market_features_cache
    if period in _market_features_cache:
        return _market_features_cache[period]

    dfs = []
    for name, symbol in MARKET_SYMBOLS.items():
        try:
            # 終了日を2026-03-31に統一
            raw = yf.download(symbol, end="2026-04-01", period=period, progress=False)
            if raw.empty:
                continue

            # MultiIndex 対応
            if isinstance(raw.columns, pd.MultiIndex):
                try:
                    raw = raw.xs(symbol, axis=1, level=1)
                except Exception:
                    raw.columns = raw.columns.droplevel(1)

            close = raw["Close"].rename(name)
            ret = close.pct_change().rename(f"{name}_ret")
            lag1 = close.shift(1).rename(f"{name}_lag1")
            lag5 = close.shift(5).rename(f"{name}_lag5")
            dfs.extend([close, ret, lag1, lag5])

        except Exception as e:
            print(f"  市場データ取得エラー ({symbol}): {e}")

    if not dfs:
        return pd.DataFrame()

    market_df = pd.concat(dfs, axis=1)
    market_df.index = pd.to_datetime(market_df.index)
    market_df.index.name = "Date"
    
    _market_features_cache[period] = market_df
    return market_df


# ─────────────────────────────────────────────
# 3. 特徴量構築
# ─────────────────────────────────────────────
def build_features(
    ticker: str,
    company_name: str,
    period: str = "10y",
    target_days: int = 30,
) -> pd.DataFrame:
    """
    株価・テクニカル指標・ラグ特徴量・世界市場指標を結合した
    学習用 DataFrame を返す。目的変数は `Target_Price`（target_days日後終値）。
    """
    # 株価生データの取得（スプレッドシート等のハイブリッドキャッシュから）
    data = get_stock_data(ticker, period=period)
    if data is None or data.empty:
        raise ValueError(f"{ticker} のデータが取得できませんでした。")

    df = data.copy()
    
    # ── テクニカル指標のリアルタイム算出・補完 ────────────────────────
    # GAS側では計算せず生データのみを保持する方針のため、ここで動的に付与する
    df = add_technical_indicators(df)

    # ── ラグ特徴量 ──────────────────────────────
    for lag in [1, 5, 10, 20, 30]:
        df[f"Close_lag{lag}"] = df["Close"].shift(lag)
        df[f"Return_lag{lag}"] = df["Close"].pct_change(lag)

    # 出来高系
    df["Volume_lag1"] = df["Volume"].shift(1)
    df["Volume_ma20"] = df["Volume"].rolling(20).mean()
    df["Volume_ratio"] = df["Volume"] / df["Volume_ma20"].replace(0, np.nan)

    # ── 目的変数: target_days 日後の終値 ───────────────────
    df["Target_Price"] = df["Close"].shift(-target_days)
    df["Target_Return"] = (df["Target_Price"] / df["Close"]) - 1

    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"

    # ── 世界市場指標とのマージ ─────────────────────
    market_df = get_market_features(period=period)
    if not market_df.empty:
        # 日付インデックスを揃えて left join
        market_df.index = pd.to_datetime(market_df.index).normalize()
        df.index = pd.to_datetime(df.index).normalize()
        df = df.join(market_df, how="left")
        # 市場データが欠損している日（祝日など）は forward fill
        market_cols = market_df.columns.tolist()
        df[market_cols] = df[market_cols].ffill()

    return df


# ─────────────────────────────────────────────
# 4. 学習・予測
# ─────────────────────────────────────────────
FEATURE_COLS = [
    # テクニカル
    "SMA5", "SMA20", "Return",
    "BB_Upper", "BB_Lower", "MACD", "MACD_Signal", "RSI14", "Volatility",
    # ラグ
    "Close_lag1", "Close_lag5", "Close_lag10", "Close_lag20", "Close_lag30",
    "Return_lag1", "Return_lag5", "Return_lag10", "Return_lag20", "Return_lag30",
    # 出来高
    "Volume_ratio",
    # 世界市場
    "SP500", "SP500_ret", "SP500_lag1",
    "VIX", "VIX_ret", "VIX_lag1",
    "USDJPY", "USDJPY_ret", "USDJPY_lag1",
    "Bond10Y", "Bond10Y_ret",
    "Nikkei", "Nikkei_ret",
    # ニュース感情 (スカラーを列として付与)
    "news_sentiment",
]


def train_and_predict(
    ticker: str,
    company_name: str,
    period: str = "10y",
    fast_mode: bool = False,
    global_sentiment: float = None,
    target_days: int = 30,
) -> dict:
    """
    LightGBM, XGBoost, Random Forest で指定日数(target_days)後の株価をそれぞれ予測する。
    fast_mode=True が指定されても XGBoost, Random Forest の学習はスキップせず全て実行される。

    Returns dict:
        current_price     : float  本日の終値
        news_sentiment    : float  ニュース感情スコア
        n_train           : int    学習データ数
        n_test            : int    検証データ数
        models            : dict   各モデルの予測結果（ predicted_price, predicted_return, rmse, mae, direction_accuracy, feature_importance ）
    """
    if not LIGHTGBM_AVAILABLE or not XGBOOST_AVAILABLE:
        raise ImportError(
            "lightgbm または xgboost がインストールされていません。"
            "`pip install lightgbm xgboost` を実行してください。"
        )

    if global_sentiment is not None:
        sentiment = global_sentiment
        # ログが大量に出るのを避けるため、fast_mode時は表示を控えめに
    else:
        print(f"  [1/4] ニュース感情スコアを取得中...")
        sentiment = get_news_sentiment(company_name)
        print(f"        感情スコア: {sentiment:+.4f}")

    if not fast_mode:
        print(f"  [2/4] 生データを取得し、テクニカル指標をリアルタイム補完して特徴量を構築中...")
    df = build_features(ticker, company_name, period=period, target_days=target_days)

    df["news_sentiment"] = sentiment

    available_features = [c for c in FEATURE_COLS if c in df.columns]
    target_col = "Target_Price"

    df_clean = df.dropna(subset=available_features + [target_col])

    if len(df_clean) < 200:
        raise ValueError(f"有効データが不足しています ({len(df_clean)} 行)。")

    X = df_clean[available_features].values
    y = df_clean[target_col].values

    # ── 時系列分割 (80% 学習 / 20% テスト) ─────────────
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    
    # 方向正解率計算のための実際の価格
    actual_prices = df_clean["Close"].iloc[split_idx:].values

    latest_df = df.dropna(subset=available_features).tail(1)
    if latest_df.empty:
        raise ValueError("最新データの特徴量に欠損値が多く、予測できません。")

    latest_features = latest_df[available_features].values
    current_price = float(df["Close"].iloc[-1])

    results = {}

    if not fast_mode:
        print(f"  [3/4] 3つのモデルを学習・検証中... (学習: {len(X_train)}行, テスト: {len(X_test)}行)")

    # 指標計算用ヘルパー
    def calc_metrics(y_true, y_pred, pred_price):
        rmse = float(np.sqrt(np.mean((y_pred - y_true) ** 2)))
        mae = float(np.mean(np.abs(y_pred - y_true)))
        actual_dir = (y_true > actual_prices).astype(int)
        pred_dir = (y_pred > actual_prices).astype(int)
        dir_acc = float(np.mean(actual_dir == pred_dir))
        return {
            "predicted_price": float(pred_price),
            "predicted_return": float((pred_price / current_price) - 1),
            "rmse": rmse,
            "mae": mae,
            "direction_accuracy": dir_acc
        }

    # ── 1. LightGBM ──────────────────────────────
    print("        - LightGBM を学習中...")
    lgb_params = {
        "objective": "regression",
        "metric": ["rmse"],
        "n_estimators": 500,
        "learning_rate": 0.03,
        "num_leaves": 63,
        "max_depth": -1,
        "min_child_samples": 20,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "random_state": 42,
        "verbosity": -1,
    }
    model_lgb = lgb.LGBMRegressor(**lgb_params)
    model_lgb.fit(X_train, y_train, eval_set=[(X_test, y_test)], callbacks=[lgb.early_stopping(50, verbose=False)])
    
    y_pred_lgb = model_lgb.predict(X_test)
    lgb_price = model_lgb.predict(latest_features)[0]
    lgb_imp = pd.Series(model_lgb.feature_importances_, index=available_features).sort_values(ascending=False).head(20)
    
    results["LightGBM"] = calc_metrics(y_test, y_pred_lgb, lgb_price)
    results["LightGBM"]["feature_importance"] = lgb_imp

    # ── 2. XGBoost ───────────────────────────────
    if not fast_mode:
        print("        - XGBoost を学習中...")
    model_xgb = xgb.XGBRegressor(
        n_estimators=500,
        learning_rate=0.03,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        early_stopping_rounds=50,
        eval_metric="rmse"
    )
    model_xgb.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
        
    y_pred_xgb = model_xgb.predict(X_test)
    xgb_price = model_xgb.predict(latest_features)[0]
    xgb_imp = pd.Series(model_xgb.feature_importances_, index=available_features).sort_values(ascending=False).head(20)
        
    results["XGBoost"] = calc_metrics(y_test, y_pred_xgb, xgb_price)
    results["XGBoost"]["feature_importance"] = xgb_imp

    # ── 3. Random Forest ─────────────────────────
    print("        - Random Forest を学習中...")
    model_rf = RandomForestRegressor(
        n_estimators=200,
        max_depth=10,
        min_samples_split=5,
        random_state=42,
        n_jobs=-1
    )
    model_rf.fit(X_train, y_train)
        
    y_pred_rf = model_rf.predict(X_test)
    rf_price = model_rf.predict(latest_features)[0]
    rf_imp = pd.Series(model_rf.feature_importances_, index=available_features).sort_values(ascending=False).head(20)
        
    results["Random Forest"] = calc_metrics(y_test, y_pred_rf, rf_price)
    results["Random Forest"]["feature_importance"] = rf_imp

    if not fast_mode:
        print(f"  [4/4] 予測完了！")

    # ── 市場状況判定と最適モデル推薦 ─────────────────────────
    try:
        from market_advisor import get_market_condition
        market_df_for_advice = get_market_features(period=period)
        market_advice = get_market_condition(df, market_df_for_advice, sentiment)
    except Exception as e:
        print(f"  [market_advisor] 推薦処理エラー: {e}")
        market_advice = {
            "phase": "🟢 安定相場（均衡）",
            "recommended_model": None,
            "confidence": "低（3モデルが拮抗）",
            "reason": "市場状況の判定中にエラーが発生しました。3つすべてのモデルの予測を参考にしてください。",
            "indicators": {},
        }

    return {
        "current_price": current_price,
        "news_sentiment": sentiment,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "models": results,
        "market_advice": market_advice,
    }
