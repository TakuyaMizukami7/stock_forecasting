import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import feedparser
import urllib.parse

from model_utils import get_stock_data, evaluate_model

# 3. AI分析 (リアルタイムニュース - Google News RSS)
def analyze_stock_news(ticker, company_name):
    try:
        query = f"{company_name}"
        encoded_query = urllib.parse.quote(query)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ja&gl=JP&ceid=JP:ja"
        
        feed = feedparser.parse(rss_url)
        
        output = f"### 【AI市場分析レポート】\n**対象銘柄**: {company_name} ({ticker})\n\n**最新ニュース (Google News)**:\n"
        
        if not feed.entries:
             output += "ニュースが見つかりませんでした。\n"
        else:
            for entry in feed.entries[:5]:
                title = entry.title
                link = entry.link
                published = entry.get('published', '')
                output += f"*   [{title}]({link})\n"
                if published:
                    output += f"    > ({published})\n"
                
        return output
    except Exception as e:
        return f"ニュース取得中にエラーが発生しました: {e}"

# 4. ログイン機能とUI実装
def login_ui():
    import demo_trade_db
    
    # Session State Initialization
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.session_state["settings"] = {}

    if st.session_state["logged_in"]:
        return True
        
    st.title("🔐 アプリにログイン")
    
    tab_login, tab_change_pw = st.tabs(["ログイン", "パスワード変更"])
    
    with tab_login:
        with st.form("login_form"):
            user_l = st.text_input("ユーザー名")
            pass_l = st.text_input("パスワード", type="password")
            submit_l = st.form_submit_button("ログイン")
            if submit_l:
                if user_l and pass_l:
                    with st.spinner("認証中... (Google Sheets)"):
                        success, msg = demo_trade_db.verify_user(user_l, pass_l)
                    if success:
                        st.session_state["logged_in"] = True
                        st.session_state["username"] = user_l
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("すべて入力してください。")
                    
    with tab_change_pw:
        st.markdown("現在のユーザーのパスワードを変更します。")
        with st.form("change_pw_form"):
            user_c = st.text_input("ユーザー名")
            old_pass_c = st.text_input("現在のパスワード", type="password")
            new_pass_c = st.text_input("新しいパスワード", type="password")
            submit_c = st.form_submit_button("パスワードを変更")
            if submit_c:
                if user_c and old_pass_c and new_pass_c:
                    with st.spinner("更新中..."):
                        success, msg = demo_trade_db.change_password(user_c, old_pass_c, new_pass_c, is_admin=False)
                    if success:
                        st.success("パスワードを変更しました。ログインしてください。")
                    else:
                        st.error(msg)
                else:
                    st.warning("すべて入力してください。")
                    
    return False

def main():
    st.set_page_config(page_title="Stock Forecast App", layout="wide")
    
    if not login_ui():
        st.stop()
        
    # DB同期ロジック (セッション中1回だけ実行)
    if "db_synced" not in st.session_state:
        from model_utils import sync_local_csv_with_sheets
        with st.spinner("スプレッドシートから最新データを同期しています... (初回のみ)"):
            sync_local_csv_with_sheets()
        st.session_state["db_synced"] = True

    # 以降はログイン済みの場合のみ表示
    st.sidebar.markdown(f"**👤 ログイン中: {st.session_state['username']}**")
    if st.sidebar.button("ログアウト", type="secondary"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.rerun()
        
    # --- 管理者メニュー (mizukami 専用) ---
    if st.session_state.get("username") == "mizukami":
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 👑 管理者メニュー")
        import demo_trade_db
        
        # ユーザー一覧
        if st.sidebar.button("ユーザー一覧を取得"):
            users = demo_trade_db.get_all_users()
            st.sidebar.info(f"登録ユーザー:\n" + "\n".join([f"- {u}" for u in users]))
            
        # ユーザー追加
        with st.sidebar.expander("➕ 新規ユーザー追加"):
            with st.form("admin_create_user"):
                new_u = st.text_input("新規ユーザーID")
                new_p = st.text_input("初期パスワード")
                if st.form_submit_button("追加"):
                    if new_u and new_p:
                        success, msg = demo_trade_db.create_user(new_u, new_p)
                        if success: st.success(msg)
                        else: st.error(msg)
                        
        # パスワード強制変更
        with st.sidebar.expander("🔑 パスワード強制変更"):
            with st.form("admin_change_pw"):
                tgt_u = st.text_input("対象ユーザー名")
                frc_p = st.text_input("新しいパスワード")
                if st.form_submit_button("強制変更"):
                    if tgt_u and frc_p:
                        success, msg = demo_trade_db.change_password(tgt_u, "", frc_p, is_admin=True)
                        if success: st.success(msg)
                        else: st.error(msg)
                        
        # ユーザー削除
        with st.sidebar.expander("🗑️ ユーザー削除"):
            with st.form("admin_delete_user"):
                del_u = st.text_input("削除するユーザー名")
                check_del = st.checkbox("完全に削除する")
                if st.form_submit_button("削除実行"):
                    if del_u and check_del:
                        success, msg = demo_trade_db.delete_user(del_u)
                        if success: st.success(msg)
                        else: st.error(msg)
                        
    st.sidebar.markdown("---")
    
    st.title("株価トレンド予測アプリ")
    st.markdown("""
    このアプリは、機械学習技術（LightGBM, XGBoost, Random Forest）と市場環境データ、ニュースの感情分析を組み合わせた次世代の株価予測ダッシュボードです。
    
    ### 🌟 このアプリでできること
    - **高度な株価予測**: 3つの異なるAIモデルが、指定した期間（7日, 30日, 90日）後の株価を予測し、その精度や特徴量の重要度を可視化します。
    - **100社一括ランキング**: 日本を代表する100銘柄を一括で予測し、上昇・下落が期待される銘柄をランキング形式で抽出します。
    - **AIセンチメント分析**: 最新の経済ニュースから市場全体のムードを読み解き、投資判断の材料を提供します。
    - **デモトレード**: 仮想資金を使って、リスクなしで売買シミュレーションと資産推移の確認ができます。

    ### 📖 使い方
    1. **ランキングをチェック**: 「🏆 100社ランキング」タブで現在の市場全体の有望銘柄を把握します。
    2. **詳細分析**: 気になる銘柄があれば「🔮 高度予測モデル」タブでターゲット日数を選んで詳細な予測を実行します。
    3. **ニュースを確認**: 「🤖 AIセンチメント分析」で本日の主要トピックスと市場への影響を確認します。
    4. **シミュレーション**: 予測をもとに「💰 デモトレード」で取引を行い、自分の資産がどう推移するか練習してみましょう。
    """)

    # タブの作成
    tab1, tab_ranking, tab_new, tab2, tab5 = st.tabs(["🔮 高度予測モデル", "🏆 100社ランキング", "📊 モデル精度・分析メモ", "🤖 AIセンチメント分析", "💰 デモトレード"])

    # 銘柄リスト (100社)
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

    SECTORS = {
        '自動車・輸送用機器': ['7203.T', '7267.T', '6902.T', '7269.T', '7201.T', '7270.T', '7202.T'],
        '電気・精密・半導体': ['6758.T', '6861.T', '8035.T', '6954.T', '6501.T', '6594.T', '6702.T', '7741.T', '6981.T', '6920.T', '6503.T', '6752.T', '6146.T', '7751.T', '6723.T', '6762.T', '6971.T', '6869.T', '6701.T', '6645.T', '7733.T', '6857.T'],
        '情報・通信・サービス': ['9984.T', '9432.T', '6098.T', '7974.T', '9433.T', '4661.T', '9735.T', '9434.T', '4307.T', '4689.T', '4385.T', '2413.T'],
        '銀行・証券・保険': ['8306.T', '8316.T', '8411.T', '7182.T', '8766.T', '8591.T', '8725.T', '8604.T', '8630.T', '8308.T', '8309.T'],
        '医薬品・バイオ': ['4502.T', '4568.T', '4519.T', '4523.T', '4543.T', '4507.T', '4528.T', '4578.T', '4503.T'],
        '卸売業（商社）': ['8001.T', '8031.T', '8058.T', '8053.T', '8002.T'],
        '小売・食品・生活': ['3382.T', '2914.T', '9983.T', '4911.T', '4452.T', '2502.T', '2802.T', '2503.T'],
        '化学・繊維・素材・エネルギー': ['4063.T', '4005.T', '4901.T', '5108.T', '3407.T', '3402.T', '4188.T', '5020.T', '5802.T'],
        '機械・鉄鋼・建設・不動産': ['6367.T', '1925.T', '7011.T', '6301.T', '5401.T', '1928.T', '6273.T', '8802.T', '8801.T'],
        '陸運・海運・空運': ['9022.T', '9020.T', '9021.T', '9101.T', '9104.T', '9107.T', '9202.T', '9201.T'],
        'すべて（ジャンルなし）': list(TICKERS.keys())
    }

    # ─────────────────────────────────────────────────────────────
    # タブ1: 高度予測モデル (LightGBM + 世界市場 + ニュース感情)
    # ─────────────────────────────────────────────────────────────
    with tab1:
        st.header("🔮 高度予測モデル (LightGBM × 世界市場 × ニュース感情)")
        st.markdown(
            """
            10年分の株価データ・テクニカル指標に加え、**S&P500・VIX恐怖指数・USD/JPY・米国10年国債**など
            世界市場の指標と、**Google Newsのニュース感情スコア**を特徴量として取り込んだ
            マシーンラーニングモデルで、選択した予測ターゲット日数の株価（円）を予測します。
            """
        )
        st.info("⏱ 初回実行時や銘柄変更時は、モデル学習のため **1〜3分** 程度かかります。")

        st.sidebar.header("設定パネル")
        st.sidebar.markdown("対象の銘柄を選択してください。")
        
        target_days_str = st.sidebar.selectbox("予測ターゲット (日数)", ["7日後", "30日後", "90日後"], index=1, key="adv_target_days")
        target_days = int(target_days_str.replace("日後", ""))
        st.sidebar.markdown("---")
        
        input_mode = st.sidebar.radio("選択方式", ["リストから選択 (カテゴリー式)", "直接入力 (予測変換式)"])
        
        if "リスト" in input_mode:
            sector_options = list(SECTORS.keys())
            selected_sector = st.sidebar.selectbox("業界カテゴリー", sector_options, index=0, key="adv_sector_sel")
            
            ticker_list_for_sector = SECTORS[selected_sector]
            adv_options = [f"{code}: {TICKERS.get(code, '不明')}" for code in ticker_list_for_sector]
            
            adv_selected = st.sidebar.selectbox("銘柄選択", adv_options, key="adv_ticker_sel")
            adv_ticker = adv_selected.split(":")[0].strip()
            adv_company = TICKERS.get(adv_ticker, "指定銘柄")
            st.session_state["adv_ticker"] = adv_ticker
        else:
            search_text = st.sidebar.text_input("企業名やコードの一部を入力 (予測変換)", placeholder="例: トヨタ, 7203")
            
            adv_options = []
            if search_text:
                q = search_text.lower()
                candidates = {k: v for k, v in TICKERS.items() if q in k.lower() or q in v.lower()}
                adv_options = [f"{code}: {name}" for code, name in candidates.items()]
                
                # 入力されたテキストと完全に一致するティッカーが見つからなかった場合、手動入力用アイテムとして追加
                if not any(q == k.lower() for k in candidates.keys()) and len(q) > 0:
                    adv_options.insert(0, f"{search_text.upper()}: (独自指定銘柄)")
            else:
                adv_options = [f"{code}: {name}" for code, name in TICKERS.items()]
                
            adv_selected = st.sidebar.selectbox("検索結果から選択:", adv_options, key="adv_ticker_direct_sel")
            adv_ticker = adv_selected.split(":")[0].strip()
            adv_company = TICKERS.get(adv_ticker, "指定銘柄")
            st.session_state["adv_ticker"] = adv_ticker

        if st.sidebar.button("⬇️ 最新株価を手動取得", key="adv_fetch_latest"):
            from model_utils import fetch_latest_data_manual
            with st.spinner(f"{adv_company} の最新データを手動取得しています..."):
                success, msg = fetch_latest_data_manual(adv_ticker)
            if success:
                st.sidebar.success(msg)
            else:
                st.sidebar.error(msg)

        if st.sidebar.button("予測を実行する", key="adv_predict"):
            try:
                from advanced_model import train_and_predict, LIGHTGBM_AVAILABLE
                if not LIGHTGBM_AVAILABLE:
                    st.error("lightgbm がインストールされていません。ターミナルで `pip install lightgbm` を実行してください。")
                    st.stop()

                with st.spinner(f"{adv_company} の予測モデルを学習中... (1〜3分)"):
                    result = train_and_predict(adv_ticker, adv_company, target_days=target_days)

                # ── データベース（Google Sheets）に予測結果を保存 ──
                import sheets_db
                try:
                    # 代表として LightGBM の予測結果を保存
                    lgb_res = result["models"]["LightGBM"]
                    pred_ret = lgb_res["predicted_return"] * 100
                    if pred_ret >= 5:
                        pred_val = 1
                    elif pred_ret <= -5:
                        pred_val = -1
                    else:
                        pred_val = 0
                        
                    # 信頼度は方向正解率を代用
                    dummy_confidence = lgb_res['direction_accuracy'] * 100
                    
                    saved = sheets_db.save_prediction(adv_ticker, adv_company, result["current_price"], pred_val, dummy_confidence)
                    if not saved:
                        st.toast("⚠ スプレッドシートへの保存がスキップされました。設定を確認してください。", icon="⚠️")
                except Exception as e:
                    print(f"Failed to save prediction: {e}")

                # ── 予測結果サマリー ──────────────────────────
                st.subheader("📊 予測結果 (3キャラクター比較)")
                cur_price = result["current_price"]
                st.markdown(f"**現在の株価（直近終値）: ¥{cur_price:,.1f}**")

                MODEL_UI = {
                    "LightGBM": {
                        "title": "🐆 チーターくん", 
                        "desc": "最新トレンドに敏感！直近の細かい変化にいち早く反応するスピード派"
                    },
                    "XGBoost": {
                        "title": "🦁 ライオンくん", 
                        "desc": "多角的に分析！様々な指標を総合判断して力強さを測るパワフルな王道派"
                    },
                    "Random Forest": {
                        "title": "🐘 ゾウさん", 
                        "desc": "過去の経験重視！森の中でたくさんの意見を集めて平均を取る手堅い慎重派"
                    }
                }

                cols = st.columns(len(result["models"]))
                for i, (m_name, m_res) in enumerate(result["models"].items()):
                    with cols[i]:
                        ui = MODEL_UI.get(m_name, {"title": m_name, "desc": ""})
                        st.markdown(f"### {ui['title']}")
                        st.markdown(f"**({m_name})**")
                        st.caption(ui['desc'])
                        
                        pred_price = m_res["predicted_price"]
                        pred_ret = m_res["predicted_return"] * 100
                        rmse = m_res["rmse"]
                        
                        st.metric(
                            label=f"{target_days}日後予測",
                            value=f"¥{pred_price:,.1f}",
                            delta=f"{pred_ret:+.2f}%"
                        )
                        st.caption(f"予測誤差目安(RMSE): ±¥{rmse:,.1f}")
                        
                        if pred_ret >= 5:
                            st.success("📈 上昇見通し")
                        elif pred_ret <= -5:
                            st.error("📉 下落見通し")
                        else:
                            st.info("➡️ 横ばい")

                # ── 精度指標 ──────────────────────────────────
                st.markdown("---")
                st.subheader("🎯 モデル検証精度（過去データの直近20%で評価）")
                metrics_data = []
                for m_name, m_res in result["models"].items():
                    ui = MODEL_UI.get(m_name, {"title": m_name})
                    metrics_data.append({
                        "キャラクター (モデル)": f"{ui['title']} ({m_name})",
                        "方向正解率": f"{m_res['direction_accuracy']*100:.1f}%",
                        "MAE (平均絶対誤差)": f"¥{m_res['mae']:,.1f}",
                        "RMSE": f"¥{m_res['rmse']:,.1f}"
                    })
                st.dataframe(pd.DataFrame(metrics_data), hide_index=True)

                # ── ニュース感情スコア ─────────────────────────
                st.markdown("---")
                sentiment = result["news_sentiment"]
                st.subheader("📰 ニュース感情スコア")
                if sentiment > 0.1:
                    st.success(f"😊 **ポジティブ** なニュースが優勢です（スコア: {sentiment:+.3f}）")
                elif sentiment < -0.1:
                    st.error(f"😟 **ネガティブ** なニュースが優勢です（スコア: {sentiment:+.3f}）")
                else:
                    st.info(f"😐 ニュースの感情は **中立** です（スコア: {sentiment:+.3f}）")
                st.caption("Google News RSS の最新20件のタイトルからキーワード分析した結果です。")

                # ── 特徴量重要度グラフ ────────────────────────
                st.markdown("---")
                st.subheader("📌 特徴量重要度 (代表: LightGBM 上位15件)")
                importance = result["models"]["LightGBM"]["feature_importance"].head(15).sort_values()
                fig_imp = go.Figure(go.Bar(
                    x=importance.values,
                    y=importance.index,
                    orientation="h",
                    marker=dict(
                        color=importance.values,
                        colorscale="Viridis"
                    )
                ))
                fig_imp.update_layout(
                    title="LightGBM 特徴量重要度 (gain)",
                    xaxis_title="重要度スコア",
                    height=500,
                    margin=dict(l=160)
                )
                st.plotly_chart(fig_imp)

                st.caption(
                    f"学習データ: {result['n_train']} 日分 / 検証データ: {result['n_test']} 日分"
                )

                st.markdown("---")
                st.subheader("💡 AIアナリストの最新ニュース")
                analysis = analyze_stock_news(adv_ticker, adv_company)
                st.info(analysis)

            except ImportError as ie:
                st.error(f"モジュールが見つかりません: {ie}")
            except Exception as e:
                st.error(f"予測中にエラーが発生しました: {e}")
                import traceback
                st.code(traceback.format_exc())

    with tab_ranking:
        st.header("🏆 100社一括予測ランキング (3モデル対応)")
        st.markdown("全100銘柄を高速に一括予測し、期待リターン（上昇率・下落率）が高い銘柄 Top 5 / Bottom 5 を表示します。※予測ターゲットは30日で固定しています。")
        
        import json
        import os
        from advanced_model import train_and_predict, get_news_sentiment
        
        ranking_file = "top_100_ranking_v2.json"
        
        selected_model = st.radio("ランキング基準のモデルを選択:", ["LightGBM (チーターくん)", "XGBoost (ライオンくん)", "Random Forest (ゾウさん)"], horizontal=True)
        model_key_map = {"LightGBM (チーターくん)": "LightGBM", "XGBoost (ライオンくん)": "XGBoost", "Random Forest (ゾウさん)": "Random Forest"}
        current_model_key = model_key_map[selected_model]
        
        # 予測実行ボタン
        if st.button("🔄 100社の一括予測を実行して最新化する (約3〜5分かかります)"):
            progress_text = st.empty()
            progress_bar = st.progress(0)
            
            # 全体ニューススコアの取得 (1回のみ)
            progress_text.text("市場全体のニュース感情スコアを取得中...")
            global_sentiment = get_news_sentiment("日本 経済 株式市場")
            progress_text.text(f"市場全体のニュース感情スコアを取得完了: {global_sentiment:+.3f}")
            
            results_list = []
            tickers_items = list(TICKERS.items())
            total = len(tickers_items)
            
            for i, (ticker, name) in enumerate(tickers_items):
                progress_text.text(f"予測中... {i+1}/{total}: {name} ({ticker})")
                progress_bar.progress((i + 1) / total)
                
                try:
                    res = train_and_predict(ticker, name, fast_mode=True, global_sentiment=global_sentiment, target_days=30)
                    
                    def clean_model_data(m_data):
                        if not m_data: return None
                        return {
                            "predicted_price": float(m_data["predicted_price"]),
                            "predicted_return": float(m_data["predicted_return"])
                        }
                        
                    results_list.append({
                        "ticker": ticker,
                        "name": name,
                        "current_price": float(res["current_price"]),
                        "models": {
                            "LightGBM": clean_model_data(res["models"].get("LightGBM")),
                            "XGBoost": clean_model_data(res["models"].get("XGBoost")),
                            "Random Forest": clean_model_data(res["models"].get("Random Forest"))
                        }
                    })
                except Exception as e:
                    print(f"Skipped {ticker} ({name}) due to error: {e}")
                    
            progress_text.text("全銘柄の予測が完了しました！結果を保存しています...")
            
            save_data = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "global_sentiment": global_sentiment,
                "ranking": results_list
            }
            with open(ranking_file, "w", encoding="utf-8") as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
                
            progress_bar.empty()
            progress_text.empty()
            st.success("全ての予測とランキングの更新が完了しました！")
            
        # JSONからランキングを読み込んで表示
        if os.path.exists(ranking_file):
            try:
                with open(ranking_file, "r", encoding="utf-8") as f:
                    ranking_data = json.load(f)
                    
                st.caption(f"📅 最終更新: {ranking_data['timestamp']} / 🌍 市場全体感情スコア: {ranking_data.get('global_sentiment', 0.0):+.3f}")
                
                rankings = ranking_data.get("ranking", [])
                valid_rankings = [r for r in rankings if r.get("models", {}).get(current_model_key) is not None]
                valid_rankings = sorted(valid_rankings, key=lambda x: x["models"][current_model_key]["predicted_return"], reverse=True)
                
                if len(valid_rankings) >= 5:
                    top5 = valid_rankings[:5]
                    bottom5 = valid_rankings[-5:]
                    bottom5.reverse() # 最も悪いものを1位にする
                    
                    st.markdown("---")
                    st.subheader(f"🚀 パフォーマンス期待 Top 5 ({selected_model})")
                    cols_top = st.columns(5)
                    for i, r in enumerate(top5):
                        with cols_top[i]:
                            st.markdown(f"**{i+1}位 {r['name']}**")
                            st.caption(f"{r['ticker']} / ¥{r['current_price']:,.1f}")
                            mod_data = r["models"][current_model_key]
                            st.metric(
                                label="30日後予測",
                                value=f"¥{mod_data['predicted_price']:,.1f}",
                                delta=f"{mod_data['predicted_return']*100:+.2f}%"
                            )
                            
                    st.markdown("---")
                    st.subheader(f"⚠️ 下落警戒 Bottom 5 ({selected_model})")
                    cols_bot = st.columns(5)
                    for i, r in enumerate(bottom5):
                        with cols_bot[i]:
                            st.markdown(f"**ワースト{i+1}位 {r['name']}**")
                            st.caption(f"{r['ticker']} / ¥{r['current_price']:,.1f}")
                            mod_data = r["models"][current_model_key]
                            st.metric(
                                label="30日後予測",
                                value=f"¥{mod_data['predicted_price']:,.1f}",
                                delta=f"{mod_data['predicted_return']*100:+.2f}%"
                            )
            except Exception as e:
                st.error(f"ランキング結果の読み込みに失敗しました: {e}")
        else:
            st.info("上のボタンを押して100社の一括予測を実行してください。")

    with tab_new:
        st.header("📊 モデル精度分析レポート (直近10年データ検証)")
        st.markdown("現在の過去10年分の生データを用いて、3つの機械学習モデルを学習・検証（直近20%をテストに使用）した結果です。")
        
        try:
            import json
            with open("models_evaluation.json", "r", encoding="utf-8") as f:
                eval_data = json.load(f)
            
            # --- 指標グラフ ---
            models = ["LightGBM", "XGBoost", "Random Forest"]
            avg_rmse = [eval_data[m]["avg_rmse"] for m in models]
            avg_acc = [eval_data[m]["avg_dir_acc"] for m in models]
            
            col_acc, col_rmse = st.columns(2)
            with col_acc:
                fig_acc = go.Figure(data=[go.Bar(x=models, y=avg_acc, marker_color=['#1f77b4', '#ff7f0e', '#2ca02c'])])
                fig_acc.update_layout(title="平均方向正解率 (%)", yaxis_range=[40, 60], height=300)
                st.plotly_chart(fig_acc)
            with col_rmse:
                fig_err = go.Figure(data=[go.Bar(x=models, y=avg_rmse, marker_color=['#1f77b4', '#ff7f0e', '#2ca02c'])])
                fig_err.update_layout(title="平均RMSE（予測誤差の目安 円）", height=300)
                st.plotly_chart(fig_err)
                
            st.caption(f"※ 対象銘柄数: {eval_data['metadata']['evaluated_companies']} 社 / 最終評価日時: {eval_data['metadata']['timestamp'][:10]}")
            
        except FileNotFoundError:
            st.warning("事前評価用データ（models_evaluation.json）が見つかりません。")
            
        st.markdown("---")
        st.subheader("📝 各モデルの特徴と得意なシーン（分析メモ）")
        st.markdown(
            "事前に検証した結果とアルゴリズムの性質から、各モデルには以下のような特徴が見られました。\n\n"
            "#### 🐆 チーターくん (LightGBM)\n"
            "- **得意な場面**: 株価が短期間で細かい上下を繰り返すときや、**ニュース等で相場が急変した直後**。\n"
            "- **精度傾向**: 全体的な方向感（上がるか下がるか）を当てるのが得意で、直近のラグ特徴量やS&P500などの市場指標によく反応します。\n"
            "- **弱点**: 学習速度は非常に速いですが、外れ値（異常な株価変動）に過剰に引っ張られることがあります。\n\n"
            "#### 🦁 ライオンくん (XGBoost)\n"
            "- **得意な場面**: RSIやボリンジャーバンドなど、**テクニカル指標の一定のパターン**が出たときに強い威力を発揮します。\n"
            "- **精度傾向**: 誤差が少なく安定感があり、LightGBMと同様に高い方向正解率を誇ります。過学習を抑える仕組みが強く、**堅実な予測**を行います。\n\n"
            "#### 🐘 ゾウさん (Random Forest)\n"
            "- **得意な場面**: データにノイズが多く、他のモデルが迷ってしまうような**荒れた相場環境**。\n"
            "- **精度傾向**: トレンドの外れ値に強く極端な予測をしないため大きな失敗は少ないですが、アンサンブル(平均化)の性質上、大きく上がる・下がるという変化をやや過小評価（マイルドに予測）しやすい傾向があります。方向の正答率はブースティング系(LGBM/XGB)より少し劣る傾向があります。"
        )

    with tab2:
        st.header("🤖 AIセンチメント分析 - 本日のマーケット洞察")
        st.markdown(
            "本日の主要経済ニュースを自動収集し、**OpenAI GPT** が投資家目線でマーケットへの影響を分析します。"
            "**上昇が期待される業界・企業**と**下落が懸念される業界・企業**を一目で確認できます。"
        )

        col_run, col_info = st.columns([1, 3])
        run_analysis = col_run.button("🔄 今日の分析を実行", key="run_sentiment", type="primary")
        col_info.caption(
            f"📅 分析基準日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M')} / "
            "同じ日の2回目以降は**キャッシュ**から即時表示されます"
        )

        @st.cache_data(ttl=3600, show_spinner=False)
        def cached_sentiment_analysis():
            from news_sentiment import run_sentiment_analysis
            return run_sentiment_analysis()

        if run_analysis:
            with st.spinner("📰 本日のニュースを収集してAIが分析中... (20〜40秒)"):
                result = cached_sentiment_analysis()

            if result.get("error"):
                st.error(f"❌ エラー: {result['error']}")
            else:
                analysis = result["analysis"]
                news_list = result["news"]

                # ── 市場全体の総評 ──────────────────────────
                st.markdown("---")
                st.subheader("📋 本日のマーケット総評")
                overview = analysis.get("market_overview", "取得できませんでした")
                st.info(f"💬 {overview}")

                # ── 上昇 / 下落 業界・企業 (2カラム展開) ──────
                st.markdown("---")
                col_bull, col_bear = st.columns(2)

                with col_bull:
                    st.subheader("📈 上昇が期待される業界・企業")
                    bullish = analysis.get("bullish_sectors", [])
                    if not bullish:
                        st.info("該当なし")
                    for item in bullish:
                        with st.container(border=True):
                            st.markdown(f"### 🚀 {item.get('name', '')}")
                            st.success(item.get("reason", ""))

                with col_bear:
                    st.subheader("📉 下落が懸念される業界・企業")
                    bearish = analysis.get("bearish_sectors", [])
                    if not bearish:
                        st.info("該当なし")
                    for item in bearish:
                        with st.container(border=True):
                            st.markdown(f"### ⚠️ {item.get('name', '')}")
                            st.error(item.get("reason", ""))

                # ── 注目ニュース ────────────────────────────
                st.markdown("---")
                st.subheader("🔑 本日の注目ニュースと市場インパクト")
                key_news = analysis.get("key_news", [])
                for news in key_news:
                    with st.expander(f"📰 {news.get('headline', '')}"):
                        st.markdown(f"**💡 市場への影響**: {news.get('impact', '')}")

                # ── アナリストコメント ────────────────────────
                st.markdown("---")
                st.subheader("🧑‍💼 AIアナリストの総合コメント")
                comment = analysis.get("analyst_comment", "")
                st.warning(f"📌 {comment}")

                # ── 取得したニュース一覧 ──────────────────────
                st.markdown("---")
                with st.expander(f"📄 分析に使用したニュース一覧 ({len(news_list)} 件)"):
                    for i, item in enumerate(news_list):
                        st.markdown(f"{i+1}. [{item['title']}]({item['link']})")
                        if item.get('published'):
                            st.caption(f"　　{item['published']}")

        else:
            st.markdown(
                """<div style='text-align:center; padding: 60px 0; color: #888;'>
                <h2>🤖</h2>
                <p>「今日の分析を実行」ボタンを押すと、本日の主要ニュースを収集して<br>
                AIが投資家目線でマーケットを分析します。</p>
                </div>""",
                unsafe_allow_html=True
            )


    with tab5:
        st.header("💰 デモトレード（シミュレーション）")
        st.markdown(
            "Google Sheetsをバックエンドとして、指定した銘柄の仮想売買シミュレーションを行います。<br>"
            "※実際の取引ではありませんので、投資の練習にお使いください。",
            unsafe_allow_html=True
        )
        
        # データベース操作モジュールの読み込み
        import demo_trade_db
        
        # データベース初期化ボタン
        col_init, _ = st.columns([1, 4])
        with col_init:
            if st.button("🔄 取引DBの初期化・接続確認", key="init_demo_db", help="初回のみ実行してスプレッドシートのシートを作成します"):
                with st.spinner("シートを作成・確認しています..."):
                    if demo_trade_db.init_demo_db():
                        st.success("初期化が完了しました。")
                    else:
                        st.error("初期化に失敗しました。認証情報などを確認してください。")
                
        # 現在の資産状況・ポートフォリオ
        st.markdown("---")
        st.subheader("🏦 現在の資産状況")
        
        # キャッシュを用いた効率的な取得 (Streamlitのrerun時に毎回DBアクセスするのを防ぐ設計も可能だが、今回は直接取得)
        username = st.session_state["username"]
        df_portfolio = demo_trade_db.get_portfolio(username)
        df_transactions = demo_trade_db.get_transactions(username)
        
        cash = 0
        if not df_portfolio.empty and "CASH" in df_portfolio["Ticker"].values:
            cash_row = df_portfolio[df_portfolio["Ticker"] == "CASH"]
            if not cash_row.empty:
                try:
                    cash = float(cash_row["Quantity"].iloc[0])
                except ValueError:
                    cash = 0.0
                
        # =================================================
        # 📊 総資産の推移 (現金 + 株式評価額)
        # =================================================
        st.markdown("---")
        st.subheader("📊 総資産の推移")
        
        current_total_asset = cash
        
        try:
            df_tx = df_transactions.copy()
            if not df_tx.empty:
                df_tx['Timestamp'] = pd.to_datetime(df_tx['Timestamp']).dt.date
                df_hist_all = pd.read_csv("stock_historical.csv", parse_dates=["Date"])
                df_hist_all['Date'] = df_hist_all['Date'].dt.date
                
                min_date = df_tx['Timestamp'].min()
                max_date = pd.Timestamp.now().date()
                date_range = pd.date_range(start=min_date, end=max_date).date
                
                asset_history = []
                current_sim_cash = 0.0
                current_portfolio = {} # ticker -> qty
                
                tx_grouped = df_tx.groupby('Timestamp')
                last_prices = {} # fallback for weekends
                
                for d in date_range:
                    # 1. Update portfolio from transactions on this day
                    if d in tx_grouped.groups:
                        day_txs = tx_grouped.get_group(d)
                        for _, row in day_txs.iterrows():
                            tx_type = str(row['Type']).upper()
                            tx_ticker = str(row['Ticker'])
                            amt = float(row['Total Amount'])
                            tx_qty = float(row.get('Quantity', 0))
                            
                            if tx_type == "DEPOSIT":
                                current_sim_cash += amt
                            elif tx_type == "BUY":
                                current_sim_cash -= amt
                                current_portfolio[tx_ticker] = current_portfolio.get(tx_ticker, 0) + tx_qty
                            elif tx_type == "SELL":
                                current_sim_cash += amt
                                current_portfolio[tx_ticker] = current_portfolio.get(tx_ticker, 0) - tx_qty
                                if current_portfolio[tx_ticker] <= 0:
                                    del current_portfolio[tx_ticker]
                                    
                    # 2. End of day valuation
                    stock_value = 0.0
                    day_data = df_hist_all[df_hist_all['Date'] == d]
                    
                    for port_ticker, port_qty in current_portfolio.items():
                        price_row = day_data[day_data['Ticker'] == port_ticker]
                        if not price_row.empty:
                            p = float(price_row['Close'].iloc[0])
                            last_prices[port_ticker] = p
                        else:
                            p = last_prices.get(port_ticker, 0.0)
                        stock_value += p * port_qty
                        
                    total_asset = current_sim_cash + stock_value
                    asset_history.append({'Date': d, 'Total Asset': total_asset, 'Cash': current_sim_cash, 'Stock Value': stock_value})
                    
                df_asset = pd.DataFrame(asset_history)
                if not df_asset.empty:
                    # 履歴に初期入金が記録されていない分のズレを補正（現在の実際の現金残高との差分を加算）
                    cash_offset = cash - current_sim_cash
                    df_asset['Cash'] += cash_offset
                    df_asset['Total Asset'] += cash_offset
                    current_total_asset = df_asset.iloc[-1]['Total Asset']
                
                # Display Metrics side by side
                col_asset, col_cash, col_add = st.columns([1.5, 1, 1.5])
                with col_asset:
                    st.metric(label="現在の総資産 (評価額合計)", value=f"¥ {current_total_asset:,.0f}")
                with col_cash:
                    st.metric(label="現金残高 (JPY Cash)", value=f"¥ {cash:,.0f}")
                with col_add:
                    expander = st.expander("💸 資金(100万円)を追加")
                    with expander:
                        if st.button("1,000,000円 を追加", help="デモトレード用の仮想資金を追加します"):
                            with st.spinner("入金処理中..."):
                                success, msg = demo_trade_db.add_cash(username, 1000000)
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                
                # Render Asset Graph
                fig_asset = go.Figure()
                fig_asset.add_trace(go.Scatter(x=df_asset['Date'], y=df_asset['Total Asset'], mode='lines', name='総資産', stackgroup='one', fillcolor='rgba(44, 160, 44, 0.3)', line=dict(color='rgb(44, 160, 44)')))
                fig_asset.update_layout(
                    height=300,
                    margin=dict(l=0, r=0, t=10, b=0),
                    yaxis_title="評価額 (円)",
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
                    yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)')
                )
                st.plotly_chart(fig_asset)
            else:
                # No transactions fallback
                col_asset, col_cash, col_add = st.columns([1.5, 1, 1.5])
                with col_asset:
                    st.metric(label="現在の総資産 (評価額合計)", value=f"¥ {current_total_asset:,.0f}")
                with col_cash:
                    st.metric(label="現金残高 (JPY Cash)", value=f"¥ {cash:,.0f}")
                with col_add:
                    expander = st.expander("💸 資金(100万円)を追加")
                    with expander:
                        if st.button("1,000,000円 を追加"):
                            with st.spinner("入金処理中..."):
                                success, msg = demo_trade_db.add_cash(username, 1000000)
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                st.info("取引履歴がないため、推移グラフは表示されません。")
        except Exception as e:
            st.error(f"グラフ描画エラー: {e}")
        st.markdown("---")
        st.subheader("🛒 取引 (売買)")
        
        # 銘柄選択
        trade_input_mode = st.radio("選択方式", ["リストから選択 (カテゴリー式)", "直接入力 (予測変換式)"], key="trade_input_mode")
        
        # セッションステート同期用の初期値
        default_ticker = "7203.T"
        if "adv_ticker" in st.session_state:
            default_ticker = st.session_state["adv_ticker"]
            
        if "リスト" in trade_input_mode:
            sector_options = list(SECTORS.keys())
            
            # デフォルト銘柄が属するセクターを探す
            default_sector_idx = 0
            for i, (sec, tickers_in_sec) in enumerate(SECTORS.items()):
                if default_ticker in tickers_in_sec:
                    default_sector_idx = i
                    break
                    
            selected_sector = st.selectbox("業界カテゴリー", sector_options, index=default_sector_idx, key="trade_sector_sel")
            
            ticker_list_for_sector = SECTORS[selected_sector]
            trade_options = [f"{code}: {TICKERS.get(code, '不明')}" for code in ticker_list_for_sector]
            
            # デフォルト銘柄のインデックスを探す
            trade_selected_idx = 0
            for i, opt in enumerate(trade_options):
                if opt.startswith(default_ticker):
                    trade_selected_idx = i
                    break
                    
            if not trade_options:
                trade_options = ["-: 銘柄なし"]
                trade_selected_idx = 0
                
            trade_ticker_sel = st.selectbox("銘柄選択", trade_options, index=trade_selected_idx, key="trade_ticker_main_sel")
            trade_ticker = trade_ticker_sel.split(":")[0].strip()
            trade_company = TICKERS.get(trade_ticker, "指定銘柄")
            st.session_state["adv_ticker"] = trade_ticker
            
        else:
            search_text = st.text_input("企業名やコードの一部を入力 (予測変換)", placeholder="例: トヨタ, 7203", key="trade_search_text")
            
            trade_options = []
            if search_text:
                q = search_text.lower()
                candidates = {k: v for k, v in TICKERS.items() if q in k.lower() or q in v.lower()}
                trade_options = [f"{code}: {name}" for code, name in candidates.items()]
                
                # 入力されたテキストと完全に一致するティッカーが見つからなかった場合、手動入力用アイテムとして追加
                if not any(q == k.lower() for k in candidates.keys()) and len(q) > 0:
                    trade_options.insert(0, f"{search_text.upper()}: (独自指定銘柄)")
            else:
                trade_options = [f"{code}: {name}" for code, name in TICKERS.items()]
                
            # デフォルトの選択
            trade_selected_idx = 0
            if not search_text and trade_options:
                for i, opt in enumerate(trade_options):
                    if opt.startswith(default_ticker):
                        trade_selected_idx = i
                        break
                        
            if not trade_options:
                trade_options = [f"{default_ticker}: 検索中"]

            trade_ticker_sel = st.selectbox("検索結果から選択:", trade_options, index=trade_selected_idx, key="trade_ticker_direct_sel")
            trade_ticker = trade_ticker_sel.split(":")[0].strip()
            trade_company = TICKERS.get(trade_ticker, "指定銘柄")
            st.session_state["adv_ticker"] = trade_ticker
        
        # 選択された銘柄の最新株価と保有株数を取得
        current_price = 0
        df_stock = None
        
        if st.button("⬇️ 選択中銘柄の最新株価を手動で取得 (yfinance)", key="trade_fetch_latest"):
            from model_utils import fetch_latest_data_manual
            with st.spinner(f"{trade_company} の最新データを手動取得しています..."):
                success, msg = fetch_latest_data_manual(trade_ticker)
            if success:
                st.success(msg)
            else:
                st.error(msg)
                
        with st.spinner(f"{trade_company} の株価データを取得中..."):
            try:
                from model_utils import get_stock_data
                df_stock = get_stock_data(trade_ticker)
                if df_stock is not None and not df_stock.empty:
                    current_price = df_stock['Close'].iloc[-1]
                else:
                    st.error("株価データの取得に失敗しました。")
            except Exception as e:
                st.error(f"エラー: {e}")
                
        # ユーザーの保有株数
        owned_shares = 0
        if not df_portfolio.empty and trade_ticker in df_portfolio["Ticker"].values:
            ticker_row = df_portfolio[df_portfolio["Ticker"] == trade_ticker]
            if not ticker_row.empty:
                try:
                    owned_shares = int(ticker_row["Quantity"].iloc[0])
                except ValueError:
                    pass
        
        col_price, col_owned = st.columns(2)
        with col_price:
            st.metric(label="現在の株価（直近終値）", value=f"¥ {current_price:,.1f}")
        with col_owned:
            st.metric(label="現在保有している株数", value=f"{owned_shares} 株")
            
        qty = st.number_input("数量（株）", min_value=1, step=100, value=100)
        total_estimate = current_price * qty
        st.write(f"**取引概算金額:** ¥ {total_estimate:,.0f}")
        
        col_buy, col_sell = st.columns(2)
        with col_buy:
            if st.button("🟢 買い注文 (BUY)", type="primary"):
                if current_price > 0:
                    with st.spinner("買い注文を処理中..."):
                        success, msg = demo_trade_db.buy_stock(username, trade_ticker, trade_company, current_price, qty)
                    if success:
                        st.success(f"{trade_company} を {qty}株 買付しました。")
                        st.rerun() # リロードして資産残高を更新
                    else:
                        st.error(msg)
        with col_sell:
            if st.button("🔴 売り注文 (SELL)"):
                if current_price > 0:
                    with st.spinner("売り注文を処理中..."):
                        success, msg = demo_trade_db.sell_stock(username, trade_ticker, trade_company, current_price, qty)
                    if success:
                        st.success(f"{trade_company} を {qty}株 売却しました。")
                        st.rerun()
                    else:
                        st.error(msg)

        st.markdown("---")
        st.subheader("💼 保有銘柄 (Portfolio)")
        if not df_portfolio.empty:
            # CASH以外の銘柄を表示し、数量が0のものは除外
            df_portfolio['Quantity'] = pd.to_numeric(df_portfolio['Quantity'], errors='coerce').fillna(0)
            port_view = df_portfolio[(df_portfolio["Ticker"] != "CASH") & (df_portfolio["Quantity"] > 0)]
            if not port_view.empty:
                # 評価額と含み損益の計算列を追加することも可能
                st.dataframe(port_view)
            else:
                st.info("現在保有している株式はありません。")
        else:
            st.info("データがありません。取引DBの初期化を行ってください。")
                
        st.markdown("---")
        st.subheader("📋 取引履歴 (Transactions)")
        if not df_transactions.empty:
            # 最新の履歴から表示 (降順)
            st.dataframe(df_transactions.iloc[::-1], hide_index=True)
        else:
            st.info("取引履歴はありません。")

if __name__ == "__main__":
    main()
