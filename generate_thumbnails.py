#!/usr/bin/env python3
"""
既存の履歴データからサムネイルを一括生成するスクリプト
original_thumbnail.png が存在しない履歴に対して、original.png からサムネイルを生成します。

使用方法:
  python generate_thumbnails.py                                      # .envのバケットを使用
  python generate_thumbnails.py --bucket bento-pro-generator-production  # 本番バケットを指定
"""

import os
import io
import argparse
from PIL import Image
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError

# 環境変数の読み込み
load_dotenv()

# AWS S3設定
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_REGION = os.getenv("S3_REGION")

# グローバル変数（後でコマンドライン引数で上書き可能）
BUCKET_NAME = S3_BUCKET_NAME

# S3クライアント初期化
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=S3_REGION
    )
else:
    print("エラー: AWS認証情報が設定されていません")
    exit(1)


def list_history_folders():
    """S3から履歴フォルダ一覧を取得"""
    try:
        response = s3_client.list_objects_v2(Bucket=BUCKET_NAME, Delimiter='/')
        if 'CommonPrefixes' not in response:
            return []
        folders = [prefix['Prefix'].rstrip('/') for prefix in response['CommonPrefixes']]
        return sorted(folders)
    except ClientError as e:
        print(f"S3リストエラー: {str(e)}")
        return []


def check_file_exists(key):
    """S3上にファイルが存在するかチェック"""
    try:
        s3_client.head_object(Bucket=BUCKET_NAME, Key=key)
        return True
    except ClientError:
        return False


def get_image_from_s3(key):
    """S3から画像を取得"""
    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=key)
        return Image.open(io.BytesIO(response['Body'].read()))
    except ClientError as e:
        print(f"  画像取得エラー ({key}): {str(e)}")
        return None


def save_image_to_s3(image, key):
    """画像をS3にアップロード"""
    try:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        s3_client.upload_fileobj(
            img_byte_arr,
            BUCKET_NAME,
            key,
            ExtraArgs={'ContentType': 'image/png'}
        )
        return True
    except ClientError as e:
        print(f"  S3アップロードエラー ({key}): {str(e)}")
        return False


def generate_thumbnail_for_folder(folder):
    """指定されたフォルダのサムネイルを生成"""
    original_thumbnail_key = f"{folder}/original_thumbnail.png"
    original_key = f"{folder}/original.png"

    # original_thumbnail.png が既に存在するかチェック
    if check_file_exists(original_thumbnail_key):
        print(f"  [スキップ] {folder}: サムネイル既に存在")
        return "skip"

    # original.png が存在するかチェック
    if not check_file_exists(original_key):
        print(f"  [エラー] {folder}: original.png が存在しません")
        return "error"

    # original.png を取得
    print(f"  [処理中] {folder}: サムネイル生成中...")
    original_image = get_image_from_s3(original_key)
    if not original_image:
        return "error"

    # サムネイル生成（長辺400px）
    thumbnail = original_image.copy()
    thumbnail.thumbnail((400, 400), Image.Resampling.LANCZOS)

    # S3にアップロード
    if save_image_to_s3(thumbnail, original_thumbnail_key):
        print(f"  [完了] {folder}: サムネイル生成完了")
        return "success"
    else:
        return "error"


def main():
    global BUCKET_NAME

    # コマンドライン引数のパース
    parser = argparse.ArgumentParser(
        description='既存の履歴データからサムネイルを一括生成します',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
使用例:
  python generate_thumbnails.py
    → .envのS3_BUCKET_NAMEを使用

  python generate_thumbnails.py --bucket bento-pro-generator-production
    → 本番環境のバケットを指定
        '''
    )
    parser.add_argument(
        '--bucket',
        type=str,
        help='S3バケット名（指定しない場合は.envの設定を使用）'
    )

    args = parser.parse_args()

    # バケット名の決定
    if args.bucket:
        BUCKET_NAME = args.bucket

    print("=" * 60)
    print("既存履歴のサムネイル一括生成スクリプト")
    print("=" * 60)
    print()
    print(f"対象バケット: {BUCKET_NAME}")
    print()

    # 実行確認
    print("このバケットに対してサムネイルを生成します。")
    print("既存のサムネイルは上書きされません（新規作成のみ）。")
    confirm = input("実行しますか？ (y/n): ")

    if confirm.lower() != 'y':
        print("キャンセルしました。")
        return

    print()

    # 履歴フォルダ一覧を取得
    print("S3から履歴フォルダ一覧を取得中...")
    folders = list_history_folders()

    if not folders:
        print("履歴フォルダが見つかりませんでした。")
        return

    print(f"取得完了: {len(folders)}件の履歴が見つかりました")
    print()

    # 各フォルダを処理
    stats = {"success": 0, "skip": 0, "error": 0}

    for idx, folder in enumerate(folders, 1):
        print(f"[{idx}/{len(folders)}] {folder}")
        result = generate_thumbnail_for_folder(folder)
        stats[result] += 1
        print()

    # 結果サマリー
    print("=" * 60)
    print("処理完了")
    print("=" * 60)
    print(f"成功: {stats['success']}件")
    print(f"スキップ（既存）: {stats['skip']}件")
    print(f"エラー: {stats['error']}件")
    print()


if __name__ == "__main__":
    main()
