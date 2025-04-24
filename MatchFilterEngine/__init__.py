import logging
import azure.functions as func
import os
import requests
from azure.cosmos import CosmosClient

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('MatchFilterEngine triggered.')

    try:
        cosmos_url = os.environ['COSMOS_ENDPOINT']
        cosmos_key = os.environ['COSMOS_KEY']
        client = CosmosClient(cosmos_url, cosmos_key)
        db = client.get_database_client("SOJAS")
        container = db.get_container_client("Resumes")

        query = "SELECT * FROM c WHERE c.status = 'Pending'"
        items = list(container.query_items(query=query, enable_cross_partition_query=True))

        keywords = ["python", "azure", "machine learning", "django", "flask"]
        updated = 0

        for item in items:
            match_count = sum(k.lower() in item.get("resumeText", "").lower() for k in keywords)
            item["matchedScore"] = match_count * 20
            item["status"] = "Shortlisted" if match_count >= 2 else "Rejected"
            container.upsert_item(item)
            updated += 1

        # Trigger InterviewScheduler
        requests.post("https://interviewschedulingclass.azurewebsites.net/api/interviewscheduler")

        return func.HttpResponse(f"✅ Processed {updated} resumes.", status_code=200)
    except Exception as e:
        logging.error(f"Matching failed: {e}")
        return func.HttpResponse("Matching error occurred.", status_code=500)
