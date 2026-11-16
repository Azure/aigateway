"""Triage support tickets with a Jev decision model through AI Gateway.

Reads AI_GATEWAY_URL, AI_GATEWAY_API_KEY, and AI_GATEWAY_MODEL (the alias, ticket-triage by default). Each ticket
gets three typed answers: is it urgent (noul), which team owns it (choice), and how frustrated the customer is (score).

    python infra/triage.py             # triage three sample tickets
    python infra/triage.py --burst 8   # send 8 decisions in a row to see the alias's request rate limit
"""

import argparse
import os
import time

from typesafe_sdk import Choice, Noul, RetryPolicy, Score, TypeSafeAPIError, TypeSafeClient

TICKETS = [
    {
        "subject": "Charged twice for invoice INV-2291",
        "message": "Hi, my card was charged twice for invoice INV-2291 this morning. Please refund the duplicate "
        "today: I need that money for rent tomorrow. This is the second time it has happened!",
        "plan": "Pro",
    },
    {
        "subject": "Webhook calls fail with 500 since the last release",
        "message": "Since yesterday's release every webhook delivery to our endpoint fails with a 500 and our "
        "orders are stuck. Nothing changed on our side. Production is down, please escalate.",
        "plan": "Enterprise",
    },
    {
        "subject": "Add a second admin",
        "message": "Hello, when you get a chance, could you tell me how to give my colleague admin rights on our "
        "workspace? No rush, thanks!",
        "plan": "Free",
    },
]

# The same questions for every ticket. Jev answers each one with a typed value and a probability.
QUESTIONS = {
    "urgent": Noul(instructions="Does the customer need an answer today?"),
    "team": Choice(
        instructions="Which support team should own this ticket?",
        criteria={
            "billing": "Payments, invoices, refunds, or subscription changes",
            "technical": "Bugs, errors, outages, or integration problems",
            "account": "Sign-in, users, permissions, or account settings",
        },
    ),
    "frustration": Score(
        instructions="How frustrated is the customer?",
        criteria=["Calm, just stating facts", "Frustrated but civil", "Very angry, strong language"],
    ),
}


ALIAS = os.environ.get("AI_GATEWAY_MODEL", "ticket-triage")


def make_client() -> TypeSafeClient:
    # The SDK's base URL is the gateway's System One base: it adds /v1/systemone to it. The gateway takes only
    # uncompressed JSON, so turn compression off. No retries, so that a 429 from the gateway shows up right away.
    return TypeSafeClient(
        api_key=os.environ["AI_GATEWAY_API_KEY"],
        base_url=os.environ["AI_GATEWAY_URL"].rstrip("/") + "/default/models/typesafe",
        model=ALIAS,
        compression=False,
        retry=RetryPolicy(max_retries=0),
    )


def triage(client: TypeSafeClient) -> None:
    print(f"{'Ticket':<36} {'Urgent':>6}  {'Team':<16}  {'Frustration':<28} {'ms':>5}  Tokens")
    for ticket in TICKETS:
        start = time.perf_counter()
        result = client.system_one(state={"ticket": ticket}, questions=QUESTIONS)
        ms = (time.perf_counter() - start) * 1000
        urgent = result.nouls["urgent"].noul
        team = result.choices["team"]
        frustration = result.scores["frustration"]
        level = frustration.legend[round(frustration.score)]
        print(
            f"{ticket['subject'][:36]:<36} {urgent:>6.2f}  {team.choice:<9} ({team.confidence:.2f})  "
            f"{frustration.score:.1f} {level:<24} {ms:>5.0f}  "
            f"{result.usage.input_tokens} in, {result.usage.output_tokens} out"
        )
    print(f"✅ {len(TICKETS)} tickets triaged by {result.model} through the alias {ALIAS}")


def burst(client: TypeSafeClient, count: int) -> None:
    ticket = TICKETS[0]
    for i in range(1, count + 1):
        try:
            result = client.system_one(state={"ticket": ticket}, questions={"urgent": QUESTIONS["urgent"]})
            print(f"#{i}: 200, urgent = {result.nouls['urgent'].noul:.2f}")
        except TypeSafeAPIError as err:
            print(f"#{i}: {err.status}, Retry-After {err.headers.get('retry-after')} s: {err.body}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--burst", type=int, metavar="N", help="send N decision requests in a row")
    args = parser.parse_args()
    with make_client() as jev:
        burst(jev, args.burst) if args.burst else triage(jev)
