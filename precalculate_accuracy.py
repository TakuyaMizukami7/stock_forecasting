import json
import os
import time
from model_utils import evaluate_model

TICKERS = {
    '7203.T': 'トヨタ自動車',
    '6758.T': 'ソニーグループ',
    '9984.T': 'ソフトバンクグループ',
    '9432.T': '日本電信電話',
    '8306.T': '三菱UFJFG',
    '6861.T': 'キーエンス',
    '6098.T': 'リクルートHD',
    '4063.T': '信越化学工業',
    '8035.T': '東京エレクトロン',
    '7974.T': '任天堂',
    '8001.T': '伊藤忠商事',
    '7267.T': 'ホンダ',
    '8316.T': '三井住友FG',
    '6902.T': 'デンソー',
    '4502.T': '武田薬品工業',
    '6954.T': 'ファナック',
    '6501.T': '日立製作所',
    '8411.T': 'みずほFG',
    '6367.T': 'ダイキン工業',
    '4568.T': '第一三共'
}

def main():
    print("Pre-calculating model accuracy for 2016-01-01 to 2025-12-31...")
    accuracies = {}
    total = len(TICKERS)
    for i, (code, name) in enumerate(TICKERS.items()):
        print(f"[{i+1}/{total}] Processing {name} ({code})...")
        try:
            acc = evaluate_model(code, start="2016-01-01", end="2025-12-31")
            if acc is not None:
                accuracies[name] = acc * 100
            else:
                print(f"Skipping {name}: Data insufficient.")
        except Exception as e:
            print(f"Error processing {name}: {e}")
            
    with open("precomputed_accuracy.json", "w", encoding="utf-8") as f:
        json.dump(accuracies, f, ensure_ascii=False, indent=2)
        
    print("Saved results to precomputed_accuracy.json.")

if __name__ == "__main__":
    main()
