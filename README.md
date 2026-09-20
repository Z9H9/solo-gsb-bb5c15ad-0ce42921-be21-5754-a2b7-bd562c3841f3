# 🧶 编织行指令审校工具

一个用于审校编织花样行指令的 Web 应用：填写起始针数与逐行指令，系统解析并展开每一行，
以上一行的产出作为下一行的可用针数，逐行显示**消耗 / 产出 / 剩余**；针数不匹配时，
自动定位**第一条无法执行的源指令**并给出短缺或未消耗数量。修改任意行后实时重算后续所有行，
方案可导入 / 导出为 JSON。

技术栈：Python 3.12 · FastAPI · 原生 HTML/CSS/JavaScript（无前端框架、无构建步骤）。

## 快速启动（单条命令）

```bash
docker compose up --build
```

启动后访问：**http://localhost:8000**

> 依赖安装与初始化已全部纳入镜像构建与容器启动流程，无需任何额外步骤。

## 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| 对外端口 | `8000` | 修改 `docker-compose.yml` 中 `ports` 的左侧端口即可，如 `"8080:8000"` |

应用本身无需数据库或其他外部服务，无状态、开箱即用。

## 指令语法

| 指令 | 含义 | 消耗 | 产出 |
| --- | --- | --- | --- |
| `kN` | 平针 N 针 | N | N |
| `incN` | 加针：1 针中织出 N 针 | 1 | N |
| `decN` | 减针：N 针并为 1 针 | N | 1 |
| `[序列]*M` | 将序列重复 M 次，**可嵌套**，如 `[k2 [inc2 k1]*2]*3` | — | — |

- 指令之间可用空格、逗号或分号分隔；大小写不敏感（`K2` 与 `k2` 等价）。
- 行内新产出的针放到另一根针上，本行不再消耗；行末剩下的即“未消耗”针数。
- 上一行的 **产出 + 未消耗** 即下一行的可用针数；空行原样传递针数。
- 针数不足时，高亮第一条无法执行的指令，标明需要 / 仅剩 / 短缺数量；
  若发生在重复分组内，还会指出“第几次重复”。

## JSON 导入 / 导出格式

```json
{
  "start": 12,
  "rows": ["k12", "[inc2 k1]*6", "[k2 dec2]*4 k2"]
}
```

页面提供“导入 JSON / 导出 JSON”按钮；导出文件名为 `knitting-plan.json`。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/evaluate` | 请求体同上方 JSON；返回每行的 `available/consumed/produced/remaining`、展开序列与错误定位 |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/` | 单页应用 |

## 本地开发（不用 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

运行测试（需额外安装 `pytest` 与 `httpx`）：

```bash
pip install pytest httpx
pytest
```

## 项目结构

```
├── app/
│   ├── main.py            # FastAPI 入口：静态页面 + /api/evaluate
│   ├── parser.py          # 指令解析、展开与逐行求值（核心逻辑）
│   └── static/            # 原生 HTML / CSS / JS 前端
├── tests/test_parser.py   # 解析、求值、错误定位与 API 测试
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```
