import markdown
from referencing import Resource
import streamlit as st
from typing import Any, List
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Optional
from gdrive import read_json_from_drive, store_pydantic_to_drive, get_gdrive_file_id

SYNTHESE_ASSISTANT_ID: str = "asst_FRpITbk1I9E0VwHQ0ssfwV9l"
ESSAI_ASSISTANT_ID: str = "asst_kBQpeDfziFayy2itJb7LY7dY"
TRADUCTION_ASSISTANT_ID: str = "asst_pSFwOLVQZwWtLJA99hrfUAMP"


# Pydantic Models with Field Descriptions
class Configuration(BaseModel):
    """Handles application configuration settings."""

    synthese_assistant_id: str = Field(
        ...,
        description="OpenAI Assistant ID for Synthèse",
    )
    essai_assistant_id: str = Field(
        ...,
        description="OpenAI Assistant ID for Essai",
    )
    traduction_assistant_id: str = Field(
        ...,
        description="OpenAI Assistant ID for Traduction",
    )

    synthese_weight: int = Field(
        30, description="Weight of Synthèse section in Mock Exam grading"
    )
    essai_weight: int = Field(
        50, description="Weight of Essai section in Mock Exam grading"
    )
    traduction_weight: int = Field(
        20, description="Weight of Traduction section in Mock Exam grading"
    )

    current_batch: Optional[str] = Field(
        "Mock Exams Feb 2025", description="Current batch of submissions"
    )

    config_file_name: Optional[str] = Field(
        "gaconfig.json", description="Name of the configuration file"
    )

    @classmethod
    def load_from_drive(cls, config_file_name: str | None) -> "Configuration":
        service: Any = st.session_state.drive_service
        config_file_id: str | None = get_gdrive_file_id(
            service,
            st.session_state.config_directory_id,
            config_file_name or st.session_state.config_file_name,
        )
        if config_file_id is None:
            print("No configuration file ID found, creating new configuration.")
            return make_configuration()
        config_data: Any | None = read_json_from_drive(service, config_file_id)
        if config_data is None:
            print("No configuration data found, creating new configuration.")
            return make_configuration()
        else:
            return cls(**config_data)

    def save_to_drive(self) -> None:
        service: Resource = st.session_state.drive_service
        file_name: str = (
            self.config_file_name
            if self.config_file_name is not None
            else "config.json"
        )
        print(f"Saving configuration to Google Drive file {file_name}...")
        store_pydantic_to_drive(
            service, self, st.session_state.config_directory_id, file_name
        )


def make_configuration() -> Configuration:
    return Configuration(
        synthese_assistant_id=SYNTHESE_ASSISTANT_ID,
        essai_assistant_id=ESSAI_ASSISTANT_ID,
        traduction_assistant_id=TRADUCTION_ASSISTANT_ID,
    )


# Pydantic Models with Field Descriptions
class Submission(BaseModel):
    """Represents a single student submission, containing metadata and content."""

    name: str = Field(
        ...,
        description="Name of the student if found or empty string.  Might be in the original file name.",
    )
    date: str = Field(
        ...,
        description="Date of submission formatted as YYYY-MM-DD or empty string if none found",
    )
    description: str = Field(..., description="Description of the submission")
    original_file: str = Field(
        ..., description="Google Drive file ID of the original submission"
    )
    original_file_name: str = Field(
        ..., description="Name of the original submission file"
    )
    markdown_content: str = Field(
        ...,
        description="Markdown-formatted content of the submission if found, empty string otherwise",
    )
    word_count: int = Field(
        ..., description="Word count of the markdown content of the submission"
    )

    @classmethod
    def get_assistant_id(cls, config: Configuration) -> str:
        """Returns the assistant ID for grading. Should be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement get_assistant_id method")

    @classmethod
    def submission_type(cls) -> str:
        """Returns the type of submission. Should be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement submission_type method")


class Assessment(BaseModel):
    """Represents the assessment of a submission, including feedback and grading."""

    assessment_text: str = Field(
        ..., description="Generated assessment text providing feedback and corrections"
    )
    error_distribution: Dict[str, int] = Field(
        ..., description="Dictionary mapping error types to their count"
    )
    final_score: int = Field(
        ..., description="Final score of the submission, from 0 to 20"
    )


class Synthese(Submission):
    """Represents the Synthèse section of a Mock Exam submission."""

    @classmethod
    def get_assistant_id(cls, config: Configuration):
        return config.synthese_assistant_id

    @classmethod
    def submission_type(cls) -> str:
        return "Synthèse"


class Essai(Submission):
    """Represents the Essai section of a Mock Exam submission."""

    @classmethod
    def get_assistant_id(cls, config: Configuration):
        return config.essai_assistant_id

    @classmethod
    def submission_type(cls) -> str:
        return "Essai"


class Traduction(Submission):
    """Represents the Traduction section of a Mock Exam submission."""

    @classmethod
    def get_assistant_id(cls, config: Configuration):
        return config.traduction_assistant_id

    @classmethod
    def submission_type(cls) -> str:
        return "Traduction"


class MockExam(Submission):
    """Represents a complete Mock Exam, consisting of three sections: Synthèse, Essai, and Traduction."""

    synthese: Synthese = Field(..., description="Synthèse section of the Mock Exam")
    essai: Essai = Field(..., description="Essai section of the Mock Exam")
    traduction: Traduction = Field(
        ..., description="Traduction section of the Mock Exam"
    )

    @classmethod
    def submission_type(cls) -> str:
        return "Mock Exam"


class Batch(BaseModel):
    """Represents a batch of submissions, including metadata and references to stored files."""

    name: str = Field(
        ...,
        description="Batch name, typically representing a set of Mock Exam submissions",
    )
    description: Optional[str] = Field(
        "", description="Optional description of the batch"
    )
    date: datetime = Field(..., description="Date of batch processing")
    directory_id: str = Field(
        ..., description="Google Drive folder ID for storing batch files"
    )
    excel_file_id: str = Field(
        ..., description="Google Drive file ID of the batch grading Excel sheet"
    )
    submissions: List[Submission] = Field(
        ..., description="List of student submissions in the batch"
    )
