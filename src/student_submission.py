import re
from typing import Any
import streamlit as st
from datetime import datetime
import smtplib
import ssl
from email.message import EmailMessage

from streamlit.runtime.uploaded_file_manager import UploadedFile
from gdrive import (
    generate_gdrive_link,
    get_gdrive_folder_path,
    init_google_drive,
    list_gdrive_subfolders,
    convert_gdrive_file_to_markdown,
    store_uploaded_file,
)

# Set page config with favicon
st.set_page_config(page_title="Student Submission", page_icon="📤", layout="wide")

# Google Drive Setup
init_google_drive()


def make_student_submission_filename(student_name: str, file_name: str) -> str:
    """
    Prepends the student's name to the uploaded file name with ' - ' if not already included.

    Args:
        student_name (str): The name of the student.
        file_name (str): The original uploaded file name.

    Returns:
        str: The formatted file name.
    """

    # Normalize names by removing non-alphanumeric characters (excluding spaces and dots)
    def normalize_name(name: str) -> str:
        return re.sub(r"[^a-zA-Z0-9\s.]", "", name).strip().lower()

    normalized_student_name: str = normalize_name(student_name)
    normalized_file_name: str = normalize_name(file_name)

    if normalized_student_name in normalized_file_name:
        return file_name  # Return original if the name is already included

    return f"{student_name} - {file_name}"


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


def send_email_notification(
    student_name: str,
    student_email: str,
    file_name: str,
    md_file_id: str,
    orig_file_id: str,
) -> bool:
    """
    Sends an email notification to the professor when a student's submission is processed.

    Args:
        professor_email (str): The recipient's email (professor).
        student_name (str): The name of the student who submitted the work.
        file_name (str): The name of the submitted file.

    Returns:
        None
    """
    # ✅ Configure Email Sender & Receiver
    sender_email: str = "ghanimaghanemprof@gmail.com"  # Use an authorized sender email
    sender_password: str = st.secrets["config"]["grading_assistant_gmail_app_key"]
    subject: str = f"📢 New Student Submission Processed from {student_name}"
    body: str = f"""
    Dear Professor,

    A new student submission has been successfully uploaded and processed.
    
    Student Name: {student_name}
    Student Email: {student_email}
    File Submitted: {file_name}
    
    You can access the Markdown file in Google Drive using the following link:
    {generate_gdrive_link(md_file_id)}
    
    You can access the original file in Google Drive using the following link:
    {generate_gdrive_link(orig_file_id)}

    Regards,
    
    The Grading Assistant
    """

    # ✅ Set up Email Message
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = st.secrets["config"]["professor_email"]  # Professor's email

    # ✅ Secure Connection and Send Email
    try:
        context: smtplib.SSLContext = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
            print("✅ Email sent successfully!")
        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False


if "batch_directories" not in st.session_state:
    st.session_state.batch_directories = get_batch_directories()

st.title("🤖 GrAIding Assistant")

st.header("Welcome to Professor Ghanem's GrAIding Assistant!")
st.subheader("📤  Upload your work here for grading.")
st.subheader("Instructions")

st.markdown(
    """
    Use this app to upload your DOCX or ODT files for grading.   
    Enter your name and email, choose the exam you are entering work for, and upload your file.
    
    If you need assistance, please contact Professor Ghanem at [ghanima.ghanem@gmail.com](mailto:ghanima.ghanem@gmail.com).
    
    Please let Professor Ghanem know when you have uploaded your work.
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
        "Select the exam you are entering work for:",
        list(batch_directories.keys()),
        index=0,
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
    final_file_name: str = make_student_submission_filename(
        student_name, uploaded_file.name
    )
    with st.status(
        f"Uploading and processing {uploaded_file.name}, renaming to {final_file_name}..."
    ):
        batch_dir_id: str = batch_directories[selected_batch]
        with st.spinner(f"Uploading file {uploaded_file.name}..."):
            # Upload to Attachments Directory
            file_id: str | None = store_uploaded_file(
                drive_service, uploaded_file, batch_dir_id, final_file_name
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
                drive_service, file_id, final_file_name, batch_dir_id, headers
            )

            if markdown_file_id:
                st.success("Processing successful - congratulations!")
                # Send Email Notification
                send_email_notification(
                    student_name,
                    student_email,
                    final_file_name,
                    markdown_file_id,
                    file_id,
                )
            else:
                st.error("❌ Error in processing. Please try again later.")
