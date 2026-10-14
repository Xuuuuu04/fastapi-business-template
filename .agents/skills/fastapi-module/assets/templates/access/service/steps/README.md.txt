# 步骤

`sign_in.py` 是登录的步骤：查找账号、核对口令、整理登录结果。`accounts.py` 是新建账号的步骤：核对授权范围、计算口令摘要、保存账号。`passwords.py` 是这些步骤共用的口令计算，用到 `hashlib`，所以不放在 calc/；计算放在 `heavy=True` 的步骤里，受 `APP_HEAVY_CONCURRENCY` 限制同时计算的数量。
