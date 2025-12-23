import streamlit as st
from google import genai
from google.genai import types
from PIL import Image, ImageOps
import io
import os
from dotenv import load_dotenv
import base64
import time
import json
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# 環境変数の読み込み
load_dotenv()

# Gemini API設定
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    client = genai.Client(api_key=GOOGLE_API_KEY)
else:
    client = None

# AWS S3設定
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_REGION = os.getenv("S3_REGION")


# S3クライアント初期化
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=S3_REGION
    )
else:
    s3_client = None

# ページ設定
st.set_page_config(
    page_title="Bento Pro Generator",
    layout="wide"
)

# S3ヘルパー関数
def save_image_to_s3(image, key):
    """画像をS3にアップロード"""
    if not s3_client:
        return False
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        s3_client.upload_fileobj(
            img_byte_arr,
            S3_BUCKET_NAME,
            key,
            ExtraArgs={'ContentType': 'image/png'}
        )
        return True
    except ClientError as e:
        st.error(f"S3アップロードエラー: {str(e)}")
        return False

def save_metadata_to_s3(metadata, key):
    """メタデータ(JSON)をS3にアップロード"""
    if not s3_client:
        return False
    try:
        metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=key,
            Body=metadata_json.encode('utf-8'),
            ContentType='application/json'
        )
        return True
    except ClientError as e:
        st.error(f"S3アップロードエラー: {str(e)}")
        return False

def get_image_from_s3(key):
    """S3から画像を取得"""
    if not s3_client:
        return None
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=key)
        return Image.open(io.BytesIO(response['Body'].read()))
    except ClientError as e:
        st.error(f"S3ダウンロードエラー: {str(e)}")
        return None

def get_metadata_from_s3(key):
    """S3からメタデータ(JSON)を取得"""
    if not s3_client:
        return None
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=key)
        return json.loads(response['Body'].read().decode('utf-8'))
    except ClientError as e:
        st.error(f"S3ダウンロードエラー: {str(e)}")
        return None

def list_history_from_s3():
    """S3から履歴一覧を取得"""
    if not s3_client:
        return []
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME, Delimiter='/')
        if 'CommonPrefixes' not in response:
            return []
        folders = [prefix['Prefix'].rstrip('/') for prefix in response['CommonPrefixes']]
        return sorted(folders, reverse=True)
    except ClientError as e:
        st.error(f"S3リストエラー: {str(e)}")
        return []

def get_image_bytes_from_s3(key):
    """S3から画像のバイナリデータを取得（ダウンロードボタン用）"""
    if not s3_client:
        return None
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=key)
        return response['Body'].read()
    except ClientError as e:
        st.error(f"S3ダウンロードエラー: {str(e)}")
        return None

# セッションステート初期化
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'generation_completed' not in st.session_state:
    st.session_state.generation_completed = False
if 'current_uploaded_file' not in st.session_state:
    st.session_state.current_uploaded_file = None

# 履歴フォルダの作成
HISTORY_DIR = "history"
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)


# サイドバー：AI加工ボタンと履歴
with st.sidebar:
    # AI加工ボタン
    if st.button("TOP", use_container_width=True, type="primary"):
        st.session_state.selected_history = None
        st.rerun()

    st.markdown("---")

    # S3から履歴一覧を取得
    history_folders = list_history_from_s3()

    if history_folders:
        st.markdown(f"**履歴 {len(history_folders)}件**")

        # 最新10件をボタンとして表示
        for folder in history_folders[:10]:
            if st.button(f"{folder}", key=f"hist_{folder}", use_container_width=True):
                st.session_state.selected_history = folder
                st.rerun()
    else:
        st.info("まだ履歴がありません")

# CSS: フォントサイズ縮小
st.markdown("""
<style>
[data-testid="stMetricValue"] {
    font-size: 1.2rem;
}
[data-testid="stMetricLabel"] {
    font-size: 0.85rem;
}
h3 {
    font-size: 1.1rem;
    margin-top: 1rem;
    margin-bottom: 0.5rem;
}
/* アンカーリンクアイコンを非表示 */
h1 a, h2 a, h3 a, h4 a {
    display: none !important;
}
.css-15zrgzn {
    display: none !important;
}
</style>
""", unsafe_allow_html=True)

# メインエリア
# 履歴が選択されている場合は履歴詳細を表示
if 'selected_history' in st.session_state and st.session_state.selected_history:
    st.markdown(f"**履歴詳細:** `{st.session_state.selected_history}`")

    # S3から履歴データを読み込む
    timestamp = st.session_state.selected_history

    with st.spinner("履歴データを読み込み中..."):
        metadata = get_metadata_from_s3(f"{timestamp}/metadata.json")

    if metadata:
        # 設定情報表示
        st.markdown("### 設定情報")
        col_info1, col_info2, col_info3, col_info4, col_info5 = st.columns(5)
        with col_info1:
            st.metric("背景", metadata.get('background', 'N/A'))
        with col_info2:
            st.metric("角度", metadata.get('angle', 'N/A'))
        with col_info3:
            st.metric("照明", metadata.get('lighting', 'N/A'))
        with col_info4:
            st.metric("余白", metadata.get('margin', 'N/A'))
        with col_info5:
            st.metric("向き", metadata.get('rotation', 'N/A'))

        st.metric("処理時間", f"{metadata.get('total_time', 0):.2f}秒")

        # 画像表示（列幅調整で中央寄せ）
        st.markdown("### 画像比較")
        col_spacer1, col_hist1, col_hist2, col_spacer2 = st.columns([1, 2, 2, 1])

        with col_hist1:
            st.subheader("オリジナル画像")
            with st.spinner("画像を読み込み中..."):
                original_image = get_image_from_s3(f"{timestamp}/original.png")
            if original_image:
                st.image(original_image, use_container_width=True)
            else:
                st.warning("画像が見つかりません")

        with col_hist2:
            st.subheader("加工画像")
            with st.spinner("画像を読み込み中..."):
                generated_image = get_image_from_s3(f"{timestamp}/generated.png")
            if generated_image:
                st.image(generated_image, use_container_width=True)

                # ダウンロードボタン
                generated_bytes = get_image_bytes_from_s3(f"{timestamp}/generated.png")
                if generated_bytes:
                    st.download_button(
                        label="加工画像をダウンロード",
                        data=generated_bytes,
                        file_name=f"bento_pro_{timestamp}.png",
                        mime="image/png",
                        use_container_width=True
                    )
            else:
                st.warning("画像が見つかりません")

    else:
        st.error("履歴データが見つかりません")
        if st.button("← 戻る"):
            st.session_state.selected_history = None
            st.rerun()
else:
    # 通常の新規作成画面（1列レイアウト）
    st.subheader("元画像")
    uploaded_file = st.file_uploader(
        "弁当の写真をアップロードしてください",
        type=["jpg", "jpeg", "png"]
    )

    # 新しい画像がアップロードされたら生成完了フラグをリセット
    if uploaded_file:
        if st.session_state.current_uploaded_file != uploaded_file.name:
            st.session_state.current_uploaded_file = uploaded_file.name
            st.session_state.generation_completed = False

        image = Image.open(uploaded_file)
        # Exif情報に基づいて自動回転（プレビューでも向きを維持）
        image = ImageOps.exif_transpose(image)
        st.image(image, caption="アップロードされた画像", width=400)

    # スタイル選択オプション
    st.markdown("---")
    st.markdown("### スタイル設定")

    st.markdown("#### 背景")
    background = st.radio(
        "background_label",
        ["白背景", "黒背景", "木目テーブル", "大理石", "和紙"],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.markdown("#### 撮影角度")
    angle = st.radio(
        "angle_label",
        ["斜め45度", "真上俯瞰", "やや低め30度"],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.markdown("#### 照明スタイル")
    lighting = st.radio(
        "lighting_label",
        ["明るいスタジオ", "柔らか自然光", "ドラマチック"],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.markdown("#### 余白サイズ")
    margin = st.radio(
        "margin_label",
        ["狭い", "標準", "広い"],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.markdown("#### 弁当の向き")
    rotation = st.radio(
        "rotation_label",
        ["正面配置", "軽く回転", "斜め配置"],
        horizontal=True,
        label_visibility="collapsed"
    )

    # 生成画像エリア
    st.markdown("---")
    st.subheader("加工後")
    result_placeholder = st.empty()

    with result_placeholder.container():
        st.info("画像をアップロードして「変換」ボタンを押してください")

    # 変換ボタン（生成完了後は非表示）
    if uploaded_file and not st.session_state.generation_completed:
        if st.button("プロ写真に変換", type="primary", use_container_width=True):
            st.session_state.processing = True
            try:
                start_time = time.time()  # 全体開始時間

                # プログレスバー
                progress_bar = st.progress(0)
                status_text = st.empty()

                # Step 1: 画像解析（Vision API）
                status_text.text("Step 1/3: 容器と食材を詳細に解析中...")
                progress_bar.progress(33)
                step1_start = time.time()

                # 画像をバイトデータに変換（軽量化）
                img_byte_arr = io.BytesIO()
                # 長辺を1024pxにリサイズして軽量化
                image_copy = image.copy()
                # Exif情報に基づいて自動回転（向きを維持）
                image_copy = ImageOps.exif_transpose(image_copy)
                image_copy.thumbnail((1024, 1024))
                image_copy.save(img_byte_arr, format='JPEG')
                img_byte_arr.seek(0)  # ストリームを先頭に戻す

                # Vision APIで解析（容器・配置・食材を明確に指示）
                vision_prompt = """
                Analyze this bento image for a commercial photography prompt.
                Extract the following visual details accurately:

                1. CONTAINER: Describe the material, shape, color, and pattern of the bento box (e.g., wood-grain paper box, black plastic, round, rectangular).
                2. LAYOUT: Describe specifically where each food item is placed (e.g., Grilled salmon on the center-left, Tamagoyaki on the top-right).
                3. FOOD: List all food items with visual details (texture, color).

                IMPORTANT: Do NOT describe the camera angle, shooting angle, or perspective (e.g., high-angle, overhead, low-angle).
                Only describe the container, food arrangement, and food details.

                Format the output as a descriptive paragraph for image generation.
                Answer in English.
                """

                # 新SDK: Gemini Vision Model で画像解析 + Thinking mode最適化
                # response = client.models.generate_content(
                #     model='gemini-3-flash-preview',
                #     contents=[vision_prompt, Image.open(img_byte_arr)],
                #     config=types.GenerateContentConfig(
                #         thinking_config=types.ThinkingConfig(thinking_level="medium")
                #     )
                # )

                response = client.models.generate_content(
                    model='gemini-3-pro-preview',
                    contents=[vision_prompt, Image.open(img_byte_arr)],
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(thinking_level="high")
                    )
                )

                analyzed_content = response.text.strip()
                step1_time = time.time() - step1_start

                st.success(f"解析完了 ({step1_time:.2f}秒): {analyzed_content[:100]}...")

                # Step 2: プロンプト合成
                status_text.text("Step 2/3: プロンプトを合成中...")
                progress_bar.progress(66)

                # 背景設定
                background_map = {
                    "白背景": "clean white background",
                    "黒背景": "matte black background",
                    "木目テーブル": "natural wood grain table surface",
                    "大理石": "elegant marble table surface",
                    "和紙": "traditional Japanese washi paper background"
                }

                # 撮影角度設定（上下の角度のみ）
                angle_map = {
                    "斜め45度": "High-angle shot (approx 45 degrees from above).",
                    "真上俯瞰": "Overhead shot (90 degrees, directly from above).",
                    "やや低め30度": "Low-angle shot (approx 30 degrees from above)."
                }

                # 弁当の向き設定（水平回転）- 命令形で直接的に指示
                rotation_map = {
                    "正面配置": "Place the bento box perfectly straight and parallel to the camera frame, with all edges aligned to the image borders. NO rotation whatsoever.",
                    "軽く回転": "Rotate the bento box slightly (about 15-20 degrees clockwise) from the parallel position to add subtle depth and dimension.",
                    "斜め配置": "Rotate the bento box diagonally (about 45 degrees clockwise) to create dynamic depth and visual interest. The box should NOT be parallel to the frame."
                }

                # 照明設定
                lighting_map = {
                    "明るいスタジオ": "Bright, even studio lighting (high-key). Soft shadows. The food looks fresh, glossy, vibrant, and appetizing.",
                    "柔らか自然光": "Soft, natural window light. Gentle shadows. The food looks fresh, natural, and inviting.",
                    "ドラマチック": "Dramatic side lighting with strong shadows. The food looks bold, artistic, and textured."
                }

                # 余白設定
                margin_map = {
                    "狭い": "The bento box fills most of the frame with minimal margins around it.",
                    "標準": "The bento box is centered with moderate margins around it.",
                    "広い": "The bento box is centered with generous margins and plenty of negative space around it."
                }

                # 1. 回転指示（最優先で最初に配置）
                rotation_instruction = rotation_map[rotation]

                # 2. 基本スタイルとアングル（選択に応じて動的生成）
                style_part = f"Professional commercial food photography. {angle_map[angle]} The bento box is placed on a {background_map[background]}. {margin_map[margin]}"

                # 3. 光と質感（選択に応じて動的生成）+ 湯気禁止
                lighting_part = f"{lighting_map[lighting]} NO steam, NO vapor. 8k resolution, highly detailed."

                # 4. 中身の指定（可変：画像解析結果をそのまま採用）
                content_part = f"Subject Description: {analyzed_content}"

                # 最終プロンプト（回転指示を最初に配置）
                final_prompt = f"{rotation_instruction}\n\n{style_part}\n\n{lighting_part}\n\n{content_part}"

                # Step 3: 画像生成
                status_text.text("Step 3/3: 元画像を参照しながらプロ写真を生成中...")
                progress_bar.progress(100)
                step3_start = time.time()

                # 画像参照型プロンプト（元画像を見ながらスタイルだけを変換）
                reference_prompt = f"""
Refine this specific image into a professional commercial food photography style.

STRICT CONSTRAINTS:
1. Keep the EXACT container type, material, color, and shape shown in the input image.
2. Keep the EXACT food arrangement and portion sizes shown in the input image. Do NOT add extra food.
3. Apply the following style:

{rotation_instruction}

{style_part}

{lighting_part}

Subject Content for reference:
{analyzed_content}
"""

                # 画像ストリームを先頭に戻す
                img_byte_arr.seek(0)

                # 新SDK: Gemini 3 Pro Image で画像生成
                generation_response = client.models.generate_content(
                    model='gemini-3-pro-image-preview',
                    contents=[
                        reference_prompt,
                        Image.open(img_byte_arr)
                    ]
                )

                # 生成された画像を表示
                if generation_response.candidates:
                    step3_time = time.time() - step3_start
                    total_time = time.time() - start_time

                    generated_image_data = generation_response.candidates[0].content.parts[0].inline_data.data
                    generated_image = Image.open(io.BytesIO(generated_image_data))

                    with result_placeholder.container():
                        st.image(generated_image, caption="生成されたプロ写真", width=600)

                        # ダウンロードボタン
                        buf = io.BytesIO()
                        generated_image.save(buf, format="PNG")
                        byte_im = buf.getvalue()

                        st.download_button(
                            label="画像をダウンロード",
                            data=byte_im,
                            file_name="bento_pro.png",
                            mime="image/png",
                            width='stretch'
                        )

                    # 履歴保存（S3）
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

                    # 元画像をS3に保存
                    save_image_to_s3(image, f"{timestamp}/original.png")

                    # 生成画像をS3に保存
                    save_image_to_s3(generated_image, f"{timestamp}/generated.png")

                    # メタデータを保存
                    metadata = {
                        "timestamp": timestamp,
                        "background": background,
                        "angle": angle,
                        "lighting": lighting,
                        "margin": margin,
                        "rotation": rotation,
                        "analyzed_content": analyzed_content,
                        "full_prompt": final_prompt,
                        "step1_time": step1_time,
                        "step3_time": step3_time,
                        "total_time": total_time
                    }
                    save_metadata_to_s3(metadata, f"{timestamp}/metadata.json")

                    status_text.success(f"生成完了 | 解析: {step1_time:.2f}秒 | 生成: {step3_time:.2f}秒 | 合計: {total_time:.2f}秒")
                    progress_bar.empty()
                    st.session_state.processing = False
                    st.session_state.generation_completed = True
                else:
                    st.error("画像生成に失敗しました。もう一度お試しください。")
                    status_text.empty()
                    progress_bar.empty()
                    st.session_state.processing = False

            except Exception as e:
                st.error(f"エラーが発生しました: {str(e)}")
                st.info("API KeyやモデルIDを確認してください。")
                status_text.empty()
                progress_bar.empty()
                st.session_state.processing = False

# フッター
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray; font-size: 0.9em;'>
Powered by Google Gemini 3 Pro Image | Bento Pro Generator v1.0
</div>
""", unsafe_allow_html=True)
