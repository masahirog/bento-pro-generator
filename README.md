# Bento Pro Generator

弁当の写真をアップロードするだけで、商業用プロ写真に自動変換するWebアプリケーション

## 機能概要

- スマホで撮影した弁当写真を自動解析
- プロ仕様の構図・ライティングで画像を再生成
- Google Gemini 3 Pro Image API を使用した高品質な画像生成

## 技術スタック

- **Python 3.10+**
- **Streamlit** - WebUIフレームワーク
- **Google GenAI SDK (google-genai)** - 最新のGemini API SDK
- **Pillow** - 画像処理

## セットアップ手順

### 1. Google API Keyの取得

1. [Google AI Studio](https://aistudio.google.com/app/apikey) にアクセス
2. 「Create API Key」をクリックしてAPIキーを取得
3. 取得したAPIキーをコピー

### 2. 環境構築

```bash
cd bento-pro-generator

# 仮想環境の作成（推奨）
python -m venv venv
source venv/bin/activate  # Windowsの場合: venv\Scripts\activate

# 依存パッケージのインストール
pip install -r requirements.txt
```

### 3. 環境変数の設定

```bash
# .env.exampleをコピーして.envファイルを作成
cp .env.example .env

# .envファイルを編集してAPIキーを設定
# GOOGLE_API_KEY=取得したAPIキーをここに貼り付け
```

### 4. アプリの起動

```bash
streamlit run app.py
```

ブラウザが自動的に開き、`http://localhost:8501` でアプリが起動します。

## 使い方

1. サイドバーにGoogle API Keyを入力（.envで設定済みの場合は不要）
2. 弁当の写真をアップロード
3. 「プロ写真に変換」ボタンをクリック
4. 生成された画像をダウンロード

## アプリの処理フロー

### Step 1: 画像解析（Vision API）
- **Gemini 2.5 Flash** を使用（Thinking mode無効化で高速化）
- 弁当の中身（食材・配置）をテキスト化
- 最大3倍の速度向上を実現

### Step 2: プロンプト合成
- 固定プロンプト（構図・ライティング）と解析結果を結合
- プロ仕様の撮影指示を自動生成

### Step 3: 画像生成（Image Generation API）
- **Gemini 3 Pro Image** を使用して高品質画像を生成
- 8k解像度、スタジオライティング相当の仕上がり

## プロンプト構成

### 固定部分（スタイル・ライティング）
```
Professional commercial food photography. High-angle diagonal shot (approx 45 degrees).
The bento box is placed on a clean white background and rotated slightly diagonally to create depth.
It is NOT placed parallel to the frame.

Bright, even studio lighting (high-key). Soft shadows.
The food looks fresh, glossy, warm, and appetizing. 8k resolution, highly detailed.
```

### 可変部分（解析結果）
```
Content: A Japanese bento box containing [解析された食材リスト].
Maintain the original food arrangement inside the box.
```

## トラブルシューティング

### API Keyエラー
- Google AI Studioで正しいAPIキーが取得できているか確認
- .envファイルまたはサイドバーに正しく設定されているか確認

### モデルが見つからないエラー
- `imagen-3.0-generate-001` モデルがアカウントで利用可能か確認
- 必要に応じて `gemini-1.5-pro` などの代替モデルに変更

### 画像生成が遅い
- Gemini APIの応答には時間がかかる場合があります（30秒〜2分程度）
- ネットワーク環境を確認してください
- Vision解析はThinking mode無効化により高速化されています

## Streamlit Cloudへのデプロイ

### 1. GitHubへのpush

```bash
# Gitリポジトリの初期化（初回のみ）
git init
git add .
git commit -m "Initial commit"

# リモートリポジトリの設定
git remote add origin https://github.com/masahirog/bento-pro-generator.git
git branch -M main
git push -u origin main
```

### 2. Streamlit Cloudでのデプロイ

1. [Streamlit Cloud](https://share.streamlit.io/) にアクセス
2. GitHubアカウントでログイン
3. 「New app」をクリック
4. リポジトリ: `masahirog/bento-pro-generator`
5. Branch: `main`
6. Main file path: `app.py`
7. 「Advanced settings」をクリックして環境変数を設定:
   - `GOOGLE_API_KEY`: Google AI StudioのAPIキー
   - `AWS_ACCESS_KEY_ID`: AWS アクセスキー
   - `AWS_SECRET_ACCESS_KEY`: AWS シークレットキー
   - `S3_BUCKET_NAME`: S3バケット名
   - `S3_REGION`: S3リージョン（例: ap-northeast-1）
8. 「Deploy!」をクリック

### 3. デプロイ後の確認

- アプリが起動するまで数分かかります
- デプロイが完了すると、公開URLが発行されます
- 環境変数が正しく設定されているか確認してください

## 今後の拡張予定

- [x] 複数スタイルの選択機能（背景、角度、照明、余白、向き）
- [x] AWS S3への履歴保存機能
- [ ] バッチ処理（複数画像の一括変換）
- [ ] ユーザー設定のプリセット保存機能

## ライセンス

MIT License

## 開発者

Bento Pro Generator v1.0
Powered by Google Gemini 3 Pro Image
