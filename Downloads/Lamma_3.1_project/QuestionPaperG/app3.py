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

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.DEBUG)

SYSTEM_PROMPT = (
    "You are an AI assistant that generates questions from a given text. "
    "For each unit in the provided syllabus, generate exactly 2 four-mark questions and 2 six-mark questions. "
    "Each question must be a separate entry and should include the number of marks in parentheses at the end of the question. "
    "Ensure that all units have exactly 4 questions in total (2 four-mark questions and 2 six-mark questions) without exceptions. "
    "Make sure the questions are relevant, engaging, and cover the key topics in the text. "
    "Output format should be as follows:\n\n"
    "1. Question text (4 marks)\n\n"
    "2. Question text (6 marks)\n\n"
    "Ensure consistent and accurate formatting, and that each unit receives exactly 4 questions."
)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DATABASE = 'data/questions.db'

# Initialize the database
def init_db():
    os.makedirs('data', exist_ok=True)
    logging.debug("Data directory created or already exists.")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('DROP TABLE IF EXISTS questions')
    
    cursor.execute('''
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit TEXT NOT NULL,
            question TEXT NOT NULL,
            marks INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Clear all questions from the database
def clear_questions():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM questions')
    conn.commit()
    conn.close()

# Store questions into the database
def store_questions(unit_questions):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    for unit, questions in unit_questions.items():
        for question, marks in questions:
            cursor.execute('INSERT INTO questions (unit, question, marks) VALUES (?, ?, ?)', (unit, question, marks))
    
    conn.commit()
    conn.close()

# Retrieve all questions by unit
def get_all_questions_by_unit():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT unit, question, marks FROM questions')
    questions = cursor.fetchall()
    conn.close()

    # Organize questions by unit
    unit_questions = {}
    for unit, question, marks in questions:
        if unit not in unit_questions:
            unit_questions[unit] = []
        unit_questions[unit].append((question, marks))
    
    return unit_questions

# Home route
@app.route('/')
def index():
    return render_template('index.html')

# View all questions
@app.route('/view-questions', methods=['GET'])
def view_questions():
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT id, unit, question, marks FROM questions')
        rows = cursor.fetchall()
        conn.close()

        questions = [
            {"id": row[0], "unit": row[1], "question": row[2], "marks": row[3]}
            for row in rows
        ]

        # Render as an HTML template
        return render_template('view_questions.html', questions=questions)
    except Exception as e:
        logging.error(f"An error occurred while fetching questions: {str(e)}")
        return jsonify({'error': 'Failed to fetch questions.'}), 500

# Generate questions from uploaded syllabus
@app.route('/generate-questions', methods=['POST'])
def generate_questions():
    try:
        logging.debug("Received request to generate questions.")
        
        base_prompt = request.form['base_prompt']
        syllabus_file = request.files['syllabus']
        filename = secure_filename(syllabus_file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        syllabus_file.save(filepath)

        syllabus_text = extract_text_from_pdf(filepath)
        units = extract_units_from_text(syllabus_text)

        prompt = f"{SYSTEM_PROMPT}\n\nBase prompt: {base_prompt}\n\nText: {syllabus_text}"

        response = requests.post(
            'http://localhost:11434/api/generate',
            json={"model": "llama3.1", "prompt": prompt},
            stream=True
        )

        generated_questions = []
        current_question = []

        for line in response.iter_lines():
            if line:
                try:
                    json_line = json.loads(line)
                    if json_line.get('done'):
                        break
                    if 'response' not in json_line:
                        raise ValueError(f"Invalid response format: {json_line}")
                    current_question.append(json_line['response'])
                except json.JSONDecodeError:
                    logging.error(f"Error decoding JSON from line: {line}")
                    return jsonify({'error': 'Invalid response from API.'}), 500

        if current_question:
            full_questions = ''.join(current_question).strip()
            questions_list = full_questions.split('\n\n')

            unit_questions = {unit[0]: [] for unit in units}
            for question in questions_list:
                question_text = question.strip()
                marks = 6 if '6 marks' in question_text else 4
                unit_name = determine_question_unit(units, len(generated_questions))
                unit_questions[unit_name].append((question_text, marks))

        clear_questions()
        store_questions(unit_questions)

        return jsonify({"questions": [q for unit in unit_questions for q, _ in unit_questions[unit]]}), 200  
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        return jsonify({'error': 'An error occurred while processing the request.'}), 500

# Helper functions
def extract_units_from_text(syllabus_text):
    units = []
    lines = syllabus_text.splitlines()
    for index, line in enumerate(lines):
        line = line.strip()
        if line.lower().startswith("unit"):
            units.append((line, index))
    return units

def determine_question_unit(units, question_position):
    for i in range(len(units)):
        current_unit_position = units[i][1]
        next_unit_position = units[i + 1][1] if i < len(units) - 1 else float('inf')
        if current_unit_position <= question_position < next_unit_position:
            return units[i][0]
    return units[-1][0]

def extract_text_from_pdf(filepath):
    text = ''
    with open(filepath, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + '\n'
    return text

def generate_pdf(questions, filepath):
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = [Paragraph(question, styles['BodyText']) for question in questions]
    doc.build(elements)

if __name__ == '__main__':
    init_db()  # Initialize the database when the app starts
    app.run(debug=True)
