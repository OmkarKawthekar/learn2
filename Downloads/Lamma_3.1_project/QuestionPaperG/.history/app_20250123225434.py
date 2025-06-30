from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import logging
import os
import requests
import json
import random
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from database import init_db, clear_questions, store_questions, get_all_questions_by_unit

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# System prompt for AI model
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

# Function: Extract Text from PDF
def extract_text_from_pdf(filepath):
    try:
        text = ''
        with open(filepath, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + '\n'
        return text
    except Exception as e:
        logging.exception("Failed to extract text from PDF.")
        raise

# Function: Extract Units from Text
def extract_units_from_text(syllabus_text):
    units = {}
    for line in syllabus_text.splitlines():
        if re.match(r'^Unit\s+\d+.*', line, re.IGNORECASE):
            unit_number = line.split(':')[0].strip()
            units[unit_number] = line.strip()
    return units

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-questions', methods=['POST'])
def generate_questions():
    try:
        syllabus_file = request.files.get('syllabus', None)
        if not syllabus_file:
            return jsonify({'error': 'No syllabus file uploaded.'}), 400

        filename = secure_filename(syllabus_file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        syllabus_file.save(filepath)

        syllabus_text = extract_text_from_pdf(filepath)
        units = extract_units_from_text(syllabus_text)

        if not units:
            return jsonify({'error': 'No units found in the syllabus text.'}), 400

        units_text = '\n'.join(units.keys())
        prompt = f"{SYSTEM_PROMPT}\n\nUnits:\n{units_text}\n\nText:\n{syllabus_text}"

        response = requests.post(
            'http://localhost:11434/api/generate',
            json={"model": "llama3.2-vision", "prompt": prompt},
            stream=True
        )

        if response.status_code != 200:
            return jsonify({'error': 'Failed to generate questions from AI API.'}), 500

        generated_text = ''
        for line in response.iter_lines():
            if line:
                json_line = json.loads(line)
                if 'response' in json_line:
                    generated_text += json_line['response']

        if not generated_text.strip():
            return jsonify({'error': 'No questions received from AI API.'}), 500

        # Parse and store questions (omitted for brevity but should use your existing logic)
        # clear_questions()
        # store_questions(parsed_questions)

        return jsonify({"message": "Questions generated successfully."}), 200
    except Exception as e:
        logging.exception("Error occurred in generating questions.")
        return jsonify({'error': 'An error occurred.'}), 500

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
