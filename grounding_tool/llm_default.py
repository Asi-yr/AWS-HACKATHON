from dotenv import load_dotenv
from google.genai import types
from google import genai
import llm_mcp
import os

def context_model(context: str, sysinstruct: str, rthoughts: bool, thinking_budget: int, model: str) -> str:
    load_dotenv()
    client = genai.Client(api_key=os.getenv("exclusive_genai_key"))
    config = types.GenerateContentConfig(
        system_instruction=sysinstruct,
        thinking_config=types.ThinkingConfig(
            include_thoughts=rthoughts,
            thinking_budget=thinking_budget
        )
    )

    response = client.models.generate_content(
        model=model,
        contents=context,
        config=config
    )

    # ---
    # uncomment to display thoughts.
    # ---
    # print("\n--- INTERNAL THOUGHTS ---")
    # found_thoughts = False
    # for part in response.candidates[0].content.parts:
    #     if part.thought:  # This checks if the part is a reasoning/thought part
    #         print(part.text)
    #         found_thoughts = True
    # if not found_thoughts:
    #     print("No thinking parts were returned for this prompt.")

    return response.text