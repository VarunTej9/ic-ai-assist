

```markdown
# IC AI Assist - Architecture

## Architecture diagram

```text
User
 |
 v
Streamlit UI
 |
 v
Application Service
 |
 +--> Audit History Service
 |
 +--> Anomaly Detection Service
 |
 +--> Retrieval Service
 |       |
 |       +--> Synthetic Documents
 |       +--> Vector Store
 |
 +--> Recommendation Service
 |
 v
Local Storage
 |
 +--> SQLite or PostgreSQL
 +--> ChromaDB or pgvector
 +--> Evaluation Results
