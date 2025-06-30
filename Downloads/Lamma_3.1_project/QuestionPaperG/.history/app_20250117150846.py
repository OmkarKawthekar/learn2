from flask import Flask, request, jsonify, render_template, send_from_directory
import requests
from werkzeug.utils import secure_filename
import os
import PyPDF2
import logging
from flask_cors import CORS
import json
import sqlite3
import random
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import sys
import re  # Import regular expressions

app = Flask(__name__)
CORS(app)

# Configure Logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Constants and Configuration
SYSTEM_PROMPT = (
    "As an AI assistant, your task is to generate exam questions from the provided text. "
    "For each unit listed in the 'Units' section below, you must generate exactly 6 questions: "
    "3 four-mark questions and 3 six-mark questions. "
    "Do not generate more or fewer questions for any unit. "
    "Each question should be relevant to the corresponding unit and cover key concepts. "
    "Use the following strict format for each unit and question:\n\n"
    "Unit X:\n"
    "1. Question text [CO:X] [BT:Y] (4 marks).\n"
    "2. Question text [CO:X] [BT:Y] (4 marks).\n"
    "3. Question text [CO:X] [BT:Y] (4 marks).\n"
    "4. Question text [CO:X] [BT:Y] (6 marks).\n"
    "5. Question text [CO:X] [BT:Y] (6 marks).\n"
    "6. Question text [CO:X] [BT:Y] (6 marks).\n\n"
    "Important Guidelines:\n"
    "- **CO Number Must Match Unit Number:** For each question, the [CO:X] must be the same as the unit number. For example, questions in Unit 1 must have [CO:1].\n"
    "- **Single CO Number:** Only a single CO number is allowed. Do not include multiple CO numbers or ranges.\n"
    "- **Bloom's Taxonomy (BT):** The [BT:Y] should be a Bloom's Taxonomy level between 1 and 6, appropriate for the question.\n"
    "- **Exact Format:** Use square brackets '[ ]' and colons ':' exactly as shown in the format.\n"
    "- **No Additional Text:** Do not include any additional text, notes, or disclaimers other than what is specified in the format.\n"
    "- **No Introductions or Conclusions:** Do not add introductions, explanations, or any text before or after the units and questions.\n"
    "- **Correct Numbering and Marks:** Ensure that each question is numbered correctly and corresponds to the marks indicated.\n"
    "- **Use Provided Units:** The 'Units' section contains the unit numbers and titles. Use them as provided.\n"
    "- **Do Not Omit Anything:** Do not omit any units or questions.\n"
    "- **Strict Adherence:** Adhere strictly to the format and guidelines without deviation.\n"
    "- **Non-Compliance:** If you cannot comply with these instructions, do not generate any output."
)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DATABASE = 'data/questions.db'

# Database Initialization
def init_db():
    os.makedirs('data', exist_ok=True)
    logging.debug("Ensured that the data directory exists.")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    # Create the 'questions' table with 'unit', 'question', and 'marks' columns
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit TEXT NOT NULL,
            question TEXT NOT NULL,
            marks INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("Database initialized successfully.")

# Clear Existing Questions
def clear_questions():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM questions')
    conn.commit()
    conn.close()
    logging.info("Cleared all existing questions from the database.")

# Store Questions in Database
def store_questions(unit_questions):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    for unit, marks_dict in unit_questions.items():
        for mark, questions in marks_dict.items():
            for question_data in questions:
                question_text = question_data['text']
                # Store 'unit', 'question', and 'marks'
                cursor.execute(
                    'INSERT INTO questions (unit, question, marks) VALUES (?, ?, ?)',
                    (unit, question_text, int(mark))
                )
                logging.debug(f"Stored question for {unit}: {question_text} ({mark} marks)")

    conn.commit()
    conn.close()
    logging.info("All questions have been stored in the database.")

# Retrieve All Questions Grouped by Unit and Marks
def get_all_questions_by_unit():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT unit, question, marks FROM questions')
    questions = cursor.fetchall()
    conn.close()

    # Organize questions by unit and marks
    unit_questions = {}
    for unit, question, marks in questions:
        if unit not in unit_questions:
            unit_questions[unit] = {'4': [], '6': []}
        question_data = {'text': question, 'marks': marks}
        if marks == 4:
            unit_questions[unit]['4'].append(question_data)
        elif marks == 6:
            unit_questions[unit]['6'].append(question_data)

    logging.debug(f"Retrieved questions grouped by unit: {unit_questions}")
    return unit_questions

# Route: Homepage
@app.route('/')
def index():
    return render_template('index.html')

# Route: Generate Questions
@app.route('/generate-questions', methods=['POST'])
def generate_questions():
    try:
        logging.info("Received request to generate questions.")

        # Retrieve syllabus file
        syllabus_file = request.files.get('syllabus', None)
        if not syllabus_file:
            logging.error("No syllabus file uploaded.")
            return jsonify({'error': 'No syllabus file uploaded.'}), 400

        # Secure and save the uploaded file
        filename = secure_filename(syllabus_file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        syllabus_file.save(filepath)
        logging.info(f"Syllabus file saved to: {filepath}")

        # Extract text from PDF
        syllabus_text = extract_text_from_pdf(filepath)
        logging.debug(f"Extracted syllabus text (first 500 characters): {syllabus_text[:500]}")

        # Extract units from the syllabus text
        units = extract_units_from_text(syllabus_text)
        logging.info(f"Extracted units: {units}")

        if not units:
            logging.error("No units found in the syllabus text.")
            return jsonify({'error': 'No units found in the syllabus text.'}), 400

        # Prepare the units list for the prompt
        units_text = '\n'.join(units.keys())  # Only unit numbers (e.g., 'Unit 1', 'Unit 2', etc.)

        # Construct prompt for AI
        prompt = f"{SYSTEM_PROMPT}\n\nUnits:\n{units_text}\n\nText:\n{syllabus_text}"
        logging.debug("Constructed prompt for AI model.")

        # Send prompt to AI API
        response = requests.post(
            'http://localhost:11434/api/generate',
            json={"model": "llama3.2-vision", "prompt": prompt},
            stream=True
        )

        logging.info(f"AI API response status: {response.status_code}")

        if response.status_code != 200:
            logging.error(f"AI API returned non-200 status code: {response.status_code}")
            return jsonify({'error': 'Failed to generate questions from AI API.'}), 500

        # Collect AI response
        generated_text = ''
        for line in response.iter_lines():
            if line:
                try:
                    json_line = json.loads(line)
                    logging.debug(f"Received line from AI API: {json_line}")
                    if json_line.get('done'):
                        break
                    if 'response' not in json_line:
                        logging.error(f"Invalid response format: {json_line}")
                        raise ValueError(f"Invalid response format: {json_line}")
                    generated_text += json_line['response']
                except json.JSONDecodeError:
                    logging.error(f"Error decoding JSON from line: {line}")
                    return jsonify({'error': 'Invalid response from AI API.'}), 500

        if not generated_text.strip():
            logging.error("No questions received from AI API.")
            return jsonify({'error': 'No questions received from AI API.'}), 500

        # Remove any additional text after the last expected question
        end_pattern = re.compile(r'(Unit\s+\d+:.*?6\.\s*.*?\(6\s*marks\)\.)', re.DOTALL | re.IGNORECASE)
        match = end_pattern.findall(generated_text)
        if match:
            generated_text = '\n'.join(match)
        else:
            logging.warning("Could not find the end of the expected questions. The AI output may contain extra text.")

        logging.debug(f"Full generated text after trimming: {generated_text}")

        # Parse generated questions
        unit_questions = parse_generated_questions(generated_text, units)

        # Validate the number of questions per unit
        insufficient_units = []
        for unit, questions in unit_questions.items():
            num_four_mark = len(questions['4'])
            num_six_mark = len(questions['6'])
            total_questions = num_four_mark + num_six_mark
            if total_questions != 6 or num_four_mark != 3 or num_six_mark != 3:
                insufficient_units.append(unit)
                logging.error(f"Unit '{unit}' has {num_four_mark} four-mark questions and {num_six_mark} six-mark questions.")

        if insufficient_units:
            logging.error(f"Units {insufficient_units} do not have the required number of questions.")
            return jsonify({
                'error': f"Units {insufficient_units} do not have the required number of questions."
            }), 500

        logging.info("All questions have been successfully generated and assigned to units.")

        # Clear existing questions and store new ones
        clear_questions()
        store_questions(unit_questions)

        return jsonify({"message": "Questions generated and stored successfully.", "units": list(unit_questions.keys())}), 200
    except Exception as e:
        logging.exception("An error occurred while generating questions.")
        return jsonify({'error': 'An error occurred while processing the request.'}), 500

# Function: Parse Generated Questions
def parse_generated_questions(generated_text, units):
    unit_questions = {unit_num: {'4': [], '6': []} for unit_num in units.keys()}
    current_unit_number = None
    co_number_expected = None

    lines = generated_text.strip().splitlines()
    question_pattern = re.compile(
        r'^(\d+)\.\s*(.+?)\s*\[CO:(\d+)\]\s*\[BT:(\d+)\]\s*\((\d+)\s*marks\)\.?$',
        re.IGNORECASE
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue  # Skip empty lines

        # Detect unit titles in the AI-generated text (e.g., 'Unit 1:')
        if re.match(r'^Unit\s+\d+:$', line, re.IGNORECASE):
            unit_number = line.split(':')[0].strip()
            if unit_number in units:
                current_unit_number = unit_number
                co_number_expected = int(re.search(r'\d+', unit_number).group())
                logging.debug(f"Detected current unit: {current_unit_number}, expected CO number: {co_number_expected}")
            else:
                logging.warning(f"Unknown unit detected: {unit_number}")
            continue  # Skip unit titles

        if not current_unit_number:
            logging.warning(f"Question found before any unit title: {line}")
            continue  # Skip questions before any unit is detected

        # Extract question and marks using regex
        match = question_pattern.match(line)
        if match:
            question_number = int(match.group(1).strip())
            question_text = match.group(2).strip()
            co_number = int(match.group(3).strip())
            bt_number = int(match.group(4).strip())
            marks = match.group(5).strip()
            if marks in ['4', '6']:
                if co_number != co_number_expected:
                    logging.warning(f"CO number {co_number} does not match expected CO number {co_number_expected} for unit {current_unit_number}")
                    continue  # Skip questions with incorrect CO numbers
                if not (1 <= bt_number <= 6):
                    logging.warning(f"BT number {bt_number} is out of expected range (1-6)")
                    continue  # Skip questions with invalid BT numbers
                # Include CO and BT in the question text
                question_text_with_co_bt = f"{question_text} [CO:{co_number}] [BT:{bt_number}]"
                question_data = {'text': question_text_with_co_bt, 'marks': marks}
                unit_questions[current_unit_number][marks].append(question_data)
                logging.debug(f"Parsed question {question_number} for {current_unit_number}: {question_text_with_co_bt} ({marks} marks)")
            else:
                logging.warning(f"Unexpected marks value: {marks} in line: {line}")
        else:
            logging.warning(f"Line does not match expected question format: {line}")

    # Map unit numbers back to full unit titles
    mapped_unit_questions = {}
    for unit_number, questions in unit_questions.items():
        full_title = units[unit_number]
        mapped_unit_questions[full_title] = questions

    return mapped_unit_questions

# Function: Extract Units from Syllabus Text
def extract_units_from_text(syllabus_text):
    units = {}
    lines = syllabus_text.splitlines()
    for line in lines:
        line = line.strip()
        # Detect unit lines, assuming they start with 'Unit' followed by a number
        if re.match(r'^Unit\s+\d+.*', line, re.IGNORECASE):
            unit_line = line.split(':')[0]  # Get 'Unit X' part
            unit_number = unit_line.strip()
            units[unit_number] = line.strip()  # Store the full line as the unit title
    logging.debug(f"Units extracted from text: {units}")
    return units

# Function: Extract Text from PDF
def extract_text_from_pdf(filepath):
    try:
        text = ''
        with open(filepath, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page_num, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + '\n'
                    logging.debug(f"Extracted text from page {page_num}.")
                else:
                    logging.warning(f"No text found on page {page_num}.")
        return text
    except Exception as e:
        logging.exception(f"Failed to extract text from PDF: {filepath}")
        raise

# Function: Generate PDF from Questions in Table Format
def generate_pdf(unit_questions, filepath):
    try:
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        # Define a custom style for main titles
        main_title_style = ParagraphStyle(
            name='MainTitle',
            parent=styles['Heading1'],
            alignment=1,  # Center alignment
            spaceAfter=12
        )

        # Define a custom style for table headers
        header_style = ParagraphStyle(
            name='TableHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            alignment=1,  # Center alignment
            textColor=colors.whitesmoke
        )

        # Add Main Titles at the Top
        exam_title = Paragraph("Exam Question Paper", main_title_style)
        course_title = Paragraph("Course: Data Communications", styles['Heading2'])
        instructor = Paragraph("Instructor: Dr. Jane Doe", styles['Normal'])
        date = Paragraph("Date: 23-Nov-2024", styles['Normal'])

        elements.extend([exam_title, course_title, instructor, date, Spacer(1, 24)])

        # Define table data with headers
        table_data = [
            [
                Paragraph('Question No', header_style),
                Paragraph('Subquestion', header_style),
                Paragraph('Question Text', header_style),
                Paragraph('CO', header_style),
                Paragraph('BT', header_style),
                Paragraph('Marks', header_style)
            ]
        ]

        # Initialize question number
        question_num = 1

        for unit, questions in unit_questions.items():
            # For each unit, select 2 questions (1 four-mark and 1 six-mark)
            selected_questions_4 = questions['4'][:1]  # 1 four-mark question
            selected_questions_6 = questions['6'][:1]  # 1 six-mark question

            # Combine selected questions
            selected_questions = selected_questions_4 + selected_questions_6

            for idx, question in enumerate(selected_questions):
                sub_label = chr(97 + idx)  # 'a', 'b'
                formatted_question_num = f"{question_num}{sub_label}"
                # Extract CO and BT from the question text
                co_match = re.search(r'\[CO:(\d+)\]', question['text'])
                bt_match = re.search(r'\[BT:(\d+)\]', question['text'])
                co = co_match.group(1) if co_match else 'N/A'
                bt = bt_match.group(1) if bt_match else 'N/A'

                # Remove [CO:X] and [BT:Y] from the question text for clarity in the table
                question_text_clean = re.sub(r'\[CO:\d+\]\s*\[BT:\d+\]', '', question['text']).strip()

                # Append the row to table data
                table_data.append([
                    Paragraph(formatted_question_num, styles['Normal']),  # Question No (e.g., '1a')
                    sub_label,                                          # Subquestion ('a', 'b')
                    Paragraph(question_text_clean, styles['Normal']),
                    str(co),
                    str(bt),
                    str(question['marks'])
                ])

            # Add a blank row after each unit for differentiation
            table_data.append(['', '', '', '', '', ''])

            question_num += 1  # Increment main question number for next unit

        # Define column widths
        col_widths = [80, 60, 300, 40, 40, 40]

        # Create the table
        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Add table style
        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),

            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),

            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),

            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

            ('GRID', (0,0), (-1,-1), 1, colors.black),
        ])
        table.setStyle(table_style)

        # Alternate row colors (starting from the first data row)
        for i in range(1, len(table_data)):
            # Skip blank rows
            if all(cell == '' for cell in table_data[i]):
                continue
            elif i % 7 == 0:
                # Every 7th row is a blank row; skip coloring
                continue
            elif i % 2 == 0:
                bg_color = colors.lightgrey
            else:
                bg_color = colors.whitesmoke
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, i), (-1, i), bg_color)
            ]))

        elements.append(table)
        elements.append(Spacer(1, 24))  # Space after the table

        # Build the PDF
        doc.build(elements)
        logging.debug(f"PDF generated at: {filepath}")
    except Exception as e:
        logging.exception(f"Failed to generate PDF: {filepath}")
        raise

# Route: Generate Question Papers
@app.route('/generate-papers', methods=['GET'])
def generate_papers():
    try:
        logging.info("Received request to generate question papers.")
        unit_questions = get_all_questions_by_unit()

        # Verify that each unit has at least 6 questions
        insufficient_units = []
        for unit, questions in unit_questions.items():
            total_questions = len(questions['4']) + len(questions['6'])
            if total_questions < 6:
                insufficient_units.append(unit)

        if insufficient_units:
            logging.error(f"Units {insufficient_units} do not have enough questions to generate papers.")
            return jsonify({'error': f"Units {insufficient_units} do not have enough questions to generate papers."}), 500

        papers = []
        num_papers = 3  # Number of question papers to generate

        # For each unit and marks, shuffle the questions
        shuffled_unit_questions = {}
        for unit, marks in unit_questions.items():
            shuffled_unit_questions[unit] = {
                '4': random.sample(marks['4'], len(marks['4'])),
                '6': random.sample(marks['6'], len(marks['6']))
            }
            logging.debug(f"Shuffled questions for {unit}: {shuffled_unit_questions[unit]}")

        # Assign questions to papers
        for paper_num in range(1, num_papers + 1):
            paper_questions = {}
            logging.info(f"Generating paper {paper_num}.")

            for unit, marks in shuffled_unit_questions.items():
                # Select 1 four-mark and 1 six-mark question per unit
                q4 = marks['4'][0]  # Select the first four-mark question
                q6 = marks['6'][0]  # Select the first six-mark question

                # Initialize unit in paper_questions if not already
                if unit not in paper_questions:
                    paper_questions[unit] = {'4': [], '6': []}

                # Append questions
                paper_questions[unit]['4'].append(q4)
                paper_questions[unit]['6'].append(q6)

                logging.debug(f"Selected questions for {unit} in paper {paper_num}: {q4['text']} (4 marks), {q6['text']} (6 marks)")

            # Generate PDF with table format
            pdf_filename = f'question_paper_{paper_num}.pdf'
            pdf_filepath = os.path.join(UPLOAD_FOLDER, pdf_filename)
            generate_pdf(paper_questions, pdf_filepath)
            logging.info(f"Generated PDF for paper {paper_num}: {pdf_filepath}")
            papers.append(pdf_filename)

        logging.info("All question papers have been generated successfully.")
        return jsonify({"message": "Question papers generated successfully.", "papers": papers}), 200
    except Exception as e:
        logging.exception("An error occurred while generating question papers.")
        return jsonify({'error': 'An error occurred while generating question papers.'}), 500

# Route: Download Generated PDFs
@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    try:
        logging.info(f"Download request received for file: {filename}")
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    except Exception as e:
        logging.exception(f"An error occurred while trying to download the file: {filename}")
        return jsonify({'error': 'File not found or an error occurred while downloading.'}), 404

# Initialize Database Before Running the App
if __name__ == '__main__':
    init_db()  # Initialize the database when the app starts
    app.run(debug=True)
