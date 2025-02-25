import time
import pprint
from threading import Thread
from httpx import delete
from openai import OpenAI
from openai.types.beta.threads.run import Run
from referencing import Resource
import streamlit as st
from pprint import pprint
from typing import Any, Literal

from gaclasses import Assessment, MockExam, Submission
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
                    drive_service, batch_dir_id, md_file_id
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

    with st.form(
        "Grade Mock Exam",
        border=True,
        clear_on_submit=False,
        enter_to_submit=False,
    ):
        print("Entering grading form...")
        st.subheader("Step 3: Grade Mock Exam Sections")
        st.session_state.selected_exam = st.selectbox(
            "Select mock exam", list(st.session_state.mock_exams.keys())
        )
        if st.session_state.selected_exam is not None:
            print(f"Selected exam: {st.session_state.selected_exam}")
            st.subheader(f"Mock exam for {st.session_state.selected_exam}")
            st.json(
                st.session_state.mock_exams[st.session_state.selected_exam].dict(),
                expanded=False,
            )
        grade_button: bool = st.form_submit_button("Grade Mock Exam")
    if grade_button:
        print("Grading button pushed...")
        if st.session_state.selected_exam is None:
            st.error("No mock exam selected!")
            return
        print("Grading mock exam...")
        exam: MockExam = st.session_state.mock_exams[st.session_state.selected_exam]
        with st.status(f"Grading mock exam..."):
            st.info("Grading Synthèse section...")
            synthese_grade: str = call_assistant(
                st.session_state.config.synthese_assistant_id,
                exam.synthese.markdown_content,
            )
            st.info("Grading Essai section...")
            essai_grade: str = call_assistant(
                st.session_state.config.essai_assistant_id,
                exam.essai.markdown_content,
            )
            st.info("Grading Traduction section...")
            traduction_grade: str = call_assistant(
                st.session_state.config.traduction_assistant_id,
                exam.traduction.markdown_content,
            )
            st.success("Mock exam graded successfully!")
        st.subheader("Mock Exam Grades")
        st.markdown(f"**Synthèse Grade**:\n\n {synthese_grade}")
        st.markdown(f"**Essai Grade**:\n\n {essai_grade}")
        st.markdown(f"**Traduction Grade**:\n\n {traduction_grade}")


mock_exam_grading_page()
