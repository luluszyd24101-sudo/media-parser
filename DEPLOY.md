# 短视频去水印 API + 微信小程序 — 完整部署指南

> 项目结构：后端（Python Flask） + 前端（微信小程序）
>
> 仓库：
> - 后端：`github.com/luluszyd24101-sudo/media-parser`
> - 前端：`github.com/luluszyd24101-sudo/media-parser-app`

---

## 目录

- [第零步：准备工作](#第零步准备工作)
- [第一步：部署后端到云服务器](#第一步部署后端到云服务器)
- [第二步：配置小程序前端](#第二步配置小程序前端)
- [第三步：微信小程序发布流程](#第三步微信小程序发布流程)
- [第四步：开通流量主](#第四步开通流量主)
- [常见问题](#常见问题)

---

## 第零步：准备工作

### 你需要准备的

| 项目 | 最低配置 | 预算 |
|------|---------|------|
| **云服务器** | 1核2G，Linux | 30-50元/月 |
| **域名** | 已备案（国内服务器必需） | 30-50元/年 |
| **微信小程序账号** | 个人或企业 | 个人免费（企业300元/年） |

### 推荐服务器

- **阿里云** ECS 轻量应用服务器（1核2G，约 34元/月）
- **腾讯云** 轻量服务器（1核2G，约 30元/月）
- **雨云** 等小众厂商（有时更便宜）

> ⚠️ **重要**：微信小程序要求所有请求必须是 **HTTPS**，所以需要域名 + 备案 + SSL 证书。

---

## 第一步：部署后端到云服务器

有两种方式，推荐 **方式一（Docker）**。

### 方式一：Docker 部署（推荐）

#### 1. 安装 Docker

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
sudo systemctl enable docker

# 验证
docker --version
```

#### 2. 拉取代码

```bash
git clone https://github.com/luluszyd24101-sudo/media-parser.git
cd media-parser
```

#### 3. 配置环境变量

```bash
cp .env.example .env
vim .env
```

填写以下内容：

```ini
SECRET_KEY=这里填一个随机字符串，不要太短
DOMAIN=https://你的域名.com

# 小红书 Cookie（登录后从浏览器复制）
XIAOHONGSHU_COOKIE=a1=xxxx; webId=xxxx

# 快手 Cookie（非必需，有则填）
KUAISHOU_COOKIE=kpf=PC_WEB; ...
```

#### 4. 启动服务

```bash
docker-compose up -d
```

服务将运行在 `0.0.0.0:8051`

#### 5. 配置 Nginx 反代 + SSL

> 如果你有域名且已备案，用 Nginx 反代并配置 HTTPS。

```bash
# 安装 Nginx
apt install nginx -y

# 配置
vim /etc/nginx/sites-available/media-parser
```

写入：

```nginx
server {
    listen 80;
    server_name 你的域名.com;

    # 申请 SSL 证书后改成 443
    location / {
        proxy_pass http://127.0.0.1:8051;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        # 视频流支持
        proxy_buffering off;
    }

    # 文件上传/下载大小限制
    client_max_body_size 50M;
}
```

启用配置：

```bash
ln -s /etc/nginx/sites-available/media-parser /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

#### 6. 申请 SSL 证书（免费）

```bash
apt install certbot python3-certbot-nginx -y
certbot --nginx -d 你的域名.com
```

> 证书自动续期，不需要手动管。

#### 7. 验证

```bash
curl https://你的域名.com/
# 返回: {"status": "ok", "message": "Media Parser API is running"}

curl -X POST https://你的域名.com/api/parse \
  -H "Content-Type: application/json" \
  -d '{"text": "https://www.bilibili.com/video/BV1GJ411x7dQ"}'
# 返回解析结果
```

---

### 方式二：手动部署（不用 Docker）

```bash
# 安装 Python 3.11+
apt install python3 python3-pip python3-venv -y

# 克隆代码
git clone https://github.com/luluszyd24101-sudo/media-parser.git
cd media-parser

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
vim .env

# 使用 Gunicorn 启动
gunicorn -w 3 -b 0.0.0.0:8051 app:app --daemon
```

配置 systemd 实现开机自启：

```bash
vim /etc/systemd/system/media-parser.service
```

```ini
[Unit]
Description=Media Parser API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/media-parser
EnvironmentFile=/root/media-parser/.env
ExecStart=/root/media-parser/venv/bin/gunicorn -w 3 -b 0.0.0.0:8051 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable media-parser
systemctl start media-parser
```

---

## 第二步：配置小程序前端

### 1. 下载代码

```bash
git clone https://github.com/luluszyd24101-sudo/media-parser-app.git
```

### 2. 修改 API 地址

打开 `utils/config.js`，把 `baseURL` 改成你的服务器域名：

```js
const config = {
  baseURL: 'https://你的域名.com',   // ← 改成你的
  timeout: 15000,
  maxRetries: 1
};
```

### 3. 在微信开发者工具中打开

1. 打开 **微信开发者工具**
2. 选择「导入项目」
3. 选择 `media-parser-app` 文件夹
4. 填入小程序的 **AppID**（在微信公众平台获取）
5. 点击导入

### 4. 配置域名白名单

在 **微信公众平台** → **开发管理** → **服务器域名** 中添加：

| 类型 | 域名 |
|------|------|
| request | `https://你的域名.com` |

> ⚠️ 不加这一步，小程序请求会被拦截

### 5. 本地调试

在开发者工具中点击「预览」，用手机扫码即可在真机上测试。

---

## 第三步：微信小程序发布流程

### 1. 注册小程序账号

1. 前往 https://mp.weixin.qq.com 注册
2. 选择「小程序」
3. 个人开发者注册（免费）
4. 完成实名认证

### 2. 获取 AppID

在公众平台 → 开发管理 → 开发设置 → 复制 AppID

### 3. 提交审核

1. 开发者工具 → 上传
2. 登录公众平台 → 版本管理 → 提交审核
3. 审核通常 1-3 天

### 4. 注意事项

| 事项 | 说明 |
|------|------|
| **类目** | 选择「**工具**」类，审核最快 |
| **ICP 备案** | 小程序需要备案（有域名即可）|
| **用户隐私协议** | 需要在后台填写（复制模板改一下） |
| **不要提"去水印"** | 审核时如被问，说是"视频解析工具" |

---

## 第四步：开通流量主

### 条件

- 累计独立访客（UV）≥ **1000** 人
- 满足后可以在公众平台 → 流量主 → 开通

### 广告位类型

| 类型 | 说明 | 适合位置 |
|------|------|---------|
| **Banner 广告** | 底部或中间横幅 | 解析结果下方 |
| **激励视频广告** | 看完视频获得奖励 | 解析前/下载前（推荐） |
| **插屏广告** | 页面切换时弹出 | 解析成功后 |
| **视频贴片广告** | 视频播放前 | 视频预览前 |

### 收入预估

| 日 UV | 月收入（预估） |
|-------|--------------|
| 100-300 | 20-80 元 |
| 300-1000 | 80-300 元 |
| 1000-3000 | 300-1000 元 |

### 广告代码接入指南

**Banner 广告** — 在页面合适位置加入：

```html
<!-- 在 index.wxml 结果区下面加入 -->
<ad unit-id="你的广告单元ID" type="banner" binderror="onAdError"></ad>
```

**激励视频广告** — 在下载前弹出：

```js
// 在 index.js 中添加
let videoAd = null;
Page({
  onLoad() {
    // 创建激励视频广告
    if (wx.createRewardedVideoAd) {
      videoAd = wx.createRewardedVideoAd({ adUnitId: '你的激励视频ID' });
      videoAd.onClose((res) => {
        if (res && res.isEnded) {
          // 用户看完广告，开始下载
          this.doDownload();
        }
      });
    }
  },
  saveVideo() {
    if (videoAd) {
      videoAd.show().catch(() => this.doDownload());
    } else {
      this.doDownload();
    }
  },
  doDownload() {
    // 原来的下载逻辑
  }
});
```

---

## 常见问题

### Q: 抖音解析失败怎么办？

抖音官方 API 可能因风控失效，解析器会自动切换到第三方 API 兜底。如果仍失败，可能原因：
- 视频已被删除
- 短视频平台改了接口 — 需要更新解析器

### Q: 小红书需要 Cookie，怎么获取？

1. 浏览器打开 `xiaohongshu.com` 并登录
2. 按 F12 → Network → 刷新页面
3. 点击任意请求 → Headers → 复制 Cookie
4. 设置到环境变量 `XIAOHONGSHU_COOKIE`

### Q: B站的视频链接为什么是服务器的地址？

B站视频有防盗链，不能直接返回原始链接。解析器会把视频下载到服务器本地，再返回你的域名地址。

### Q: 服务器存储空间够吗？

B站解析会下载视频到 `static/videos/` 目录，建议：
- 定期清理：`find static/videos -type f -mtime +1 -delete`
- 或用 cron 每天凌晨清理一次

### Q: 小程序审核被拒怎么办？

常见原因和处理：
- **"涉及视频下载"** → 修改描述为"视频解析工具，用于在线预览"
- **"需要用户协议"** → 在公众平台填写隐私协议
- **"类目不符"** → 选「工具 - 信息查询」

---

## 维护清单

| 频率 | 操作 |
|------|------|
| 每天 | 清理 `static/videos/` 缓存文件 |
| 每周 | 检查 API 是否正常返回 |
| 每月 | 更新抖音/快手/小红书 Cookie（可能过期） |
| 按需 | 解析器升级（平台接口变更时） |

---

> 有任何问题，在 GitHub 提 Issue 或联系开发者。
