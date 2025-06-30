from flask import Flask, request, jsonify, render_template, send_from_directory
import os
import PyPDF2
import logging
from werkzeug.utils import secure_filename
from flask_cors import CORS
import sqlite3
import re
import json
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

app = Flask(__name__)
CORS(app)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Helper: Extract text from PDF
def extract_text_from_pdf(filepath):
    text = ''
    with open(filepath, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text() + '\n'
    return text

# Route: Upload Template
@app.route('/upload-template', methods=['POST'])
def upload_template():
    template_file = request.files.get('template', None)
    if not template_file:
        return jsonify({'error': 'No template file uploaded.'}), 400

    filename = secure_filename(template_file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    template_file.save(filepath)

    template_text = extract_text_from_pdf(filepath)
    logging.info(f"Template extracted: {template_text[:200]}...")

    return jsonify({'message': 'Template uploaded and processed successfully.'}), 200

# Route: Upload Syllabus and Notes
@app.route('/upload-syllabus-notes', methods=['POST'])
def upload_syllabus_notes():
    syllabus_file = request.files.get('syllabus', None)
    notes_file = request.files.get('notes', None)

    if not syllabus_file or not notes_file:
        return jsonify({'error': 'Both syllabus and notes files must be uploaded.'}), 400

    syllabus_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(syllabus_file.filename))
    notes_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(notes_file.filename))

    syllabus_file.save(syllabus_path)
    notes_file.save(notes_path)

    syllabus_text = extract_text_from_pdf(syllabus_path)
    notes_text = extract_text_from_pdf(notes_path)

    logging.info(f"Syllabus: {syllabus_text[:200]}...")
    logging.info(f"Notes: {notes_text[:200]}...")

    return jsonify({'message': 'Syllabus and notes uploaded and processed successfully.'}), 200

# Route: Generate Question Paper
@app.route('/generate-question-paper', methods=['POST'])
def generate_question_paper():
    try:
        # Simulate combining template, syllabus, and notes to generate question papers
        template = request.json.get('template', '')
        syllabus = request.json.get('syllabus', '')
        notes = request.json.get('notes', '')

        if not template or not syllabus or not notes:
            return jsonify({'error': 'Template, syllabus, and notes are required to generate question papers.'}), 400

        # Process and combine the inputs (placeholder logic for demo purposes)
        generated_questions = f"Template: {template[:100]}\nSyllabus: {syllabus[:100]}\nNotes: {notes[:100]}"

        logging.info("Generated questions successfully.")
        return jsonify({'message': 'Question paper generated successfully.', 'questions': generated_questions}), 200
    except Exception as e:
        logging.exception("An error occurred while generating the question paper.")
        return jsonify({'error': 'Failed to generate question paper.'}), 500

# Route: Homepage
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
