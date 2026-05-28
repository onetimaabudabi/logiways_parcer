from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import io
import os
import time
import sys
from pathlib import Path

# Добавляем корневую папку в путь
root_dir = Path(__file__).parent.parent  # поднимаемся на 2 уровня вверх
sys.path.append(str(root_dir))
from main import start_parse

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'drive/credentials.json'

ROOT_FOLDER_ID = "1RCtFGqRQjFEsZMC19S9FTiTysVSoEcem" #Тарифы транспортных компаний
DOWNLOAD_DIR = "drive/downloads"

CHECK_INTERVAL = 60 * 2  # 1 час


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)


def get_start_page_token(service):
    return service.changes().getStartPageToken().execute()['startPageToken']


def get_file_meta(service, file_id):
    return service.files().get(
        fileId=file_id,
        fields="id, name, parents, mimeType"
    ).execute()


def download_file(service, file_id, file_name, folder_name):
    local_folder = os.path.join(DOWNLOAD_DIR, folder_name)
    if os.path.exists(local_folder):
        filepath = os.path.join(local_folder, file_name)
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"🗑 Deleted: {filepath}")
    else:
        os.makedirs(local_folder, exist_ok=True)

    filepath = os.path.join(local_folder, file_name)

    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(filepath, 'wb')
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    print(f"✅ Downloaded: {folder_name}/{file_name}")
    return True


def watch_changes(service, page_token):
    while True:
        download = False
        print("⏳ Checking changes...")

        response = service.changes().list(
            pageToken=page_token,
            spaces='drive',
            fields='nextPageToken, changes(fileId, removed, file(id, name, mimeType, parents))'#'nextPageToken, changes(fileId, file(name, parents))'
        ).execute()

        for change in response.get('changes', []):
            print(change)
            if change.get('removed'):
                continue
            file = change.get('file')
            if not file:
                continue

            parents = file.get('parents', [])
            if not parents:
                continue
            if ROOT_FOLDER_ID in parents:
                print("📁 Changed:", file['name'])
            for parent_id in parents:

                # 👉 получаем инфу о родительской папке
                parent_meta = get_file_meta(service, parent_id)

                folder_name = parent_meta['name']
                file_id = change.get('fileId')
                file_name = file['name']

                print(f"🆕 New file: {folder_name}/{file_name}")
                download = download_file(service, file_id, file_name, folder_name)

        # обновляем токен
        page_token = response.get('nextPageToken', page_token)

        if 'newStartPageToken' in response:
            page_token = response['newStartPageToken']
        if download:
            start_parse()
        print("😴 Sleeping 1 hour...\n")
        time.sleep(CHECK_INTERVAL)


def main():
    service = get_service()
    token = get_start_page_token(service)
    watch_changes(service, token)


if __name__ == "__main__":
    main()