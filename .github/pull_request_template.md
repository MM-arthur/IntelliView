## 变更说明

<!-- 题库 PR：改了哪个岗位包 / 新增了什么岗位 -->

### 题库 PR Checklist（改了 questions/ 必勾）

- [ ] 通过 `python cli.py bank validate questions/xxx.json`
- [ ] `id` 全局唯一（小写/数字/连字符）
- [ ] 题量 8-12，且 easy / medium / hard 三档都有
- [ ] 每题都有 `follow_up`，且追问有区分度（能挖出知识边界，不是背诵检查）
- [ ] 没有 LeetCode 原题或某公司泄露面经
- [ ] 更新了 `questions/README.md` 的包列表（如有新增包）

### 代码 PR Checklist

- [ ] 本地跑过相关自检（`python tests/test_plugin.py` / `tests/test_mcp_server.py` / `tests/test_cli.py`）
- [ ] 引擎保持零 SDK 依赖；适配器改动不引入宿主知识