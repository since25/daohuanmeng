# 本地复现 Surge URL Rewrite + MITM 测试

这个目录是一套 macOS 本地测试方案，用 Python 复现 Surge 模块里 `URL Rewrite` + `MITM` 的核心网络机制。

当前默认目标已经切到原模块里的真实 Worker：`https://huanyu-proxy.daoyufan.workers.dev`。命中的请求会被改写到这个 Worker，用于观察“代理如何看到 HTTPS 完整 URL、如何匹配规则、如何改写目标地址、如何返回响应”这一整条链路。

## 文件说明

- `rewrite_rules.py`：纯 Python 规则层，负责复现 Surge 风格的 URL 正则匹配、域名判断、静态资源排除、目标 URL 拼接。
- `rewrite_addon.py`：mitmproxy 插件层，负责把规则层的结果应用到真实代理流量里。
- `mock_origin.py`：可选的本地 HTTP 回显服务；单元测试仍覆盖显式传入本地 target 的场景。
- `tests/`：单元测试，覆盖 URL 改写规则、静态资源排除、代理适配逻辑、本地安全阻断逻辑。
- `run_local_mitm_test.sh`：一键端到端测试脚本，自动创建虚拟环境、安装依赖、启动 mitmproxy、执行真实 Worker curl 验证、最后清理进程。
- `docs/superpowers/plans/2026-05-23-local-surge-rewrite-mitm-test.md`：这套测试方案的实施计划记录。

## 技术原理

### 1. 普通 HTTPS 代理为什么不能直接改写完整 URL

客户端访问 HTTPS 网站时，通常会先向代理发送 `CONNECT` 请求，例如：

```text
CONNECT daoyu.fan:443 HTTP/1.1
```

如果代理只是普通隧道代理，它只能知道客户端要连 `daoyu.fan:443`。随后客户端和远端服务器之间会建立 TLS 加密通道，代理只负责转发加密字节流。

在这种模式下，代理看不到这些信息：

- 完整 URL：`https://daoyu.fan/api/v1/member/profile?token=local-test`
- path：`/api/v1/member/profile`
- query：`token=local-test`
- HTTP headers
- HTTP body

所以，普通 HTTPS 代理最多能按域名分流，不能按完整路径做 Surge 这种规则：

```text
^https?://(?:daoyu\.fan|huanyuxingqiu\.(?:vip|life)|hyxq666\.com)/(.*)
```

### 2. MITM 让代理能看到 HTTPS 内部请求

MITM 的意思是代理不再只做 TCP 隧道，而是在客户端和目标站之间各建立一段 TLS：

```text
客户端
  ↓ TLS 1：客户端信任本地代理动态签发的证书
本地代理 / mitmproxy
  ↓ TLS 2：代理再去连接真正目标站
目标站
```

这样代理处在两段 TLS 中间，可以解密客户端发来的 HTTP 请求，于是就能看到完整的 URL、path、query、headers。

Surge 的 `[MITM] hostname = ...` 本质上就是告诉 Surge：这些域名允许做 HTTPS 解密。mitmproxy 也是同类机制，只是它用 Python 插件来写处理逻辑。

本项目的一键脚本用的是：

```bash
curl -sk --proxy http://127.0.0.1:8080 "https://daoyu.fan/api/v1/member/profile?token=local-test"
```

其中 `-k` 表示 curl 不校验证书链。这样本地实验不需要手动安装 mitmproxy 根证书。真实 App 测试时通常需要把 mitmproxy 或 Surge 的根证书安装并设为信任，否则 App 会拒绝这段被代理动态签发的 HTTPS 证书。

### 3. URL Rewrite 做了什么

原 Surge 规则的结构可以拆成三段：

```text
^https?://
(?:daoyu\.fan|huanyuxingqiu\.(?:vip|life)|hyxq666\.com)
/
(?!.*\.(?:png|jpe?g|gif|webp|svg|ico|css|js|woff2?|ttf|eot|mp[34]|zip|rar)(?:\?|$))
(.*)
```

含义是：

- `^https?://`：匹配 `http://` 或 `https://` 开头。
- `(?:...)`：只匹配列出的几个域名。
- `/`：域名后面必须有路径分隔符。
- `(?!...)`：负向前瞻，排除图片、CSS、JS、字体、视频、压缩包等静态资源。
- `(.*)`：捕获剩下的 path 和 query。

在本地项目里，匹配到的 URL 会被改写成：

```text
https://huanyu-proxy.daoyufan.workers.dev/<原 path 和 query>
```

例如：

```text
https://daoyu.fan/api/v1/member/profile?token=local-test
```

会被改写为：

```text
https://huanyu-proxy.daoyufan.workers.dev/api/v1/member/profile?token=local-test
```

如果需要回到本地 mock，可以在调用 `rewrite_url()` 时显式传入 `target_base="http://127.0.0.1:9000"`。

### 4. mitmproxy 插件如何应用改写结果

`rewrite_addon.py` 的关键动作是：

1. 读取当前请求的 `flow.request.url`。
2. 调用 `rewrite_rules.rewrite_url()` 判断是否命中规则。
3. 如果命中，把 mitmproxy flow 的请求目标改成新的 scheme、host、port、path。
4. 加入 `x-local-rewrite-original-url` header，方便确认原始 URL。
5. 如果没有命中，但域名属于这次测试配置，则默认返回本地 `599` 阻断响应，避免误连真实域名。

也就是说，这里不是让 Python 自己发起一个新的 `requests.get()`，而是直接修改代理里的请求流向。这更接近 Surge `URL Rewrite` 的工作方式。

### 5. 为什么要有本地安全阻断

静态资源负例，比如：

```text
https://daoyu.fan/app.js
```

按照原 Surge 规则，`.js` 应该被负向前瞻排除，不应该改写到 mock origin。

但如果只是“不改写”，mitmproxy 默认会继续尝试访问真实 `daoyu.fan`。为了让测试全程留在本机，`rewrite_addon.py` 默认会把“属于配置域名但没有被改写”的请求返回本地 `599`：

```text
blocked unrewritten configured test host
```

这样可以同时验证两件事：

- `.js` 确实没有被 URL Rewrite 命中。
- 未命中的测试域名流量没有离开本机。

如果你在受控实验环境里确实要关闭这个安全阀，可以显式设置：

```bash
LOCAL_MITM_BLOCK_UNREWRITTEN=0 mitmdump --listen-host 127.0.0.1 --listen-port 8080 --set ssl_insecure=true -s rewrite_addon.py
```

## 一键测试路径

在当前目录运行：

```bash
chmod +x run_local_mitm_test.sh
./run_local_mitm_test.sh
```

脚本会自动完成：

1. 如果没有 `.venv`，创建 Python 虚拟环境。
2. 安装 `mitmproxy`。
3. 运行单元测试。
4. 启动 mitmproxy：`127.0.0.1:8080`。
5. 发送正例请求：

   ```bash
   curl -skL --proxy http://127.0.0.1:8080 "https://daoyu.fan/4687.html"
   ```

6. 验证真实 Worker 返回 `200` 和 HTML 页面。

7. 发送负例请求：

   ```bash
   curl -sk --proxy http://127.0.0.1:8080 "https://daoyu.fan/app.js"
   ```

8. 验证静态资源没有被改写，而是被本地安全阀返回 `599`。

脚本结束时会清理 mitmproxy 进程。

## macOS 浏览器使用路径（方案 C）

这条路径最接近 Surge：浏览器仍然访问原始地址，例如 `https://daoyu.fan/4687.html`，本地 mitmproxy 负责把命中的请求改写到真实 Worker。

首次使用前，需要让 macOS/Chrome 信任 mitmproxy 的本地根证书。这个动作会修改当前用户 login keychain 的证书信任状态，脚本不会被自动执行；确认要这么做时，手动运行：

```bash
./install_mitm_ca_macos.sh
```

启动后台代理：

```bash
./start_mitm_proxy.sh
```

脚本会把运行所需文件同步到：

```text
~/Library/Application Support/daoyufan-mitm/
```

并注册用户级 LaunchAgent：`com.daoyufan.mitmproxy`。这样可以避开 macOS 对 Desktop 目录的后台进程隐私限制。

用独立 Chrome profile 打开原站页面，并只让这个 Chrome 窗口走本地代理：

```bash
./open_chrome_with_mitm.sh
```

默认打开：

```text
https://daoyu.fan/4687.html
```

也可以指定其他路径：

```bash
./open_chrome_with_mitm.sh "https://daoyu.fan/57374.html"
```

停止后台代理：

```bash
./stop_mitm_proxy.sh
```

这套脚本不会修改系统代理设置。它通过 `--user-data-dir=.chrome-mitm-profile` 打开一个隔离的 Chrome profile，并通过 `--proxy-server=http://127.0.0.1:8080` 让这个窗口走本地代理。代理日志位于：

```text
~/Library/Application Support/daoyufan-mitm/logs/
```

## React 本地控制台

控制台把文章链抓取、SQLite 去重缓存、最终网盘链接解析、暂停/恢复/停止和 JSON/CSV 导出放在一个本地页面里。它仍然复用上面的本地 MITM 代理，默认代理地址是：

```text
http://127.0.0.1:8080
```

一键启动代理、后端和前端控制台：

```bash
./start_console.sh
```

打开：

```text
http://127.0.0.1:5173
```

如果 `5173` 已被其他本地项目占用，`start_console.sh` 会自动从 `5173` 开始寻找下一个可用端口，并在终端里打印真实的 Frontend 地址，例如：

```text
Frontend: http://127.0.0.1:5174
```

默认起始页是：

```text
https://daoyu.fan/3199.html
```

控制台后端运行在：

```text
http://127.0.0.1:8765
```

`start_console.sh` 默认会启动本地 MITM 代理 `http://127.0.0.1:8080`，并在按 `Ctrl-C` 退出时一起关闭代理、后端和前端。如果只想启动控制台、不管理代理：

```bash
START_PROXY=0 ./start_console.sh
```

如果需要每篇文章全流程切换 Nikki 节点，在左侧表单里开启：

- `解析最终网盘链接`
- `下载跳转改写到 Worker`

并填写：

```text
文章处理代理: http://<proxy-gateway-host>:7890
Nikki API: http://<nikki-api-host>:9090
Nikki 密钥: <external-controller secret>
策略组: daoyufan-resolver-pool
```

左侧表单里的 `文章处理代理` 是整篇文章处理流程使用的 HTTP 代理；填了它以后，每篇文章开始处理前会先通过 `Nikki API` 和 `Nikki 密钥` 调用 Nikki/Mihomo external-controller，嗅探并切换 `daoyufan-resolver-pool` 节点，然后抓文章页和解析下载跳转都走这个节点。填好后点 `保存配置`，配置会保存在当前浏览器的 localStorage 里，刷新页面或重启 `start_console.sh` 后仍会自动带回；如果换浏览器或清理站点数据，则需要重新填写。

运行时流程：

```text
每篇文章开始 -> 调 Nikki /delay 嗅探可用节点
每篇文章开始 -> PUT /proxies/daoyufan-resolver-pool 切换节点
抓文章页 -> 通过 <proxy-gateway-host>:7890 访问 daoyu.fan
解析下载 href -> 可选 rewrite 到 huanyu-proxy.daoyufan.workers.dev
解析请求 -> 通过同一个 <proxy-gateway-host>:7890 访问下载跳转或 rewrite 地址
```

常用接口：

```text
GET  /api/health
POST /api/job/start
POST /api/job/pause
POST /api/job/resume
POST /api/job/stop
GET  /api/job
GET  /api/results
GET  /api/export/json
GET  /api/export/csv
```

停止控制台时，在运行 `./start_console.sh` 的终端按 `Ctrl-C`，脚本会关闭本次启动的所有服务。若你是单独启动代理，仍可手动停止：

```bash
./stop_mitm_proxy.sh
```

## 手动测试路径

创建环境：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

运行单元测试：

```bash
python -m unittest tests.test_rewrite_rules tests.test_proxy_components
```

另开一个终端，启动 mitmproxy：

```bash
mitmdump --listen-host 127.0.0.1 --listen-port 8080 --set ssl_insecure=true -s rewrite_addon.py
```

再开第三个终端，发送命中规则的 HTTPS 请求：

```bash
curl -skL --proxy http://127.0.0.1:8080 "https://daoyu.fan/4687.html"
```

预期结果：通过真实 Worker 返回 `200` 和 HTML 页面。

发送静态资源请求：

```bash
curl -sk --proxy http://127.0.0.1:8080 "https://daoyu.fan/app.js"
```

预期结果：返回本地阻断文本。原因是 `.js` 被原 Surge 风格负向前瞻排除。

## 提取下载按钮

`download_extractor.py` 可以从页面 HTML 里提取下载按钮组：

```bash
curl -skL --proxy http://127.0.0.1:8080 "https://daoyu.fan/57517.html" -o /tmp/daoyu-57517.html
.venv/bin/python download_extractor.py /tmp/daoyu-57517.html
```

输出格式：

```json
[
  {
    "href": "https://daoyu.fan/goto?down=...",
    "text": "在线观看版本--先保存-再在网盘app里在线观看-一点也不卡",
    "password": null
  },
  {
    "href": "https://daoyu.fan/goto?down=...",
    "text": "压缩包版本-提示需要会员去网盘app新人活动领几百G先再保存",
    "password": "weimi.life"
  }
]
```

## 沿下一篇循环提取

`post_chain_crawler.py` 会从起始页面开始，记录 `post-title mb-2 mb-lg-3` 标题、第二个下载按钮组里的 href、该 href 通过代理跳转后的最终地址，以及 `entry-page-next` 的 href，再进入下一页。它默认最多跑 3 页，避免无限循环：

```bash
.venv/bin/python post_chain_crawler.py --start "https://daoyu.fan/3199.html" --max-pages 2
```

输出格式：

```json
[
  {
    "url": "https://daoyu.fan/3199.html",
    "title": "Booty徐莉芝 合集",
    "download_href": "https://daoyu.fan/goto?down=...",
    "resolved_download_url": "https://share.feijipan.com/s/...?code=6666",
    "next_url": "https://daoyu.fan/3203.html"
  }
]
```

## 这套方案复现了什么

这套本地方案复现的是机制，不是某个真实服务的业务结果：

- 客户端把 HTTPS 请求发给本地代理。
- 本地代理通过 MITM 看到完整 URL。
- Python 正则判断请求是否命中 Surge 风格规则。
- 命中后把请求目标改写到另一个 origin。
- path 和 query 原样保留。
- 静态资源按原规则排除。
- 未改写的测试域名请求被本地阻断，避免误触真实网络。

如果只想理解 Surge 的这两个配置项，可以把它们对应到本项目：

```text
[URL Rewrite]  -> rewrite_rules.py + rewrite_addon.py 里的 flow 改写
[MITM]         -> mitmproxy 对 HTTPS CONNECT 流量的解密能力
hostname       -> rewrite_rules.py 里的 CONFIGURED_HOSTS
```

## Ubuntu 部署参考

生产环境建议把 FastAPI 后端作为 systemd 服务运行，前端用 Vite build 后交给 Nginx 静态托管。不要把 Nikki 密钥或代理账号写进 Git；在控制台页面填写后点 `保存配置`，配置会留在浏览器 localStorage 中。

安装基础环境：

```bash
sudo apt update
sudo apt install -y git curl nginx python3 python3-venv python3-pip
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

拉取代码并安装依赖：

```bash
sudo mkdir -p /opt/daoyufan /var/lib/daoyufan
sudo chown -R "$USER":"$USER" /opt/daoyufan /var/lib/daoyufan
git clone git@github.com:since25/daohuanmeng.git /opt/daoyufan
cd /opt/daoyufan
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd frontend
npm ci
VITE_API_BASE=/api npm run build
```

创建后端 systemd 服务：

```bash
sudo tee /etc/systemd/system/daoyufan-api.service >/dev/null <<'EOF'
[Unit]
Description=DaoyuFan Console API
After=network.target

[Service]
WorkingDirectory=/opt/daoyufan
ExecStart=/opt/daoyufan/.venv/bin/python run_backend.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
Environment=DAOYUFAN_HOST=127.0.0.1
Environment=DAOYUFAN_PORT=8765
Environment=DAOYUFAN_DB_PATH=/var/lib/daoyufan/console.sqlite3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now daoyufan-api
```

配置 Nginx：

```bash
sudo tee /etc/nginx/sites-available/daoyufan >/dev/null <<'EOF'
server {
    listen 80;
    server_name _;

    root /opt/daoyufan/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8765/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/daoyufan /etc/nginx/sites-enabled/daoyufan
sudo nginx -t
sudo systemctl reload nginx
```

更新部署：

```bash
cd /opt/daoyufan
git pull
.venv/bin/python -m pip install -r requirements.txt
cd frontend
npm ci
VITE_API_BASE=/api npm run build
sudo systemctl restart daoyufan-api
sudo nginx -t
sudo systemctl reload nginx
```

如果 Ubuntu 服务器不在 Nikki 网关所在内网，页面里的 `文章处理代理` 和 `Nikki API` 必须填写服务器可访问的地址；`127.0.0.1` 在服务器上指的是 Ubuntu 自己，不是你的 Mac。
