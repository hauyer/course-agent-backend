import os
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from app.services.llm_config_service import get_active_llm_runtime

load_dotenv()

#union llm
def init_model():
    runtime = get_active_llm_runtime()
    if runtime:
        kwargs = {
            "model_provider": runtime["provider"],
            "api_key": runtime["api_key"],
            "timeout": 60,
        }
        if runtime.get("base_url"):
            kwargs["base_url"] = runtime["base_url"]
        return init_chat_model(runtime["model_name"], **kwargs)
    return init_chat_model(os.getenv("LLM_MODEL"))
