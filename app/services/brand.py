"""Personal-brand content plans for batch video generation.

A brand profile (see brand.example.toml) describes the niche, audience, tone
and content rubrics. From it this module builds a content plan (one topic per
video) and turns the plan into a cli.py --batch-file manifest whose scripts are
written in the brand's voice.
"""
import json
import re
from typing import Any, Callable, List, Optional

import toml
from loguru import logger

from app.models.schema import VideoAspect

MAX_PLAN_COUNT = 30
# VideoParams.video_script_prompt is capped at 2000 characters; the brand
# brief has to fit alongside the per-topic hook.
MAX_SCRIPT_PROMPT_LENGTH = 2000
MAX_EXAMPLE_TEXT_LENGTH = 400

DEFAULT_VIDEO = {
    "voice_name": "ru-RU-SvetlanaNeural-Female",
    "video_aspect": VideoAspect.portrait.value,
    "paragraph_number": 1,
    "font_name": "MicrosoftYaHeiBold.ttc",
    "video_source": "pexels",
}
_VIDEO_KEYS = tuple(DEFAULT_VIDEO)


def load_profile(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = toml.load(f)
    return normalize_profile(data)


def normalize_profile(data: dict) -> dict:
    brand = dict(data.get("brand") or {})
    for key in ("niche", "audience", "tone"):
        if not str(brand.get(key, "")).strip():
            raise ValueError(f"brand profile is missing [brand].{key}")
    brand.setdefault("name", "")
    brand.setdefault("language", "ru-RU")
    brand["posts_per_week"] = int(brand.get("posts_per_week") or 3)
    brand["stop_words"] = [str(w) for w in brand.get("stop_words") or []]
    brand["example_texts"] = [str(t) for t in brand.get("example_texts") or []]

    rubrics = []
    for item in data.get("rubrics") or []:
        name = str(item.get("name", "")).strip()
        if name:
            rubrics.append(
                {"name": name, "description": str(item.get("description", "")).strip()}
            )
    if not rubrics:
        rubrics = [{"name": "Польза", "description": "практический совет"}]

    video = dict(DEFAULT_VIDEO)
    video.update(
        {k: v for k, v in (data.get("video") or {}).items() if k in _VIDEO_KEYS}
    )
    return {"brand": brand, "rubrics": rubrics, "video": video}


def build_brand_brief(profile: dict) -> str:
    """Voice instructions appended to every script prompt of the brand."""
    brand = profile["brand"]
    lines = ["Пиши сценарий для личного бренда."]
    if brand["name"]:
        lines.append(f"- Автор и голос: {brand['name']}, говорит от первого лица.")
    lines.append(f"- Ниша: {brand['niche']}")
    lines.append(f"- Аудитория: {brand['audience']}")
    lines.append(f"- Тон: {brand['tone']}")
    lines.append(
        "- Первая фраза должна цеплять за 3 секунды; в конце один короткий призыв "
        "(сохранить, написать в комментариях или подписаться)."
    )
    if brand["stop_words"]:
        lines.append(f"- Не используй: {', '.join(brand['stop_words'])}")
    for text in brand["example_texts"]:
        lines.append(f"- Пример голоса автора: {text[:MAX_EXAMPLE_TEXT_LENGTH]}")
    return "\n".join(lines)


def build_script_prompt(profile: dict, topic: dict) -> str:
    parts = [build_brand_brief(profile)]
    if topic.get("rubric"):
        parts.append(f"Рубрика: {topic['rubric']}")
    if topic.get("hook"):
        parts.append(f"Идея захода: {topic['hook']}")
    prompt = "\n".join(parts)
    if len(prompt) > MAX_SCRIPT_PROMPT_LENGTH:
        logger.warning("brand script prompt is too long and will be truncated")
        prompt = prompt[:MAX_SCRIPT_PROMPT_LENGTH]
    return prompt


def build_plan_prompt(profile: dict, count: int) -> str:
    brand = profile["brand"]
    rubrics = "\n".join(
        f"- {r['name']}: {r['description']}" if r["description"] else f"- {r['name']}"
        for r in profile["rubrics"]
    )
    return f"""Ты контент-стратег личного бренда. Составь контент-план из {count} коротких вертикальных видео (30–60 секунд).

Ниша: {brand['niche']}
Аудитория: {brand['audience']}
Тон: {brand['tone']}
Язык: {brand['language']}

Рубрики (чередуй их по очереди):
{rubrics}

Темы должны быть конкретными, без повторов, и такими, чтобы по каждой хватило одного ролика.

Верни только JSON-массив без пояснений, по одному объекту на видео:
[{{"rubric": "название рубрики", "subject": "тема ролика", "hook": "первая фраза, которая цепляет"}}]"""


def _parse_plan(response: str, count: int) -> List[dict]:
    text = (response or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            raise ValueError("content plan response is not a JSON array")
        data = json.loads(match.group(0))
    if not isinstance(data, list):
        raise ValueError("content plan response is not a JSON array")

    topics = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject", "")).strip()
        if not subject:
            continue
        topics.append(
            {
                "rubric": str(item.get("rubric", "")).strip(),
                "subject": subject,
                "hook": str(item.get("hook", "")).strip(),
            }
        )
    if not topics:
        raise ValueError("content plan response contains no topics")
    return topics[:count]


def generate_plan(
    profile: dict,
    count: int,
    generate: Optional[Callable[[str], str]] = None,
    retries: int = 3,
) -> List[dict]:
    if count < 1 or count > MAX_PLAN_COUNT:
        raise ValueError(f"count must be between 1 and {MAX_PLAN_COUNT}")
    if generate is None:
        from app.services.llm import _generate_response as generate

    prompt = build_plan_prompt(profile, count)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = generate(prompt)
            if isinstance(response, str) and response.startswith("Error: "):
                raise ValueError(response)
            return _parse_plan(response, count)
        except Exception as exc:
            last_error = exc
            logger.warning(f"failed to generate content plan ({attempt + 1}): {exc}")
    raise ValueError(f"failed to generate content plan: {last_error}")


def topics_from_lines(profile: dict, lines: List[str]) -> List[dict]:
    """Use the owner's own topics; rubrics are assigned in rotation."""
    rubrics = profile["rubrics"]
    subjects = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    return [
        {"rubric": rubrics[i % len(rubrics)]["name"], "subject": s, "hook": ""}
        for i, s in enumerate(subjects)
    ]


def plan_to_manifest(profile: dict, topics: List[dict]) -> List[dict[str, Any]]:
    video = profile["video"]
    return [
        {
            "video_subject": topic["subject"],
            "video_script_prompt": build_script_prompt(profile, topic),
            "video_language": profile["brand"]["language"],
            **video,
        }
        for topic in topics
    ]


def plan_to_markdown(profile: dict, topics: List[dict]) -> str:
    title = profile["brand"]["name"] or "личного бренда"
    lines = [f"# Контент-план: {title}", ""]
    for i, topic in enumerate(topics, 1):
        rubric = f" ({topic['rubric']})" if topic["rubric"] else ""
        lines.append(f"{i}. **{topic['subject']}**{rubric}")
        if topic["hook"]:
            lines.append(f"   Заход: {topic['hook']}")
    return "\n".join(lines) + "\n"
