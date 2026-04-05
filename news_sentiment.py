"""
news_sentiment.py
Google News RSS からニュースを取得し、OpenAI でセンチメント分析を行うモジュール。
「今後伸びる業界・企業」「下がる業界・企業」を投資家目線でレポートする。
"""

import os
import json
import feedparser
import urllib.parse
from datetime import datetime
from openai import OpenAI


# ──────────────────────────────────────────────────────────────────
# クライアント生成
# ──────────────────────────────────────────────────────────────────
def get_openai_client() -> OpenAI | None:
    """
    環境変数 または st.secrets から OpenAI クライアントを生成する。
    未設定の場合は None を返す。
    """
    # 1. 環境変数をチェック（.env用）
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API")
    
    # 2. Streamlit Cloud上の Secrets をチェック
    if not api_key:
        try:
            import streamlit as st
            if "OPENAI_API_KEY" in st.secrets:
                api_key = st.secrets["OPENAI_API_KEY"]
            elif "OPENAI_API" in st.secrets:
                api_key = st.secrets["OPENAI_API"]
        except (ImportError, Exception):
            pass

    if not api_key:
        return None
    
    # 改行や空白が混入している場合を除去（Streamlit Secretsのコピペミス対策）
    if isinstance(api_key, str):
        api_key = api_key.replace("\n", "").replace("\r", "").strip()

    return OpenAI(api_key=api_key)


# ──────────────────────────────────────────────────────────────────
# ニュース取得
# ──────────────────────────────────────────────────────────────────
NEWS_CATEGORIES = {
    "日本経済・ビジネス": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRFZ6YVdZU0FtcGhHZ0pLVUNnQVAB?hl=ja&gl=JP&ceid=JP:ja",
    "国際経済": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtcGhHZ0pLVUNnQVAB?hl=ja&gl=JP&ceid=JP:ja",
}

FALLBACK_URL = "https://news.google.com/rss/search?q=%E6%A0%AA%E4%BE%A1+%E7%B5%8C%E6%B8%88+%E6%A5%AD%E7%95%8C&hl=ja&gl=JP&ceid=JP:ja"


def fetch_today_news(max_items: int = 20) -> list[dict]:
    """
    Google News RSS から本日の主要ニュースを取得してリスト化する。
    Returns: [{"title": str, "summary": str, "link": str, "published": str}, ...]
    """
    results = []
    seen_titles = set()

    urls = list(NEWS_CATEGORIES.values()) + [FALLBACK_URL]

    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                results.append({
                    "title": title,
                    "summary": entry.get("summary", title),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
                if len(results) >= max_items:
                    break
        except Exception as e:
            print(f"ニュース取得エラー ({url}): {e}")
        
        if len(results) >= max_items:
            break

    return results[:max_items]


# ──────────────────────────────────────────────────────────────────
# OpenAI 分析
# ──────────────────────────────────────────────────────────────────
ANALYSIS_SYSTEM_PROMPT = """
あなたはベテランの株式アナリストです。
提示された「本日のニュースヘッドライン一覧」を分析し、株式市場・投資家目線で重要な洞察をまとめてください。

必ず以下のJSON形式のみで回答してください。

{
  "market_overview": "本日のマクロ経済・市場全体の概況を2〜3文で総評（日本語）",
  "bullish_sectors": [
    {"name": "業界または企業名", "reason": "上昇が期待される理由（投資家目線で一言）"},
    {"name": "...", "reason": "..."}
  ],
  "bearish_sectors": [
    {"name": "業界または企業名", "reason": "下落が懸念される理由（投資家目線で一言）"},
    {"name": "...", "reason": "..."}
  ],
  "key_news": [
    {"headline": "最も重要なニュースタイトル", "impact": "株式市場への影響の要点（一文）"},
    {"headline": "...", "impact": "..."}
  ],
  "analyst_comment": "総合的な投資戦略コメント（2〜3文、日本語）"
}

bullish_sectors, bearish_sectors はそれぞれ3〜5件、key_newsは3〜5件を目安に。
日本語で回答してください。
"""


def analyze_market_with_ai(client: OpenAI, news_items: list[dict]) -> dict | None:
    """
    ニュース記事をOpenAI GPTに渡してマーケット分析を行う。
    Returns: 分析結果のdict (JSON) or None (エラー時)
    """
    if not news_items:
        return None

    # ニュース一覧をテキスト化
    news_text = "\n".join(
        [f"- {i+1}. {item['title']}" for i, item in enumerate(news_items)]
    )
    user_message = f"【本日のニュースヘッドライン】\n{news_text}"

    try:
        # 新しい Responses API を使用
        response = client.responses.create(
            model="gpt-5.4-mini",
            instructions=ANALYSIS_SYSTEM_PROMPT,
            input=user_message,
            reasoning={
                "effort": "none"   # 分析タスクなので推論ステップは不要
            },
        )
        # output_text は JSON 文字列で返ってくる
        content = response.output_text
        return json.loads(content)
    except Exception as e:
        print(f"OpenAI 分析エラー: {e}")
        return None


# ──────────────────────────────────────────────────────────────────
# エントリポイント (Streamlit タブから呼び出す)
# ──────────────────────────────────────────────────────────────────
def run_sentiment_analysis() -> dict:
    """
    ニュース取得 → AI分析 を実行し、すべての結果をまとめて返す。
    Returns: {"news": list, "analysis": dict | None, "error": str | None}
    """
    client = get_openai_client()
    if client is None:
        return {
            "news": [],
            "analysis": None,
            "error": "環境変数または Streamlit Secrets に `OPENAI_API_KEY` が設定されていません。",
        }

    news = fetch_today_news(max_items=20)
    if not news:
        return {
            "news": [],
            "analysis": None,
            "error": "ニュースの取得に失敗しました。ネットワーク接続を確認してください。",
        }

    analysis = analyze_market_with_ai(client, news)
    return {
        "news": news,
        "analysis": analysis,
        "error": None if analysis else "AI分析に失敗しました。しばらくしてから再試行してください。",
    }
