from flask import Flask, request, jsonify, send_from_directory
import logging
from azure.cosmos import CosmosClient, PartitionKey
import os
import uuid
from datetime import datetime, timedelta
import json
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.communication.email import EmailClient
import threading
import time

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

COSMOS_ENDPOINT = "https://finalproj-cosmos.documents.azure.com:443/"
COSMOS_KEY = "jLfTrYuzKAoDAjOp7UYolqlXEIbcUJEdzmCMEO8Sfwm6BA2mG0bqByduTatCR7n1upaH2AZcCLJAACDbKOdx6A=="
SERVICE_BUS_CONNECTION_STRING = "Endpoint=sb://finalproj.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=Vhx8DNxQU0K/FHAXv9dZkPEXIkQGeyMgP+ASbOZbM5I="
SERVICE_BUS_QUEUE_NAME = "finalprojqueue"
ACS_CONNECTION_STRING = "endpoint=https://emailcommunicationfinalproj.unitedstates.communication.azure.com/;accesskey=6JMmFWB8pr293b3yDfmBNarjJrRyFXSI2iUuZoSkh48k8Ki3hEC4JQQJ99BDACULyCpciToOAAAAAZCS3FHT"

logging.info("Starting InterviewSchedulerApp...")

try:
    client = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
    logging.info("CosmosClient initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize CosmosClient: {str(e)}")
    raise

try:
    servicebus_client = ServiceBusClient.from_connection_string(SERVICE_BUS_CONNECTION_STRING)
    logging.info("ServiceBusClient initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize ServiceBusClient: {str(e)}")
    raise

try:
    email_client = EmailClient.from_connection_string(ACS_CONNECTION_STRING)
    logging.info("EmailClient initialized successfully.")
except Exception as e:
    logging.error(f"Failed to initialize EmailClient: {str(e)}")
    raise

try:
    database = client.get_database_client("FinalProjDb")
    logging.info("Connected to database FinalProjDb.")
    
    container = database.get_container_client("Resumes")
    logging.info("Connected to container Resumes.")

    try:
        container_emails = database.create_container_if_not_exists(
            id="Emails",
            partition_key=PartitionKey(path="/id"),
            offer_throughput=400
        )
        logging.info("Emails container created or accessed successfully.")
    except Exception as e:
        logging.error(f"Failed to create or access Emails container: {str(e)}")
        container_emails = None
except Exception as e:
    logging.error(f"Failed to connect to database or containers: {str(e)}")
    database = None
    container = None
    container_emails = None

def generate_interview_slots():
    slots = []
    current_date = datetime.now().date()
    days_to_monday = (7 - current_date.weekday()) % 7  
    if days_to_monday == 0:  
        days_to_monday = 7
    start_date = current_date + timedelta(days=days_to_monday)

    for day in range(5):  
        date = start_date + timedelta(days=day)
        for hour in range(9, 17): 
            for minute in (0, 30):
                slot_time = datetime(date.year, date.month, date.day, hour, minute)
                slots.append(slot_time)

    return slots

def assign_time_slot(used_slots):
    logging.info("Assigning a time slot...")
    available_slots = generate_interview_slots()
    logging.info(f"Generated {len(available_slots)} available time slots.")
    for slot in available_slots:
        slot_str = slot.strftime("%Y-%m-%d %H:%M:%S")
        if slot_str not in used_slots:
            logging.info(f"Assigned time slot: {slot_str}")
            return slot_str
    logging.warning("No available time slots found.")
    return None  

def email_processor_task():
    while True:
        try:
            with servicebus_client:
                receiver = servicebus_client.get_queue_receiver(queue_name=SERVICE_BUS_QUEUE_NAME)
                with receiver:
                    for message in receiver:
                        try:
                            email_data = json.loads(str(message))
                            email = email_data["email"]
                            interview_time = email_data["interview_time"]

                            message_content = {
                                "senderAddress": "DoNotReply@2a1083c6-24da-4a2c-bef9-2befb55b094f.azurecomm.net",
                                "recipients": {
                                    "to": [{"address": email}]
                                },
                                "content": {
                                    "subject": "Interview Invitation",
                                    "plainText": f"You have been shortlisted! Please confirm your availability for an interview scheduled on {interview_time}.",
                                    "html": (
                                        "<html>"
                                        "<body>"
                                        "<h1>Interview Invitation</h1>"
                                        "<p>You have been shortlisted! Please confirm your availability for an interview scheduled on <strong>" + interview_time + "</strong>.</p>"
                                        "</body>"
                                        "</html>"
                                    )
                                }
                            }
                            poller = email_client.begin_send(message_content)
                            result = poller.result()
                            logging.info(f"Email sent to {email}: user")

                            receiver.complete_message(message)
                        except Exception as e:
                            logging.error(f"Failed to process queue message: {str(e)}")
                            receiver.abandon_message(message) 
                            time.sleep(60)  
        except Exception as e:
            logging.error(f"Error in email processor thread: {str(e)}")
            time.sleep(60)  

email_thread = threading.Thread(target=email_processor_task, daemon=True)
email_thread.start()

@app.route('/schedule_interviews', methods=['POST'])
def schedule_interviews():
    logging.info('InterviewScheduler triggered via web app.')
    
    try:
        logging.info("Connecting to Cosmos DB...")
        if container is None or container_emails is None:
            logging.error("Cosmos DB containers are not initialized.")
            return jsonify({"message": "Cosmos DB containers are not initialized.", "status": "error"}), 500

        logging.info("Querying for shortlisted candidates...")
        query = "SELECT * FROM c WHERE c.status = 'Shortlisted'"
        items = list(container.query_items(query=query, enable_cross_partition_query=True))
        logging.info(f"Found {len(items)} shortlisted candidates.")

        if not items:
            logging.info("No shortlisted candidates to process.")
            return jsonify({"message": "✅ Scheduled interviews for 0 candidates.", "status": "success"}), 200

        used_slots = []
        try:
            scheduled_items = list(container_emails.query_items(
                query="SELECT * FROM c",
                enable_cross_partition_query=True
            ))
            for item in scheduled_items:
                if "interviewTime" in item:
                    used_slots.append(item["interviewTime"])
            logging.info(f"Found {len(used_slots)} used time slots.")
        except Exception as e:
            logging.error(f"Failed to query Emails container for used time slots: {str(e)}")
            used_slots = [] 

        count = 0
        interview_schedules = [] 
        for item in items:
            if "email" not in item:
                logging.warning(f"Skipping item {item.get('id', 'unknown')} due to missing email.")
                continue

            interview_time = assign_time_slot(used_slots)
            if not interview_time:
                logging.warning(f"No available time slots for item {item['id']}. Skipping.")
                continue

            used_slots.append(interview_time)

            if not isinstance(interview_time, str):
                interview_time = str(interview_time)
            interview_time_safe = interview_time.replace('"', '').replace("'", '')

            logging.info(f"Queuing email for {item['email']} with interview time {interview_time_safe}...")
            email_message = {
                "email": item["email"],
                "interview_time": interview_time_safe
            }
            with servicebus_client:
                sender = servicebus_client.get_queue_sender(queue_name=SERVICE_BUS_QUEUE_NAME)
                message = ServiceBusMessage(json.dumps(email_message))
                sender.send_messages(message)
                logging.info(f"Email task queued for {item['email']} with interview time {interview_time_safe}.")

            interview_schedule = {
                "id": str(uuid.uuid4()),
                "candidateId": item["id"],
                "email": item["email"],
                "interviewTime": interview_time
            }
            interview_schedules.append(interview_schedule)

            logging.info(f"Updating status for item {item['id']} to 'Interview Scheduled' with time {interview_time}.")
            item["status"] = "Interview Scheduled"
            item["interviewTime"] = interview_time
            container.upsert_item(item)
            count += 1

        for schedule in interview_schedules:
            logging.info(f"Storing interview schedule for candidate {schedule['candidateId']} in Emails container.")
            container_emails.upsert_item(schedule)

        logging.info(f"Scheduled interviews for {count} candidates.")
        return jsonify({"message": f"✅ Scheduled interviews for {count} candidates.", "status": "success"}), 200
    except Exception as e:
        logging.error(f"Scheduler error: {str(e)}")
        return jsonify({"message": "Scheduling error occurred.", "status": "error"}), 500

@app.route('/')
def health_check():
    logging.info("Health check endpoint accessed.")
    return jsonify({"status": "App is running", "message": "Use /schedule_interviews to schedule interviews."})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)