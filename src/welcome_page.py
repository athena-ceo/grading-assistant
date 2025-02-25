import streamlit as st

st.write(
    "The grading assistant uses the power of Artificial Intelligence to help you grade student submissions!"
)
st.write(
    "The app will let you select docx or odt files from the Google Drive Attachments directory where the zap automatically saves the student submissions from emails sent to ghanimaghanemprof@gmail.com."
)
st.write(
    "You can configure the grading assistant by clicking on the 'Configuration' tab on the left."
)
st.write(
    "Then you can grade a set of chosen submissions by clicking on the 'Grading' tab on the left."
)

st.write("The grading process follows the following steps:")
st.write("1. Convert the docx or odt files to Markdown.")
st.write("2. Extract the Synthèse, Essai, and Traduction sections.")
st.write("3. Call the OpenAI Assistants to grade each section.")
st.write("4. Calculate the final score based on the grades of the three sections.")
st.write("5. Save the grades in an Excel spreadsheet.")
