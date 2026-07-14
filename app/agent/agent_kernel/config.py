import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

load_dotenv()

#union llm
def init_model():
    llm=init_chat_model(os.getenv("LLM_MODEL"))
    return llm