# SET FOREIGN_KEY_CHECKS = 0;

# TRUNCATE TABLE password_reset_tokens;
# TRUNCATE TABLE query_provenance;
# TRUNCATE TABLE embeddings_metadata;
# TRUNCATE TABLE document_chunks;
# TRUNCATE TABLE ingestion_jobs;
# TRUNCATE TABLE documents;
# TRUNCATE TABLE messages;
# TRUNCATE TABLE threads;
# TRUNCATE TABLE user_tools;
# TRUNCATE TABLE auth_tokens;
# TRUNCATE TABLE user_settings;
# TRUNCATE TABLE expenses;
# TRUNCATE TABLE expense_subcategories;
# TRUNCATE TABLE expense_categories;
# TRUNCATE TABLE tools;
# TRUNCATE TABLE users;

# SET FOREIGN_KEY_CHECKS = 1;



# # PowerShell – run from project root
# Get-ChildItem -Path . -Include *.pyc -Recurse | Remove-Item -Force
# Get-ChildItem -Path . -Include *.pyo -Recurse | Remove-Item -Force
# Get-ChildItem -Path . -Directory -Name __pycache__ -Recurse | Remove-Item -Recurse -Force
# rm uploads -Recurse -Force
# rm faiss_indexes -Recurse -Force


# exec into the container
# docker exec -it <redis-container-name> redis-cli
# FLUSHALL