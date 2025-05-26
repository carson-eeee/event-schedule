from openai import OpenAI
from dotenv import load_dotenv
import os
import openai

# Load environment variables
load_dotenv()

# Initialize the OpenAI client
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url="https://api.chatanywhere.tech/v1"
)

def gpt_35_api(messages: list,model:str):
    """为提供的对话消息创建新的回答

    Args:
        messages (list): 完整的对话消息
    """
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages
        )
        return completion.choices[0].message.content
    except openai.AuthenticationError:
        return "Error: Invalid API key or authentication failure. Please check OPENAI_API_KEY in .env."
    except openai.RateLimitError:
        return "Error: Rate limit exceeded. Please try again later."
    except Exception as e:
        return f"Error: {str(e)}"