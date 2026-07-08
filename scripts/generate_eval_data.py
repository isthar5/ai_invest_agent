import json
import asyncio
from openai import AsyncOpenAI
from qdrant_client import QdrantClient
import os
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

qdrant = QdrantClient(
    host=os.getenv("QDRANT_HOST"),
    port=int(os.getenv("QDRANT_PORT"))
)

COLLECTION_NAME = os.getenv("COLLECTION_NAME")


PROMPT_TEMPLATE = """
你是一个金融助手。

给定一段文档内容，请生成 2 个用户可能提出的查询问题。

要求：
1. 问题必须自然
2. 与内容强相关
3. 用中文

文档：
{content}

输出 JSON：
[
  {{"query": "..."}},
  {{"query": "..."}}
]
"""


async def generate_queries(doc_text):
    prompt = PROMPT_TEMPLATE.format(content=doc_text[:500])  # 截断防止过长

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    text = resp.choices[0].message.content

    try:
        return json.loads(text)
    except:
        return []


async def main():
    eval_data = []

    # 从Qdrant随机取文档
    docs = qdrant.scroll(
        collection_name=COLLECTION_NAME,
        limit=50,
        with_payload=True
    )[0]

    for doc in docs:
        doc_id = str(doc.id)
        content = doc.payload.get("text", "")

        if not content:
            continue

        queries = await generate_queries(content)

        for q in queries:
            eval_data.append({
                "query": q["query"],
                "relevant_docs": [doc_id]
            })

        print(f"✔ processed doc {doc_id}")

    # 保存
    with open("eval_data.json", "w", encoding="utf-8") as f:
        json.dump(eval_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 生成完成，共 {len(eval_data)} 条数据")


if __name__ == "__main__":
    asyncio.run(main())