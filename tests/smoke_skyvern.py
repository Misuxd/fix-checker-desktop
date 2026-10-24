"""Initialize the actual embedded Skyvern API and ephemeral DB without LLM calls."""
import asyncio

from skyvern import Skyvern
from skyvern.schemas.llm import LLMConfig


async def main():
    config = LLMConfig(model_name="openai/gpt-6-luna", required_env_vars=[],
                       supports_vision=True, add_assistant_prefix=False,
                       litellm_params={"api_key": "dummy-not-a-real-key"},
                       temperature=None, max_tokens=None, max_completion_tokens=8192,
                       reasoning_effort="none")
    client = Skyvern.local(llm_config=config, use_in_memory_db=True)
    try:
        runs = await client.get_runs_v2(page=1, page_size=1)
        assert isinstance(runs, list), type(runs)
        print("PASS: embedded Skyvern API, model configuration and in-memory database")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
