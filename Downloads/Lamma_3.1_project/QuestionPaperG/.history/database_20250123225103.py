import os
import sqlite3
import logging

DATABASE = 'data/questions.db'

# Initialize Logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def init_db():
    os.makedirs('data', exist_ok=True)
    logging.debug("Ensured that the data directory exists.")
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit TEXT NOT NULL,
        question TEXT NOT NULL,
        marks INTEGER NOT NULL
    )''')
    conn.commit()
    conn.close()
    logging.info("Database initialized successfully.")

def clear_questions():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM questions')
    conn.commit()
    conn.close()
    logging.info("Cleared all existing questions from the database.")

def store_questions(unit_questions):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    for unit, marks_dict in unit_questions.items():
        for mark, questions in marks_dict.items():
            for question_data in questions:
                question_text = question_data['text']
                cursor.execute(
                    'INSERT INTO questions (unit, question, marks) VALUES (?, ?, ?)',
                    (unit, question_text, int(mark))
                )
                logging.debug(f"Stored question for {unit}: {question_text} ({mark} marks)")
    conn.commit()
    conn.close()
    logging.info("All questions have been stored in the database.")

def get_all_questions_by_unit():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT unit, question, marks FROM questions')
    questions = cursor.fetchall()
    conn.close()

    unit_questions = {}
    for unit, question, marks in questions:
        if unit not in unit_questions:
            unit_questions[unit] = {'4': [], '6': []}
        question_data = {'text': question, 'marks': marks}
        unit_questions[unit][str(marks)].append(question_data)
    logging.debug(f"Retrieved questions grouped by unit: {unit_questions}")
    return unit_questions
