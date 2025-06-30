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
import re
import fitz  # PyMuPDF for better PDF processing

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
SYSTEM_PROMPT = """
As an AI assistant, your task is to generate exam questions from the provided materials.
Consider the following inputs:
1. Template: Previous year question paper format
2. Syllabus: Course syllabus with units and topics
3. Reference Materials: Course notes and books

Generate questions that:
- Match the style and difficulty level of the template
- Cover topics from the syllabus
- Use content from reference materials
- Follow the same format as the template

For each unit listed in the syllabus, generate exactly 6 questions:
3 four-mark questions and 3 six-mark questions.

Use the following strict format for each unit and question:
Unit X:
1. Question text [CO:X] [BT:Y] (4 marks).
2. Question text [CO:X] [BT:Y] (4 marks).
3. Question text [CO:X] [BT:Y] (4 marks).
4. Question text [CO:X] [BT:Y] (6 marks).
5. Question text [CO:X] [BT:Y] (6 marks).
6. Question text [CO:X] [BT:Y] (6 marks).

Important Guidelines:
[Previous guidelines remain the same...]
"""

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DATABASE = 'data/questions.db'

# New function to extract template structure
def analyze_template(filepath):
    try:
        template_info = {
            'structure': [],
            'formatting': {},
            'question_patterns': []
        }
        
        doc = fitz.open(filepath)
        for page in doc:
            text = page.get_text()
            
            # Analyze question patterns
            question_matches = re.finditer(r'\d+\.\s*(.*?)\s*\(\d+\s*marks\)', text)
            for match in question_matches:
                template_info['question_patterns'].append({
                    'format': match.group(0),
                    'style': 'standard'  # You can enhance this with more style detection
                })
            
            # Detect sections and structure
            sections = re.findall(r'(SECTION[- ][A-Z]|PART[- ][A-Z])', text)
            template_info['structure'].extend(sections)
            
            # Analyze formatting (you can expand this based on your needs)
            template_info['formatting'] = {
                'has_sections': bool(sections),
                'marks_pattern': r'\(\d+\s*marks\)',
                'question_numbering': 'numeric'  # You can enhance this detection
            }
        
        doc.close()
        return template_info
    except Exception as e:
        logging.exception("Error analyzing template")
        raise

# New function to process reference materials
def process_reference_materials(filepath):
    try:
        content = ''
        doc = fitz.open(filepath)
        for page in doc:
            content += page.get_text() + '\n'
        doc.close()
        return content
    except Exception as e:
        logging.exception("Error processing reference materials")
        raise

# Modified route for the homepage
@app.route('/')
def index():
    return render_template('index.html')

# New route to handle template upload
@app.route('/upload-template', methods=['POST'])
def upload_template():
    try:
        if 'template' not in request.files:
            return jsonify({'error': 'No template file uploaded'}), 400
        
        template_file = request.files['template']
        if template_file.filename == '':
            return jsonify({'error': 'No template file selected'}), 400
        
        filename = secure_filename(template_file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        template_file.save(filepath)
        
        # Analyze template structure
        template_info = analyze_template(filepath)
        
        return jsonify({
            'message': 'Template uploaded and analyzed successfully',
            'template_info': template_info
        }), 200
    except Exception as e:
        logging.exception("Error uploading template")
        return jsonify({'error': str(e)}), 500

# Modified generate questions route
@app.route('/generate-questions', methods=['POST'])
def generate_questions():
    try:
        logging.info("Received request to generate questions.")
        
        # Check for required files
        if 'template' not in request.files or 'syllabus' not in request.files or 'references' not in request.files:
            return jsonify({'error': 'Missing required files'}), 400
        
        # Process template
        template_file = request.files['template']
        template_filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(template_file.filename))
        template_file.save(template_filepath)
        template_info = analyze_template(template_filepath)
        
        # Process syllabus
        syllabus_file = request.files['syllabus']
        syllabus_filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(syllabus_file.filename))
        syllabus_file.save(syllabus_filepath)
        syllabus_text = extract_text_from_pdf(syllabus_filepath)
        
        # Process reference materials
        reference_files = request.files.getlist('references')
        reference_content = ''
        for ref_file in reference_files:
            ref_filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(ref_file.filename))
            ref_file.save(ref_filepath)
            reference_content += process_reference_materials(ref_filepath) + '\n'
        
        # Extract units from syllabus
        units = extract_units_from_text(syllabus_text)
        
        if not units:
            return jsonify({'error': 'No units found in the syllabus text.'}), 400
        
        # Prepare units list and combined content for AI prompt
        units_text = '\n'.join(units.keys())
        combined_content = f"""
Template Structure:
{json.dumps(template_info, indent=2)}

Syllabus:
{syllabus_text}

Reference Materials:
{reference_content}
"""
        
        # Construct prompt for AI
        prompt = f"{SYSTEM_PROMPT}\n\nUnits:\n{units_text}\n\nContent:\n{combined_content}"
        
        # Send prompt to AI API
        response = requests.post(
            'http://localhost:11434/api/generate',
            json={"model": "llama3.2-vision", "prompt": prompt},
            stream=True
        )
        
        # [Rest of the function remains the same as in your original code]
        # Including collecting AI response, parsing questions, storing in database, etc.
        
        return jsonify({"message": "Questions generated and stored successfully.", "units": list(units.keys())}), 200
        
    except Exception as e:
        logging.exception("An error occurred while generating questions.")
        return jsonify({'error': str(e)}), 500

# Modified generate papers function to use template
def generate_pdf(unit_questions, filepath, template_info):
    try:
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []
        
        # Apply template formatting
        if template_info['formatting'].get('has_sections'):
            # Generate sections based on template structure
            for section in template_info['structure']:
                section_title = Paragraph(section, styles['Heading1'])
                elements.append(section_title)
                elements.append(Spacer(1, 12))
                
                # Add questions for this section
                # [Add logic to distribute questions across sections]
        
        # [Rest of the PDF generation logic remains similar but adapted to template structure]
        
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

# [Rest of your original code remains the same]
# Including database functions, helper functions, and other routes

if __name__ == '__main__':
    init_db()
    app.run(debug=True)