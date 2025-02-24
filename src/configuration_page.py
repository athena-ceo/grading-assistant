import streamlit as st
from gaclasses import Configuration
import unicodedata

from gdrive import list_gdrive_files


def normalize_string(s: str) -> str:
    """Converts a string to lowercase and removes accents."""
    normalized: str = unicodedata.normalize("NFD", s)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").lower()


def configuration_page() -> None:
    st.title("Configuration Settings")

    config: Configuration = st.session_state.config

    with st.form("Upload Configuration", clear_on_submit=True):
        st.subheader("Upload Configuration File")
        config_files: dict[str, str] = list_gdrive_files(
            st.session_state.drive_service,
            st.session_state.config_directory_id,
            tuple(["json"]),
        )
        print(f"Config files: {config_files}")
        selected_config_file: str = st.selectbox(
            "Select config file", list(config_files.keys())
        )
        load_config_button: bool = st.form_submit_button("Load configuration")

    if load_config_button:
        Configuration.load_from_drive(selected_config_file)
        st.success("Configuration loaded successfully!")

    st.subheader("OpenAI Keys")
    st.session_state.openai_api_key = st.text_input(
        "Enter OpenAI API Key", st.secrets["OpenAI"]["OPENAI_API_KEY"], type="password"
    )
    st.session_state.openai_org_id = st.text_input(
        "Enter OpenAI Organization ID",
        st.secrets["OpenAI"]["OPENAI_ORGANIZATION_ID"],
        type="password",
    )
    st.session_state.openai_project_id = st.text_input(
        "Enter OpenAI Project ID",
        st.secrets["OpenAI"]["OPENAI_PROJECT_ID"],
        type="password",
    )

    st.subheader("Assistant IDs")
    config.synthese_assistant_id = st.text_input(
        "Synthèse Assistant ID", config.synthese_assistant_id
    )
    config.essai_assistant_id = st.text_input(
        "Essai Assistant ID", config.essai_assistant_id
    )
    config.traduction_assistant_id = st.text_input(
        "Traduction Assistant ID", config.traduction_assistant_id
    )

    st.subheader("Mock Exam Section Weights")
    sections: dict[str, int] = {"Synthèse": 30, "Essai": 50, "Traduction": 20}
    for sec, default_weight in sections.items():
        section_name: str = f"{normalize_string(sec)}_weight"
        setattr(
            config,
            section_name,
            st.slider(
                f"{sec} Weight (%)",
                0,
                100,
                getattr(config, section_name, default_weight),
            ),
        )

    st.subheader("Current Batch")
    config.current_batch = st.text_input("Current Batch", config.current_batch)
    config.config_file_name = st.text_input(
        "Configuration File Name", st.session_state.config_file_name
    )

    if st.button("Save Configuration"):
        if (
            config.synthese_weight + config.essai_weight + config.traduction_weight
            != 100
        ):
            st.error("Weights must add up to 100!")
            return
        try:
            config.save_to_drive()
            st.success("Configuration saved successfully!")
        except Exception as e:
            st.error(f"Error saving configuration: {e}")


configuration_page()
