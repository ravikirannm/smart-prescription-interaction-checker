from dotenv import load_dotenv
load_dotenv()

import logging
# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)
logger.info("Starting the Prescription Interaction Checker backend...")
import torch
logger.info(f"CUDA available: {torch.cuda.is_available()}")

from engine.main import app
# Start the application
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)


