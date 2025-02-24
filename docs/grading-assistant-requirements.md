# Grading Assistant Requirements

## Overview

The grading assistant helps a teacher in France grade papers from
students in a French prépa studying English as a foreign language with
the help of AI from OpenAI.

The papers come in batches. A batch means all the papers for the
students in the same class taking the same mock exam or assignment
around the same date. The batches might be handled in separate runs of
the application as emails arrive from students for that batch.

The grading assistant reads student papers and mock exams from a Google
Drive directory that is populated automatically with attachments from
emails sent to the teacher's special email addres.

The application moves files from the attachment directory a new
directory for the batch of exams currently being handled while
converting from the original docx or odt format to Markdown format.

It then splits them into appropriate parts that are then stored as new
files in the directory for the batch with a unique name that references
the original name with the type of section.

Then the assistant grades each part using an OpenAI Assistant. The grade
is a detailed analysis of the student's work including detailed
corrections, assessments, and suggestions for improvement as well as a
final grade. This detailed assessment is stored in a file next to the
student's work on the Google Drive. The teacher will then email this
assessment back to the student manually.

For each paper graded, each section is assigned a grade out of 20
points. For a multi-sectioned paper, the grades are then averaged with
separate weights to form a total aggregate grade for that paper.

As a part of the grading, the mistakes in the paper are categorized and
a table and chart of the different types of mistakes are produced to
help the student focus on their weak areas in preparation for the final
exam. These are included in the assessment but should also be aggregated
for a whole batch.

The grades, once assigned, are then stored in an Excel file with one
line per student and one column per section graded and a final column
showing the aggregate grade computed from the others with the
appropriate weights. The Excel file keeps getting updated with each
unique paper in a given batch.

The aggregate number of errors per type per paper is also stored in a
worksheet in the Excel file and updated for each unique paper graded.

## The application

The application is a multi-page Streamlit application written in Python.

It will be deployed on the Streamlit community cloud, so storage must be
handled via the Google Drive API attached to the account
<ghanimaghanemprof@gmail.com>. The directory structure under the root
directory of this account is:

-   app -- All the files associated with the app configuration and
    maintenance, notably the configuration.json file and any other
    configuration files.

-   Attachments -- Where all the attachments from emails to students are
    automatically placed by a Zapier app.

-   Output -- The output root directory -- Where all the output files
    go, in different subdirectories, one subdirectory for each batch.

The app has two pages to start with:

-   One page for the Configuration (denoted with the gear wheel icon).

-   One page for each new paper or exam. To start with there is just one
    kind of exam, called "Mock Exam". A Mock Exam has three sections, a
    Synthèse, an Essai, and a Traduction. These sections are clearly
    marked in the student's paper and are used to split the mock exam
    paper into three sections.

On the configuration page we have the following parameters, initialized
from a configuration.json JSON file in the "app" subdirectory of the
Google Drive root.

-   OpenAI API Key: The OpenAI API key

-   Attachments Directory: The Google Drive directory for the source
    attachments.

-   Root Output Directory: Root Google Drive directory for the graded
    papers and aggregate results.

-   Mock Exam Section: A section with an area for each section of a Mock
    Exam. The sections are: "Synthèse", "Essai," and "Traduction". Each
    section has the following fields:

    -   Name: The name of the section (non-modifiable)

    -   Weight: The weight of the grade of the section as a % of the
        total grade. The default weights are Synthèse -- 30%; Essai --
        50%; Traduction -- 20%.

    -   Assistant ID: The OpenAI Assistant ID for the section.

-   Error Types: A section with the list of error types to use for
    computing the error type distribution. This should be a list of
    sections with the following elements for each section:

    -   Error type name: The name of the error type

    -   Error type description: The description of the error type

    -   There should also be a way to add and delete error types.

-   Save configuration button: Save the configuration in a JSON file to
    be chosen (default is configuration.json in the current directory).

-   Load configuration button: Load a configuration from a chosen JSON
    file.

On the Mock Exam page, we have the following elements:

-   Batch name: Text field for the name of the batch to work on. The
    default should be the previous value when the application was run,
    or "Mock Exam \<today's date\>" if there was no previous value.

-   Output directory: A field to select or create a directory to store
    the output. By default this should be a directory under the root
    directory in the configuration with the batch name.

-   Files to grade: A field to select either a single file or an entire
    directory as the source of the files to process. By default, this is
    the attachments directory in the configuration.

-   Overwrite: A checkbox to indicate if the grader should overwrite
    existing files with the same name or create new versions of them.

-   Grading Progress: An area for the status of the grading as it
    proceeds -- this is updated by the program as it goes through each
    step in the process.

-   Grades: An area to show the final table of grades for the batch with
    one row per student and one column for the student's name and the
    Synthèse, Essai, and Traduction, as well as a final column for the
    weighted average for the student. The weighted average is calculated
    using the weights in the configuration which are percentages of the
    total.

-   Errors: An area to show the final table of error distributions
    across the error types, and a pie chart summarizing the
    distribution.

-   A "Start Grading" button.

When the "Start Grading" button is pressed, the following process
happens:

For each file in the selected directory, or the single file selected, do
the following steps, and update the progress area with an appropriate
message as each step progresses:

1.  The full name of the file is \<base\>.\<type\>. \<type\> is either
    "docx" or "odt"; any other file types should be noted in the
    progress area and ignored.

2.  Move (do not copy) the file from its current directory to the output
    directory. If the file already exists, and the overwrite option is
    unchecked, make a new file by appending a number to the name
    (incrementing the number if necessary to the \<base\> name). If the
    overwrite option is checked, simply replace any existing files with
    the same name.

3.  Using the appropriate Python library, transform the file from docx
    or odt format to markdown. Store the file in a file named
    \<base\>(-\<version\>).md.

4.  Using OpenAI parse API and structured output, transform the markdown
    file into the following structure:

    a.  name: The name of the student

    b.  date: The date of the paper, if found

    c.  synthese: The Synthèse section of the paper as markdown text

    d.  essai: The Essai section of the paper as markdown text

    e.  traduction: The Traduction section of the paper as markdown
        text.

5.  Save the synthese, essai, and traduction sections as new files with
    the names \<base\>(-\<version\>)-synthese.md,
    \<base\>(-\<version\>)-essai.md, and
    \<base\>(-\<version\>)-traduction.md. These are the section files.

6.  For each of the section files, call the appropriate OpenAI assistant
    using the Assistant API to generate the graded assessment. Store the
    graded assessment in a new file called
    \<base\>(-\<version\>)-\<section\>-assessment.md, in a subdirectory
    of the output directory called "assessments" (create it if it does
    not already exist). The assistant also returns a grade for the
    section which needs to be stored in a row in the grading Excel file
    which is in a file in the assessments directory called \<batch
    name\>-assessments.xlsx in the worksheet called "notes". The
    assistant also returns a list of error types and number of errors
    per type, which must be stored in the Excel file in the worksheet
    "erreurs", one row per paper with one column per error type.

7.  At the end, show a row in the Grades section for each paper graded
    with the name of the student, the grade for each section in the
    appropriate column and a total weighted aggregate grade at the end.
    There should also be a column with a link to all three of the
    assessment files generated for that paper and a link to the original
    student paper and the markdown version of it.

8.  At the end, show a row in the Errors section for each paper with a
    column for each error type showing the number and percentage of
    errors for that error type. Show an aggregate pie chart for all the
    errors for the batch.
