---
title: HuggingClaw
emoji: 🔥
colorFrom: gray
colorTo: yellow
sdk: docker
pinned: false
license: mit
short_description: HuggingClaw
app_port: 7860
---

## 初始化与运行

### 克隆仓库

```bash
git clone https://huggingface.co/spaces/tao-shen/HuggingClaw
cd HuggingClaw
```

### 在 Hugging Face Space 上运行

1. Fork 或使用本 Space，在 **Settings → Repository secrets** 中配置：
   - `HF_TOKEN`：具有写权限的 HF Access Token
   - `OPENCLAW_DATASET_REPO`：用于持久化的 Dataset 仓库（如 `username/openclaw-backup`）
2. 重新启动 Space 即可。

### 本地 Docker 运行（可选）

1. 复制环境变量模板并填写必填项：
   ```bash
   cp .env.example .env
   # 编辑 .env，至少填写 HF_TOKEN 和 OPENCLAW_DATASET_REPO
   ```
2. 构建并运行（需先安装 Docker）：
   ```bash
   docker build -t huggingclaw .
   docker run --rm -p 7860:7860 --env-file .env huggingclaw
   ```
3. 浏览器访问 `http://localhost:7860`。

---

## Environment Variables

### Persistence (Required)
- `HF_TOKEN` - Hugging Face access token with write permissions
- `OPENCLAW_DATASET_REPO` - Dataset repository for backup (e.g., `username/dataset-name`)

### Telegram Bot (Optional)
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
- `TELEGRAM_BOT_NAME` - Bot username
- `TELEGRAM_ALLOW_USER` - Your Telegram username to allow

### Optional
- `SYNC_INTERVAL` - Seconds between syncs (default: 120)
- `ENABLE_AUX_SERVICES` - Enable aux services (default: false)
