import logging
import azure.functions as func
import os
import uuid
import requests
from azure.cosmos import CosmosClient

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('ResumeUploadUI triggered.')

    try:
        file = req.files.get('resume')
        if not file:
            return func.HttpResponse(" No file uploaded.", status_code=400)

        resume_text = file.stream.read().decode('utf-8', errors='ignore')
        filename = file.filename

        cosmos_url = os.environ['COSMOS_ENDPOINT']
        cosmos_key = os.environ['COSMOS_KEY']
        client = CosmosClient(cosmos_url, cosmos_key)
        db = client.get_database_client("SOJAS")
        container = db.get_container_client("Resumes")

        document = {
            "id": str(uuid.uuid4()),
            "fileName": filename,
            "uploadTime": req.headers.get("Date", ""),
            "resumeText": resume_text,
            "status": "Pending"
        }

        container.create_item(document)

        # Trigger MatchFilterEngine
        requests.post("https://matchingfilteringclass.azurewebsites.net/api/matchfilterengine")

        return func.HttpResponse(f"✅ Resume '{filename}' uploaded and stored.", status_code=200)
    except Exception as e:
        logging.error(f"Upload failed: {e}")
        return func.HttpResponse(" Internal error occurred.", status_code=500)
