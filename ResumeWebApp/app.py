from flask import Flask, request, jsonify, send_from_directory
import logging
import uuid
import requests
from azure.cosmos import CosmosClient
import base64
import os
import json
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import threading
import time
import random

app = Flask(__name__, static_folder='static', static_url_path='')
logging.basicConfig(level=logging.INFO)

COSMOS_ENDPOINT = ""
COSMOS_KEY = ""
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx'}
MAX_FILE_SIZE = 2 * 1024 * 1024
SERVICE_BUS_CONNECTION_STRING = ""
SERVICE_BUS_QUEUE_NAME = ""

client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)

try:
    servicebus_client = ServiceBusClient.from_connection_string(SERVICE_BUS_CONNECTION_STRING)
    logging.info("ServiceBusClient initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize ServiceBusClient: {str(e)}")
    raise

def allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS

def matchfilter_processor_task():
    retry_count = 0
    max_retries = 5
    base_delay = 1 

    while True:
        try:
            with servicebus_client:
                receiver = servicebus_client.get_queue_receiver(queue_name=SERVICE_BUS_QUEUE_NAME)
                with receiver:
                    for message in receiver:
                        try:
                            message_body = next(message.body).decode('utf-8')  
                            trigger_data = json.loads(message_body)
                            
                            if "candidate_id" not in trigger_data:
                                logging.error(f"Malformed message in queue, missing 'candidate_id': {message_body}")
                                receiver.complete_message(message)  
                                continue

                            candidate_id = trigger_data["candidate_id"]
                            logging.info(f"Triggering MatchFilterEngineApp for candidate {candidate_id}...")
                            response = requests.post("")
                            response.raise_for_status()
                            logging.info(f"Successfully triggered MatchFilterEngineApp for candidate {candidate_id}: {response.status_code}")
                            receiver.complete_message(message)
                            retry_count = 0 
                        except Exception as e:
                            logging.error(f"Failed to process queue message for MatchFilterEngineApp: {str(e)}")
                            receiver.abandon_message(message)  
                            time.sleep(base_delay) 
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                logging.error(f"Max retries ({max_retries}) reached for Service Bus connection. Exiting thread.")
                break
            delay = base_delay * (2 ** retry_count) + random.uniform(0, 1) 
            logging.error(f"Error in matchfilter processor thread: {str(e)}. Retrying in {delay:.2f} seconds (attempt {retry_count + 1}/{max_retries})...")
            time.sleep(delay)

matchfilter_thread = threading.Thread(target=matchfilter_processor_task, daemon=True)
matchfilter_thread.start()

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    logging.info('ResumeUploadUI triggered via Flask.')
    
    try:
        if 'resume' not in request.files:
            return jsonify({"message": "No file uploaded."}), 400

        file = request.files['resume']
        email = request.form.get('email')

        if not file:
            return jsonify({"message": "No file uploaded."}), 400

        if not email:
            return jsonify({"message": "No email provided."}), 400

        if not allowed_file(file.filename):
            return jsonify({"message": "Invalid file type. Only PDF, DOC, or DOCX files are allowed."}), 400

        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        if file_size > MAX_FILE_SIZE:
            return jsonify({"message": "File too large. Maximum size is 2MB."}), 400
        file.seek(0)  

        file_content = file.read()
        file_content_base64 = base64.b64encode(file_content).decode('utf-8')
        filename = file.filename

        database = client.get_database_client("")
        container = database.get_container_client("")

        document = {
            "id": str(uuid.uuid4()),
            "fileName": filename,
            "uploadTime": request.headers.get("Date", ""),
            "resumeContent": file_content_base64,
            "email": email,
            "status": "Pending"
        }

        try:
            logging.info(f"Attempting to write document to Cosmos DB: {document['id']}")
            container.create_item(document)
            logging.info(f"Successfully wrote document to Cosmos DB: {document['id']}")
        except Exception as cosmos_error:
            logging.error(f"Failed to write to Cosmos DB: {str(cosmos_error)}")
            return jsonify({"message": f"Failed to write to Cosmos DB: {str(cosmos_error)}"}), 500

        logging.info(f"Queuing trigger for MatchFilterEngineApp for candidate {document['id']}...")
        trigger_message = {
            "candidate_id": document["id"]
        }
        try:
            with servicebus_client:
                sender = servicebus_client.get_queue_sender(queue_name=SERVICE_BUS_QUEUE_NAME)
                message = ServiceBusMessage(json.dumps(trigger_message))
                sender.send_messages(message)
                logging.info(f"Trigger task queued for MatchFilterEngineApp for candidate {document['id']}.")
        except Exception as sb_error:
            logging.error(f"Failed to queue trigger for MatchFilterEngineApp: {str(sb_error)}")
            return jsonify({"message": f"Failed to queue trigger for MatchFilterEngineApp: {str(sb_error)}"}), 500

        return jsonify({"message": f"✅ Resume '{filename}' uploaded and stored for {email}."}), 200
    except Exception as e:
        logging.error(f"Upload failed: {str(e)}")
        return jsonify({"message": f"Upload failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)