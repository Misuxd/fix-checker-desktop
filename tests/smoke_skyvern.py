"""Verify the real Skyvern SDK authenticates with its own key; no network calls."""
import asyncio

import httpx
from skyvern import Skyvern


async def main():
    def respond(request):
        assert request.headers["x-api-key"] == "dummy-skyvern-key"
        assert request.url.host == "api.skyvern.com"
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = Skyvern(api_key="dummy-skyvern-key", httpx_client=http)
        try:
            runs = await client.get_runs_v2(page=1, page_size=1)
            assert isinstance(runs, list), type(runs)
            print("PASS: real Skyvern cloud SDK sends the Skyvern API key")
        finally:
            await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
