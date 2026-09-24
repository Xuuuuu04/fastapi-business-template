# contracts：约定测试

同一个约定有多个实现时，用同一组测试检查它们行为一致。新增实现（例如新的运行记录保存位置、新的数据来源）时，把它加入参数列表即可复用全部检查。

[test_cache_and_files.py](test_cache_and_files.py) 中的 Redis 和 S3 实现只在设置环境变量时参加，变量见文件开头的说明。
