# quality：质量测试

- `test_project_quality.py`：对真实项目运行 `fastapi_check.quality` 的全部检查。
- `test_rule_examples.py`：在临时目录故意写出违规样例，确认每条检查都会报出，防止检查失效却一直显示通过。

不要为了通过检查修改阈值。
