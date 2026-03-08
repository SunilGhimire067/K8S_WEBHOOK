from openai import OpenAI

from .config import get_litellm_api_key, get_litellm_base_url, get_litellm_model


def get_openai_client() -> OpenAI:
    return OpenAI(base_url=get_litellm_base_url(), api_key=get_litellm_api_key())


def get_model() -> str:
    return get_litellm_model()
