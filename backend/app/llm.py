from langchain.chat_models import init_chat_model

from .config import settings


def make_llm():
    """Chat model for both agents."""
    extra = {"reasoning_effort": "low"}
    return init_chat_model(
        settings.llm_model,
        model_provider=settings.llm_provider,
        temperature=0,
        timeout=30,
        max_retries=2,
        **extra,
    )
