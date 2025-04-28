from flask import Flask, request, jsonify, send_from_directory
import logging
import uuid
import requests
from azure.cosmos import CosmosClient
import base64
import os

app = Flask(__name__, static_folder='static', static_url_path='')
logging.basicConfig(level=logging.INFO)

# Hardcoded configuration variables
COSMOS_ENDPOINT = "https://finalproj-cosmos.documents.azure.com:443/"
COSMOS_KEY = "jLfTrYuzKAoDAjOp7UYolqlXEIbcUJEdzmCMEO8Sfwm6BA2mG0bqByduTatCR7n1upaH2AZcCLJAACDbKOdx6A=="
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx'}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB in bytes

# Authenticate with Cosmos DB key
client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)

def allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS

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

        # Validate file type
        if not allowed_file(file.filename):
            return jsonify({"message": "Invalid file type. Only PDF, DOC, or DOCX files are allowed."}), 400

        # Validate file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        if file_size > MAX_FILE_SIZE:
            return jsonify({"message": "File too large. Maximum size is 2MB."}), 400
        file.seek(0)  # Reset file pointer to the beginning

        # Read file content as binary and encode as base64
        file_content = file.read()
        file_content_base64 = base64.b64encode(file_content).decode('utf-8')
        filename = file.filename

        # Connect to Azure Cosmos DB
        database = client.get_database_client("FinalProjDb")
        container = database.get_container_client("Resumes")

        document = {
            "id": str(uuid.uuid4()),
            "fileName": filename,
            "uploadTime": request.headers.get("Date", ""),
            "resumeContent": file_content_base64,
            "email": email,
            "status": "Pending"
        }

        # Write to Cosmos DB
        try:
            logging.info(f"Attempting to write document to Cosmos DB: {document['id']}")
            container.create_item(document)
            logging.info(f"Successfully wrote document to Cosmos DB: {document['id']}")
        except Exception as cosmos_error:
            logging.error(f"Failed to write to Cosmos DB: {str(cosmos_error)}")
            return jsonify({"message": f"Failed to write to Cosmos DB: {str(cosmos_error)}"}), 500

        # Trigger MatchFilterEngine (updated to new App Service endpoint)
        try:
            logging.info("Triggering MatchFilterEngine.")
            response = requests.post("https://enginematchfinalproj.azurewebsites.net/schedule_interviews")
            response.raise_for_status()  # Raise an exception for HTTP errors
            logging.info("Successfully triggered MatchFilterEngine.")
        except requests.RequestException as req_error:
            logging.error(f"Failed to trigger MatchFilterEngine: {str(req_error)}")
            # Continue despite the failure, as the document is already in Cosmos DB
            pass

        return jsonify({"message": f"✅ Resume '{filename}' uploaded and stored for {email}."}), 200
    except Exception as e:
        logging.error(f"Upload failed: {str(e)}")
        return jsonify({"message": f"Upload failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)