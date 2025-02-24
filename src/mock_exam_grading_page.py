import pprint
from openai import OpenAI
from referencing import Resource
import streamlit as st
from pprint import pprint
from typing import Any, Literal

from gaclasses import MockExam, Submission
from gdrive import (
    convert_gdrive_file_to_markdown,
    ensure_gdrive_directory,
    get_gdrive_markdown_text,
    list_gdrive_files,
    upload_markdown_to_gdrive,
)

SPLIT_PROMPT = "Analyze this student's mock exam in English for a French prépa and split it into three parts for the Synthèse, Essai, and Traduction."


def generate_mock_exam(
    drive_service: Any, batch_dir_id: str, md_file_id: str
) -> MockExam | None:
    client: OpenAI = st.session_state.openai_client
    md_text: str | None = get_gdrive_markdown_text(
        st.session_state.drive_service, md_file_id
    )
    if md_text is None:
        return None
    try:
        response: Any = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SPLIT_PROMPT},
                {"role": "user", "content": md_text},
            ],
            response_format=MockExam,
        )
    except Exception as e:
        st.error(f"Error generating mock exam: {e}")
        return None
    result: MockExam = response.choices[0].message.parsed
    return result


def write_mock_exam_sections(
    drive_service: Resource[Any],
    batch_dir_id: str,
    md_file_name: str,
    mock_exam: MockExam,
) -> None:
    st.info(f"Writing mock exam sections for {md_file_name}...")
    for section in [mock_exam.synthese, mock_exam.essai, mock_exam.traduction]:
        section: Submission
        section_file_name: str = f"{md_file_name} - {section.submission_type()}.md"
        section_text: str = section.markdown_content
        section_file_id: str = upload_markdown_to_gdrive(
            drive_service, section_file_name, batch_dir_id, section_text
        )
        st.success(
            f"Mock exam section {section.submission_type()} written successfully to {section_file_id}!"
        )
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
        " - synthese",
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


def mock_exam_grading_page() -> None:
    drive_service: Resource = st.session_state.drive_service
    batch_name: str = st.session_state.config.current_batch
    st.header("Mock Exam Grading")
    with st.form(
        "convert_to_md", border=True, clear_on_submit=False, enter_to_submit=False
    ):
        st.subheader("Choose the student submissions (docx or odt):")
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
        st.subheader("Choose the student submissions (md):")
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
        with st.status("Splitting markdown files..."):
            st.info("Splitting markdown files...")
            nerrors: int = 0
            exams: dict[str, MockExam] = {}
            for md_file in selected_md_files:
                md_file_id: str = md_files[md_file]
                mock_exam: MockExam | None = generate_mock_exam(
                    drive_service, batch_dir_id, md_file_id
                )
                if mock_exam is None:
                    st.error(f"Error generating mock exam for file {md_file}")
                    nerrors += 1
                else:
                    st.success(f"Mock exam generated for file {md_file}")
                    print(f"Mock exam for {md_file}:")
                    pprint(mock_exam.dict())
                    exams[md_file] = mock_exam
                    write_mock_exam_sections(
                        drive_service, batch_dir_id, md_file, mock_exam
                    )
                    st.success(f"Mock exam sections written for {md_file}!")
            if nerrors == 0:
                st.success("Markdown files split successfully!")
            else:
                st.error(f"Encountered {nerrors} errors splitting markdown files!")
        selected_exam: str = st.selectbox("Select mock exam", list(exams.keys()))
        st.subheader(f"Mock exam for {selected_exam}")
        st.json(exams[selected_exam].dict(), expanded=False)


mock_exam_grading_page()
