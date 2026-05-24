# 本地 Surge Rewrite + MITM 测试实施计划

> **给后续 agentic worker 的说明：** 本计划已经完成实施，保留此文件用于记录设计和验证路径。若继续扩展，请优先使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，并按任务逐项验证。

**目标：** 在 macOS 本地构建一套 Python 测试方案，复现 Surge `URL Rewrite` + `MITM` 的核心机制，但不转发到真实上游服务。

**架构：** 把 URL 匹配和改写决策放在纯 Python 模块 `rewrite_rules.py` 中，方便脱离代理做单元测试。`rewrite_addon.py` 只作为 mitmproxy 适配层，把规则层结果应用到真实代理 flow。`mock_origin.py` 作为本地目标服务，用 JSON 回显被改写后的请求细节。

**技术栈：** Python 3 标准库、`unittest`、mitmproxy、curl。

---

## 技术拆解

### 规则层

`rewrite_rules.py` 负责复现 Surge URL Rewrite 规则中的可测试部分：

- 只匹配指定域名：`daoyu.fan`、`huanyuxingqiu.vip`、`huanyuxingqiu.life`、`hyxq666.com`。
- 允许 `http` 和 `https`。
- 保留原始 path 和 query。
- 排除图片、CSS、JS、字体、视频、压缩包等静态资源。
- 把命中的请求改写到本地 mock origin：`http://127.0.0.1:9000`。

### 代理适配层

`rewrite_addon.py` 运行在 mitmproxy 里，处理每个请求 flow：

1. 从 `flow.request.url` 读取完整 URL。
2. 调用 `rewrite_url()` 得到本地目标 URL。
3. 命中时修改 `flow.request.scheme`、`host`、`port`、`path`。
4. 添加 `x-local-rewrite-original-url`，用于验证原始请求来源。
5. 没命中但属于配置域名时，默认返回本地 `599` 阻断响应，避免请求真实域名。

### Mock origin

`mock_origin.py` 是一个本地 HTTP 服务，监听 `127.0.0.1:9000`。它不会做业务逻辑，只返回请求方法、路径、headers 和说明文本。这样端到端测试可以直接判断请求是否真的被改写到了本地。

### 端到端脚本

`run_local_mitm_test.sh` 串起完整链路：

1. 准备 `.venv`。
2. 安装 mitmproxy。
3. 跑单元测试。
4. 启动 mock origin。
5. 启动 mitmdump。
6. 用 curl 通过代理发送 HTTPS 正例。
7. 检查 mock origin JSON。
8. 用 curl 发送静态资源负例。
9. 检查负例被本地安全阀阻断。
10. 清理后台进程。

---

## 已完成任务

### 任务 1：纯规则层

**文件：**

- `rewrite_rules.py`
- `tests/test_rewrite_rules.py`

**完成内容：**

- 增加正例测试：匹配域名会改写到 `127.0.0.1:9000`。
- 增加多域名测试：覆盖原 Surge 模块列出的几个域名。
- 增加负例测试：`.js`、`.png`、`.woff2`、`.zip` 等静态资源不会被改写。
- 增加非配置域名测试：`example.com` 不会被改写。
- 增加配置域名识别测试：用于安全阻断逻辑。

**验证命令：**

```bash
python3 -m unittest tests.test_rewrite_rules
```

### 任务 2：mitmproxy 适配层和 mock origin

**文件：**

- `rewrite_addon.py`
- `mock_origin.py`
- `requirements.txt`
- `tests/test_proxy_components.py`

**完成内容：**

- `rewrite_addon.py` 把规则结果应用到 mitmproxy flow。
- 命中请求会改写 scheme、host、port、path。
- 命中请求会附带 `x-local-rewrite-original-url`。
- 未命中的配置域名请求默认返回 `599` 本地阻断。
- `mock_origin.py` 回显 method、path、headers。
- 单元测试覆盖 flow 改写、静态资源不改写、安全阻断、mock JSON 响应。

**验证命令：**

```bash
python3 -m unittest tests.test_proxy_components
```

### 任务 3：完整链路和中文说明

**文件：**

- `run_local_mitm_test.sh`
- `README.md`

**完成内容：**

- 一键脚本自动创建环境、安装依赖、启动服务、跑 curl、校验响应、清理进程。
- README 提供中文说明、技术原理、完整一键路径和手动路径。
- 正例验证 HTTPS 请求被 MITM 后改写到本机 mock origin。
- 负例验证静态资源不被改写，并由本地安全阀阻断。

**验证命令：**

```bash
python3 -m unittest tests.test_rewrite_rules tests.test_proxy_components
./run_local_mitm_test.sh
```

---

## 当前验证结果

最近一次验证结果：

- `python3 -m unittest tests.test_rewrite_rules tests.test_proxy_components`：9 个测试通过。
- `./run_local_mitm_test.sh`：完整链路通过。
- 正例请求：`https://daoyu.fan/api/v1/member/profile?token=local-test` 被改写到 `127.0.0.1:9000`。
- 负例请求：`https://daoyu.fan/app.js` 未改写到 mock origin，本地返回 `599`。

---

## 后续可扩展方向

- 增加更多 Surge URL Rewrite 语法样例解析。
- 增加 request body 回显，用于测试 POST/JSON 请求。
- 增加证书安装说明，用于真实 App 走 mitmproxy 的场景。
- 增加 mitmproxy 日志解析，把每次改写记录输出成结构化 JSON。
