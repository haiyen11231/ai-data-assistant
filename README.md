# AI Data Assistant

> An AI-powered web application that lets users upload CSV/Excel files, explore data, ask natural language questions, generate charts, and manage prompt history.

## Table of Contents

1. [Overview](#overview)
2. [Functional Requirements](#functional-requirements)
3. [Non-Functional Requirements](#non-functional-requirements)
4. [Project Structure](#project-structure)
5. [Technology Stack](#technology-stack)
6. [System Architecture](#system-architecture)
7. [Quick Start](#quick-start)
8. [Local Setup](#local-setup-without-docker)
9. [Further Improvements](#further-improvements)
10. [References](#references)

## Overview

This application allows users to:

- Upload one or more CSV / Excel (`.csv`, `.xlsx`, `.xls`) files
- Preview the top N rows of any uploaded sheet
- Ask natural language questions about their data and receive AI-generated answers and charts
- Browse and reuse a history of past prompts
- Rate answers with thumbs up / thumbs down feedback

The system is designed around five pillars: **scalability**, **reliability**, **availability**, **performance efficiency**, and **security**.

## Functional Requirements

### 1. File Upload
- User uploads one or more `.csv`, `.xlsx`, or `.xls` files
- Minimum file size: 250 rows
- System validates file type, size (max 10 MB), and content
- System parses file, extracts schema and metadata, assigns a `dataset_id`
- Raw file stored in MinIO object storage

### 2. Data Preview
- User selects a dataset and a sheet (for multi-sheet Excel files)
- User defines N (top N rows to display)
- System returns a paginated table view

### 3. AI Query
- User types a free-text question about the selected dataset
- System generates a natural language answer and optionally a chart
- Model is capable of generating graphs

### 4. Prompt History
- Every prompt and its result is persisted per session
- User can browse past prompts filtered by dataset
- User can one-click reuse a past prompt

### 5. Feedback (Bonus)
- User can rate each answer: 👍 useful (+1) or 👎 not useful (−1)

## Non-Functional Requirements

| Pillar | Requirement | Solution |
|---|---|---|
| **Scalability** | Handle many users, datasets, queries | Stateless FastAPI replicas behind NGINX load balancer; Celery workers scale independently via shared Redis task queue |
| **Reliability** | No crash on bad prompts, large files, or code errors | RestrictedPython sandbox; Celery re-queues on worker crash; exponential backoff retry on OpenAI calls; multi-layer file validation |
| **Availability** | Service always responds | Async FastAPI offloads slow LLM calls to Celery, keeping HTTP responsive |
| **Performance** | Low latency for common operations | In-process LRU DFCache for DataFrames; async Celery queue decouples slow operations; Redis caches history results for reruns without repeat LLM calls |
| **Security** | Protect API key, prevent code injection, isolate sessions | RestrictedPython sandbox; API key management; NGINX IP-based rate limiting |

## Project Structure

```
ai-csv-app/
├── backend/
│   ├── main.py              
│   └── requirements.txt
├── frontend/
│   ├── app.py        
│   └── requirements.txt
├── docker-compose.yml
├── Makefile
├── .env
└── README.md
```

## Technology Stack

- **Frontend:** Streamlit
- **Backend API:** FastAPI + Uvicorn
- **AI Engine:** PandasAI 
- **Code Sandbox:** RestrictedPython
- **Task Queue:** Celery
- **Message Broker:** Redis 
- **DataFrame Cache:** In-process LRU dict
- **Query Result Cache:** Redis (history rerun only, not free-text queries)
- **File Storage:** MinIO
- **Database:** PostgreSQL
- **Reverse Proxy:** NGINX 
- **Containerization:** Docker Compose

## System Architecture

```mermaid
graph TB
    Browser([Browser])
    Browser -->|HTTPS 80| NGINX

    subgraph edge["Edge layer"]
        NGINX[NGINX<br/>reverse proxy · rate limit · TLS]
    end

    NGINX -->|UI requests| Streamlit
    NGINX -->|/api/* requests| FastAPI

    subgraph frontend["Frontend"]
        Streamlit[Streamlit<br/>UI · JWT in session_state]
    end

    subgraph backend["Backend - FastAPI"]
        FastAPI[FastAPI<br/>routing · validation]
        FastAPI --> DatasetSvc[Dataset service<br/>upload · parse · preview]
        FastAPI --> QuerySvc[Query / AI service<br/>enqueue · poll]
        FastAPI --> HistorySvc[History service<br/>save · list · reuse]
        FastAPI --> FeedbackSvc[Feedback service<br/>ratings · store]
    end

    Streamlit -->|internal Docker network| FastAPI

    subgraph async["Async layer"]
        CeleryWorker[Celery worker<br/>PandasAI · LIDA · sandbox]
        CeleryBeat[Celery Beat<br/>scheduled cleanup]
    end

    QuerySvc -->|enqueue task| CeleryWorker
    DatasetSvc -->|enqueue parse| CeleryWorker

    subgraph storage["Storage"]
        DFCache[(In-proc LRU<br/>DFCache)]
        MinIO[(MinIO<br/>raw files)]
        Redis[(Redis<br/>public key · broker · results)]
        Postgres[(PostgreSQL<br/>users · history · feedback)]
    end

    FastAPI -->|fetch public key| Redis
    DatasetSvc <-->|read/write df| DFCache
    DatasetSvc -->|store raw file| MinIO
    CeleryWorker <-->|df cache| DFCache
    CeleryWorker -->|reload on miss| MinIO
    CeleryWorker -->|write result| Redis
    CeleryWorker -->|save history| Postgres
    QuerySvc -->|poll result| Redis
    QuerySvc -->|enqueue via broker| Redis
    HistorySvc -->|read/write| Postgres
    FeedbackSvc -->|write| Postgres
    CeleryBeat -->|cleanup tasks| Redis

    subgraph external["External"]
        OpenAI([OpenAI API])
    end

    CeleryWorker -->|LLM call| OpenAI

```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11

### 1. Clone and configure
```bash
git clone https://github.com/haiyen11231/ai-data-assistant.git
cd ai-data-assistant
touch .env
```

Edit `.env` and add your OpenAI API key:
```bash
# Example
...
```

### 2. Start all services
```bash
docker-compose up --build
```

### 3. Open the app
- Frontend: ...
- Backend API docs: ...

## Local Setup (without Docker)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### Backend
```bash
cd backend
pip install -r requirements.txt
...
```

### Frontend
```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

## To Do List

- [x] System should be able to allow users to upload 1 or more xls/csv files
- [x] System should be able to display top N rows of the sheets uploaded
  - [x] System should be able to allow users to define N
  - [x] System should be able to allow users to select which sheet/file to preview
- [x] System should have some suggested prompts according to selected sheets
- [x] System should be able to allow users to ask questions about uploaded data
    - [x] System should be able to return responses in different formats (text/table/chart)
    - [ ] System should be able to handle mixed response types (text + table + chart)
    - [ ] System should be able to handle edge cases
        - [x] System should be able to handle simple question (simple sentence)
        - [ ] System should be able to handle complex question (compound sentence)
        - [x] System should be able to handle no result / empty response
        - [ ] System should be able to handle invalid queries
- [ ] System should have some suggested prompts according to selected sheets
to get answers from the CSVs/Excels. User can ask questions for any of the sheets/ CSVs
- [x] System should be able to support querying one sheet at a time
- [ ] System should be able to support querying multiple sheets/files (future improvement)
    - [ ] System should be able to define relationships or joins between datasets
    - [ ] System should be able to allow users to select multiple datasets
    - [ ] Fix: summary not consistent through different dataset in format, some parsed in table, some in text string
    - [ ] System should be able to store chat history in terms of files

- [ ] System should be able to keep a history of prompts that users can re-use when needed.
- [ ] System should be able to store chat history per session per file/sheet
- [ ] System should be able to link chat history with uploaded files
- [ ] System should be able to allow users to reuse previous prompts
- [ ] System should be able to display chat history in the UI
- [ ] System should be able to allow users to provide feedback on responses

## Further Improvements

- **Kubernetes:** swap Docker Compose for K8s when horizontal scaling is needed

## References

- 
