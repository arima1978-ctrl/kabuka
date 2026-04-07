# kabuka

東証プライム市場の指定期間における値下がり率上位20社を抽出し、配当・売上を付与して Telegram に返信する Bot。

## 構成

- **データ源**: [J-Quants API](https://jpx-jquants.com/)（JPX公式、Lightプラン以上推奨）
- **実行環境**: `skyuser@192.168.1.16`
- **通知**: Telegram Bot（専用チャンネル）

## ファイル

| ファイル | 役割 |
|---|---|
| `jquants.py` | J-Quants API クライアント（認証・エンドポイント） |
| `analyze.py` | プライム銘柄の期間値下がり率計算・Top20抽出・財務付与 |
| `format.py` | Telegram 用 Markdown 整形（3種の表） |
| `bot.py` | Telegram 受信・返信のメインループ |
| `kabuka-bot.service` | systemd 常駐化ユニット |
| `.env.example` | 認証情報テンプレート |

## セットアップ（skyuser@192.168.1.16）

```bash
cd ~
git clone https://github.com/arima1978-ctrl/kabuka.git
cd kabuka
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env に J-Quants / Telegram の認証情報を記入

# 常駐化
sudo cp kabuka-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kabuka-bot
sudo systemctl status kabuka-bot
```

## 使い方

Telegram チャンネルに Bot を追加し、期間を送信：

```
2026-03-01 2026-03-31
```

以下のいずれかの形式に対応：
- `2026-03-01 2026-03-31`
- `2026/03/01 - 2026/03/31`
- `20260301 20260331`

## 出力形式

1. 値下がり率 上位20社
2. 配当利回り順（上位20社内）
3. 売上高順（上位20社内）

結果の生 JSON は `data/{from}_{to}_{timestamp}.json` に保存されます。

## 注意

- J-Quants Free プランは株価が12週遅延、かつ財務データ (`/fins/statements`) は取得不可。Light プラン（月1,650円）以上が必要です。
- 期間の `from` / `to` は営業日を指定してください（非営業日だと該当日の株価が取れません）。
- プライム市場の判定は `MarketCode == "0111"` を使用。
