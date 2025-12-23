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
        # サムネイルが存在しない場合など、静かに None を返す
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

def delete_history_from_s3(timestamp):
    """S3から指定されたタイムスタンプの履歴を削除"""
    if not s3_client:
        return False
    try:
        # フォルダ内のすべてのオブジェクトを取得
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix=f"{timestamp}/"
        )

        if 'Contents' in response:
            # すべてのオブジェクトを削除
            for obj in response['Contents']:
                s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=obj['Key'])

        return True
    except ClientError as e:
        st.error(f"S3削除エラー: {str(e)}")
        return False

# セッションステート初期化
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'generation_completed' not in st.session_state:
    st.session_state.generation_completed = False
if 'current_uploaded_file' not in st.session_state:
    st.session_state.current_uploaded_file = None

# クエリパラメータから履歴を読み込み
if 'history' in st.query_params:
    st.session_state.selected_history = st.query_params['history']
elif 'selected_history' not in st.session_state:
    st.session_state.selected_history = None

# 履歴フォルダの作成
HISTORY_DIR = "history"
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)


# S3から履歴一覧を取得
history_folders = list_history_from_s3()

# サイドバー：AI加工ボタンと履歴
with st.sidebar:
    # AI加工ボタン
    if st.button("新規画像加工", use_container_width=True, type="primary"):
        st.session_state.selected_history = None
        st.query_params.clear()
        st.rerun()

    if st.button("加工履歴一覧", use_container_width=True, type="secondary"):
        st.query_params['view'] = 'list'
        st.session_state.selected_history = None
        st.rerun()

    st.markdown("---")

    if history_folders:
        st.markdown(f"**直近の履歴 {len(history_folders)}件**")

        # 最新10件をボタンとして表示
        for folder in history_folders[:10]:
            if st.button(f"{folder}", key=f"hist_{folder}", use_container_width=True):
                st.session_state.selected_history = folder
                st.query_params['history'] = folder
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
# クエリパラメータでビューモードを判定
view_mode = st.query_params.get('view', None)

# 一覧ページ
if view_mode == 'list':
    st.title("履歴一覧")

    # S3から全履歴を取得
    history_folders = list_history_from_s3()

    # 検索機能
    st.markdown("### 検索・絞り込み")
    search_query = st.text_input("タイトル、タグ、内容で検索", placeholder="例: ハンバーグ")

    # ページネーション設定
    items_per_page = 20
    total_pages = (len(history_folders) - 1) // items_per_page + 1 if history_folders else 0

    # セッションステートでページ番号を管理
    if 'list_page' not in st.session_state:
        st.session_state.list_page = 0

    # ページ番号選択
    if total_pages > 1:
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("◀ 前へ", disabled=st.session_state.list_page == 0):
                st.session_state.list_page -= 1
                st.rerun()
        with col_page:
            st.markdown(f"**{st.session_state.list_page + 1} / {total_pages} ページ**", unsafe_allow_html=True)
        with col_next:
            if st.button("次へ ▶", disabled=st.session_state.list_page >= total_pages - 1):
                st.session_state.list_page += 1
                st.rerun()

    st.markdown("---")

    # 履歴を取得してフィルタリング
    start_idx = st.session_state.list_page * items_per_page
    end_idx = start_idx + items_per_page
    page_folders = history_folders[start_idx:end_idx]

    # メタデータを取得してフィルタリング
    filtered_items = []
    for folder in page_folders:
        metadata = get_metadata_from_s3(f"{folder}/metadata.json")
        if metadata:
            # 検索クエリでフィルタリング
            if search_query:
                search_text = f"{metadata.get('title', '')} {' '.join(metadata.get('tags', []))} {metadata.get('description', '')}"
                if search_query.lower() not in search_text.lower():
                    continue
            filtered_items.append((folder, metadata))

    # グリッド表示（4列）
    if filtered_items:
        st.markdown(f"**{len(filtered_items)}件の履歴**")
        cols_per_row = 4
        for i in range(0, len(filtered_items), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                if i + j < len(filtered_items):
                    folder, metadata = filtered_items[i + j]
                    with col:
                        # 固定高さのコンテナを作成
                        with st.container():
                            # カード全体のHTMLを構築（固定高さ）
                            thumbnail = get_image_from_s3(f"{folder}/thumbnail.png")
                            if not thumbnail:
                                thumbnail = get_image_from_s3(f"{folder}/generated.png")

                            # 画像HTML
                            if thumbnail:
                                # 画像を一時的に保存してbase64エンコード
                                import base64
                                from io import BytesIO
                                buffered = BytesIO()
                                thumbnail.save(buffered, format="PNG")
                                img_str = base64.b64encode(buffered.getvalue()).decode()
                                img_html = f'<img src="data:image/png;base64,{img_str}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 4px;">'
                            else:
                                img_html = '<div style="height: 200px; background-color: #f0f0f0; display: flex; align-items: center; justify-content: center; border-radius: 4px;">画像なし</div>'

                            # タイトルHTML
                            title = metadata.get('title', folder)
                            if metadata.get('favorite', False):
                                title_html = f'<div style="background-color: #fff3cd; padding: 8px; border-radius: 4px; border-left: 4px solid #ffc107; height: 60px; display: flex; align-items: center; overflow: hidden;"><strong>{title}</strong></div>'
                            else:
                                title_html = f'<div style="height: 60px; display: flex; align-items: center; overflow: hidden; padding: 8px;"><strong>{title}</strong></div>'

                            # タグHTML
                            tags_str = " ".join([f"<code>{tag}</code>" for tag in metadata.get('tags', [])])
                            tags_html = f'<div style="height: 40px; font-size: 0.85em; overflow: hidden; padding: 4px 8px;">{tags_str if tags_str else "&nbsp;"}</div>'

                            # カード全体をHTMLで表示（ボタンエリアを除く）
                            st.markdown(f'''
                                <div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; background-color: white; margin-bottom: 8px;">
                                    <div style="margin-bottom: 8px;">
                                        {img_html}
                                    </div>
                                    <div style="margin-bottom: 4px;">
                                        {title_html}
                                    </div>
                                    <div style="margin-bottom: 8px;">
                                        {tags_html}
                                    </div>
                                </div>
                            ''', unsafe_allow_html=True)

                            # 詳細ボタンをカードの下部に配置
                            if st.button("詳細", key=f"detail_{folder}", use_container_width=True):
                                st.session_state.selected_history = folder
                                st.query_params['history'] = folder
                                st.query_params.pop('view', None)
                                st.rerun()
    else:
        st.info("該当する履歴がありません")

# 履歴編集ページ
elif 'selected_history' in st.session_state and st.session_state.selected_history and st.query_params.get('edit') == 'true':
    # 一覧に戻るボタン
    if st.button("← 一覧に戻る"):
        st.session_state.selected_history = None
        st.query_params.clear()
        st.query_params['view'] = 'list'
        st.rerun()

    st.title("履歴を編集")

    # S3から履歴データを読み込む
    timestamp = st.session_state.selected_history

    with st.spinner("履歴データを読み込み中..."):
        metadata = get_metadata_from_s3(f"{timestamp}/metadata.json")

    if metadata:
        st.markdown(f"**履歴ID:** `{timestamp}`")
        st.markdown("---")

        # 編集フォーム
        with st.form("edit_form"):
            st.markdown("### メタデータ編集")

            # タイトル編集
            edited_title = st.text_input(
                "タイトル",
                value=metadata.get('title', ''),
                max_chars=50,
                placeholder="例: ハンバーグ弁当"
            )

            # 説明文編集
            edited_description = st.text_area(
                "説明文",
                value=metadata.get('description', ''),
                max_chars=200,
                placeholder="弁当の簡単な説明を入力",
                height=100
            )

            # タグ編集（カンマ区切り）
            current_tags = metadata.get('tags', [])
            tags_str = ", ".join(current_tags) if current_tags else ""
            edited_tags_str = st.text_input(
                "タグ（カンマ区切り）",
                value=tags_str,
                placeholder="例: ハンバーグ, 和食, 唐揚げ"
            )

            # お気に入り設定
            edited_favorite = st.checkbox(
                "お気に入りに設定",
                value=metadata.get('favorite', False)
            )

            st.markdown("---")
            col_save, col_cancel = st.columns(2)

            with col_save:
                save_button = st.form_submit_button("保存", type="primary", use_container_width=True)

            with col_cancel:
                cancel_button = st.form_submit_button("キャンセル", use_container_width=True)

        # 保存処理
        if save_button:
            # タグをリストに変換
            edited_tags = [tag.strip() for tag in edited_tags_str.split(',') if tag.strip()]

            # メタデータを更新
            metadata['title'] = edited_title
            metadata['description'] = edited_description
            metadata['tags'] = edited_tags
            metadata['favorite'] = edited_favorite

            # S3に保存
            if save_metadata_to_s3(metadata, f"{timestamp}/metadata.json"):
                st.success("保存しました！")
                st.query_params.pop('edit', None)
                time.sleep(1)
                st.rerun()
            else:
                st.error("保存に失敗しました")

        # キャンセル処理
        if cancel_button:
            st.query_params.pop('edit', None)
            st.rerun()

    else:
        st.error("履歴データが見つかりません")
        if st.button("← 戻る"):
            st.session_state.selected_history = None
            st.query_params.clear()
            st.rerun()

# 履歴が選択されている場合は履歴詳細を表示
elif 'selected_history' in st.session_state and st.session_state.selected_history:
    # 一覧に戻るボタン
    if st.button("← 一覧に戻る"):
        st.session_state.selected_history = None
        st.query_params.clear()
        st.query_params['view'] = 'list'
        st.rerun()

    # S3から履歴データを読み込む
    timestamp = st.session_state.selected_history

    with st.spinner("履歴データを読み込み中..."):
        metadata = get_metadata_from_s3(f"{timestamp}/metadata.json")

    if metadata:
        # タイトル、お気に入り、編集ボタンを表示
        col_title, col_fav_btn, col_edit_btn = st.columns([3, 1, 1])
        with col_title:
            st.title(metadata.get('title', '弁当'))

        with col_fav_btn:
            is_favorite = metadata.get('favorite', False)
            fav_label = "お気に入り解除" if is_favorite else "お気に入り"
            if st.button(fav_label, use_container_width=True):
                # お気に入り状態を切り替え
                metadata['favorite'] = not is_favorite
                if save_metadata_to_s3(metadata, f"{timestamp}/metadata.json"):
                    st.rerun()
                else:
                    st.error("更新に失敗しました")

        with col_edit_btn:
            if st.button("編集", use_container_width=True, key="edit_btn"):
                st.query_params['edit'] = 'true'
                st.rerun()

        if metadata.get('tags'):
            tags_str = " ".join([f"`{tag}`" for tag in metadata.get('tags', [])])
            st.markdown(tags_str)
        if metadata.get('description'):
            st.markdown(f"*{metadata.get('description')}*")
        st.markdown(f"**履歴詳細:** `{st.session_state.selected_history}`")
        # 設定情報表示
        st.markdown("### 設定情報")
        col_info1, col_info2, col_info3, col_info4 = st.columns(4)
        with col_info1:
            st.metric("背景", metadata.get('background', 'N/A'))
        with col_info2:
            st.metric("角度", metadata.get('angle', 'N/A'))
        with col_info3:
            st.metric("照明", metadata.get('lighting', 'N/A'))
        with col_info4:
            st.metric("余白", metadata.get('margin', 'N/A'))

        col_info5, col_info6, col_info7, col_info8 = st.columns(4)
        with col_info5:
            st.metric("サイズ", metadata.get('aspect_ratio', 'N/A'))
        with col_info6:
            st.metric("向き", metadata.get('rotation', 'N/A'))
        with col_info7:
            st.metric("容器補正", metadata.get('container_clean', 'N/A'))
        with col_info8:
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

        # 削除ボタン
        st.markdown("---")
        col_del1, col_del2, col_del3 = st.columns([1, 1, 1])
        with col_del2:
            if st.button("この履歴を削除", type="secondary", use_container_width=True):
                with st.spinner("削除中..."):
                    if delete_history_from_s3(timestamp):
                        st.success("履歴を削除しました")
                        st.session_state.selected_history = None
                        st.query_params.clear()
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("削除に失敗しました")

    else:
        st.error("履歴データが見つかりません")
        if st.button("← 戻る"):
            st.session_state.selected_history = None
            st.query_params.clear()
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
        ["斜め45度", "真上俯瞰"],
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
        ["標準", "広い"],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.markdown("#### 画像サイズ")
    aspect_ratio = st.radio(
        "aspect_ratio_label",
        ["正方形(1:1)", "縦長(3:4)", "横長(4:3)"],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.markdown("#### 弁当の向き")
    rotation = st.radio(
        "rotation_label",
        ["正面配置", "斜め配置"],
        horizontal=True,
        label_visibility="collapsed"
    )

    st.markdown("#### 容器汚れ補正")
    container_clean = st.radio(
        "container_clean_label",
        ["補正なし", "容器汚れを補正"],
        horizontal=True,
        label_visibility="collapsed"
    )

    # 生成画像エリア
    st.markdown("---")
    st.subheader("加工後")
    result_placeholder = st.empty()

    with result_placeholder.container():
        st.info("画像をアップロードして「変換」ボタンを押してください。何度も押さないように注意してください。")

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

                # メタデータ生成（タイトル、説明、タグ）
                metadata_prompt = """
                Based on this bento description, generate the following metadata in JSON format:
                - title: A short Japanese title (max 20 characters, e.g., "ハンバーグ弁当", "幕の内弁当")
                - description: A brief Japanese description (max 50 characters)
                - tags: An array of 3-5 Japanese search tags (e.g., ["ハンバーグ", "和食", "唐揚げ"])

                Return ONLY valid JSON in this exact format:
                {
                  "title": "...",
                  "description": "...",
                  "tags": ["...", "...", "..."]
                }

                Bento description:
                """ + analyzed_content

                metadata_response = client.models.generate_content(
                    model='gemini-2.0-flash-exp',
                    contents=metadata_prompt
                )

                # JSONをパース
                import json
                metadata_text = metadata_response.text.strip()
                # マークダウンのコードブロックを削除
                if metadata_text.startswith("```"):
                    metadata_text = metadata_text.split("```")[1]
                    if metadata_text.startswith("json"):
                        metadata_text = metadata_text[4:]
                metadata_dict = json.loads(metadata_text.strip())

                step1_time = time.time() - step1_start

                st.success(f"解析完了 ({step1_time:.2f}秒): {metadata_dict['title']} - {analyzed_content[:80]}...")

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

                # 撮影角度設定（y軸方向：カメラの高さ/俯瞰度）
                angle_map = {
                    "斜め45度": "The camera is positioned at a moderate height above the table, looking down at the bento box at approximately 30-40 degrees from horizontal. This angle shows both the top surface of the food AND the front vertical side wall of the container clearly, creating depth while maintaining visibility of contents.",
                    "真上俯瞰": "The camera is positioned DIRECTLY overhead at 90 degrees, perfectly perpendicular to the table surface. Pure bird's eye view looking STRAIGHT DOWN. NO angle whatsoever - completely flat, top-down perspective."
                }

                # 弁当の向き設定（テーブル上での物理的な配置）
                rotation_map = {
                    "正面配置": {
                        "rule": "**[Crucial: Orientation & Alignment]**\n* The bento box is NOT rotated diagonally on the table surface.\n* The edges of the box are perfectly parallel to the frame edges (top edge parallel to top of frame, sides parallel to sides of frame).\n* NO rotation whatsoever. The box maintains a straight, unrotated position.",
                        "description": "The box faces the camera squarely."
                    },
                    "斜め配置": {
                        "rule": "**[Crucial: Orientation & Alignment]**\n* The bento box IS rotated diagonally on the table surface.\n* The box is tilted approximately 45 degrees CLOCKWISE (from viewer's perspective).\n* One corner of the box points towards the top of the frame, creating a diamond-like orientation.",
                        "description": "Creates dynamic diagonal depth."
                    }
                }

                # 照明設定
                lighting_map = {
                    "明るいスタジオ": "Bright, even studio lighting (high-key). Soft shadows. The food looks fresh, glossy, vibrant, and appetizing.",
                    "柔らか自然光": "Soft, natural window light. Gentle shadows. The food looks fresh, natural, and inviting.",
                    "ドラマチック": "Dramatic side lighting with strong shadows. The food looks bold, artistic, and textured."
                }

                # 余白設定（構図の概念で指定し、縁が見切れないことを保証）
                margin_map = {
                    "標準": "With some negative space around the bento box. A little breathing room on the table surface. Not cropped tightly. Centered composition. The entire bento box must fit completely within the frame with NO edges cut off.",
                    "広い": "Ample negative space. Vast empty table surface surrounding the bento box. Minimalist composition with lots of empty space. Long shot. The bento box is small in the center of the large frame. The entire bento box must fit completely within the frame with NO edges cut off."
                }

                # プロンプト構成: 重要ルール → カメラ設定 → 配置 → 照明 → 内容

                # 1. 弁当の向き（最優先ルール）
                rotation_rule = rotation_map[rotation]["rule"]
                rotation_desc = rotation_map[rotation]["description"]

                # 2. カメラ設定
                camera_setup = f"**[Camera Angle & Perspective]**\n* {angle_map[angle]}"

                # 3. 背景と余白
                environment = f"**[Environment & Composition]**\n* The bento box is placed on a {background_map[background]}.\n* {margin_map[margin]}"

                # 4. 照明
                lighting_section = f"**[Lighting & Style]**\n* {lighting_map[lighting]}\n* NO steam, NO vapor. 8k resolution, highly detailed."

                # 5. 内容
                content_part = f"**[Contents Description]**\n{analyzed_content}"

                # 最終プロンプト（ルール → カメラ → 環境 → 照明 → 内容の順）
                final_prompt = f"Professional commercial food photography.\n\n{rotation_rule}\n\n{camera_setup}\n\n{environment}\n\n{lighting_section}\n\n{content_part}"

                # Step 3: 画像生成
                status_text.text("Step 3/3: 元画像を参照しながらプロ写真に加工中...")
                progress_bar.progress(100)
                step3_start = time.time()

                # 容器清掃指示（選択された場合のみ）
                container_clean_instruction = ""
                if container_clean == "汚れを補正":
                    container_clean_instruction = """
CONTAINER CLEANING:
- Clean any sauce stains, oil marks, or liquid spills on the bento box container surfaces (walls, edges, exterior)
- The container should look pristine and clean
- CRITICAL: Do NOT alter, change, or modify the food contents inside the compartments
- Only clean the container itself, not the food
"""

                # 画像参照型プロンプト（元画像を見ながらスタイルだけを変換）
                reference_prompt = f"""
Refine this specific image into a professional commercial food photography style.

**CRITICAL CONSTRAINTS - MUST FOLLOW EXACTLY:**
1. Keep the EXACT container type, material, color, and shape shown in the input image.
2. Keep the EXACT food arrangement and portion sizes shown in the input image. Do NOT add extra food.

{rotation_rule}

{camera_setup}

{environment}

{lighting_section}

{container_clean_instruction}

**[Contents Description]**
{analyzed_content}
"""

                # 画像ストリームを先頭に戻す
                img_byte_arr.seek(0)

                # アスペクト比マッピング（プロンプト用）
                aspect_ratio_prompt_map = {
                    "正方形(1:1)": "**[Output Format]**\nGenerate the output image in SQUARE format with 1:1 aspect ratio (width equals height).",
                    "縦長(3:4)": "**[Output Format]**\nGenerate the output image in PORTRAIT/VERTICAL format with 3:4 aspect ratio (width:height = 3:4, taller than wide).",
                    "横長(4:3)": "**[Output Format]**\nGenerate the output image in LANDSCAPE/HORIZONTAL format with 4:3 aspect ratio (width:height = 4:3, wider than tall)."
                }

                # アスペクト比指定をプロンプトに追加
                reference_prompt_with_aspect = f"{reference_prompt}\n\n{aspect_ratio_prompt_map[aspect_ratio]}"

                # 新SDK: Gemini 3 Pro Image で画像生成
                generation_response = client.models.generate_content(
                    model='gemini-3-pro-image-preview',
                    contents=[
                        reference_prompt_with_aspect,
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
                        st.image(generated_image, caption="加工後の写真", width=600)

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

                    # サムネイル生成（長辺400px）
                    thumbnail = generated_image.copy()
                    thumbnail.thumbnail((400, 400), Image.Resampling.LANCZOS)
                    save_image_to_s3(thumbnail, f"{timestamp}/thumbnail.png")

                    # メタデータを保存
                    metadata = {
                        "timestamp": timestamp,
                        "title": metadata_dict.get("title", "弁当"),
                        "description": metadata_dict.get("description", ""),
                        "tags": metadata_dict.get("tags", []),
                        "favorite": False,
                        "background": background,
                        "angle": angle,
                        "lighting": lighting,
                        "margin": margin,
                        "aspect_ratio": aspect_ratio,
                        "rotation": rotation,
                        "container_clean": container_clean,
                        "analyzed_content": analyzed_content,
                        "full_prompt": final_prompt,
                        "step1_time": step1_time,
                        "step3_time": step3_time,
                        "total_time": total_time
                    }
                    save_metadata_to_s3(metadata, f"{timestamp}/metadata.json")

                    status_text.success(f"加工完了 | 解析: {step1_time:.2f}秒 | 加工: {step3_time:.2f}秒 | 合計: {total_time:.2f}秒")
                    progress_bar.empty()
                    st.session_state.processing = False
                    st.session_state.generation_completed = True

                    # 生成完了後、履歴詳細ページへ遷移
                    st.session_state.selected_history = timestamp
                    st.query_params['history'] = timestamp
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("画像加工に失敗しました。もう一度お試しください。")
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
