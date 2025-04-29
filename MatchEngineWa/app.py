from flask import Flask, Response
import logging
import requests
from azure.cosmos import CosmosClient
import base64

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

COSMOS_ENDPOINT = "https://finalproj-cosmos.documents.azure.com:443/"
COSMOS_KEY = "jLfTrYuzKAoDAjOp7UYolqlXEIbcUJEdzmCMEO8Sfwm6BA2mG0bqByduTatCR7n1upaH2AZcCLJAACDbKOdx6A=="

client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)

@app.route('/matchfilterengine', methods=['POST'])
def match_filter_engine():
    logging.info('MatchFilterEngine triggered.')

    try:
        db = client.get_database_client("FinalProjDb")
        container = db.get_container_client("Resumes")

        query = "SELECT * FROM c WHERE c.status = 'Pending'"
        items = list(container.query_items(query=query, enable_cross_partition_query=True))
        logging.info(f"Found {len(items)} pending resumes to process.")

        keywords = ["python", "azure", "machine learning", "django", "flask"]
        updated = 0

        for item in items:
            logging.info(f"Processing resume with ID: {item['id']}")
            try:
                resume_content_base64 = item.get("resumeContent", "")
                resume_text = base64.b64decode(resume_content_base64).decode('utf-8', errors='ignore')
            except Exception as e:
                logging.error(f"Failed to decode resumeContent for resume {item['id']}: {str(e)}")
                resume_text = ""

            match_count = sum(k.lower() in resume_text.lower() for k in keywords)
            item["matchedScore"] = match_count * 20
            item["status"] = "Shortlisted" if match_count >= 2 else "Rejected"
            logging.info(f"Resume {item['id']} matched {match_count} keywords, new status: {item['status']}")
            container.upsert_item(item)
            updated += 1

        try:
            logging.info("Triggering InterviewScheduler.")
            requests.post("https://finalprojschedulerwa.azurewebsites.net/schedule_interviews")
            logging.info("InterviewScheduler trigger initiated (fire-and-forget).")
        except requests.exceptions.RequestException as req_error:
            logging.error(f"Failed to initiate InterviewScheduler trigger: {str(req_error)}")
            pass

        return Response(f"✅ Processed {updated} resumes.", status=200, mimetype='text/plain')
    except Exception as e:
        logging.error(f"Matching failed: {e}")
        return Response("Matching error occurred.", status=500, mimetype='text/plain')

if __name__ == '__main__':
    app.run(debug=True)