# framework：框架测试

[sample_modules.py](sample_modules.py) 定义了几个只用于测试的小模块（示例计算、慢任务、说明文字、外层操作），表登记在单独的 metadata 上，不进入正式迁移。

测试覆盖：执行器与事务、声明检查的反例、步骤运行时约束、后台任务、大模型入口、运行记录与图。

成员链使用 [fanout_driver.py](fanout_driver.py) 的受控队列时钟；[test_fanout_timing.py](test_fanout_timing.py) 单独验证等待超时、租约与并发提交。失败证据在本机 `var/development/failures/`，含操作报告及夹具销毁前的成员、任务、租约状态。
