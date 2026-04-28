import datetime
import json
import os
import uuid
from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from pymongo import MongoClient

from .state import AgentState
from .prompts import (
    REPLAN_PROMPT, RESPONSE_PROMPT, INTENT_PROMPT, get_schema_string,
    CHITCHAT_PROMPT, PLANNER_PROMPT, ADD_PROMPT, UPDATE_PROMPT,
    DELETE_PROMPT, INQUIRY_RESPONSE_PROMPT, DB_PATH, DB_NAME
)
from langgraph.store.base import BaseStore


load_dotenv()
llm = ChatOpenAI(model='gpt-5.4-mini', temperature=0)

def get_mongo_client():
    """Returns a MongoDB client connection."""
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    return MongoClient(mongo_uri)


def intent_node(state: AgentState, config: RunnableConfig, store: BaseStore):
    """Determines the intent of the user's question."""
    print("start intent")
    # Get the user ID from the config
    user_id = config["configurable"].get("thread_id", "default")
    memory_namespace = ("user_memories", user_id)

    # Get the last user message
    messages = state["messages"]
    last_user_message = messages[-1].content if messages else ""

    system_prompt = INTENT_PROMPT
    human_prompt = HumanMessage(content=f"""
    User request:
    {last_user_message}""")

    response = llm.invoke([system_prompt, human_prompt]).content

    # Parse the JSON response
    try:
        parsed = json.loads(response)
        intent = parsed.get("intent", "CHITCHAT").upper()
        facts = parsed.get("facts", [])
    except:
        intent = "CHITCHAT"
        facts = []

    print(intent)

    # Storing facts in the semantic memory
    for fact in facts:
        if isinstance(fact, str) and fact.strip():
            if len(fact) > 2000:
                print(f"Ignored massive fact: {len(fact)} characters")
                continue
            store.put(memory_namespace, str(uuid.uuid4()), {"fact": fact.strip()})

    # Showing all memory items (debugging purposes)
    all_items = store.search(memory_namespace, query="", limit=100)
    print("\n CURRENT MEMORY STATE:")

    for item in all_items:
        print(item.value)
    print("-" * 40)

    # Retrieving relevant facts from the semantic memory
    retrieved_items = store.search(memory_namespace, query=state["question"], limit=5)
    semantic_memory = []

    threshold = 0.3

    filtered = [
        item for item in retrieved_items
        if item.score is not None and item.score >= threshold
    ]

    for item in filtered:
        print(item.value)

    # if filtered:
    # Extract the 'fact' strings from the dictionary we stored them in
    semantic_memory = [item.value["fact"] for item in filtered]
    print(f"Retrieved {len(semantic_memory)} memories for context.")

    print("stop intent")

    return {
        "intent": intent,
        "semantic_memory": semantic_memory,
        "context_data": {},
        "sql_result": None,
        "error": None,
        "task_type": None,
        "steps": []
    }



def inquiry_planner(state: AgentState):
    """Plans the steps needed to answer the user's inquiry.
    The LLM receives the real DB schema and returns a list of steps where
    every step contains a descriptive name.
    No hardcoded step registry needed in the execution layer.
    """
    print("start inquiry_planner")

    system_prompt = SystemMessage(content=PLANNER_PROMPT)
    
    # Dynamically fetch existing user categories
    categories = []
    try:
        client = get_mongo_client()
        db = client[DB_NAME]

        # Get distinct categories from transactions and budgets
        txn_categories = db.transactions.distinct("category")
        budget_categories = db.budgets.distinct("category")
        categories = list(set(txn_categories + budget_categories))
        client.close()

    except Exception as e:
        print(f"Error fetching categories: {e}")

    cat_context = f"\n\nExisting user categories in database: {categories}" if categories else ""
    
    human_prompt = HumanMessage(content=f"User Request: {state['question']}{cat_context}")
    result = llm.invoke([system_prompt, human_prompt]).content

    try:
        # Strip markdown fences if the model wraps the JSON
        if "```json" in result:
            result = result.split("```json")[1].split("```")[0]
        elif "```" in result:
            result = result.split("```")[1].split("```")[0]

        parsed = json.loads(result.strip())
        task_type = parsed.get("task_type", "simple_query")
        # Each step is expected to be {"name": str, "query": str}
        steps: list[dict] = parsed.get("steps", [])

        # Defensive: skip any step that is missing its query field
        steps = [s for s in steps if isinstance(s, dict) and s.get("query")]

    except Exception as e:
        print(f"Error parsing planner response: {e}\nRaw output:\n{result}")
        task_type = "simple_query"
        steps = []

    print(f"Plan: {task_type} -> {[s.get('name') for s in steps]}")
    return {"task_type": task_type, "steps": steps}


def inquire_node(state: AgentState):
    """Executes every MongoDB step produced by inquiry_planner."""
    print("start inquire_node")

    # Run the planner inline if steps aren't in state yet
    if not state.get("steps"):
        plan = inquiry_planner(state)
        state = {**state, **plan}

    steps: list[dict] = state.get("steps", [])
    context_data: dict = {}

    for step in steps:
        name = step.get("name", "unnamed_step")
        query  = step.get("query", "")
        print(f"Executing step '{name}': {query}")
        context_data[name] = _execute_query(query)

    print("stop inquire_node")

    for item in state:
        print(f"{item}: {state[item]}")

    return {"context_data": context_data}


def _execute_query(query: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        print(f"Query error: {e}")
        return []


def _execute_query(query: dict):
    """Executes a MongoDB query."""
    try:
        client = get_mongo_client()
        db = client[DB_NAME]

        collection_name = query.get("collection")
        operation = query.get("operation", "find")

        if not collection_name:
            return []

        collection = db[collection_name]

        if operation == "find":
            filter_query = query.get("filter", {})
            projection = query.get("projection")
            limit = query.get("limit", 100)
            sort = query.get("sort")

            cursor = collection.find(filter_query, projection).limit(limit)
            if sort:
                cursor = cursor.sort(sort)

            result = list(cursor)
        elif operation == "aggregate":
            pipeline = query.get("pipeline", [])
            result = list(collection.aggregate(pipeline))
        elif operation == "count":
            filter_query = query.get("filter", {})
            result = [{"count": collection.count_documents(filter_query)}]
        else:
            result = []


        # Convert ObjectId to string for JSON serialization
        for doc in result:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])

        client.close()
        return result
    except Exception as e:
        print(f"Query error: {e}")
        return []


def inquiry_responder_node(state: AgentState):
    """Turns the multi-step context_data into a friendly natural-language reply."""
    context_data = state.get("context_data", {})
    semantic_memory = state.get("semantic_memory", [])

    # Format results so the LLM can read them easily
    results_text = ""
    for step_name, rows in context_data.items():
        results_text += f"\n[{step_name}]\n"
        if rows:
            results_text += "\n".join(str(row) for row in rows)
        else:
            results_text += "(no data)"

    memory_text = "\n".join(semantic_memory) if semantic_memory else "None"

    prompt = INQUIRY_RESPONSE_PROMPT.format(
        question=state["question"],
        results=results_text,
        memory=memory_text,
    )

    response = llm.invoke(prompt)
    return {
        "messages": [response],
    }


def add_node(state: AgentState):
    """Adds a new record to the database"""
    print("start add")
    semantic_memory = state.get("semantic_memory", [])
    # Build context from semantic memory
    context = ""
    if semantic_memory:
        context = f"\nRelevant facts from memory:\n" + "\n".join(semantic_memory)
    system_prompt = SystemMessage(content=ADD_PROMPT)
    last_user_message = state["messages"][-1].content

    human_prompt = HumanMessage(
        content=f"""
    User request:
    {last_user_message}

    {context}
    """
    )

    response = llm.invoke(
        [system_prompt, human_prompt],
        config={"max_tokens": 300}
    )
    print(response)
    print("stop add")
    return {
        "query": response.content.strip(),
    }


def update_node(state: AgentState):
    """Updates an existing record or value in the database"""
    semantic_memory = state.get("semantic_memory", [])
    # Build context from semantic memory
    context = ""
    if semantic_memory:
        context = f"\nRelevant facts from memory:\n" + "\n".join(semantic_memory)
    last_user_message = state["messages"][-1].content
    system_prompt = SystemMessage(content=UPDATE_PROMPT)
    human_prompt = HumanMessage(content=f"""
    User request:
    {last_user_message}

    {context}
    """)
    response = llm.invoke([system_prompt, human_prompt])
    return {
        "query": response.content.strip(),
    }


def delete_node(state: AgentState):
    """Delets a record or value from the databse"""
    semantic_memory = state.get("semantic_memory", [])
    # Build context from semantic memory
    context = ""
    if semantic_memory:
        context = f"\nRelevant facts from memory:\n" + "\n".join(semantic_memory)
    last_user_message = state["messages"][-1].content
    system_prompt = SystemMessage(content=DELETE_PROMPT)
    human_prompt = HumanMessage(content=f"""
    User request:
    {last_user_message}

    {context}
    """)
    response = llm.invoke([system_prompt, human_prompt])
    return {
        "query": response.content.strip(),
    }


def query_executor_node(state: AgentState):
    """Executes the NoSQL query against MongoDB."""
    query_str = state["query"]

    try:
        # Parse the query string to JSON
        if "```json" in query_str:
            query_str = query_str.split("```json")[1].split("```")[0]
        elif "```" in query_str:
            query_str = query_str.split("```")[1].split("```")[0]

        query = json.loads(query_str.strip())

        client = get_mongo_client()
        db = client[DB_NAME]

        collection_name = query.get("collection")
        operation = query.get("operation")

        if not collection_name or not operation:
            raise ValueError("Query must contain 'collection' and 'operation' fields")

        collection = db[collection_name]
        result = None

        if operation == "insert_one":
            document = query.get("document", {})
            # Add timestamp
            document["created_at"] = datetime.utcnow()
            result = collection.insert_one(document)
            result = {"inserted_id": str(result.inserted_id), "acknowledged": result.acknowledged}

        elif operation == "update_one":
            filter_query = query.get("filter", {})
            update = query.get("update", {})
            result = collection.update_one(filter_query, update)
            result = {"matched_count": result.matched_count, "modified_count": result.modified_count}

        elif operation == "delete_one":
            filter_query = query.get("filter", {})
            result = collection.delete_one(filter_query)
            result = {"deleted_count": result.deleted_count}

        elif operation == "find":
            filter_query = query.get("filter", {})
            result = list(collection.find(filter_query).limit(10))
            # Convert ObjectId to string
            for doc in result:
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])

        client.close()

        return {
            **state,
            "query_result": result,
            "error": None,
        }
    except Exception as e:
        print(f"Execution error: {e}")
        return {
            **state,
            "query_result": None,
            "error": str(e),
        }


def query_corrector_node(state: AgentState):
    """Refines the SQL if an error occurred."""
    error = state["error"]
    previous_query = state["query", ""]
    system_prompt = SystemMessage(content=REPLAN_PROMPT)
    human_prompt = HumanMessage(content=f"Previous query:\n{previous_query}\n\nError:\n{error}")
    response = llm.invoke([system_prompt, human_prompt])
    query = response.content.strip()
    return {
        **state,
        "query": query,
        "error": None,
    }


def chitchat_node(state: AgentState):
    """Generates a response based on the user's question."""
    question = state['question']
    system_prompt = SystemMessage(content=CHITCHAT_PROMPT)
    human_prompt = HumanMessage(content=question)
    response = llm.invoke([system_prompt, human_prompt])
    return {
        "messages": [response],
    }

def responder_node(state: AgentState):
    query_result = state["query_result"]
    system_prompt = SystemMessage(content=RESPONSE_PROMPT)
    human_prompt = HumanMessage(content=f"Query:{state['query']} Result Rows:{query_result}")
    response = llm.invoke([system_prompt, human_prompt])
    return {
        "messages": [response],
    }