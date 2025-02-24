from typing import Any, Optional
from googleapiclient.discovery import Resource
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload, MediaFileUpload
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError
import io
import json
from pydantic import BaseModel, Field
import pypandoc
import os
import tempfile


class MyData(BaseModel):
    name: str = Field(..., description="Name of the item")
    value: int = Field(..., description="Integer value")


def create_drive_service(service_account_file: str) -> Optional[Resource]:
    """Creates a Google Drive service object.

    Args:
        service_account_file: Path to your service account key file.

    Returns:
        A Google Drive service object, or None if an error occurs.
    """
    try:
        creds: service_account.Credentials = (
            service_account.Credentials.from_service_account_file(
                filename=service_account_file,
                scopes=[
                    "https://www.googleapis.com/auth/drive"
                ],  # Note: This scope allows read/write
            )
        )
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"Error creating Drive service: {e}")
        return None


def get_gdrive_file_id(
    drive_service: Resource, folder_id: str, file_name: str
) -> str | None:
    """
    Returns the file ID of a file with a given name in a specific Google Drive folder.

    :param drive_service: Authenticated Google Drive API service instance.
    :param folder_id: The Google Drive folder ID where the file is located.
    :param file_name: The exact name of the file to search for.
    :return: The file ID if found, None otherwise.
    """
    try:
        # Query to find the file by name in the given folder
        query: str = (
            f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
        )

        # Execute the search
        response = (
            drive_service.files().list(q=query, fields="files(id, name)").execute()
        )

        files = response.get("files", [])

        if files:
            return files[0]["id"]  # Return the first matching file ID
        else:
            return None  # File not found
    except HttpError as e:
        print(f"Error searching for file: {e}")
        return None


def check_gdrive_file_exists(drive_service: Resource, file_id: str) -> bool:
    """
    Checks if a Google Drive file exists given its file ID.

    :param drive_service: Authenticated Google Drive API service instance.
    :param file_id: The ID of the file to check.
    :return: True if the file exists, False otherwise.
    """
    try:
        drive_service.files().get(fileId=file_id, fields="id").execute()
        return True  # File exists
    except HttpError as e:
        if e.resp.status in [404]:  # File not found
            return False
        else:
            raise  # Re-raise other unexpected errors


def read_json_from_drive(service: Resource, file_id: str) -> Optional[Any]:
    """Reads a JSON file from Google Drive.

    Args:
        service: The Google Drive service object.
        file_id: The ID of the Google Drive file.

    Returns:
        A dictionary representing the JSON data, or None if an error occurs.
    """
    try:
        if not check_gdrive_file_exists(service, file_id):
            print(f"File with ID {file_id} does not exist.")
            return None
        request: Any = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}.")

        fh.seek(0)
        return json.load(fh)

    except Exception as e:
        print(f"Error reading JSON from Drive: {e}")
        return None


def store_pydantic_to_drive(
    service: Resource,
    data_instance: BaseModel,
    target_dir_id: str,
    file_name: str = "config.json",
) -> bool:
    """
    Stores a Pydantic model instance as JSON to Google Drive, replacing any existing file with the same name.

    :param service: Authenticated Google Drive API service instance.
    :param data_instance: The Pydantic model instance to store.
    :param target_dir_id: The ID of the Google Drive directory where the file will be stored.
    :param file_name: The name of the file to store.
    :return: True if successful, False otherwise.
    """
    try:
        # Step 1: Search for an existing file with the same name in the target directory
        query: str = (
            f"name = '{file_name}' and '{target_dir_id}' in parents and trashed = false"
        )
        response = service.files().list(q=query, fields="files(id)").execute()
        files: dict[str, Any] = response.get("files", [])

        # Step 2: If a file exists, delete it
        if files:
            existing_file_id: str = files[0]["id"]
            service.files().delete(fileId=existing_file_id).execute()
            print(f"🗑️ Existing file '{file_name}' (ID: {existing_file_id}) deleted.")

        # Step 3: Upload the new JSON file
        file_metadata: dict[str, Any] = {"name": file_name, "parents": [target_dir_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(data_instance.model_dump()).encode()),
            mimetype="application/json",
        )

        uploaded_file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        print(
            f"✅ '{file_name}' uploaded successfully to Drive folder {target_dir_id}: {uploaded_file}."
        )
        return True

    except HttpError as e:
        print(f"❌ Google Drive API Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        return False


def ensure_gdrive_directory(
    drive_service: Any, root_id: str, subdirectory_name: str
) -> str | None:
    """
    Ensures that a subdirectory exists under the specified root directory in Google Drive.
    If the subdirectory does not exist, it creates it.

    Args:
        drive_service: Authenticated Google Drive service instance.
        root_id (str): The ID of the parent/root directory.
        subdirectory_name (str): The name of the subdirectory to create or check.

    Returns:
        str: The Google Drive file ID of the existing or newly created directory.
    """
    try:
        # Search for the folder inside the root directory
        query: str = (
            f"name='{subdirectory_name}' and mimeType='application/vnd.google-apps.folder' and '{root_id}' in parents and trashed=false"
        )
        response = (
            drive_service.files()
            .list(q=query, spaces="drive", fields="files(id, name)")
            .execute()
        )
        folders = response.get("files", [])

        if folders:
            # Folder already exists, return its ID
            return folders[0]["id"]

        # Folder does not exist, create it
        folder_metadata: dict[str, Any] = {
            "name": subdirectory_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [root_id],
        }
        folder = (
            drive_service.files().create(body=folder_metadata, fields="id").execute()
        )
        return folder["id"]

    except HttpError as error:
        print(f"An error occurred: {error}")
        return None  # Return None in case of an error


# Example Usage:
# drive_service = build("drive", "v3", credentials=your_credentials)
# subdirectory_id = ensure_gdrive_directory(drive_service, root_output_directory_id, "Batch_2024_Exam")
# print(f"Subdirectory ID: {subdirectory_id}")


def list_gdrive_files(
    drive_service: Any, folder_id: str, extensions: tuple[str, ...] = ("docx", "odt")
) -> dict[str, str]:
    """Lists files in a Google Drive folder with specific extensions."""
    query: str = (
        f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false"
    )
    results = (
        drive_service.files()
        .list(q=query, fields="files(id, name, mimeType)")
        .execute()
    )
    files = results.get("files", [])

    # Filter files by allowed extensions
    filtered_files: dict[Any, Any] = {
        file["name"]: file["id"]
        for file in files
        if file["name"].lower().endswith(extensions)
    }

    return filtered_files  # Returns {filename: file_id} dictionary


def get_gdrive_folder_path(drive_service: Resource, folder_id: str) -> str | None:
    """
    Retrieves the full path of a Google Drive folder given its folder ID.

    :param drive_service: Authenticated Google Drive API service instance.
    :param folder_id: The ID of the folder to retrieve the full path for.
    :return: The full folder path (e.g., "Root/ParentFolder/MyFolder").
    """
    try:
        folder_path: list[str] = []
        current_folder_id: str = folder_id

        while current_folder_id:
            # Get folder metadata (name and parent ID)
            folder: Any = (
                drive_service.files()
                .get(fileId=current_folder_id, fields="name, parents")
                .execute()
            )

            folder_path.append(folder["name"])
            parents: Any = folder.get("parents")

            # If no parents, we've reached the root
            if not parents:
                break

            # Move to the parent folder
            current_folder_id = parents[0]

        # Reverse to get the correct path order
        return "/".join(reversed(folder_path))

    except HttpError as e:
        print(f"Error retrieving folder path: {e}")
        return None


def convert_gdrive_file_to_markdown(
    drive_service: Any, file_id: str, file_name: str, target_dir_id: str
) -> str | None:
    """
    Downloads a Google Drive file, converts it to Markdown, and uploads it back to a specified Google Drive folder.

    :param drive_service: Authenticated Google Drive API service instance.
    :param file_id: The ID of the file to convert.
    :param target_dir_id: The ID of the target Google Drive folder where the markdown file will be uploaded.
    """
    print(f"Converting file '{file_name}' to Markdown...")
    try:
        # Step 1: Get file metadata to retrieve original filename
        file_metadata = drive_service.files().get(fileId=file_id).execute()
        original_name: str = file_metadata["name"]
        original_ext: str = os.path.splitext(original_name)[
            1
        ]  # Get original file extension
        markdown_name: str = (
            os.path.splitext(original_name)[0] + ".md"
        )  # New markdown file name
        print(f"Converting file '{original_name}' to Markdown file {markdown_name}...")
        print(f"Directory is: {get_gdrive_folder_path(drive_service, target_dir_id)}")
        # Step 2: Download the file from Google Drive
        request = drive_service.files().get_media(fileId=file_id)
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=original_ext
        ) as temp_file:
            temp_file_path: str = temp_file.name
            print(f"Downloading file to: {temp_file_path}")
            downloader = MediaIoBaseDownload(temp_file, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        # Step 3: Convert to Markdown using pypandoc
        markdown_path: str = temp_file_path.replace(original_ext, ".md")
        print(f"Converting to Markdown file: {markdown_path}")
        result: str = pypandoc.convert_file(
            source_file=temp_file_path, to="md", outputfile=markdown_path
        )
        print(f"Conversion result: '{result}'")

        # Step 4: Upload the markdown file to Google Drive
        print(f"Uploading Markdown file to Google Drive...")
        new_file_id: str | None = replace_gdrive_file(
            drive_service, markdown_path, target_dir_id
        )

        # Cleanup temporary files
        print("Cleaning up temporary files...")
        os.remove(temp_file_path)
        os.remove(markdown_path)

        print(
            f"File successfully converted and uploaded as {markdown_name} with file ID {new_file_id}."
        )
        return new_file_id
    except Exception as e:
        print(f"Error: {e}")
        return None


def get_gdrive_markdown_text(drive_service: Resource, file_id: str) -> str | None:
    """
    Retrieves the text content of a Markdown (.md) file from Google Drive.

    :param drive_service: Authenticated Google Drive API service instance.
    :param file_id: The ID of the Markdown file.
    :return: The text content of the Markdown file.
    """
    try:
        # Step 1: Request file content
        request = drive_service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()

        # Step 2: Download file
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        # Step 3: Convert bytes to string
        file_stream.seek(0)
        markdown_text = file_stream.read().decode("utf-8")

        return markdown_text

    except Exception as e:
        print(f"❌ Error retrieving Markdown file: {e}")
        return None


def upload_markdown_to_gdrive(
    drive_service: Resource, file_name: str, target_dir_id: str, markdown_text: str
) -> str | None:
    """
    Creates or replaces a Markdown (.md) file in a specific Google Drive folder.

    :param drive_service: Authenticated Google Drive API service instance.
    :param file_name: The name of the Markdown file.
    :param target_dir_id: The Google Drive folder ID where the file should be stored.
    :param markdown_text: The Markdown content to store in the file.
    :return: The file ID of the uploaded file or None if there was an error.
    """
    try:
        # Step 1: Search for an existing file with the same name in the target directory
        query: str = (
            f"name = '{file_name}' and '{target_dir_id}' in parents and trashed = false"
        )
        print(
            f"Searching for existing file '{file_name}' in Drive folder {target_dir_id}, query is {query}..."
        )
        response = drive_service.files().list(q=query, fields="files(id)").execute()
        files = response.get("files", [])

        # Step 2: If the file exists, delete it
        if files:
            existing_file_id = files[0]["id"]
            drive_service.files().delete(fileId=existing_file_id).execute()
            print(f"🗑️ Existing file '{file_name}' (ID: {existing_file_id}) deleted.")

        # Step 3: Create the new Markdown file in memory
        print(f"Creating file in memory...")
        file_metadata: dict[str, Any] = {
            "name": file_name,
            "parents": [target_dir_id],
            "mimeType": "text/markdown",
        }
        media = MediaIoBaseUpload(
            io.BytesIO(markdown_text.encode()), mimetype="text/markdown"
        )

        # Step 4: Upload the new file to Google Drive
        print(f"Uploading file to Drive folder {target_dir_id}...")
        uploaded_file = (
            drive_service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        file_id = uploaded_file.get("id")
        print(
            f"✅ '{file_name}' uploaded successfully to Drive folder {target_dir_id}."
        )
        return file_id

    except HttpError as e:
        print(f"❌ Google Drive API Error: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        return None


def replace_gdrive_file(
    drive_service: Resource, local_file_path: str, target_dir_id: str
) -> str | None:
    """
    Uploads a local file to a specific Google Drive folder, replacing any existing file with the same name.

    :param drive_service: Authenticated Google Drive API service instance.
    :param local_file_path: Path to the local file.
    :param target_dir_id: Google Drive folder ID where the file will be uploaded.
    :return: The new uploaded file's Google Drive ID.
    """
    try:
        file_name = os.path.basename(local_file_path)  # Extract the file name

        # Step 1: Search for an existing file with the same name in the target directory
        query = (
            f"name = '{file_name}' and '{target_dir_id}' in parents and trashed = false"
        )
        response = (
            drive_service.files().list(q=query, fields="files(id, name)").execute()
        )
        files = response.get("files", [])

        # Step 2: If a file exists, delete it
        if files:
            existing_file_id = files[0]["id"]
            drive_service.files().delete(fileId=existing_file_id).execute()
            print(f"🗑️ Existing file '{file_name}' (ID: {existing_file_id}) deleted.")

        # Step 3: Upload the new file
        file_metadata = {"name": file_name, "parents": [target_dir_id]}
        media = MediaFileUpload(local_file_path, mimetype="text/markdown")

        uploaded_file = (
            drive_service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        print(
            f"✅ '{file_name}' uploaded successfully to Drive folder {target_dir_id}."
        )
        return uploaded_file["id"]

    except HttpError as e:
        print(f"❌ Google Drive API Error: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        return None


def download_gdrive_file(drive_service: Resource, file_id: str, save_path: str) -> None:
    """
    Downloads a Google Drive file by its ID.

    Parameters:
    drive_service: The Google Drive service instance to use for the request.
    file_id (str): The ID of the file to download.
    save_path (str): The local path where the file will be saved.

    Returns:
    None
    """
    request = drive_service.files().get_media(fileId=file_id)
    with open(save_path, "wb") as f:
        f.write(request.execute())


def test_read_write() -> None:
    service_account_file = "service_account.json"
    file_id = "1wQbb8zBi-LiDH6D_WcrOEsuqk_U9V_Kq"

    drive_service = create_drive_service(service_account_file)

    if drive_service:
        # Read data
        data = read_json_from_drive(drive_service, file_id)
        print(f"Read data from Drive: {data}")

        # Create and store a Pydantic instance
        my_data = MyData(name="Example Item", value=123)
        success = store_pydantic_to_drive(drive_service, my_data, file_id)
        print(f"Data stored to Drive successfully: {success}")
    else:
        print("Failed to create Drive service.")


if __name__ == "__main__":
    test_read_write()
