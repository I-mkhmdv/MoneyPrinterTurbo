"""Build a personal-brand content plan and a cli.py batch manifest.

    uv run python brand_plan.py --profile brand.toml
    uv run python brand_plan.py --profile brand.toml --topics my_topics.txt
    uv run python cli.py --batch-file storage/brand/tasks.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from loguru import logger


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a brand content plan and a batch manifest for cli.py."
    )
    parser.add_argument("--profile", default="brand.toml", help="brand profile TOML")
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="number of videos (default: [brand].posts_per_week)",
    )
    parser.add_argument(
        "--topics",
        default="",
        help="text file with one topic per line; skips LLM planning",
    )
    parser.add_argument(
        "--out-dir", default=os.path.join("storage", "brand"), help="output directory"
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    from app.services import brand

    try:
        profile = brand.load_profile(args.profile)
    except (OSError, ValueError) as exc:
        logger.error(f"cannot load brand profile {args.profile}: {exc}")
        return 2

    if args.topics:
        with open(args.topics, encoding="utf-8") as f:
            topics = brand.topics_from_lines(profile, f.readlines())
        if args.count:
            topics = topics[: args.count]
        if not topics:
            logger.error(f"no topics found in {args.topics}")
            return 2
    else:
        count = args.count or profile["brand"]["posts_per_week"]
        try:
            topics = brand.generate_plan(profile, count)
        except ValueError as exc:
            logger.error(str(exc))
            return 1

    os.makedirs(args.out_dir, exist_ok=True)
    manifest_path = os.path.join(args.out_dir, "tasks.jsonl")
    plan_path = os.path.join(args.out_dir, "plan.md")
    with open(manifest_path, "w", encoding="utf-8") as f:
        for entry in brand.plan_to_manifest(profile, topics):
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    with open(plan_path, "w", encoding="utf-8") as f:
        f.write(brand.plan_to_markdown(profile, topics))

    print(brand.plan_to_markdown(profile, topics))
    print(f"plan: {plan_path}")
    print(f"manifest: {manifest_path}")
    print(f"next: uv run python cli.py --batch-file {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
