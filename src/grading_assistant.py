from typing import Any, Literal
from altair import Config
import streamlit as st
from openai import OpenAI
from streamlit.navigation.page import StreamlitPage
from gdrive import create_drive_service
from gaclasses import Configuration

# https://drive.google.com/file/d/1wQbb8zBi-LiDH6D_WcrOEsuqk_U9V_Kq/view?usp=drive_link
# https://drive.google.com/drive/folders/104roznIvXeeWKTVyTana-3_htKBTPMyl?usp=drive_link
# Attachments:  https://drive.google.com/drive/folders/1WcoD2aBEdRqLTmj7A5BgUTYifD7Y3Ysy?usp=sharing

CONFIG_FILE_NAME: str = "gaconfig.json"
CONFIG_DIRECTORY_ID: str = "104roznIvXeeWKTVyTana-3_htKBTPMyl"
OUTPUT_FOLDER_ID: str = "1WRPts82BjAhhnlO4cQl9hEv4Px3KR3LX"
ATTACHMENTS_FOLDER_ID: str = "1WcoD2aBEdRqLTmj7A5BgUTYifD7Y3Ysy"


def init_config() -> None:
    if "config" in st.session_state:
        return
    st.session_state.config = Configuration.load_from_drive(None)
    st.session_state.mock_exams = {}
    st.session_state.selected_exam = None


# Google Drive Setup
def init_google_drive() -> None:
    if "drive_service" in st.session_state:
        return
    service_account_file = "service_account.json"

    drive_service: Any = create_drive_service(service_account_file)
    st.session_state.drive_service = drive_service

    st.session_state.config_directory_id = CONFIG_DIRECTORY_ID
    st.session_state.config_file_name = CONFIG_FILE_NAME
    st.session_state.output_folder_id = OUTPUT_FOLDER_ID
    st.session_state.attachments_folder_id = ATTACHMENTS_FOLDER_ID


def init_openai() -> None:
    if "openai_client" in st.session_state:
        return
    api_key: str = st.secrets["OpenAI"]["OPENAI_API_KEY"]
    openai_org_id: str = st.secrets["OpenAI"]["OPENAI_ORGANIZATION_ID"]
    openai_project_id: str = st.secrets["OpenAI"]["OPENAI_PROJECT_ID"]
    client = OpenAI(
        organization=openai_org_id, project=openai_project_id, api_key=api_key
    )
    st.session_state.openai_client = client
    print("Known assistants:")
    for assistant in client.beta.assistants.list().data:
        print(f" Assistant: {assistant.id} - {assistant.name}")


def init() -> None:
    init_google_drive()
    init_openai()
    init_config()


st.set_page_config(page_title="Grading Assistant", page_icon="📚", layout="wide")

init()

welcome_page: StreamlitPage = st.Page(
    "welcome_page.py", title="Welcome", icon=":material/home:"
)

config_page: StreamlitPage = st.Page(
    "configuration_page.py", title="Configuration Settings", icon=":material/settings:"
)
grading_page: StreamlitPage = st.Page(
    "mock_exam_grading_page.py", title="Mock Exam Grading", icon="📝"
)

pg: StreamlitPage = st.navigation([welcome_page, grading_page, config_page])

st.header("Professor Ghanem's Grading Assistant", divider=True)

pg.run()
