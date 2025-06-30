from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import logging
import os
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

# System Prompt
SYSTEM_PROMPT = (
    "As an AI assistant, your task is to generate exam questions from the provided text. "
    "For each unit listed in the 'Units' section below, you must generate a specified number of questions "
    "and marks based on user customization. Adhere strictly to the format and guidelines."
)

# Logging Configuration
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# Utility Functions
def extract_text_from_pdf(filepath):
    """Extract text from a PDF file."""
    try:
        from PyPDF2 import PdfReader
        text = ''
        with open(filepath, 'rb') as file:
            reader = PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + '\n'
        return text
    except Exception as e:
        logging.exception("Failed to extract text from PDF.")
        raise

def extract_units_from_text(syllabus_text):
    """Extract units from the syllabus text."""
    units = {}
    for line in syllabus_text.splitlines():
        if re.match(r'^Unit\s+\d+.*', line, re.IGNORECASE):
            unit_number = line.split(':')[0].strip()
            units[unit_number] = line.strip()
    return units

def generate_pdf(unit_questions, filepath):
    """Generate a question paper PDF with the given questions."""
    try:
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        # Add title
        title = Paragraph("Customizable Question Paper", styles['Heading1'])
        elements.append(title)
        elements.append(Spacer(1, 12))

        # Table data
        table_data = [["Unit", "Question No.", "Marks", "Question Text"]]

        for unit, questions in unit_questions.items():
            for question in questions:
                table_data.append([unit, question['number'], question['marks'], question['text']])

        table = Table(table_data, colWidths=[100, 100, 50, 300])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(table)
        doc.build(elements)
    except Exception as e:
        logging.exception("Failed to generate PDF.")
        raise

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate-questions', methods=['POST'])
def generate_questions():
    """Generate questions based on syllabus and user customization."""
    try:
        # Get the syllabus file
        syllabus_file = request.files.get('syllabus')
        if not syllabus_file:
            return jsonify({'error': 'No syllabus file uploaded.'}), 400

        # Save the syllabus file
        filename = secure_filename(syllabus_file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        syllabus_file.save(filepath)

        # Extract text and units
        syllabus_text = extract_text_from_pdf(filepath)
        units = extract_units_from_text(syllabus_text)
        if not units:
            return jsonify({'error': 'No units found in the syllabus text.'}), 400

        # User customization
        total_marks = int(request.form.get('total_marks', 100))
        selected_units = request.form.getlist('units')  # List of selected units
        unit_marks_distribution = json.loads(request.form.get('unit_marks_distribution', '{}'))

        # Validate units
        available_units = list(units.keys())
        invalid_units = [u for u in selected_units if u not in available_units]
        if invalid_units:
            return jsonify({'error': f"Invalid units selected: {invalid_units}"}), 400

        # Generate questions for each unit
        unit_questions = {}
        for unit in selected_units:
            unit_total_marks = unit_marks_distribution.get(unit, {}).get('total_marks', 0)
            subquestion_distribution = unit_marks_distribution.get(unit, {}).get('subquestions', {})
            
            unit_questions[unit] = []
            questions = get_all_questions_by_unit().get(unit, {'4': [], '6': []})
            
            # Shuffle questions
            random.shuffle(questions['4'])
            random.shuffle(questions['6'])

            for marks, count in subquestion_distribution.items():
                marks = str(marks)
                if marks in questions and len(questions[marks]) >= count:
                    unit_questions[unit].extend(questions[marks][:count])
                else:
                    return jsonify({'error': f"Not enough {marks}-mark questions in Unit {unit}"}), 400

        # Generate the PDF
        pdf_filename = 'custom_question_paper.pdf'
        pdf_filepath = os.path.join(UPLOAD_FOLDER, pdf_filename)
        generate_pdf(unit_questions, pdf_filepath)

        return jsonify({
            'message': 'Question paper generated successfully.',
            'download_url': f'/download/{pdf_filename}'
        })
    except Exception as e:
        logging.exception("Error occurred in generating questions.")
        return jsonify({'error': 'An error occurred while processing the request.'}), 500

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """Allow the user to download the generated question paper."""
    try:
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    except Exception as e:
        logging.exception("Error occurred in file download.")
        return jsonify({'error': 'File not found.'}), 404

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
