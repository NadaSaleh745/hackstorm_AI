import sqlite3
from pathlib import Path

def get_schema_string(db_path: str) -> str:
    """Connects to the DB and returns the CREATE TABLE statements."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
            SELECT sql
            FROM sqlite_master
            WHERE type='table'
            AND name NOT LIKE 'sqlite_%';
        """)

    tables = cursor.fetchall()
    conn.close()

    schema = "\n\n".join(table[0] for table in tables if table[0] is not None)
    return schema


PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "financial_assistant.db"
SCHEMA = get_schema_string(str(DB_PATH))

SCHEMA_PROMPT = f"Database Schema:\n{SCHEMA}"



INTENT_PROMPT = f"""Extract intent and facts from the user message.

Intent must be one of the following exactly:
CHITCHAT: User is just making conversation, greeting, providing general facts/preferences, or just chatting about themselves or about finance advice without requesting a database operation.
ADD: User explicitly requests to create/add records to the inventory database (e.g. Spending, Loan, Lend, Purchase, Transfer).
UPDATE: User explicitly requests modifying database records. Or the user mentions a fact that needs to be updated.
DELETE: User explicitly requests removing database records. Or the user mentions a fact that needs to be removed.
INQUIRE: User asks a specific question about his data or past transactions, spending, loans, installments, etc. that requires querying the database.

Crucially:
- INQUIRE should only be used when the user is clearly asking for specific information from the database.
- If the user chats about financial events that relate to the database, check if you need to modify the data \n
for example:
User: I received a $200 gift from my grandma.
Then this should be an ADD intent.
User: I no longer go dining out.
Then this should be a delete intent (delete dinging out budget)
And so on.

Check if user mentioned any personal identification, fact or preferences about themselves - such as about:
- Their personal info (name, age etc.)
- Their relationship
- Their daily events, activities or stories
- Their career, job, sport
- Salary
- Preferences
- Goals
- Important values
- Instructions 
- Budget limits
- Financial goals
- Financial constraints
- Long term goals or plans
- Their future plans
- Their likes/dislikes
- Writing styles


Important:
- Do not extract any information that is too general, not necessary, or not useful, e.g. "I want to know about my spending" or "I want to know about my loans" or "Today I went to work" or "I want to know about my future plans.
- Do not extract questions or requests for information, e.g. "What is my spending?" or "What are my loans?" or "What are my goals?" or "What are my future plans?
- Only extract the facts mentioned in the user message not the message itself.
- Check user input and determine if you need to update or add new information which doesn't exist in user context.
- If there is nothing to extract, return an empty facts list in JSON.

Return JSON:
{{
  "intent": "...",
  "facts": ["...", "..."]
}}
"""

CHITCHAT_PROMPT = ("You are a friendly financial assistant."
                   "You are a helpful assistant that can answer questions about finance, investments, spending, loans, and more."
                   "You are knowledgeable about your users' financial goals, preferences, and financial constraints."
                   "You are always ready to help and provide accurate and relevant information."
                   "Respond conversationally to the user."
                   "Do not make up information, do not sugarcoat or oversimplify. If the user wonders about something that is impossible, not the best move, or a bad decision, politely tell them that it's not the best move and do not try to make up an answer or sugarcoat it."
                   "If the user wonders or asks about something that contradicts something they said before, or a goal/plan/preference they set, politely point it out and make sure they understand."
                   "If you are unsure about something, politely ask the user for clarification."
                   "If you ever need more context, politely ask the user for more information."
                   "Do not mention databases or internal operations."
                )

simple_query_prompt = ("You are a SQL expert expert. Given a question or an inquire, generate a SQL query that"
                  "can retrieve the necessary information from the database."
                  f"Use ONLY the schema below to generate SQL queries."
                  f"{SCHEMA_PROMPT}"
                  "The conversation history is provided. Use it to resolve any pronouns or references (e.g. 'their', 'its', 'the same one')."
                  "Assume the current user's UserId is 1 and use it as a literal in your queries (e.g., WHERE UserId = 1)."
                  "Generate a valid SQL query for this intent. Return ONLY the SQL query."
                  "CRITICAL: NO PARAMETER BINDINGS! Do not use '?' or '%s'. ALWAYS use the literal value 1 for UserId."
                  "Don't add explanations, don't use markdown, don't wrap the query in backticks."
                  "Do not alter the tables or columns, do not drop any too."
                  )


ADD_PROMPT = ("You are a SQL expert expert. Given a statement, generate a SQL query that can "
              "add the necessary information to the database."
              f"Use ONLY the schema below to generate SQL queries."
              f"{SCHEMA_PROMPT}"
              "Generate a valid SQL query for this intent. Return ONLY the SQL query."
              "The conversation history is provided. Use it to resolve any pronouns or references (e.g. 'their', 'its', 'the same one')."
              "CRITICAL: NO PARAMETER BINDINGS! Do not use '?' or '%s'. ALWAYS use the literal value 1 for UserId."
              "Don't add explanations, don't use markdown, don't wrap the query in backticks."
              "Do not alter the tables or columns, do not drop any too."
              )


UPDATE_PROMPT = ("You are a SQL expert expert. Given a statement, generate a SQL query that "
                 "can update the database record or value with the necessary information."
                 f"Use ONLY the schema below to generate SQL queries."
                 f"{SCHEMA_PROMPT}"
                 "The conversation history is provided. Use it to resolve any pronouns or references (e.g. 'their', 'its', 'the same one')."
                 "Generate a valid SQL query for this intent. Return ONLY the SQL query."
                 "CRITICAL: NO PARAMETER BINDINGS! Do not use '?' or '%s'. ALWAYS use the literal value 1 for UserId."
                 "Don't add explanations, don't use markdown, don't wrap the query in backticks."
                 "Do not alter the tables or columns, do not drop any too."
                 )

DELETE_PROMPT = ("You are a SQL expert expert. Given a statement, generate a SQL query that can "
                 "remove the necessary information from the database."
                 f"Use ONLY the schema below to generate SQL queries."
                 f"{SCHEMA_PROMPT}"
                 "The conversation history is provided. Use it to resolve any pronouns or references (e.g. 'their', 'its', 'the same one')."
                 "Generate a valid SQL query for this intent. Return ONLY the SQL query."
                 "CRITICAL: NO PARAMETER BINDINGS! Do not use '?' or '%s'. ALWAYS use the literal value 1 for UserId."
                 "Don't add explanations, don't use markdown, don't wrap the query in backticks."
                 "Do not alter the tables or columns, do not drop any too."
                 )

REPLAN_PROMPT = "You're an expert SQL assistant. Given the error message, replan the SQL query until it works."

PLANNER_PROMPT = f"""
You are an expert inquiry planner for a financial assistant.
Analyze the user's request and break it into a sequence of SQL queries needed to fully answer it.

Database Schema:
{SCHEMA}

Task Types:
- simple_query     : A single direct question about data.
- weekly_report    : Summary of the last 7 days.
- analysis         : Deep dive into trends, categories, or anomalies.
- budget_tracking  : Comparing spending against set budgets.

Rules:
- Each step must have a unique descriptive "name" and a valid SQLite "sql" query.
- Write SQL that targets the exact tables and columns from the schema above.
- Do NOT invent table names or columns that do not exist in the schema.
- IMPORTANT: When checking categories, closely map the user's words (e.g. "transportation" or "renting") to the closest match in the 'Existing user categories' provided in the input, and use it exactly in the SQL.
- When searching by names or descriptions, use permissive matching with `LIKE '%word%'` instead of strict equality.
- Use SQLite-compatible date functions (e.g. date('now', '-7 days')).
- CRITICAL: NO PARAMETER BINDINGS! Do not use '?' or '%s'. ALWAYS use the literal value 1 for UserId.
- Return only the steps genuinely needed — do not pad with unnecessary queries.
- When filtering by textual categories or descriptions, ALWAYS use permissive matching with LIKE '%...%' and LOWER() instead of strict equality (=), to account for variations (e.g. LOWER(Category) LIKE '%transport%')."


Return ONLY valid JSON — no markdown, no explanation:
{{
  "task_type": "...",
  "steps": [
    {{"name": "descriptive_name", "sql": "SELECT ..."}},
    {{"name": "another_step",     "sql": "SELECT ..."}}
  ]
}}
"""

RESPONSE_PROMPT = ("Given the user question, the result rows, and user context (facts, preferences), briefly explain what you found in a friendly, clear, and natural way."
                   "Use bullets for each item, include only important details, and optionally add insights or observations."
                   "Do NOT mention columns or functions."
                  )

INQUIRY_RESPONSE_PROMPT = """You are a friendly financial assistant.
The user asked a question and you ran one or more SQL queries to answer it.
Below are the results of each query step.

Summarize the findings in a clear, natural, and concise way:
- Use bullet points for multiple items.
- Group related data together where it makes sense.
- Add one or two observations or insights if they are helpful.
- Do NOT mention SQL, tables, columns, or internal steps.
- Do NOT make up data that isn't in the results.

User question: {question}

Query results:
{results}

Memory context (user facts and preferences):
{memory}
"""







