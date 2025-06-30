from flask import Flask, jsonify, request, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from database import init_db, clear_questions, get_all_questions_by_unit, store_questions
import logging
import os
import random
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import PyPDF2
import requests

app = Flask(__name__)
CORS(app)

# Logging Configuration
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

OLLAMA_URL = "http://localhost:11434/api/generate"  # Ollama API endpoint

# Utility Function: Extract Text from PDF
def extract_text_from_pdf(filepath):
    """
    Extract text from a PDF file.
    """
    try:
        text = ""
        with open(filepath, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        logging.exception("Failed to extract text from PDF.")
        raise


# Utility Function: Generate PDF
def generate_pdf(unit_questions, filepath):
    try:
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        # Add title
        title = Paragraph("Custom Question Paper", styles["Heading1"])
        elements.append(title)
        elements.append(Spacer(1, 12))

        # Add table for questions
        table_data = [["Unit", "Marks", "Question"]]
        for unit, questions in unit_questions.items():
            for question in questions:
                table_data.append([unit, question["marks"], question["text"]])

        table = Table(table_data, colWidths=[100, 50, 300])
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


@app.route('/')
def index():
    return render_template('index2.html')


@app.route("/generate-questions", methods=["POST"])
def generate_questions():
    """
    Generate questions based on the syllabus PDF and store them in the database.
    """
    try:
        syllabus_file = request.files.get("syllabus")
        if not syllabus_file:
            return jsonify({"error": "No syllabus file uploaded."}), 400

        # Save the uploaded syllabus PDF
        filename = secure_filename(syllabus_file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        syllabus_file.save(filepath)

        # Extract text from the syllabus PDF
        syllabus_text = extract_text_from_pdf(filepath)

        # Send the syllabus text to Ollama to generate questions
        response = requests.post(
            OLLAMA_URL,
            json={"model": "llama3.2-vision", "prompt": f"Generate questions from the syllabus:\n\n{syllabus_text}"},
            stream=True
        )

        if response.status_code != 200:
            return jsonify({"error": "Failed to generate questions using Ollama."}), 500

        # Collect questions from Ollama's response
        generated_questions = {}
        for line in response.iter_lines():
            if line:
                json_line = line.decode('utf-8')
                question_data = eval(json_line)
                unit = question_data.get("unit")
                question_text = question_data.get("text")
                marks = question_data.get("marks")

                if unit not in generated_questions:
                    generated_questions[unit] = {"4": [], "6": []}

                generated_questions[unit][str(marks)].append({"text": question_text, "marks": marks})

        # Store questions in the database
        clear_questions()
        store_questions(generated_questions)

        return jsonify({"message": "Questions generated and stored successfully."}), 200
    except Exception as e:
        logging.exception("Error in generating and storing questions.")
        return jsonify({"error": "An error occurred while processing the request."}), 500


@app.route("/generate-qp", methods=["POST"])
def generate_question_paper():
    """
    Generate a question paper based on stored questions and user customization.
    """
    try:
        data = request.json

        # Input Validation
        total_marks = data.get("total_marks")
        unit_details = data.get("unit_details", [])

        if not total_marks or not unit_details:
            return jsonify({"error": "Total marks and unit details are required."}), 400

        # Validate that marks match the total
        calculated_marks = sum(
            sum(q_count * int(q_marks) for q_marks, q_count in unit["questions"].items())
            for unit in unit_details
        )
        if calculated_marks != total_marks:
            return jsonify({"error": f"Total marks mismatch. Expected {total_marks}, got {calculated_marks}"}), 400

        # Fetch questions from the database
        all_questions = get_all_questions_by_unit()
        unit_questions = {}

        for unit in unit_details:
            unit_name = unit["unit"]
            questions = []
            for q_marks, q_count in unit["questions"].items():
                q_marks_str = str(q_marks)
                if q_marks_str in all_questions[unit_name] and len(all_questions[unit_name][q_marks_str]) >= q_count:
                    selected_questions = all_questions[unit_name][q_marks_str][:q_count]
                    questions.extend(selected_questions)
                else:
                    return jsonify({
                        "error": f"Not enough questions for {q_marks}-mark in Unit {unit_name}. Requested {q_count}."
                    }), 400

            unit_questions[unit_name] = questions

        # Generate PDF
        pdf_filename = "custom_question_paper.pdf"
        pdf_filepath = os.path.join(UPLOAD_FOLDER, pdf_filename)
        generate_pdf(unit_questions, pdf_filepath)

        return jsonify({
            "message": "Question paper generated successfully.",
            "download_url": f"/download/{pdf_filename}"
        })
    except Exception as e:
        logging.exception("Error in question paper generation.")
        return jsonify({"error": "An error occurred while processing the request."}), 500


@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """
    Allow the user to download the generated question paper.
    """
    try:
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    except Exception as e:
        logging.exception("Error occurred in file download.")
        return jsonify({'error': 'File not found.'}), 404


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
