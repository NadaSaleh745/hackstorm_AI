from typing import TypedDict, Annotated, List, Union, Optional, Any
from langchain_core.messages import BaseMessage
import operator

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    question: str
    query: Optional[str]
    query_result: Optional[Union[List[dict], str, List[Any]]]
    error: Optional[str]
    intent: str
    task_type: Optional[str]
    steps: Optional[List[dict]]          # Each step: {"name": str, "query": dict}
    context_data: Optional[dict]         # Accumulated results from multi-step execution
    semantic_memory: Optional[List[str]] # Facts retrieved from long-term memory
