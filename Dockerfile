# Run the fire-safety self-check prototype anywhere.
# Stage: prototype, data is synthetic. Python 3.12+ recommended.
FROM python:3.12-slim

# Run as an ordinary user with uid 1000 (required by Hugging Face Spaces, safer anywhere)
RUN useradd -m -u 1000 user
ENV HOME=/home/user
WORKDIR /app

# Dependencies first: this layer is cached while YAML bases are edited.
COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

# App + norm bases. app.py, core/ and the YAML files must stay in this folder.
COPY app.py ./
COPY core/ core/
# questionnaire, themes and PPR text fingerprints (core/loader.py reads data/)
COPY data/ data/
COPY checklist_525.yaml requirements_production.yaml \
     requirements_warehouse.yaml scores_production_draft.yaml scores_warehouse_draft.yaml ./
# Streamlit settings: no usage statistics, minimal toolbar
COPY .streamlit/ .streamlit/

USER user
EXPOSE 8501

# Answers live only in memory for the current session; nothing is written to disk.
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
