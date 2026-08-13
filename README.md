# websitebench-pipeline — WebsiteBench 离线网站复刻流水线

本仓库包含 WebsiteBench 的配置驱动生产流水线：从范围定义与源证据采集开始，
构建离线网站 clone，执行机器诊断，并派生 Harbor interaction contract 与评测
instance。诊断结果是维护者判断的输入，不自动构成验收、合并、部署或发布许可。

## 公开导出范围

这个 public repository 仅发布可再分发的流水线代码、schemas、通用工具、文档和
站点无关测试。内部金样本 TripIt 的抓取证据、镜像 clone、Harbor reference /
instance，以及站点专属部署配置未包含在公开导出中：该样本的权利审查明确没有
授予 TripIt / Concur / SAP 商标、页面内容、图片和字体的公开再分发许可。

如需使用流水线，请从自己的、已获授权的目标站点创建新材料目录；不要把源站
访问凭据、cookie、授权头、支付数据或敏感表单值写入仓库、日志或证据产物。

## 快速开始

```bash
# Python >= 3.11
uv venv
source .venv/bin/activate
uv pip install -e '.[dev]'
python -m playwright install chromium

# 查看通用离线 clone 工具
python tools/offline_clone/run.py tools list

# 创建一个新站点骨架
websitebench-offline-clone contribution init \
  --repo . \
  --site-id <site-id> \
  --display-name "<Name>" \
  --source-url https://example.test/

# 对站点运行静态与浏览器诊断
websitebench-offline-clone verify --site materials/<site-id>
```

## 流程入口

- `prompts/offline-clone/RUNBOOK.md`：人类发起任务和提供授权范围的入口。
- `prompts/offline-clone/autonomous-source-to-clone.md`：agent 执行契约。
- `ACCEPTANCE.md`：分阶段人工/agent 验收清单。
- `AGENTS.md`：仓库安全、命名、证据与后端约束。
- `docs/source-evidence-access-policy.md`：真实站点证据采集政策。

核心目录：

- `src/websitebench/`：CLI 与 Python 库。
- `websitebench/`：schemas、capability packs 与 corpus 元数据。
- `tools/offline_clone/`：跨站诊断工具。
- `deploy/generic-offline-clone/`：通用 public-demo 部署包。
- `harbor/`：Harbor schemas 与通用运行时。
- `tests/`：站点无关自检。

## 安全边界

- 源站探索默认只读；没有精确场景与显式授权时不发送非 GET 请求。
- clone 诊断是 `diagnostic-only`，不能替代版权、再分发或部署授权。
- 后端、邮件与支付能力必须使用仓库生成的 runtime contract；live payment
  credentials 永远禁止。
- 公网发布必须使用固定的单站 dispatcher，并由人明确授权。

## License

仓库自有代码按 [Apache License 2.0](LICENSE) 发布。第三方名称、商标、内容与
资产仍归各自权利人所有；Apache-2.0 不会为它们额外授予权利。
