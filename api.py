import os
import sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

# Add the parent directory to sys.path so we can import 'agent'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.graph import app

# Load environment variables
load_dotenv()

app_api = FastAPI(title="Hackstorm AI Bridge API")

class ChatRequest(BaseModel):
    message: str
    user_id: str

class ChatResponse(BaseModel):
    response: str
    intent: Optional[str] = None
    sql_query: Optional[str] = None
    error: Optional[str] = None

@app_api.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        # Prepare the state for LangGraph
        new_message = HumanMessage(content=request.message)
        state = {
            "messages": [new_message],
            "question": request.message,
        }
        
        # Configuration for thread/user persistence
        config = {
            "configurable": {
                "thread_id": request.user_id
            }
        }
        
        # Invoke the AI graph
        result = app.invoke(state, config=config)
        
        # Extract results
        return ChatResponse(
            response=result["messages"][-1].content,
            intent=result.get("intent"),
            sql_query=result.get("sql_query"),
            error=result.get("error")
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app_api, host="0.0.0.0", port=8000)
