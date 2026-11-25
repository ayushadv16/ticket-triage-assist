
import json
import os

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

# Approximate USD rates per 1 million tokens.
INPUT_PRICE_PER_MILLION = float(
    os.getenv("GROQ_INPUT_PRICE_PER_MILLION", "0.075")
)
OUTPUT_PRICE_PER_MILLION = float(
    os.getenv("GROQ_OUTPUT_PRICE_PER_MILLION", "0.30")
)

PRIORITIES = ["Low", "Medium", "High", "Urgent"]


def analyse_ticket(subject, product_area, replies):
    """
    Analyse a ticket conversation using Groq.

    Returns summary, priority, token counts and estimated USD cost.
    """

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise ValueError("GROQ_API_KEY is missing from .env")

    client = Groq(api_key=api_key)

    conversation = "\n".join(
        f"{reply.sender_type}: {reply.message}"
        for reply in replies
    )

    if not conversation.strip():
        raise ValueError("No conversation available for AI analysis")

    system_prompt = """
You are a customer support ticket triage assistant.

Analyse the complete customer support conversation.

Return a concise summary and exactly one priority.

PRIORITY CLASSIFICATION:

LOW:
- General questions.
- How-to requests.
- Invoice or account information requests.
- No actual product malfunction.

MEDIUM:
- Minor or isolated bugs.
- Non-critical settings problems.
- Workarounds are available.
- Normal functionality is mostly unaffected.

HIGH:
- Important core functionality is unavailable.
- Payment failures affecting customers.
- Multiple customers affected by the same issue.
- Significant disruption to normal usage.

URGENT:
- Complete service outage affecting customers.
- Active security breach.
- Widespread critical failure.
- Severe ongoing financial or data-loss risk.

IMPORTANT CLASSIFICATION RULES:
- A complete platform outage affecting multiple customers must be Urgent.
- An isolated minor bug must not automatically be High.
- Consider actual impact, scope and available workarounds.
- Do not downgrade a widespread critical outage to Medium or High.
- Do not invent facts.
- Base the summary on the supplied conversation.
"""

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": (
                    f"Subject: {subject}\n"
                    f"Product Area: {product_area}\n\n"
                    f"Conversation:\n{conversation}\n\n"
                    "Analyse this ticket and return the required fields."
                )
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "ticket_analysis",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string"
                        },
                        "priority": {
                            "type": "string",
                            "enum": PRIORITIES
                        }
                    },
                    "required": ["summary", "priority"],
                    "additionalProperties": False
                }
            }
        },
        reasoning_effort="low",
        max_completion_tokens=1024
    )

    message = completion.choices[0].message
    raw_result = message.content

    if not raw_result:
        raise ValueError(
            f"Groq returned an empty response. "
            f"Finish reason: {completion.choices[0].finish_reason}"
        )

    try:
        result = json.loads(raw_result)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Groq returned invalid JSON: {raw_result}"
        ) from exc

    summary = result.get("summary")
    priority = result.get("priority")

    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("AI returned an invalid summary")

    if priority not in PRIORITIES:
        raise ValueError(f"AI returned invalid priority: {priority}")

    usage = completion.usage

    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0

    input_cost = (
        input_tokens / 1_000_000
    ) * INPUT_PRICE_PER_MILLION

    output_cost = (
        output_tokens / 1_000_000
    ) * OUTPUT_PRICE_PER_MILLION

    estimated_cost = input_cost + output_cost

    return {
        "summary": summary.strip(),
        "priority": priority,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost": estimated_cost
    }
