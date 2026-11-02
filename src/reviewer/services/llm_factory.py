from langchain_ollama import ChatOllama

from reviewer.config.settings import settings


def create_chat_model() ->ChatOllama:
    """ Create the local ollama chat model for CodeOps-AI"""
    return ChatOllama(
        model =settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0,
    )