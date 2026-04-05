"""
market_advisor.py
現在の市場状況（VIX、ボラティリティ、RSI、トレンド、ニュース感情スコア）を判定し、
LightGBM / XGBoost / Random Forest のうち最も適したモデルを推薦するモジュール。
"""

import pandas as pd
import numpy as np


# ─────────────────────────────────────────────
# モデルの特性プロファイル（説明文用）
# ─────────────────────────────────────────────
MODEL_PROFILES = {
    "LightGBM": {
        "emoji": "🐆",
        "name": "チーターくん (LightGBM)",
        "strength": "強いトレンド・急変直後",
        "description": "直近の細かい変化にいち早く反応する勾配ブースティング系モデル。強いトレンドやニュースの影響が出やすい局面で精度が高まります。",
    },
    "XGBoost": {
        "emoji": "🦁",
        "name": "ライオンくん (XGBoost)",
        "strength": "横ばい・レンジ・安定相場",
        "description": "テクニカル指標のパターンを総合判断する安定型。RSIが中立域でボラティリティが低い、方向感の読みにくいレンジ相場で安定した予測を行います。",
    },
    "Random Forest": {
        "emoji": "🐘",
        "name": "ゾウさん (Random Forest)",
        "strength": "高ボラティリティ・荒れ相場",
        "description": "多数決型のアンサンブル手法により、外れ値や急変動のノイズに強いモデル。VIXが高い荒れた相場では、極端な予測を避けて安定感を発揮します。",
    },
}

# 「全モデル均衡（安定相場）」用の特別プロファイル
BALANCED_PROFILE = {
    "phase": "🟢 安定相場（均衡）",
    "recommended_model": None,
    "confidence": "低（3モデルが拮抗）",
    "reason": "現時点では特定のモデルが突出して有利な状況ではありません。3つのモデルの予測を総合的に参考にしてください。",
    "indicators": {},
}


# ─────────────────────────────────────────────
# メイン関数：市場状況の判定と最適モデルの推薦
# ─────────────────────────────────────────────
def get_market_condition(
    df: pd.DataFrame,
    market_df: pd.DataFrame,
    sentiment_score: float = 0.0,
) -> dict:
    """
    現在の市場状況を判定し、最適なモデルを推薦する。

    Parameters
    ----------
    df          : build_features が返す株価・テクニカル指標 DataFrame
    market_df   : get_market_features が返す世界市場指標 DataFrame
    sentiment_score : ニュース感情スコア (-1.0 ~ 1.0)

    Returns
    -------
    dict:
        phase             : str  現在の市場フェーズ名
        recommended_model : str | None  推薦モデルキー ("LightGBM" / "XGBoost" / "Random Forest" / None)
        reason            : str  推薦理由の説明文
        confidence        : str  推薦の確信度（目安）
        indicators        : dict 判定に使用した各指標の値
    """
    indicators = {}

    try:
        # ── 1. 個別銘柄のボラティリティ (直近20日) ─────────────────
        if "Volatility" in df.columns and not df["Volatility"].dropna().empty:
            last_vol = float(df["Volatility"].dropna().iloc[-1])
            # 過去全体の中での分位点（高い=相場が荒れている）
            vol_quantile = float(df["Volatility"].dropna().rank(pct=True).iloc[-1])
            indicators["volatility_20d"] = last_vol
            indicators["volatility_quantile"] = vol_quantile
        else:
            last_vol = None
            vol_quantile = None

        # ── 2. RSI (直近値) ─────────────────────────────────────────
        if "RSI14" in df.columns and not df["RSI14"].dropna().empty:
            last_rsi = float(df["RSI14"].dropna().iloc[-1])
            indicators["rsi14"] = last_rsi
        else:
            last_rsi = None

        # ── 3. VIX (恐怖指数) ─────────────────────────────────────
        vix_value = None
        if not market_df.empty and "VIX" in market_df.columns:
            vix_series = market_df["VIX"].dropna()
            if not vix_series.empty:
                vix_value = float(vix_series.iloc[-1])
                indicators["vix"] = vix_value

        # ── 4. 日経平均のトレンド乖離率 ──────────────────────────────
        nikkei_deviation = None
        if not market_df.empty and "Nikkei" in market_df.columns:
            nikkei = market_df["Nikkei"].dropna()
            if len(nikkei) >= 20:
                nikkei_ma20 = nikkei.rolling(20).mean().iloc[-1]
                nikkei_last = nikkei.iloc[-1]
                if nikkei_ma20 != 0:
                    nikkei_deviation = float((nikkei_last - nikkei_ma20) / nikkei_ma20 * 100)
                    indicators["nikkei_deviation_pct"] = nikkei_deviation

        # ── 5. ニュース感情スコア ─────────────────────────────────
        indicators["news_sentiment"] = sentiment_score

    except Exception as e:
        print(f"  [market_advisor] 指標取得エラー: {e}")
        return BALANCED_PROFILE.copy()

    # ─────────────────────────────────────────────────────
    # フェーズ判定（優先順位順に評価）
    # ─────────────────────────────────────────────────────

    # 最優先: ニュース急変（感情スコアが強い）
    if abs(sentiment_score) >= 0.3:
        direction = "ポジティブ" if sentiment_score > 0 else "ネガティブ"
        return {
            "phase": f"🚨 急変直後（ニュースインパクト：{direction}）",
            "recommended_model": "LightGBM",
            "confidence": "高",
            "reason": (
                f"ニュース感情スコアが強い値（{sentiment_score:+.3f}）を示しています。"
                "直近の情報変化に素早く適応するLightGBMが、このような急変局面で"
                "最もリアクティブな予測を出す傾向があります。"
            ),
            "indicators": indicators,
        }

    # 高ボラティリティ判定
    is_high_vol = (
        (vix_value is not None and vix_value > 25) or
        (vol_quantile is not None and vol_quantile > 0.75)
    )
    if is_high_vol:
        vix_str = f"VIX: {vix_value:.1f}" if vix_value else ""
        vol_str = f"20日ボラティリティ: 上位{int((1-vol_quantile)*100)}%内" if vol_quantile else ""
        detail = " / ".join(filter(None, [vix_str, vol_str]))
        return {
            "phase": "🌪 高ボラティリティ（荒れ相場）",
            "recommended_model": "Random Forest",
            "confidence": "高",
            "reason": (
                f"現在の市場は荒れた状態にあります（{detail}）。"
                "多数決型のRandom Forestは、急激な価格変動のノイズに引っ張られにくく、"
                "荒れた相場でも安定した予測を維持する傾向があります。"
            ),
            "indicators": indicators,
        }

    # 強いトレンド相場判定
    if nikkei_deviation is not None and abs(nikkei_deviation) >= 5.0:
        direction = "上昇" if nikkei_deviation > 0 else "下落"
        return {
            "phase": f"📈 強いトレンド相場（日経が移動平均から{nikkei_deviation:+.1f}%乖離）",
            "recommended_model": "LightGBM",
            "confidence": "中〜高",
            "reason": (
                f"日経平均が20日移動平均から{nikkei_deviation:+.1f}%の大きな乖離を示しており、"
                f"市場全体が{direction}トレンドにあります。"
                "LightGBMはトレンドに乗った特徴量変化を素早く捉えるため、"
                "トレンド相場で高い適応力を発揮します。"
            ),
            "indicators": indicators,
        }

    # 横ばい・レンジ相場判定
    is_range_market = (
        last_rsi is not None and 38 <= last_rsi <= 62 and
        vol_quantile is not None and vol_quantile < 0.5
    )
    if is_range_market:
        return {
            "phase": "➡️ 横ばい・レンジ相場",
            "recommended_model": "XGBoost",
            "confidence": "中",
            "reason": (
                f"RSI（{last_rsi:.1f}）が中立域にあり、ボラティリティも低水準です。"
                "方向感が出にくいレンジ相場では、過学習を抑制しながら"
                "テクニカル指標のパターンを総合判断するXGBoostが安定した精度を発揮します。"
            ),
            "indicators": indicators,
        }

    # デフォルト：安定相場（全モデル均衡）
    result = BALANCED_PROFILE.copy()
    result["indicators"] = indicators
    return result
