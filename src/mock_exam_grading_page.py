from os import error
import time
import pprint
from threading import Thread
import docx
from openai import OpenAI
from openai.types.beta.threads.run import Run
from referencing import Resource
import streamlit as st
from pprint import pprint
from typing import Any

from gaclasses import Assessment, MockExam, Submission
from gdrive import (
    convert_gdrive_file_to_markdown,
    convert_gdrive_file_to_docx,
    ensure_gdrive_directory,
    get_gdrive_file_creation_date,
    get_gdrive_file_name,
    get_gdrive_markdown_text,
    list_gdrive_files,
    upload_markdown_to_gdrive,
    send_email_with_gdrive_attachment,
)
import gdrive

SPLIT_PROMPT: str = """Analyze this student's mock exam in English for a French prépa and split it into three parts for the Synthèse, Essai, and Traduction.
    The original file ID is {file_id}.
    The original file name is {file_name}.
    The date of the file is {file_date}.
    """


def generate_mock_exam(
    drive_service: Any, batch_dir_id: str, md_file_id: str, md_file: str
) -> MockExam | None:
    client: OpenAI = st.session_state.openai_client
    md_text: str | None = get_gdrive_markdown_text(
        st.session_state.drive_service, md_file_id
    )
    if md_text is None:
        return None
    try:
        md_file_date: str = get_gdrive_file_creation_date(drive_service, md_file_id)
        final_prompt: str = SPLIT_PROMPT.format(
            file_id=md_file_id,
            file_name=md_file,
            file_date=md_file_date or "unknown",
        )
        response: Any = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": final_prompt},
                {"role": "user", "content": md_text},
            ],
            response_format=MockExam,
        )
    except Exception as e:
        st.error(f"Error generating mock exam: {e}")
        return None
    result: MockExam = response.choices[0].message.parsed
    return result


def email_mock_exam_assessment(
    drive_service: Resource, mock_exam: MockExam, docx_file_id: str
) -> None:
    """Email the final docx assessment to the professor for validation"""
    prof_email: str = st.secrets["config"]["professor_email"]
    docx_file_name: str | None = get_gdrive_file_name(drive_service, docx_file_id)
    print(f"Emailing mock exam result in {docx_file_name} to {prof_email}...")
    email_subject: str = (
        f"Mock Exam grading results for {mock_exam.name} on {mock_exam.date}"
    )
    email_body: str = (
        f"Please find attached the mock exam for {mock_exam.name} on {mock_exam.date}."
        f"\n\nThe file can be found on the Google drive here: {gdrive.generate_gdrive_link(docx_file_id)}"
        f"\n\nYours truly,\n\nThe Grading Assistant"
    )

    sent_ok: bool = send_email_with_gdrive_attachment(
        drive_service,
        prof_email,
        email_subject,
        email_body,
        docx_file_id,
    )
    if sent_ok:
        st.success(f"Mock exam for {mock_exam.name} sent to {prof_email}!")
    else:
        st.error(f"Error sending mock exam to {prof_email}!")


def write_mock_exam_sections(
    drive_service: Resource[Any],
    batch_dir_id: str,
    md_file_name: str,
    mock_exam: MockExam,
) -> None:
    st.info(f"Writing mock exam sections for {md_file_name}...")
    error: bool = False
    for section in [mock_exam.synthese, mock_exam.essai, mock_exam.traduction]:
        section: Submission
        section_file_name: str = f"{md_file_name} - {section.submission_type()}.md"
        section_text: str = section.markdown_content
        section_file_id: str | None = upload_markdown_to_gdrive(
            drive_service, section_file_name, batch_dir_id, section_text
        )
        if section_file_id is None:
            st.error(f"Error writing mock exam section {section.submission_type()}!")
            error = True
        else:
            st.success(
                f"Mock exam section {section.submission_type()} written successfully to {section_file_name}!"
            )
    if error:
        st.error(f"Error writing mock exam sections for {md_file_name}!")
    else:
        st.success(f"Mock exam sections written successfully for {md_file_name}!")
    return


def ensure_batch_directory(drive_service: Resource[Any], batch_name: str) -> str | None:
    batch_folder_id: str | None = ensure_gdrive_directory(
        drive_service, st.session_state.output_folder_id, batch_name
    )
    return batch_folder_id


def filter_md_files(md_files: dict[str, str]) -> dict[str, str]:
    """Filters out files whose base names end with ' - synthese', ' - essai', or ' - traduction'."""
    excluded_suffixes: tuple[str, str, str] = (
        " - synthèse",
        " - essai",
        " - traduction",
        " - assessment",
    )

    filtered_files: dict[str, str] = {
        file_name: file_id
        for file_name, file_id in md_files.items()
        if not any(
            file_name.rsplit(".", 1)[0].lower().endswith(suffix)
            for suffix in excluded_suffixes
        )
    }

    return filtered_files


def call_assistant(assistant_id: str, msg: str) -> str:
    print(f"Calling assistant {assistant_id} with message: {len(msg)} chars.")
    client: OpenAI = st.session_state.openai_client
    try:
        thread: Thread = client.beta.threads.create()
        print(f"Thread created: {thread.id}")
        msg = client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=f"Grade this text per instructions: {msg}",
        )
        print(f"Message created: {msg.id}")
        run: Run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id,
            #           instructions="Grade this text per instructions",
        )
        print(f"Run created: {run.id}")
        while run.status != "completed":
            print(f"Waiting for run {run.id} to complete, status is {run.status}...")
            time.sleep(1)

        msgs = client.beta.threads.messages.list(thread_id=thread.id)
        print(f"Run {run.id} completed, deleting thread {thread.id}...")
        client.beta.threads.delete(thread.id)
        for m in msgs:
            print(f"{m.role}: {len(m.content[0].text.value)} chars")
        return msgs.data[0].content[0].text.value
    except Exception as e:
        st.error(f"Error grading section: {e}")
        return "Error grading section"


def get_assessment(exam: MockExam) -> Assessment:
    st.info(f"Getting assessment for mock exam {exam.description}...")


def mock_exam_grading_page() -> None:
    drive_service: Resource = st.session_state.drive_service
    batch_name: str = st.session_state.config.current_batch
    st.header("Mock Exam Grading")
    with st.form(
        "convert_to_md", border=True, clear_on_submit=False, enter_to_submit=False
    ):
        st.subheader("Step 1: Convert student submissions to markdown")
        submissions: dict[str, str] = list_gdrive_files(
            drive_service, st.session_state.attachments_folder_id
        )
        print(f"Submissions: {submissions}")
        selected_submissions: list[str] = st.multiselect(
            "Select submissions", list(submissions.keys())
        )
        conversion_button: bool = st.form_submit_button("Convert to Markdown")

    if conversion_button:

        with st.status("Converting files..."):
            target_dir_id: str | None = ensure_batch_directory(
                drive_service, batch_name
            )
            st.info(
                f"Converting files {selected_submissions} into Google drive directory {batch_name}..."
            )
            for submission in selected_submissions:
                st.info(f"Converting file {submission}...")
                convert_gdrive_file_to_markdown(
                    drive_service, submissions[submission], submission, target_dir_id
                )
                st.success(f"File {submission} converted successfully!")
            st.success("Files converted successfully!")
    else:
        st.info("No files converted yet.")

    with st.form(
        "Split Markdown Files",
        border=True,
        clear_on_submit=False,
        enter_to_submit=False,
    ):
        st.subheader("Step 2: Split Markdown files into sections")
        batch_dir_id: str | None = ensure_batch_directory(drive_service, batch_name)
        if batch_dir_id is None:
            st.error(f"Batch directory {batch_name} not found!")
            return
        md_files: dict[str, str] = list_gdrive_files(
            drive_service, batch_dir_id, tuple(["md"])
        )
        md_files = filter_md_files(md_files)
        print(f"Markdown files: {md_files}")
        selected_md_files: list[str] = st.multiselect(
            "Select Markdown files", list(md_files.keys())
        )
        print(f"Selected Markdown files: {selected_md_files}")
        split_button: bool = st.form_submit_button("Split Markdown Files")

    if split_button:
        # Split the markdown files
        if len(selected_md_files) == 0:
            st.error("No markdown files selected!")
            return
        with st.status("Splitting markdown files..."):
            st.info("Splitting markdown files...")
            nerrors: int = 0
            for md_file in selected_md_files:
                md_file_id: str = md_files[md_file]
                mock_exam: MockExam | None = generate_mock_exam(
                    drive_service, batch_dir_id, md_file_id, md_file
                )
                if mock_exam is None:
                    st.error(f"Error generating mock exam for file {md_file}")
                    nerrors += 1
                else:
                    st.success(f"Mock exam generated for file {md_file}")
                    print(f"Mock exam for {md_file}:")
                    pprint(mock_exam.dict())
                    st.session_state.mock_exams[md_file] = mock_exam
                    write_mock_exam_sections(
                        drive_service, batch_dir_id, md_file, mock_exam
                    )
                    st.success(f"Mock exam sections written for {md_file}!")
            if nerrors == 0:
                st.success("Markdown files split successfully!")
            else:
                st.error(f"Encountered {nerrors} errors splitting markdown files!")

    with st.container(border=True):
        print("Entering grading area...")
        st.subheader("Step 3: Grade Mock Exam Sections")
        st.session_state.selected_exams = st.multiselect(
            "Select mock exam", list(st.session_state.mock_exams.keys())
        )
        for mock_exam_key in st.session_state.selected_exams:
            print(f"Selected exam: {mock_exam_key}")
            st.subheader(f"Mock exam for {mock_exam_key}")
            st.json(
                st.session_state.mock_exams[mock_exam_key].dict(),
                expanded=False,
            )
        with st.form(
            "Grade Mock Exams",
            border=True,
            clear_on_submit=False,
            enter_to_submit=False,
        ):
            grade_button: bool = st.form_submit_button("Grade Mock Exam")
    if grade_button:
        print("Grading button pushed...")
        if len(st.session_state.selected_exams) == 0:
            st.error("No mock exams selected!")
            return
        print("Grading mock exams...")
        for selected_exam in st.session_state.selected_exams:
            print(f"Grading mock exam {selected_exam}...")
            exam: MockExam = st.session_state.mock_exams[selected_exam]
            full_assessment: str = (
                f"# Assessment of mock exam for {exam.name} on {exam.date}\n\n"
            )
            with st.status(f"Grading mock exam..."):
                full_assessment += (
                    "## Synthèse\n\n" + grade_section(exam.synthese) + "\n\n"
                )
                full_assessment += "## Essai\n\n" + grade_section(exam.essai) + "\n\n"
                full_assessment += "## Traduction\n\n" + grade_section(exam.traduction)
            assessment_file_name: str = (
                f"{exam.original_file_name.rsplit('.', 1)[0]} - assessment.md"
            )
            print(f"Uploading assessment to Google Drive as {assessment_file_name}...")
            st.info(f"Uploading assessment to Google Drive...")
            assessment_file_id: str | None = upload_markdown_to_gdrive(
                st.session_state.drive_service,
                assessment_file_name,
                batch_dir_id,
                full_assessment,
            )
            if assessment_file_id is None:
                st.error(f"Error uploading assessment to Google Drive!")
                return
            print(f"Assessment uploaded to Google Drive as {assessment_file_id}!")
            st.info(f"Converting assessment to docx...")
            print(f"Converting assessment to docx...")
            docx_assessment_file_id: str | None = convert_gdrive_file_to_docx(
                st.session_state.drive_service,
                assessment_file_id,
                batch_dir_id,
            )
            if docx_assessment_file_id is None:
                st.error(f"Error converting assessment to docx!")
                return
            email_mock_exam_assessment(drive_service, exam, docx_assessment_file_id)
            print(f"Assessment converted to docx as {docx_assessment_file_id}!")
            st.success(f"Assessment for {exam.name} saved to {assessment_file_name}!")


def grade_section(section: Submission) -> str:
    st.divider()
    st.info(f"Grading section {section.submission_type()}...")
    assessment: str = call_assistant(
        section.get_assistant_id(st.session_state.config), section.markdown_content
    )
    original_base_name: str = section.original_file_name.rsplit(".", 1)[0]
    file_name: str = (
        f"{original_base_name} - {section.submission_type()} - assessment.md"
    )
    upload_markdown_to_gdrive(
        st.session_state.drive_service,
        file_name,
        st.session_state.output_folder_id,
        assessment,
    )
    st.success(
        f"Section {section.submission_type()} graded successfully and saved to {file_name}!"
    )
    st.subheader(f"{section.submission_type()} Assessment")
    st.markdown(assessment)
    return assessment


mock_exam_grading_page()
