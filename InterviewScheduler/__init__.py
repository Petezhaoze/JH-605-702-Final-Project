import logging
import azure.functions as func
import os
import smtplib
from email.message import EmailMessage
from azure.cosmos import CosmosClient

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('InterviewScheduler triggered.')

    try:
        cosmos_url = os.environ['COSMOS_ENDPOINT']
        cosmos_key = os.environ['COSMOS_KEY']
        client = CosmosClient(cosmos_url, cosmos_key)
        db = client.get_database_client("SOJAS")
        container = db.get_container_client("Resumes")

        query = "SELECT * FROM c WHERE c.status = 'Shortlisted'"
        items = list(container.query_items(query=query, enable_cross_partition_query=True))

        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")

        count = 0
        for item in items:
            if "email" not in item:
                continue
            msg = EmailMessage()
            msg['Subject'] = "Interview Invitation"
            msg['From'] = smtp_user
            msg['To'] = item["email"]
            msg.set_content("You have been shortlisted! Please confirm your availability for an interview.")

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            item["status"] = "Interview Scheduled"
            container.upsert_item(item)
            count += 1

        return func.HttpResponse(f"✅ Scheduled interviews for {count} candidates.", status_code=200)
    except Exception as e:
        logging.error(f"Scheduler error: {e}")
        return func.HttpResponse("Scheduling error occurred.", status_code=500)
