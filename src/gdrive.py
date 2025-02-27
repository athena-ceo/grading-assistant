from typing import Any, Optional
from googleapiclient.discovery import Resource
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload, MediaFileUpload
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError
import io
from io import BytesIO
import json
from pydantic import BaseModel, Field
import pypandoc
import os
import tempfile
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile
import smtplib
import ssl
from email.message import EmailMessage


# Google Drive Setup
def init_google_drive() -> None:
    if "drive_service" in st.session_state:
        return

    drive_service: Any = create_drive_service()
    st.session_state.drive_service = drive_service

    st.session_state.config_directory_id = st.secrets["config"]["CONFIG_DIRECTORY_ID"]
    st.session_state.config_file_name = st.secrets["config"]["CONFIG_FILE_NAME"]
    st.session_state.output_folder_id = st.secrets["config"]["OUTPUT_FOLDER_ID"]
    st.session_state.attachments_folder_id = st.secrets["config"][
        "ATTACHMENTS_FOLDER_ID"
    ]


def create_drive_service() -> Optional[Resource]:
    """Creates a Google Drive service object.

    Args:
        service_account_file: Path to your service account key file.

    Returns:
        A Google Drive service object, or None if an error occurs.
    """
    try:
        credentials: service_account.Credentials = (
            service_account.Credentials.from_service_account_info(st.secrets["gdrive"])
        )
        result = build("drive", "v3", credentials=credentials)
        print(f"Drive service created successfully: {result}")
        return result
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
    drive_service: Any,
    folder_id: str,
    extensions: tuple[str, ...] | None = ("docx", "odt"),
) -> dict[str, str] | None:
    """Lists files in a Google Drive folder with specific extensions.  If extensions is None, return all the files."""
    query: str = (
        f"'{folder_id}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false"
    )
    try:
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
            if extensions is None or file["name"].lower().endswith(extensions)
        }

        return filtered_files  # Returns {filename: file_id} dictionary
    except Exception as e:
        print(f"An error occurred: {e}")
        return None  # Return empty dictionary in case of an error


def list_gdrive_subfolders(
    drive_service: Resource, parent_folder_id: str
) -> dict[str, str]:
    """
    Retrieves all subfolder names and their IDs inside a given Google Drive folder.

    Args:
        drive_service: Authenticated Google Drive API service instance.
        parent_folder_id (str): The ID of the parent folder to search within.

    Returns:
        Dict[str, str]: A dictionary where keys are subfolder names and values are their Google Drive IDs.
    """
    try:
        query: str = (
            f"'{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        )
        results = (
            drive_service.files()
            .list(q=query, fields="files(id, name, createdTime)")
            .execute()
        )

        # Extract subfolders with creation time
        subfolders: list[Tuple[str, str, str]] = [
            (file["name"], file["id"], file.get("createdTime", ""))
            for file in results.get("files", [])
        ]

        # Sort by createdTime (latest first)
        sorted_subfolders = sorted(subfolders, key=lambda x: x[2], reverse=True)

        return {name: folder_id for name, folder_id, _ in sorted_subfolders}

    except HttpError as error:
        print(f"Error retrieving subfolders: {error}")
        return {}


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
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None


def convert_gdrive_file_to_markdown(
    drive_service: Resource,
    file_id: str,
    file_name: str,
    output_folder_id: str,
    header_markdown: str = "",
) -> str | None:
    """
    Downloads a Google Drive file, converts it to Markdown using pypandoc, prepends a header, and uploads it back to Google Drive.

    Args:
        drive_service: Authenticated Google Drive API service instance.
        file_id (str): The ID of the file in Google Drive.
        file_name (str): The original name of the uploaded file.
        output_folder_id (str): The ID of the Google Drive folder to save the Markdown file.
        header_markdown (str): Additional Markdown content to prepend to the converted text.

    Returns:
        str | None: The Google Drive file ID of the uploaded Markdown file, or None if conversion fails.
    """
    try:
        # Extract base name without extension
        base_name: str = os.path.splitext(file_name)[0]
        file_type: str = os.path.splitext(file_name)[1].lstrip(
            "."
        )  # Get file extension
        temp_input_path: str = f"/tmp/{base_name}"
        temp_md_path: str = f"/tmp/{base_name}.md"

        # Download file content
        request = drive_service.files().get_media(fileId=file_id)
        file_data = BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        # Save the downloaded file
        with open(temp_input_path, "wb") as f:
            f.write(file_data.getvalue())

        # Convert to Markdown using Pandoc
        converted_markdown = pypandoc.convert_file(
            temp_input_path, "md", format=file_type
        )

        # Prepend the header Markdown
        full_markdown = f"{header_markdown}\n\n{converted_markdown}"

        # Save Markdown content
        with open(temp_md_path, "w", encoding="utf-8") as f:
            f.write(full_markdown)

        # Upload the converted Markdown file to Google Drive
        file_metadata = {
            "name": f"{base_name}.md",
            "mimeType": "text/markdown",
            "parents": [output_folder_id],
        }
        media = MediaFileUpload(temp_md_path, mimetype="text/markdown")
        uploaded_file = (
            drive_service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        # Cleanup temp files
        os.remove(temp_input_path)
        os.remove(temp_md_path)

        return uploaded_file["id"]

    except Exception as e:
        print(f"Error converting file {file_id} to Markdown: {e}")
        return None


def convert_gdrive_file_to_docx(
    drive_service: Resource, file_id: str, output_folder_id: str | None = None
) -> str | None:
    """
    Downloads a Google Drive file, converts it to DOCX using pypandoc, and uploads it back to Google Drive.

    Args:
        drive_service: Authenticated Google Drive API service instance.
        file_id (str): The ID of the file in Google Drive.
        output_folder_id (str): The ID of the Google Drive folder to save the DOCX file.
                               (Defaults to the same folder as the original file.)

    Returns:
        str | None: The file ID of the uploaded DOCX file, or None if conversion fails.
    """
    try:
        # Get file metadata to retrieve original name and parent folder
        file_metadata = (
            drive_service.files().get(fileId=file_id, fields="name, parents").execute()
        )
        file_name = file_metadata["name"]
        parent_folder_id: str = (
            file_metadata["parents"][0]
            if output_folder_id is None
            else output_folder_id
        )

        # Extract base name (without extension)
        base_name = os.path.splitext(file_name)[0]
        temp_md_path: str = f"/tmp/{base_name}.md"
        temp_docx_path: str = f"/tmp/{base_name}.docx"

        # Download file content as Markdown
        request = drive_service.files().get_media(fileId=file_id)
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        # Save the content as a temporary Markdown file
        with open(temp_md_path, "wb") as f:
            f.write(file_data.getvalue())

        # Convert Markdown to DOCX using pypandoc
        pypandoc.convert_file(temp_md_path, "docx", outputfile=temp_docx_path)

        # Upload the converted DOCX back to Google Drive
        file_metadata = {
            "name": f"{base_name}.docx",
            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "parents": [parent_folder_id],
        }
        media = MediaFileUpload(
            temp_docx_path,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        uploaded_file = (
            drive_service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        # Cleanup temporary files
        os.remove(temp_md_path)
        os.remove(temp_docx_path)

        return uploaded_file["id"]

    except Exception as e:
        print(f"Error converting file {file_id} to DOCX: {e}")
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
    drive_service: Resource,
    local_file_path: str,
    gdrive_file_name: str,
    target_dir_id: str,
) -> str | None:
    """
    Uploads a local file to a specific Google Drive folder, replacing any existing file with the same name.

    :param drive_service: Authenticated Google Drive API service instance.
    :param local_file_path: Path to the local file.
    :param target_dir_id: Google Drive folder ID where the file will be uploaded.
    :return: The new uploaded file's Google Drive ID.
    """
    try:
        # Step 1: Search for an existing file with the same name in the target directory
        query: str = (
            f"name = '{gdrive_file_name}' and '{target_dir_id}' in parents and trashed = false"
        )
        response = (
            drive_service.files().list(q=query, fields="files(id, name)").execute()
        )
        files = response.get("files", [])

        # Step 2: If a file exists, delete it
        if files:
            existing_file_id = files[0]["id"]
            drive_service.files().delete(fileId=existing_file_id).execute()
            print(
                f"🗑️ Existing file '{gdrive_file_name}' (ID: {existing_file_id}) deleted."
            )

        # Step 3: Upload the new file
        file_metadata: dict[str, Any] = {
            "name": gdrive_file_name,
            "parents": [target_dir_id],
        }
        media = MediaFileUpload(local_file_path, mimetype="text/markdown")

        uploaded_file = (
            drive_service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        print(
            f"✅ '{local_file_path}' uploaded successfully to file {gdrive_file_name} in Drive folder {target_dir_id}."
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


def get_gdrive_file_creation_date(drive_service, file_id: str) -> str | None:
    """
    Retrieves the creation date of a file in Google Drive based on its file ID.

    Args:
        drive_service: Authenticated Google Drive API service instance.
        file_id (str): The ID of the file to retrieve metadata for.

    Returns:
        str | None: The file's creation date in ISO format (YYYY-MM-DDTHH:MM:SS.sssZ) or None if an error occurs.
    """
    try:
        file_metadata = (
            drive_service.files().get(fileId=file_id, fields="createdTime").execute()
        )
        return file_metadata.get(
            "createdTime"
        )  # Example format: "2024-06-01T12:34:56.789Z"

    except HttpError as error:
        print(f"Error retrieving file creation date: {error}")
        return None  # Return None if an error occurs


def store_uploaded_file(
    drive_service: Resource, uploaded_file: UploadedFile, parent_folder_id: str
) -> str | None:
    """
    Handles a Streamlit UploadedFile by saving it as a temporary file and uploading it to Google Drive.

    Args:
        drive_service: Authenticated Google Drive API service instance.
        uploaded_file: Streamlit UploadedFile object.
        parent_folder_id (str): The ID of the Google Drive folder where the file should be uploaded.

    Returns:
        str | None: The Google Drive file ID of the uploaded file, or None if upload fails.
    """
    try:
        # ✅ Create a temporary file
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f".{uploaded_file.type.split('/')[-1]}"
        ) as temp_file:
            temp_file.write(uploaded_file.getbuffer())
            temp_file_path: str = temp_file.name  # ✅ Path to the temp file

        # ✅ Prepare file metadata for Google Drive upload
        file_metadata = {"name": uploaded_file.name, "parents": [parent_folder_id]}
        media = MediaFileUpload(temp_file_path, mimetype=uploaded_file.type)

        # ✅ Upload the file to Google Drive
        file_data = (
            drive_service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )
        file_id: str = file_data.get("id")

        # ✅ Cleanup temp file after upload
        os.remove(temp_file_path)

        return file_id

    except Exception as e:
        print(f"Error uploading file to Google Drive: {e}")
        return None


def generate_gdrive_link(file_id: str) -> str:
    """
    Generates a shareable Google Drive link from a file ID.

    Args:
        file_id (str): The ID of the uploaded file in Google Drive.

    Returns:
        str: The shareable Google Drive file link.
    """
    return f"https://drive.google.com/file/d/{file_id}/view"


def get_gdrive_file_name(drive_service: Resource, file_id: str) -> str | None:
    """
    Retrieves the file name of a Google Drive file using its file ID.

    Args:
        drive_service: Authenticated Google Drive API service instance.
        file_id (str): The ID of the file in Google Drive.

    Returns:
        str | None: The file name if found, otherwise None.
    """
    try:
        file_metadata = (
            drive_service.files().get(fileId=file_id, fields="name").execute()
        )
        return file_metadata.get("name")
    except HttpError as error:
        print(f"❌ Error retrieving file name: {error}")
        return None


def download_gdrive_file(drive_service: Resource, file_id: str) -> BytesIO | None:
    """
    Downloads a Google Drive file as a BytesIO object.

    Args:
        drive_service: Authenticated Google Drive API service instance.
        file_id (str): The ID of the file in Google Drive.

    Returns:
        BytesIO | None: The file data as a BytesIO stream, or None if download fails.
    """
    try:
        request = drive_service.files().get_media(fileId=file_id)
        file_data = BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        file_data.seek(0)  # Reset cursor to the beginning
        return file_data

    except Exception as e:
        print(f"❌ Error downloading file from Google Drive: {e}")
        return None


def send_email_with_gdrive_attachment(
    drive_service: Resource, recipient_email: str, subject: str, body: str, file_id: str
) -> bool:
    """
    Sends an email with an attachment downloaded from Google Drive.

    Args:
        drive_service: Authenticated Google Drive API service instance.
        recipient_email (str): The recipient's email.
        subject (str): Email subject.
        body (str): Email body.
        file_id (str): The Google Drive file ID.

    Returns:
        None
    """
    sender_email: str = "ghanimaghanemprof@gmail.com"
    sender_password: str = st.secrets["config"][
        "grading_assistant_gmail_app_key"
    ]  # Use App Password

    # ✅ Create the email message
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient_email
    msg.set_content(body)

    # ✅ Download file from Google Drive
    try:
        file_name: str | None = get_gdrive_file_name(drive_service, file_id)
        if file_name is None:
            print("❌ Error retrieving file name from Google Drive.")
            return False
        file_data: BytesIO | None = download_gdrive_file(drive_service, file_id)
        if file_data is None:
            print("❌ Error downloading file from Google Drive.")
            return False
        # ✅ Attach the downloaded file
        msg.add_attachment(
            file_data.read(),
            maintype="application",
            subtype="octet-stream",
            filename=file_name,
        )
    except Exception as e:
        print(f"❌ Error downloading file from Google Drive: {e}")
        return False

    # ✅ Secure Connection and Send Email
    try:
        context: smtplib.SSLContext = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
            print("✅ Email sent successfully with attachment!")
        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False


class MyData(BaseModel):
    name: str = Field(..., description="Name of the item")
    value: int = Field(..., description="Integer value")


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
