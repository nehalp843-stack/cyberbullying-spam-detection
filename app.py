import joblib
import os
import re
import secrets
import sqlite3
import uuid
import numpy as np
from datetime import datetime
from flask import Flask, jsonify, render_template, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)


# Load trained ML artifacts
model = joblib.load('model.pkl')
vectorizer = joblib.load('vectorizer.pkl')

label_map = {
    0: "Normal",
    1: "Spam",
    2: "Cyberbullying"
}

DB_NAME = os.environ.get('DB_PATH', 'predictions.db')


def confidence_level(confidence_score):
    if confidence_score >= 80:
        return 'high'
    if confidence_score >= 50:
        return 'medium'
    return 'low'


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            category TEXT NOT NULL,
            confidence REAL NOT NULL,
            confidence_level TEXT NOT NULL,
            device_id TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    columns = {row[1] for row in cursor.execute('PRAGMA table_info(message_logs)')}
    if 'confidence_level' not in columns:
        cursor.execute('ALTER TABLE message_logs ADD COLUMN confidence_level TEXT')
        cursor.execute('''
            UPDATE message_logs
            SET confidence_level = CASE
                WHEN confidence >= 80 THEN 'high'
                WHEN confidence >= 50 THEN 'medium'
                ELSE 'low'
            END
        ''')
    if 'device_id' not in columns:
        cursor.execute('ALTER TABLE message_logs ADD COLUMN device_id TEXT')
        cursor.execute("UPDATE message_logs SET device_id = 'legacy' WHERE device_id IS NULL")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detection_summary (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            total_messages INTEGER NOT NULL DEFAULT 0,
            normal_count INTEGER NOT NULL DEFAULT 0,
            spam_count INTEGER NOT NULL DEFAULT 0,
            cyberbullying_count INTEGER NOT NULL DEFAULT 0,
            high_confidence_count INTEGER NOT NULL DEFAULT 0,
            medium_confidence_count INTEGER NOT NULL DEFAULT 0,
            low_confidence_count INTEGER NOT NULL DEFAULT 0,
            average_confidence REAL NOT NULL DEFAULT 0
        )
    ''')
    cursor.execute('INSERT OR IGNORE INTO detection_summary (id) VALUES (1)')

    cursor.execute('''
        UPDATE detection_summary
        SET total_messages = (SELECT COUNT(*) FROM message_logs),
            normal_count = (SELECT COUNT(*) FROM message_logs WHERE category = 'Normal'),
            spam_count = (SELECT COUNT(*) FROM message_logs WHERE category = 'Spam'),
            cyberbullying_count = (SELECT COUNT(*) FROM message_logs WHERE category = 'Cyberbullying'),
            high_confidence_count = (SELECT COUNT(*) FROM message_logs WHERE confidence_level = 'high'),
            medium_confidence_count = (SELECT COUNT(*) FROM message_logs WHERE confidence_level = 'medium'),
            low_confidence_count = (SELECT COUNT(*) FROM message_logs WHERE confidence_level = 'low'),
            average_confidence = COALESCE(
                (SELECT AVG(confidence) FROM message_logs), 0
            )
        WHERE id = 1
    ''')
    conn.commit()
    conn.close()


init_db()


def clean_text(text):
    text = text.lower()
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    return text

@app.route('/')
def home():
    if not session.get('device_id'):
        session['device_id'] = str(uuid.uuid4())
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
def predict():
    data = request.get_json()
    message = data.get('message', '') if data else ''

    if not message.strip():
        return jsonify({'error': 'Message cannot be empty'}), 400

    device_id = session.get('device_id')
    if not device_id:
        device_id = str(uuid.uuid4())
        session['device_id'] = device_id

    cleaned = clean_text(message)
    vectorized = vectorizer.transform([cleaned])

    # Get probability distribution
    probs = model.predict_proba(vectorized)[0]
    prediction = int(model.predict(vectorized)[0])

    category = label_map.get(prediction, "Unknown")
    confidence_score = round(float(np.max(probs)) * 100, 2)
    level = confidence_level(confidence_score)

    # Save the individual check and update aggregate statistics in one transaction.
    conn = sqlite3.connect(DB_NAME)
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO message_logs
                (message, category, confidence, confidence_level, device_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            message,
            category,
            confidence_score,
            level,
            device_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ))
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        'message': message,
        'category': category,
        'confidence': confidence_score,
        'confidence_level': level
    })


@app.route('/stats', methods=['GET'])
def get_stats():
    device_id = session.get('device_id')
    if not device_id:
        return jsonify({'error': 'Device session is required'}), 400

    conn = sqlite3.connect(DB_NAME)
    try:
        row = conn.execute('''
            SELECT COUNT(*),
                   SUM(CASE WHEN category = 'Normal' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN category = 'Spam' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN category = 'Cyberbullying' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN confidence_level = 'high' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN confidence_level = 'medium' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN confidence_level = 'low' THEN 1 ELSE 0 END),
                   AVG(confidence)
            FROM message_logs
            WHERE device_id = ?
        ''', (device_id,)).fetchone()
    finally:
        conn.close()

    total_messages, normal, spam, cyberbullying, high, medium, low, average = row
    return jsonify({
        'total': total_messages,
        'normal': normal or 0,
        'spam': spam or 0,
        'cyberbullying': cyberbullying or 0,
        'confidence_levels': {
            'high': high or 0,
            'medium': medium or 0,
            'low': low or 0,
        },
        'average_confidence': round(float(average or 0), 2)
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)