import streamlit as st
from openai import OpenAI
from streamlit.navigation.page import StreamlitPage
from gdrive import init_google_drive
from gaclasses import Configuration

# https://drive.google.com/file/d/1wQbb8zBi-LiDH6D_WcrOEsuqk_U9V_Kq/view?usp=drive_link
# https://drive.google.com/drive/folders/104roznIvXeeWKTVyTana-3_htKBTPMyl?usp=drive_link
# Attachments:  https://drive.google.com/drive/folders/1WcoD2aBEdRqLTmj7A5BgUTYifD7Y3Ysy?usp=sharing


def init_config() -> None:
    if "config" in st.session_state:
        return
    st.session_state.config = Configuration.load_from_drive(None)
    st.session_state.mock_exams = {}
    st.session_state.selected_exam = None


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
