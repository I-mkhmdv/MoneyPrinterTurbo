# Помощник по контенту для личного бренда

`brand_plan.py` превращает профиль бренда в контент-план и пачку заданий для `cli.py`.
Каждый сценарий пишется в голосе бренда: ниша, аудитория, тон, стоп-слова и рубрики
берутся из профиля.

## 1. Профиль бренда

```bash
cp brand.example.toml brand.toml
```

Заполните в `brand.toml` нишу, аудиторию, тон, рубрики и, по желанию, пару своих текстов
в `example_texts`, чтобы модель подхватила ваш голос. Файл не попадает в git.

## 2. Контент-план

Темы придумывает нейросеть (провайдер и ключ берутся из `config.toml`, как для сценариев):

```bash
uv run python brand_plan.py --profile brand.toml --count 3
```

Или свои темы, по одной на строку:

```bash
uv run python brand_plan.py --profile brand.toml --topics my_topics.txt
```

Результат в `storage/brand/`: `plan.md` для просмотра и `tasks.jsonl` для генерации.

## 3. Ролики

Сначала можно посмотреть только сценарии, потом собрать видео целиком:

```bash
uv run python cli.py --batch-file storage/brand/tasks.jsonl --stop-at script
uv run python cli.py --batch-file storage/brand/tasks.jsonl
```

Для полного ролика нужны ключ нейросети и ключ Pexels в `config.toml`.
