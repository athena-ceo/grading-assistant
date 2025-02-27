import re
from typing import Any
import streamlit as st
from datetime import datetime

from streamlit.runtime.uploaded_file_manager import UploadedFile
from gdrive import (
    get_gdrive_folder_path,
    init_google_drive,
    list_gdrive_subfolders,
    convert_gdrive_file_to_markdown,
    store_uploaded_file,
)

# Set page config with favicon
st.set_page_config(page_title="Student Submission", page_icon="📤")

# Google Drive Setup
init_google_drive()


def get_batch_directories() -> dict[str, str]:
    """Retrieve all subdirectories (batches) from the output directory, sorted by creation date."""
    drive_service = st.session_state.drive_service
    output_folder_id: str = st.session_state.output_folder_id
    print(
        f"Batch directory is {output_folder_id} whose name is {get_gdrive_folder_path(drive_service, output_folder_id)}"
    )
    subfolders: dict[str, str] = list_gdrive_subfolders(drive_service, output_folder_id)
    print(f"Subfolders: {subfolders}")
    return subfolders


def is_valid_email(email: str) -> bool:
    """Checks if an email is in a valid format."""
    email_regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(email_regex, email) is not None


if "batch_directories" not in st.session_state:
    st.session_state.batch_directories = get_batch_directories()

st.title("🤖 GrAIding Assistant")

st.header("Welcome to Professor Ghanem's GrAIding Assistant!")
st.subheader("📤  Upload your work here for grading.")
st.subheader("Instructions")

st.markdown(
    """
    Use this app to upload your DOCX or ODT files for grading.   
    Select the correct exam for your submission, enter your name and email, choose the exam you are entering work for, and upload your file.
    
    If you need assistance, please contact Professor Ghanem at [ghanima.ghanem@gmail.com](mailto:ghanima.ghanem@gmail.com).
    """
)
st.divider()

# Student Information
student_name: str = st.text_input("Full Name")
student_email: str = st.text_input("Email")
if student_email and not is_valid_email(student_email):
    st.error("❌ Please enter a valid email address.")

# Retrieve and display batch directories
batch_directories: dict[str, str] = st.session_state.batch_directories
if batch_directories:
    default_batch: str = next(iter(batch_directories))  # Most recent batch
    selected_batch: str = st.selectbox(
        "Select Batch Directory:", list(batch_directories.keys()), index=0
    )
else:
    st.error("No batch directories found. Please contact Professor Ghanem.")
    st.stop()

# File Upload
uploaded_file: UploadedFile | None = st.file_uploader(
    "Upload your work file (DOCX or ODT):", type=["docx", "odt"]
)

if st.button("Submit Your Work"):
    if not uploaded_file:
        st.warning("❌ Please upload a DOCX or ODT file before submitting.")
        st.stop()
    if not student_name:
        st.warning("❌ Please enter your name and email before submitting.")
        st.stop()
    if not student_email:
        st.warning("❌ Please enter your email before submitting.")
        st.stop()
    if not is_valid_email(student_email):
        st.warning("❌ Please enter a valid email address.")
        st.stop()
    drive_service = st.session_state.drive_service
    with st.status(f"Uploading and processing {uploaded_file.name}..."):
        batch_dir_id: str = batch_directories[selected_batch]
        with st.spinner(f"Uploading file {uploaded_file.name}..."):
            # Upload to Attachments Directory
            file_id: str | None = store_uploaded_file(
                drive_service, uploaded_file, batch_dir_id
            )
        if file_id is None:
            st.error("❌ Error in uploading file. Please try again later.")
            st.stop()
        with st.spinner("Processing file..."):
            # Convert to Markdown and Save in Batch Directory
            batch_dir_id: str = batch_directories[selected_batch]
            headers: str = (
                f"Name: {student_name}\nEmail: {student_email}\nDate: {datetime.now().strftime('%Y-%m-%d')}"
            )
            markdown_file_id: str | None = convert_gdrive_file_to_markdown(
                drive_service, file_id, uploaded_file.name, batch_dir_id, headers
            )

            if markdown_file_id:
                st.success("Processing successful - congratulations!")
            else:
                st.error("❌ Error in processing. Please try again later.")
