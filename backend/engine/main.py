from flask import Flask, Response, request, make_response, stream_with_context
import uuid
import logging
from flask_cors import CORS
import json
from .analyzer import PresciptionInteractionChecker
from .memory import ConversationMemory

logger = logging.getLogger(__name__)
prescription_checker = PresciptionInteractionChecker()

# Create an instance of the Flask class
app = Flask(__name__)
CORS(app, 
     resources={r"/*": {"origins": ["http://localhost:4200", "http://127.0.0.1:4200"]}},
     supports_credentials=True)

@app.route('/me', methods=['GET'])
def get_user_info():
    user_id = request.cookies.get('user_id')
    if not user_id:
        user_id = str(uuid.uuid4())
        response = make_response({"user_id": user_id})
        logger.info("No user_id cookie found. Generating new user_id and setting cookie.")
        response.set_cookie('user_id', user_id, max_age=60*60*24*365)  # 1 year
        return response
    return {"user_id": user_id}

@app.route('/threads', methods=['GET'])
def get_user_threads():
    # Retreive user_id from Cookies
    user_id = request.cookies.get('user_id')
    memory = ConversationMemory(prescription_checker.db_manager, user_id)
    threads = memory.fetch_user_threads()
    logger.info(f"User {user_id} requested threads. Found {len(threads)} threads.")
    return threads

@app.route('/thread/<thread_id>', methods=['GET'])
def get_thread(thread_id):
    user_id = request.cookies.get('user_id')
    if not user_id:
        return "User not found", 404
    memory = ConversationMemory(prescription_checker.db_manager, user_id,thread_id)
    logger.info(f"User {user_id} requested thread {thread_id}.")
    return memory.fetch_thread_history()

@app.route('/analyze', methods=['POST'])
def analyze_symptoms():
    # Placeholder for symptom analysis logic
    data = request.get_json()
    user_query = data.get('query', '')
    user_id = request.cookies.get('user_id')
    thread_id = data.get('thread_id',str(uuid.uuid4()))
    def generate():
        # Iterate over the yielded events from your analyzer
        for event in prescription_checker.interaction_check(user_query, user_id, thread_id):
            # Format strictly as SSE: "data: <json_string>\n\n"
            yield f"data: {json.dumps(event)}\n\n"
    # Add thread_id to the response headers so the frontend can correlate responses
    response = Response(stream_with_context(generate()), mimetype='text/event-stream')
    response.headers['X-Thread-ID'] = thread_id
    return response

@app.route('/fetch-analysis', methods=['POST'])
def fetch_analysis():
    data = request.get_json()
    user_id = request.cookies.get('user_id')
    thread_id = data.get('thread_id')
    if not user_id or not thread_id:
        return "Invalid request", 400
    memory = ConversationMemory(prescription_checker.db_manager, user_id, thread_id)
    return memory.fetch_final_analysis()



# Start the application
if __name__ == '__main__':
    app.run(debug=True)
