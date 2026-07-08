import requests

# 健康检查
print(requests.get("http://localhost:8080/health").json())

# 工具列表
print(requests.get("http://localhost:8080/tools").json())

# 调用数学工具
resp = requests.post(
    "http://localhost:8080/call",
    json={"tool": "math", "params": {"a": 3, "b": 5}}
)
print(resp.json())