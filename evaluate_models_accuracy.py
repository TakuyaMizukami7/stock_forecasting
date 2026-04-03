import json
import os
import numpy as np
import pandas as pd
import time
import urllib.parse
import feedparser
import lightgbm as lgb
import xgboost as xgb
from sklearn.ensemble import RandomForestRegressor

from model_utils import get_stock_data, add_technical_indicators
import advanced_model
from advanced_model import FEATURE_COLS, POSITIVE_KEYWORDS, NEGATIVE_KEYWORDS, get_news_sentiment, build_features

# ── Monkey-patch get_market_features to cache results ──
_cached_market_df = None
_original_gmf = advanced_model.get_market_features

def _cached_get_market_features(period="10y"):
    global _cached_market_df
    if _cached_market_df is None:
        print("  Downloading market features once...")
        _cached_market_df = _original_gmf(period)
    return _cached_market_df

advanced_model.get_market_features = _cached_get_market_features

# 100社すべてを評価対象とする
from get_sectors import TICKERS

def evaluate_three_models_for_ticker(ticker, name):
    print(f"\nEvaluating {name} ({ticker})...")
    # 特徴量構築
    df = build_features(ticker, name, period="10y")
    if df.empty:
        return None
        
    # ダミー感情スコア(過去のバックテスト時は固定しておく)
    df["news_sentiment"] = 0.0 
    
    available_features = [c for c in FEATURE_COLS if c in df.columns]
    target_col = "Target_Price"
    
    df_clean = df.dropna(subset=available_features + [target_col])
    if len(df_clean) < 200:
        print(f"Skipping {ticker}: Not enough data.")
        return None
        
    X = df_clean[available_features].values
    y = df_clean[target_col].values
    
    # 時系列分割 (80/20)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    
    actual_prices = df_clean.iloc[split_idx:]["Close"].values
    
    def calc_metrics(y_t, y_p):
        rmse = float(np.sqrt(np.mean((y_p - y_t) ** 2)))
        actual_dir = (y_t > actual_prices).astype(int)
        pred_dir = (y_p > actual_prices).astype(int)
        dir_acc = float(np.mean(actual_dir == pred_dir)) * 100
        return rmse, dir_acc

    # LightGBM
    model_lgb = lgb.LGBMRegressor(n_estimators=500, learning_rate=0.03, num_leaves=63, max_depth=-1, min_child_samples=20, random_state=42, verbosity=-1)
    model_lgb.fit(X_train, y_train, eval_set=[(X_test, y_test)], callbacks=[lgb.early_stopping(50, verbose=False)])
    p_lgb = model_lgb.predict(X_test)
    rmse_lgb, dir_acc_lgb = calc_metrics(y_test, p_lgb)
    
    # XGBoost
    model_xgb = xgb.XGBRegressor(n_estimators=500, learning_rate=0.03, max_depth=6, subsample=0.8, colsample_bytree=0.8, random_state=42, early_stopping_rounds=50, eval_metric="rmse")
    model_xgb.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    p_xgb = model_xgb.predict(X_test)
    rmse_xgb, dir_acc_xgb = calc_metrics(y_test, p_xgb)
    
    # Random Forest
    model_rf = RandomForestRegressor(n_estimators=200, max_depth=10, min_samples_split=5, random_state=42, n_jobs=-1)
    model_rf.fit(X_train, y_train)
    p_rf = model_rf.predict(X_test)
    rmse_rf, dir_acc_rf = calc_metrics(y_test, p_rf)
    
    print(f"  LGBM  : RMSE={rmse_lgb:.2f}, DirAcc={dir_acc_lgb:.1f}%")
    print(f"  XGB   : RMSE={rmse_xgb:.2f}, DirAcc={dir_acc_xgb:.1f}%")
    print(f"  RF    : RMSE={rmse_rf:.2f}, DirAcc={dir_acc_rf:.1f}%")
    
    return {
        "LightGBM": {"rmse": rmse_lgb, "dir_acc": dir_acc_lgb},
        "XGBoost": {"rmse": rmse_xgb, "dir_acc": dir_acc_xgb},
        "Random Forest": {"rmse": rmse_rf, "dir_acc": dir_acc_rf}
    }

def main():
    results = {
        "LightGBM": {"rmse_list": [], "dir_acc_list": []},
        "XGBoost": {"rmse_list": [], "dir_acc_list": []},
        "Random Forest": {"rmse_list": [], "dir_acc_list": []}
    }
    
    for ticker, name in TICKERS.items():
        try:
            res = evaluate_three_models_for_ticker(ticker, name)
            if res:
                for model_name in results.keys():
                    results[model_name]["rmse_list"].append(res[model_name]["rmse"])
                    results[model_name]["dir_acc_list"].append(res[model_name]["dir_acc"])
        except Exception as e:
            print(f"Error on {ticker}: {e}")
            
    # 平均化
    summary = {}
    for model_name, metrics in results.items():
        summary[model_name] = {
            "avg_rmse": float(np.mean(metrics["rmse_list"])),
            "avg_dir_acc": float(np.mean(metrics["dir_acc_list"]))
        }
        
    # 補足メタデータ
    summary["metadata"] = {
        "evaluated_companies": len(results["LightGBM"]["rmse_list"]),
        "timestamp": datetime.datetime.now().isoformat() if 'datetime' in globals() else "2026-04-03"
    }
        
    with open("models_evaluation.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        
    print("\nEvaluation complete. Results saved to models_evaluation.json")

if __name__ == "__main__":
    import datetime
    main()
