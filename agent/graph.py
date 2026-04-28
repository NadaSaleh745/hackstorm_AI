import os
from langchain_openai import OpenAIEmbeddings
from langgraph.graph import StateGraph, END
from hackstorm_AI.agent.state import AgentState
from hackstorm_AI.agent.nodes import (
    sql_executor_node, sql_corrector_node,
    responder_node, intent_node, chitchat_node,
    inquiry_planner, inquire_node, inquiry_responder_node, add_node,
    update_node, delete_node
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.base import IndexConfig
from langgraph.store.redis import RedisStore
from langgraph.checkpoint.redis import RedisSaver


from dotenv import load_dotenv

load_dotenv()

REDIS_URI = os.getenv("REDIS_URI")

index_config: IndexConfig = {
    "dims": 1536,
    "embed": OpenAIEmbeddings(model="text-embedding-3-small"),
    "ann_index_config": {
        "vector_type": "vector",
    },
    "distance_type": "cosine",
}

checkpointer_cm = RedisSaver.from_conn_string(REDIS_URI)
checkpointer = checkpointer_cm.__enter__()
checkpointer.setup()

redis_store_cm = RedisStore.from_conn_string(REDIS_URI, index=index_config)
redis_store = redis_store_cm.__enter__()
redis_store.setup()

def executor_should_continue(state: AgentState):
    if state.get("error"):
        return "corrector"
    else:
        return "responder"


def intent_should_continue(state: AgentState):
    intent = state["intent"]
    if intent == "CHITCHAT":
        return "chitchat"
    elif intent == "INQUIRE":
        return "inquiry_planner"
    elif intent == "ADD":
        return "add"
    elif intent == "UPDATE":
        return "update"
    elif intent == "DELETE":
        return "delete"
    else:
        return "chitchat"

workflow = StateGraph(AgentState)

# Existing nodes
workflow.add_node("intent",    intent_node)
workflow.add_node("chitchat",  chitchat_node)
workflow.add_node("executor",  sql_executor_node)
workflow.add_node("corrector", sql_corrector_node)
workflow.add_node("responder", responder_node)
workflow.add_node("add", add_node)
workflow.add_node("update", update_node)
workflow.add_node("delete", delete_node)

# Inquiry sub-graph nodes
workflow.add_node("inquiry_planner",   inquiry_planner)
workflow.add_node("inquire_node",       inquire_node)
workflow.add_node("inquiry_responder", inquiry_responder_node)

# Entry point
workflow.set_entry_point("intent")

# Intent routing
workflow.add_conditional_edges(
    "intent",
    intent_should_continue,
    {
        "chitchat": "chitchat",
        "add": "add",
        "update": "update",
        "delete": "delete",
        "inquiry_planner": "inquiry_planner",
    },
)

workflow.add_edge("add", "executor")
workflow.add_edge("update", "executor")
workflow.add_edge("delete", "executor")

workflow.add_conditional_edges(
    "executor",
    executor_should_continue,
    {"corrector": "corrector", "responder": "responder"},
)
workflow.add_edge("corrector", "executor")
workflow.add_edge("responder", END)

# Chitchat path
workflow.add_edge("chitchat", END)

# Inquiry path
workflow.add_edge("inquiry_planner",   "inquire_node")
workflow.add_edge("inquire_node",       "inquiry_responder")
workflow.add_edge("inquiry_responder", END)

memory = MemorySaver()
app = workflow.compile(checkpointer=checkpointer, store=redis_store)

print("GRAPH COMPILED")