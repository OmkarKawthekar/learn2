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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
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
    "For each unit listed in the 'Units' section below, you must generate exactly 3 four-mark questions and exactly 3 six-mark questions. "
    "Do not generate more or fewer questions for any unit. "
    "Each question should be relevant to the corresponding unit and cover key concepts. "
    "Use the following strict format for each unit and question:\n\n"
    "Unit X:\n"
    "1. Question text (4 marks)\n"
    "2. Question text (4 marks)\n"
    "3. Question text (4 marks)\n"
    "4. Question text (6 marks)\n"
    "5. Question text (6 marks)\n"
    "6. Question text (6 marks)\n\n"
    "Important Guidelines:\n"
    "- Do not include any additional text other than what is specified in the format.\n"
    "- Do not add introductions, explanations, or any text before or after the units and questions.\n"
    "- Ensure that each question is numbered correctly and corresponds to the marks indicated.\n"
    "- The 'Units' section contains the unit numbers and titles. Use them as provided.\n"
    "- Do not omit any units or questions.\n"
    "- Adhere strictly to the format and guidelines without deviation.\n"
    "- If you cannot comply with these instructions, do not generate any output."
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

    # Create the 'questions' table if it doesn't exist
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
            for question in questions:
                cursor.execute(
                    'INSERT INTO questions (unit, question, marks) VALUES (?, ?, ?)',
                    (unit, question, int(mark))
                )
                logging.debug(f"Stored question for {unit}: {question} ({mark} marks)")

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
        if marks == 4:
            unit_questions[unit]['4'].append(question)
        elif marks == 6:
            unit_questions[unit]['6'].append(question)

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
            json={"model": "llama3.2", "prompt": prompt},
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

        logging.debug(f"Full generated text: {generated_text[:1000]}")  # Log first 1000 chars

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
    question_count = 0

    lines = generated_text.strip().splitlines()
    question_pattern = re.compile(r'^(\d+)\.\s*(.+?)\s*\((\d+)\s*marks\)$', re.IGNORECASE)

    for line in lines:
        line = line.strip()
        if not line:
            continue  # Skip empty lines

        # Detect unit titles in the AI-generated text (e.g., 'Unit 1:')
        if line.lower().startswith('unit') and ':' in line:
            unit_number = line.split(':')[0].strip()
            if unit_number in units:
                current_unit_number = unit_number
                logging.debug(f"Detected current unit: {current_unit_number}")
                question_count = 0
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
            marks = match.group(3).strip()
            if marks in ['4', '6']:
                unit_questions[current_unit_number][marks].append(question_text)
                logging.debug(f"Parsed question {question_number} for {current_unit_number}: {question_text} ({marks} marks)")
                question_count += 1
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

# Function: Generate PDF from Questions
def generate_pdf(questions, filepath):
    try:
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        styles = getSampleStyleSheet()

        elements = []
        for item in questions:
            elements.append(Paragraph(item, styles['BodyText']))
            elements.append(Spacer(1, 12))

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

        # Assign each question to a paper
        for paper_num in range(1, num_papers + 1):
            paper_questions = []
            logging.info(f"Generating paper {paper_num}.")

            for unit, marks in shuffled_unit_questions.items():
                q4_index = (paper_num - 1) % len(marks['4'])
                q6_index = (paper_num - 1) % len(marks['6'])
                q4 = marks['4'][q4_index]
                q6 = marks['6'][q6_index]
                # Avoid duplicating unit titles
                paper_questions.append(f"{unit}")
                paper_questions.append(f"1. {q4} (4 marks)")
                paper_questions.append(f"2. {q6} (6 marks)")
                logging.debug(f"Selected questions for {unit} in paper {paper_num}: {q4} (4 marks), {q6} (6 marks)")

            # Generate PDF
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
