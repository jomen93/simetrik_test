from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from src.agent.core import Agent
from src.agent.models import ConsolidatedReport
import os

import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

app = FastAPI(title="Incident Detection Agent")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

class AnalyzeRequest(BaseModel):
    date: str
    mode: str = "agentic"

@app.post("/analyze", response_model=ConsolidatedReport)
def analyze(request: AnalyzeRequest):
    """
    Analyze data for a specific date with optional agentic mode.
    """
    try:
        # Initialize agent with request config
        # Use environment variable for API key
        api_key = os.getenv("OPENAI_API_KEY")
        
        agent = Agent(
            data_dir=DATA_DIR,
            mode=request.mode,
            llm_provider="openai",
            llm_api_key=api_key,
            llm_model="gpt-4o-mini"
        )
        
        report = agent.run(request.date)
        return report
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"message": "Incident Detection Agent is running. Use POST /analyze to generate a report."}
