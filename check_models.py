import google.generativeai as genai
import os
from dotenv import load_dotenv

# 環境変数読み込み
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    print("❌ GOOGLE_API_KEYが設定されていません")
    print("サイドバーから入力するか、.envファイルを作成してください")
    exit(1)

# API設定
genai.configure(api_key=GOOGLE_API_KEY)

print("=" * 60)
print("📋 利用可能なGeminiモデル一覧")
print("=" * 60)

try:
    models = genai.list_models()

    vision_models = []
    generation_models = []
    other_models = []

    for model in models:
        model_name = model.name.replace('models/', '')

        # サポートされているメソッドを確認
        supported_methods = [method for method in model.supported_generation_methods]

        print(f"\n🔹 {model_name}")
        print(f"   サポート機能: {', '.join(supported_methods)}")

        # Vision（画像解析）対応モデル
        if 'generateContent' in supported_methods:
            if 'vision' in model_name.lower() or 'pro' in model_name.lower():
                vision_models.append(model_name)

        # 画像生成対応モデル
        if 'imagen' in model_name.lower() or 'generate' in model_name.lower():
            generation_models.append(model_name)

    print("\n" + "=" * 60)
    print("📊 推奨モデル")
    print("=" * 60)

    if vision_models:
        print(f"\n🖼️  Vision（画像解析）用:")
        for m in vision_models[:3]:  # 上位3つ
            print(f"   - {m}")

    if generation_models:
        print(f"\n🎨 画像生成用:")
        for m in generation_models[:3]:  # 上位3つ
            print(f"   - {m}")

    print("\n" + "=" * 60)

except Exception as e:
    print(f"❌ エラー: {e}")
