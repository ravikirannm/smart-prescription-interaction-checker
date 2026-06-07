# Smart Prescription Interaction Checker

![Application Screenshot](image.png)

## Overview

**Smart Prescription Interaction Checker** is a hybrid AI-assisted medical safety platform that evaluates patient medication descriptions, identifies drug interactions, and generates evidence-backed clinical insights in real time.

This project combines streaming AI analysis, drug verification, and multi-source evidence retrieval to support safer medication management and reduce the risk of adverse interactions.

## Key Features

- **Interactive medication consultation UI** with threaded sessions
- **Live streaming response** from the backend for responsive feedback
- **Drug extraction and validation** using LLM reasoning plus RxNorm lookup
- **Drug interaction detection** across verified medication pairs
- **Evidence retrieval** from OpenFDA, RxNorm, and PubMed
- **Pseudoscience flagging** for non-pharmaceutical or unverified substances
- **Persistent conversation memory** in MongoDB + PostgreSQL
- **Thread summary generation** and title auto-updates via LLM

## What Makes This Project Unique

- Uses a multi-layer verification pipeline instead of relying on a single source
- Combines real-world drug database lookups with LLM-driven clinical reasoning
- Maintains user-specific thread history and shared reasoning memory
- Supports clinician-style structured analysis with patient-friendly explanations

## Architecture

### Frontend

- Framework: **Angular 21.2.0**
- Styling: **SCSS + Bootstrap 5.3.3**
- Interaction: `fetch` + SSE-style streaming from `/analyze`
- Sanitization: `dompurify` + `marked` for safe markdown rendering

### Backend

- Framework: **Flask**
- AI: **Ollama** model `qwen2.5:7b`
- Data storage:
  - **PostgreSQL** for users, threads, and memory
  - **MongoDB** for detailed conversation history
- Medical data sources:
  - **RxNorm** for drug normalization
  - **OpenFDA** for warnings and labels
  - **PubMed** for literature retrieval

### Deployment

- Container orchestration with **Docker Compose**
- Services:
  - `backend` (Flask app)
  - `frontend` (Angular app)
  - `mongodb`
  - `postgres`
- Optional GPU passthrough configured for the backend service

## Project Structure

```
.
├── backend/
│   ├── constants.py
│   ├── Dockerfile
│   ├── engine/
│   │   ├── analyzer.py        # Core AI pipeline and data processing
│   │   ├── database.py        # PostgreSQL + MongoDB manager
│   │   ├── interaction.py     # RxNorm/OpenFDA/PubMed helper logic
│   │   ├── main.py            # Flask routes and streaming API
│   │   ├── memory.py          # Thread, user, and shared memory management
│   │   ├── data_model.py      # Pydantic-like response schemas
│   ├── requirements.txt
│   └── run.py                 # Backend entrypoint
├── docker-compose.yml
├── frontend/
│   ├── angular.json
│   ├── Dockerfile
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   │   ├── app.config.ts
│   │   │   ├── app.routes.ts
│   │   │   ├── interfaces.ts
│   │   │   ├── main/
│   │   │   │   ├── mydoc/
│   │   │   │   │   ├── mydoc.component.html
│   │   │   │   │   ├── mydoc.component.scss
│   │   │   │   │   └── mydoc.component.ts
│   │   │   └── services/
│   │   │       └── api.service.ts
│   └── README.md
├── image.png
```

## API Endpoints

### `GET /me`
- Returns or creates a persistent `user_id` cookie
- Enables thread scoping per user session

### `GET /threads`
- Returns the list of conversation threads for the current user
- Uses PostgreSQL thread metadata

### `GET /thread/<thread_id>`
- Returns the chat history for a specific thread
- Reads conversation turns from MongoDB

### `POST /analyze`
- Accepts JSON `{ query, thread_id? }`
- Streams progress events and chat tokens back to the frontend
- Returns `X-Thread-ID` header for new sessions

### `POST /fetch-analysis`
- Accepts JSON `{ thread_id }`
- Returns the final structured analysis for the current thread

## Backend Workflow

1. **Initialize memory** for the user and thread
2. **Clinical reformulation** of the query with the LLM
3. **Drug extraction** and substance verification
4. **RxNorm/OpenFDA interaction checks** on verified drug pairs
5. **PubMed evidence retrieval** and PICO-style reasoning
6. **LLM synthesis** of patient-facing clinical guidance
7. **Background memory update** with thread summaries and shared intelligence

## Frontend Workflow

- User enters a clinical medication query
- Frontend sends the query to `/analyze` using a streaming POST
- The UI receives incremental updates:
  - progress messages
  - live token stream
  - final completion event
- The right-hand evidence panel updates with:
  - verified drugs
  - interaction severity
  - pseudoscience flags
  - source links

## Setup & Installation

### Prerequisites

- Docker & Docker Compose
- Node.js and npm (for local frontend development)
- Python 3.11+ and `pip` (for backend development)
- Ollama server reachable at `http://localhost:11434`

### Run with Docker Compose

```bash
docker-compose up --build
```

This starts:
- Frontend on `http://localhost:4200`
- Backend on `http://localhost:5000`
- MongoDB on `27017`
- PostgreSQL on `5432`

### Local development

#### Backend

```bash
cd backend
pip install -r requirements.txt
python run.py
```

#### Frontend

```bash
cd frontend
npm install
npm start
```

## Environment Configuration

The backend includes `backend/constants.py` with these values:

- `OLLAMA_MODEL = "qwen2.5:7b"`
- `OLLAMA_URL = "http://host.docker.internal:11434"`

If you run Ollama on a different host or port, update `backend/constants.py` or provide a matching environment mapping.

The Docker Compose setup configures:

- `MONGO_URI=mongodb://mongodb:27017/spic`
- `POSTGRES_URI=postgresql://user:pass@postgres:5432/spic`
- `OLLAMA_BASE_URL=http://host.docker.internal:11434`

## Database Notes

- PostgreSQL is used for:
  - user and thread metadata
  - thread memory
  - shared memory
- MongoDB is used for:
  - detailed conversation history
  - step-by-step analysis turns

The backend auto-creates the required PostgreSQL schema at startup.

## Development Notes

- The backend uses **streaming responses** to provide real-time progress and token-by-token chat output.
- The frontend uses a custom `streamPostData()` implementation in `frontend/src/app/services/api.service.ts`.
- The right-side evidence pane groups sources by type: `pubmed`, `openfda`, `rxnorm`, and `icd11`.
- Thread titles are updated automatically using LLM-generated summaries.

## Troubleshooting

- If the frontend cannot connect to the backend, verify `frontend/src/app/services/api.service.ts` points to `http://localhost:5000`.
- If Ollama is unavailable, update `backend/constants.py` and restart the backend.
- If Docker Compose fails on GPU passthrough, remove the `deploy.resources.reservations.devices` block or run without GPU support.

## Future Enhancements

- Add user authentication beyond cookies
- Support additional drug knowledge graphs and EHR integration
- Add end-to-end testing for analysis workflows
- Introduce a secure production configuration for Ollama and database secrets

## Attribution

Built with a modern Angular frontend, Flask backend, PostgreSQL, MongoDB, and Ollama LLM-driven clinical reasoning.

---

**Smart Prescription Interaction Checker** is designed to help clinicians and care teams review medication safety concerns using evidence-linked AI, not to replace licensed medical judgment.
