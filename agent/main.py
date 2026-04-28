import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from hackstorm_AI.agent.graph import app
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

config = {
    "configurable": {
        "thread_id": "temp_thread_002"
    }
}


def main():
    print("Hello, I'm your assistant! How can I help you today. (Type 'exit/quit' to quit.)\n")
    while True:
        user_input = input("You: ")
        if not user_input.strip():
            print("Please enter a valid question.")
            continue

        if user_input.strip().lower() in ["exit", "quit"]:
            break

        new_message = HumanMessage(content=user_input)

        state = {
            "messages": [new_message],
            "question": user_input,
        }

        result = app.invoke(state, config=config)

        print("\nBot:")
        print(result["messages"][-1].content)
        print("\n" + "-"*50 + "\n")

if __name__ == '__main__':
    main()