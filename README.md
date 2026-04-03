# 株価トレンド予測アプリ (Stock Forecasting App)

機械学習を用いた日本株のトレード支援ダッシュボードです。

## 🌟 主な機能
- **高度予測モデル**: LightGBM, XGBoost, Random Forestを用いた多角的な株価予測。
- **100社一括ランキング**: 主要100銘柄の上昇・下落期待リターンをランキング表示。
- **AIセンチメント分析**: Google News RSSを用いた市場ニュースの感情スコア算出。
- **デモトレード**: 仮想資金を用いた売買シミュレーション機能。

## 🛠 テクノロジー
- **Backend / UI**: Python / Streamlit
- **ML Models**: LightGBM, XGBoost, Scikit-learn
- **Data Source**: yfinance, Google Sheets (Cloud Sync)
- **Sentiment**: Feedparser (RSS Analysis)

## 🚀 デプロイ方法 (Streamlit Cloud)
1. GitHub にリポジトリをアップロード。
2. Streamlit Cloud でアプリを新規作成し、[Advanced settings] > [Secrets] に以下の値を設定。
   - `gcp_service_account`: サービスアカウントの JSON 内容
   - `SPREADSHEET_ID`: 連携する Google スプレッドシートの ID

詳細は `PROJECT_MEMO.md` を参照してください。
