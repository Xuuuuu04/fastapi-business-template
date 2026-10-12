# 纯工具包

工具包保存跨业务复用的纯函数、数据类型与协议解析，不访问数据库、网络、文件、时钟和随机数。

每包包含README.md、public.py、module.json，可选data.py与calc/命名文件。public.py是唯一跨包入口，module.json声明kind=library、名称、标题、exports与aliases。步骤用calcs声明计算；依赖从导入推导。新建使用dev new-library。
