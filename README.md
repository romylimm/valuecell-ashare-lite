# ValueCell Lite：A 股单股研究

这是当前仓库的轻量运行模式。保留 ValueCell 的 Python/FastAPI 技术路线和 AKShare 免费数据工具，新增单股研究编排与中文页面，启动时只加载单股分析依赖。原版前后端和交易模块仍在仓库中供后续迁移。

## 启动

Windows PowerShell 在仓库目录执行：

```powershell
.\start-lite.ps1
```

打开 http://127.0.0.1:8008 ，输入 `600519`、`000001` 或 `300750`。点击示例也会发起真实数据请求。第一次会安装依赖，需要联网；要求 uv 与 Python 3.12+，没有 Python 时 uv 会尝试下载。

已有依赖时可直接运行：

```powershell
cd python
.\.venv\Scripts\python.exe -m uvicorn lite.app:app --host 127.0.0.1 --port 8008
```

Mac/Linux 使用 `uv venv python/.venv --python 3.12`、`uv pip install --python python/.venv/bin/python -r python/requirements-lite.txt`，再在 python 目录用 `.venv/bin/python -m uvicorn lite.app:app --host 127.0.0.1 --port 8008`。

## 第一版范围

- 六位沪深北 A 股代码（也接受 sh/sz/bj 前缀和 .SH/.SZ/.BJ 后缀），校验交易所。
- 腾讯报价：价格、涨跌幅、市盈率 TTM、市净率和报价时间。
- 腾讯 / AKShare：最近约 90 根前复权日线、20 日均线与 20 交易区间涨跌。
- 同花顺 / AKShare：最新可获取报告期财务指标，保留原始指标名和数值。
- 东方财富 / AKShare：最近新闻标题、发布时间和原文链接。
- 数据摘要不需要模型密钥。AI 解读可选；无模型时不伪装成 AI 分析。
- 数据来源、获取时间、行情时间、部分缺失与延迟提示，JSON 导出。

第三方数据接口可能限流、变更或暂时不可用；页面按来源单独显示缺失，不用模拟数据替换。AKShare 在独立子进程执行，每项最多 30 秒，到期回收进程；并行查询最多两次，成功数据缓存 5 分钟、最多 100 只股票（部分失败也缓存，5 分钟后重试）。未提供公司主营业务、公告全文研读、交易、自选股持久化和定时任务。本版财务与新闻由页面展示原始证据，进一步综合解读需要配置模型。

免费获取不等于拥有再分发权；公开部署、商用或批量分发前，需确认各源站授权与使用条款。

## 可选 AI 解读

使用兼容 Chat Completions 的服务，在启动前设置环境变量，密钥只放服务端：

```powershell
$env:LITE_LLM_BASE_URL = 'https://你的模型服务地址/v1'
$env:LITE_LLM_MODEL = '你的模型名称'
$env:LITE_LLM_API_KEY = '你的密钥'
.\start-lite.ps1
```

本地兼容服务可不填密钥。配置后页面出现可勾选的 AI 解读功能，默认关闭，每次勾选才会调用模型并可能产生费用。模型只接收本次收集的数据，失败保留数据报告。模型输出属于生成内容，仍需核验来源。API Key 不下发浏览器、不写入导出数据。

## 验证

```powershell
cd python
uv pip install --python .venv/Scripts/python.exe pytest pytest-asyncio
.\.venv\Scripts\python.exe -m pytest lite/tests -q
```

接口文档：`/api/docs`，健康检查：`/api/health`，分析：`POST /api/analyze`，请求示例 `{"symbol":"600519","use_ai":false}`。

服务默认只监听本机，当前没有账户、鉴权和分布式限流；适合作为本地研究原型。

## 来源与改造说明

本项目基于 [ValueCell-ai/valuecell](https://github.com/ValueCell-ai/valuecell) 改造，保留上游 Apache-2.0 许可证与版权声明。它是独立的 A 股轻量研究改造版，与上游官方产品无隶属关系。

本次改动：新增 `python/lite` 单股分析服务与中文页面、`start-lite.ps1` 启动入口、18 项回归检查及轻量 CI；原版应用代码保留。原有完整构建流水线移至 `docs/upstream-workflows`，避免默认触发桌面打包和完整交易测试。

源码下载自上游 main 分支（2026-10-19），使用官方压缩包，因此当前仓库不包含上游 Git 历史。该日期读取到的上游 HEAD 为 `9793e9c0563fbf56fc096757d8bb80e209ac7aab`；压缩包按分支下载，未按该提交固定。原始项目介绍见 [README.upstream.md](README.upstream.md)。
