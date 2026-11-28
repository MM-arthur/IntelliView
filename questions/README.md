# 📚 开源题库（岗位包）

一个 JSON 文件 = 一个岗位包。`intelliview bank use <id>` 一键导入并激活，
之后模拟面试优先按该题库出题；答错的题自动进错题本。

```
intelliview bank list                      # 查看所有岗位包
intelliview bank show backend-python       # 预览某个包
intelliview bank use backend-python        # 导入并激活
intelliview interview                      # 按题库开面
```

## 现有岗位包

| ID | 岗位 | 题量 |
|---|---|---|
| `backend-python` | Python 后端开发工程师 | 12 |
| `frontend-react` | 前端开发工程师（React） | 12 |
| `algorithm-fundamentals` | 算法与数据结构基础（通用） | 12 |
| `algorithm-advanced` | 算法与数据结构进阶（通用） | 12 |
| `backend-java` | Java 后端开发工程师 | 12 |
| `backend-go` | Go 后端开发工程师 | 12 |
| `ml-engineer` | 机器学习 / 算法工程师 | 12 |
| `product-manager` | 产品经理（C 端/策略向） | 12 |
| `behavioral-english` | Behavioral Interview (English) | 12 |

## 贡献新岗位包（欢迎 PR 🎉）

1. 复制 `backend-python.json` 作为模板，重命名 `<你的岗位id>.json`
2. 填写字段（格式见 [question-pack.schema.json](./question-pack.schema.json)）：
   - `id`：小写字母/数字/连字符，全局唯一
   - `position`：岗位名称
   - `key_points`：考点（3-8 条）
   - `questions`：**8-12 题**，每题包含 `question`（题干）、`category`（分类）、
     `difficulty`（easy/medium/hard）、`follow_up`（追问，可选但强烈建议）
3. 质量要求：
   - **追问必须有区分度**——目标是挖出知识边界，而不是背诵检查
   - 至少 3 个难度档位都要有题
   - 不要抄 LeetCode 原题或某家公司泄露的面经
4. 本地自检：`python cli.py bank validate questions/<你的包>.json`
   （CI 会再跑一遍全部包）
5. 提交 PR，勾选 PR 模板里的 checklist

## 用户自定义包

不放仓库也行：把 JSON 放到 `~/.intelliview/question_packs/`，
`intelliview bank list` 会一并列出。