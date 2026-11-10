# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.35"]
# ///
"""One tiny Bedrock Converse call to confirm model access (costs ~$0.001).

Usage:  uv run scripts/smoke_bedrock.py
Uses the default AWS credential chain (e.g. ~/.aws profile) and AWS_REGION (default us-east-1).
"""

from __future__ import annotations

import os
import sys
import time

import boto3
from botocore.config import Config

MODEL_ID = os.getenv("BEDROCK_SMOKE_MODEL", "us.anthropic.claude-sonnet-4-6")
REGION = os.getenv("AWS_REGION", "us-east-1")


def main() -> int:
    client = boto3.client(
        "bedrock-runtime",
        region_name=REGION,
        config=Config(
            connect_timeout=5, read_timeout=60, retries={"max_attempts": 3, "mode": "adaptive"}
        ),
    )
    started = time.perf_counter()
    resp = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": "Reply with exactly: OK"}]}],
        inferenceConfig={"maxTokens": 20, "temperature": 0},
    )
    ms = int((time.perf_counter() - started) * 1000)
    text = resp["output"]["message"]["content"][0]["text"].strip()
    usage = resp["usage"]
    print(f"model={MODEL_ID} region={REGION} latency={ms}ms stop={resp['stopReason']}")
    print(
        f"reply={text!r} input_tokens={usage['inputTokens']} output_tokens={usage['outputTokens']}"
    )
    return 0 if text else 1


if __name__ == "__main__":
    sys.exit(main())
