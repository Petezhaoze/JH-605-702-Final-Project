from flask import Flask, request, jsonify, send_from_directory
import logging
from azure.cosmos import CosmosClient
from azure.communication.email import EmailClient
import os

#app = Flask(__name__, static_folder='templates', static_url_path='')
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Hardcoded configuration variables
COSMOS_ENDPOINT = "https://finalproj-cosmos.documents.azure.com:443/"
COSMOS_KEY = "jLfTrYuzKAoDAjOp7UYolqlXEIbcUJEdzmCMEO8Sfwm6BA2mG0bqByduTatCR7n1upaH2AZcCLJAACDbKOdx6A=="
ACS_CONNECTION_STRING = "endpoint=https://emailcommunicationfinalproj.unitedstates.communication.azure.com/;accesskey=6JMmFWB8pr293b3yDfmBNarjJrRyFXSI2iUuZoSkh48k8Ki3hEC4JQQJ99BDACULyCpciToOAAAAAZCS3FHT"
SENDER_EMAIL = "DoNotReply@2a108c36-24da-442c-bef9-2befb55b094f.azurecomm.net"

# Log initialization
logging.info("Starting InterviewSchedulerApp...")

# Initialize Azure Cosmos DB client
try:
    client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
    logging.info("CosmosClient initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize CosmosClient: {str(e)}")
    raise

# Initialize ACS Email client
try:
    email_client = EmailClient.from_connection_string(ACS_CONNECTION_STRING)
    logging.info("EmailClient initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize EmailClient: {str(e)}")
    raise

@app.route('/schedule_interviews', methods=['POST'])
def schedule_interviews():
    logging.info('InterviewScheduler triggered via web app.')
    
    try:
        # Connect to Azure Cosmos DB
        logging.info("Connecting to Cosmos DB...")
        database = client.get_database_client("FinalProjDb")
        container = database.get_container_client("Resumes")

        # Query for shortlisted candidates
        logging.info("Querying for shortlisted candidates...")
        query = "SELECT * FROM c WHERE c.status = 'Shortlisted'"
        items = list(container.query_items(query=query, enable_cross_partition_query=True))
        logging.info(f"Found {len(items)} shortlisted candidates.")

        count = 0
        for item in items:
            if "email" not in item:
                logging.warning(f"Skipping item {item.get('id', 'unknown')} due to missing email.")
                continue

            # Send email via ACS
            logging.info(f"Sending email to {item['email']}...")
            message = {
                "senderAddress": "DoNotReply@2a1083c6-24da-4a2c-bef9-2befb55b094f.azurecomm.net",
                "recipients": {
                    "to": [{"address": item["email"]}]
                },
                "content": {
                    "subject": "Interview Invitation",
                    "plainText": "You have been shortlisted! Please confirm your availability for an interview.",
                    "html": """
                    <html>
                        <body>
                            <h1>Interview Invitation</h1>
                            <p>You have been shortlisted! Please confirm your availability for an interview.</p>
                        </body>
                    </html>
                    """
                }
            }
            poller = email_client.begin_send(message)
            result = poller.result()
            logging.info(f"Message sent: {item['id']}")

            # Update status in Cosmos DB
            logging.info(f"Updating status for item {item['id']} to 'Interview Scheduled'.")
            item["status"] = "Interview Scheduled"
            container.upsert_item(item)
            count += 1

        logging.info(f"Scheduled interviews for {count} candidates.")
        return jsonify({"message": f"✅ Scheduled interviews for {count} candidates.", "status": "success"})
    except Exception as e:
        logging.error(f"Scheduler error: {str(e)}")
        return jsonify({"message": "Scheduling error occurred.", "status": "error"}), 500

if __name__ == '__main__':
    app.run(debug=True)