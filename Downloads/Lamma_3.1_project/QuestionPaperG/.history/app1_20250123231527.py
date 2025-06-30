from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from database import init_db, clear_questions, get_all_questions_by_unit, store_questions
import logging
import os
import random
import json
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

app = Flask(__name__)
CORS(app)

# Logging Configuration
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


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

@app.route("/generate-qp", methods=["POST"])
def generate_question_paper():
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

        # Generate questions
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
    try:
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    except Exception as e:
        logging.exception("Error occurred in file download.")
        return jsonify({'error': 'File not found.'}), 404


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
