from flask import Flask, jsonify
import logging
import random
import time
import threading
import requests
from datetime import datetime, timedelta
import uuid
import io

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

UPLOAD_URL = ""

logging.info("")

def process_single_request():
    try:
        keywords = ["python", "azure", "machine learning", "django", "flask"]
        num_keywords = random.randint(1, len(keywords))
        selected_keywords = random.sample(keywords, num_keywords)
        keywords_str = ", ".join(selected_keywords)

        candidate_id = str(uuid.uuid4())
        email = ""
        sample_pdf_content = f"%PDF-1.4\n%Sample resume content with skills: {keywords_str}.\n%%EOF".encode('utf-8')
        file_name = f"resume_{candidate_id[:8]}.pdf"

        file_size = len(sample_pdf_content)
        if file_size > 2 * 1024 * 1024:  
            logging.error(f"Generated file size ({file_size} bytes) exceeds 2MB limit.")
            return

        logging.info(f"Generated sample resume for {email} with ID {candidate_id} and keywords: {keywords_str} (size: {file_size} bytes).")

        files = {
            'resume': (file_name, io.BytesIO(sample_pdf_content), 'application/pdf')
        }
        data = {
            'email': email
        }

        logging.info(f"Sending resume to {UPLOAD_URL} for {email}...")
        upload_response = requests.post(
            UPLOAD_URL,
            files=files,
            data=data
        )
        upload_response.raise_for_status()
        logging.info(f"Resume uploaded to ResumeUploadUI: {upload_response.status_code} - {upload_response.text}")

    except requests.RequestException as req_error:
        logging.error(f"Failed to upload resume to ResumeUploadUI: {str(req_error)}")
    except Exception as e:
        logging.error(f"Error processing request: {str(e)}")

def upload_resume_task():
    burst_hour = None
    last_day = None

    while True:
        try:
            now = datetime.now()
            current_day = now.date()
            current_hour = now.hour

            if last_day != current_day:
                burst_hour = random.randint(0, 23)  
                last_day = current_day
                logging.info(f"Selected burst hour for {current_day}: {burst_hour}:00")

            next_hour = (now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
            seconds_until_next_hour = (next_hour - now).total_seconds()

            logging.info(f"Sleeping for {seconds_until_next_hour} seconds until the next hour.")
            time.sleep(seconds_until_next_hour)

            now = datetime.now()
            is_burst_hour = (now.hour == burst_hour)

            if is_burst_hour:
                num_requests = 1000
                logging.info(f"Burst hour {now.hour}:00: Processing {num_requests} requests.")
                request_times = sorted([random.randint(0, 3599) for _ in range(num_requests)])
                start_time = now.replace(minute=0, second=0, microsecond=0)
                for i, delay in enumerate(request_times):
                    current_time = datetime.now()
                    target_time = start_time + timedelta(seconds=delay)
                    sleep_seconds = (target_time - current_time).total_seconds()
                    if sleep_seconds > 0:
                        logging.info(f"Request {i+1}/{num_requests}: Sleeping for {sleep_seconds} seconds until {target_time.strftime('%H:%M:%S')}.")
                        time.sleep(sleep_seconds)
                    process_single_request()
            else:
                random_minute = random.randint(0, 59)
                delay_seconds = random_minute * 60
                logging.info(f"Normal hour {now.hour}:00: Delaying execution by {random_minute} minutes ({delay_seconds} seconds).")
                time.sleep(delay_seconds)
                process_single_request()

        except Exception as e:
            logging.error(f"Error in upload_resume_task: {str(e)}")
            time.sleep(60) 

thread = threading.Thread(target=upload_resume_task, daemon=True)
thread.start()

@app.route('/')
def health_check():
    logging.info("Health check endpoint accessed.")
    return jsonify({"status": "finalprojtimerwa is running"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)