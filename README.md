# Advanced Chatbot Backend (FastAPI)

**Author:** HiteshKumarMeghwar  
**Last Updated:** December 2025

---

## Overview

This project is a **multi-functional AI assistant backend** built with **FastAPI**, designed to support advanced RAG (Retrieval-Augmented Generation), multi-tool agentic capabilities, and seamless integration with **LangChain** and **LangGraph**. It provides a full-stack-ready API layer for powering intelligent chat applications with multi-document support, automatic tool selection, and user management.

Key highlights of this backend:

- **LangGraph Nodes & Edges System:** Dynamically manages knowledge graph for conversation context and reasoning.  
- **Automatic Tool Calling System:** Intelligent routing to local and remote tools (via FastMCP).  
- **RAG System:** Supports multi-document retrieval, embedding, and context-aware responses.  
- **User Tool Management:** Users can activate/deactivate tools individually from their accessible tool list.  
- **Multi-document Upload:** Supports chunked document ingestion, processing, and vectorization for RAG.  
- **Authentication & Authorization:** Secure user registration, login, password reset (Redis-backed), and token management.  
- **Rate Limiting & Security:** Protects endpoints with brute-force protection, IP blacklisting, and MFA support.  

---

## Table of Contents

- [Tech Stack](#tech-stack)  
- [Architecture](#architecture)  
- [Features](#features)  
- [Project Structure](#project-structure)  
- [Setup & Installation](#setup--installation)  
- [Usage](#usage)  
- [Contributing](#contributing)  
- [License](#license)  

---

## Tech Stack

- **Backend Framework:** FastAPI (Async)  
- **Database:** MySQL + SQLAlchemy ORM  
- **Migrations:** Alembic  
- **Caching / Token Management:** Redis  
- **Vector Database:** FAISS (local indexes)  
- **AI & LLM Tools:** LangChain, LangGraph  
- **MCP Client:** FastMCP (local and remote tools)  
- **Frontend (Compatible):** Next.js (Advanced UI)  
- **Logging & Monitoring:** Loguru, JSON logs  

---

## Architecture

The backend is designed for **scalability and modularity**:

1. **API Layer:** FastAPI routes organized by functional modules (`auth`, `threads`, `messages`, `documents`, `tools`, `chat`, `user_profile`).  
2. **Graph Layer:** LangGraph constructs nodes and edges representing conversation states, RAG retrieval, and tool actions.  
3. **Tool Layer:**  
   - Local tools executed via FastMCP (`stdio` transport)  
   - Remote tools via HTTP endpoints (`streamable_http`)  
4. **RAG Engine:** Handles multi-document search, embeddings, and AI-assisted answers.  
5. **User & Settings Management:**  
   - User profile and preferences stored in DB  
   - Tool access controlled per user (allowed/denied)  
6. **Security & Limits:**  
   - Redis-backed password reset tokens  
   - Rate-limiting via SlowAPI  
   - Brute-force login protection  
   - MFA enforcement and geo/device-based blocking  

---

## Features

### Authentication & User Management
- Registration, Login, Logout, and JWT-based authentication  
- Password reset via **email + Redis token**  
- Profile management with per-user preferences and tool access  

### Multi-Tool Agentic System
- Automatic tool routing for user queries  
- Tool discovery and registration via **FastMCP client**  
- Supports both **local** (stdio transport) and **remote** (HTTP transport) tools  
- Per-user activation/inactivation of tools  

### LangGraph & LangChain Integration
- Nodes & edges system to track conversation context  
- Automatic tool calls based on graph reasoning  
- Dynamic updates to graph state per conversation  

### RAG System
- Multi-document ingestion and chunking  
- Vector embeddings stored in FAISS indexes  
- Context-aware retrieval across documents  
- Query provenance tracking  

### Document Management
- Upload multiple file types (PDF, TXT, etc.)  
- Automatic chunking & embedding generation  
- Status tracking: `uploaded`, `processing`, `indexed`, `failed`  

### Rate Limiting & Security
- IP banning and blacklist support  
- Login brute-force protection  
- MFA enforcement for sensitive actions  
- Geo-based and device fingerprinting rules  

---

## Project Structure

```text
Advanced-ChatBot/
│
├─ api/                  # API routes for all modules
├─ core/                 # Configs, database connection, utils
├─ db/                   # SQLAlchemy models & database setup
├─ graphs/               # LangGraph node/edge building
├─ services/             # Redis, FAISS, Limiting, Tools
├─ MCP/                  # FastMCP client config (local & remote tools)
├─ tools/                # Local tool implementations
├─ uploads/              # Uploaded user files
├─ worker/               # Background processing & ingestion
├─ faiss_indexes/        # Saved FAISS indexes per document set
├─ tests/                # Unit & integration tests
├─ main.py               # FastAPI app entrypoint
├─ requirements.txt      # Python dependencies
├─ docker-compose.yml    # Optional container setup
├─ Dockerfile            # Production-ready Dockerfile
├─ logs.json             # Structured logs via Loguru
```

# Setup & Installation

## 1. Clone Repo

- git clone https://github.com/HiteshKumarMeghwar/Advanced-ChatBot.git
- cd Advanced-ChatBot

## 2. Install Dependencies

- python -m venv venv
- source venv/bin/activate      # Linux / Mac
- venv\Scripts\activate         # Windows
- pip install -r requirements.txt

## 3. Configure Environment

- Set REDIS_URL, DATABASE_URL, and FASTMCP_CONFIG in .env

## 4. Create DATABASE with name

  - chatbot_db

## 5. Run Database Migrations

- alembic upgrade head

## 6. Start Development Server

- uvicorn main:app --reload

## 7. On Browser 

- http://localhost:8000/docs

## License

- MIT License © HiteshKumarMeghwar



