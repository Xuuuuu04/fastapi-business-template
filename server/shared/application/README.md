# 产品组装

产品在app/product.py声明APPLICATION，类型为ApplicationSpec。API、worker、文档、检查与开发工具共用它。

settings_type与configure负责产品配置；routers与api_setup负责产品路由与权限扩展；model_provider负责模型适配；workers声明额外的后台循环。扩展与框架队列共用服务、运行记录和停止信号。

settings("offline")与settings("test")不使用环境变量、.env或密钥文件。结构查看只描述扩展的位置，不调用网络适配器。实际运行使用settings("runtime")，读取明确的部署环境。

framework_version、product_version与部署的code_version含义不同。字段和接口的兼容性由产品版本及生成的契约变更说明判断。
