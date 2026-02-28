# OpenClaw on Hugging Face Spaces — 从源码构建
# 文档: https://huggingface.co/docs/hub/spaces-sdks-docker

FROM node:22-bookworm

# Force rebuild - upload_folder persistence v9
RUN echo "clean-build-v9-upload-folder-$(date +%s)"

# 构建依赖（包含 Python3 以便使用 huggingface_hub 做 Dataset 持久化）
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir --break-system-packages huggingface_hub

RUN corepack enable
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

WORKDIR /app
RUN git clone --depth 1 https://github.com/openclaw/openclaw.git openclaw
WORKDIR /app/openclaw

# 补丁：仅在实际成功解析消息 body 并即将投递回复时记录 inbound，
# 避免解密失败（Bad MAC）的消息被误计为已接收导致 lastInboundAt 有值但无法回复
COPY patches /app/patches
RUN if [ -f /app/patches/web-inbound-record-activity-after-body.patch ]; then patch -p1 < /app/patches/web-inbound-record-activity-after-body.patch; fi

RUN pnpm install --frozen-lockfile
RUN pnpm build
ENV OPENCLAW_PREFER_PNPM=1
RUN pnpm ui:build

# 验证构建产物完整（包含 Telegram 和 WhatsApp 扩展）
RUN test -f dist/entry.js && echo "[build-check] dist/entry.js OK" \
 && test -f dist/plugin-sdk/index.js && echo "[build-check] dist/plugin-sdk/index.js OK" \
 && test -d extensions/telegram && echo "[build-check] extensions/telegram OK" \
 && test -d extensions/whatsapp && echo "[build-check] extensions/whatsapp OK" \
 && test -d dist/control-ui && echo "[build-check] dist/control-ui OK"

# 向 Control UI 注入自动 token 配置（让浏览器自动连接，无需手动输入 token）
RUN python3 << 'PYEOF'
import pathlib
p = pathlib.Path('dist/control-ui/index.html')
script = '<script>!function(){var K="openclaw.control.settings.v1";try{var s=JSON.parse(localStorage.getItem(K)||"{}")||{};if(!s.token){s.token="openclaw-space-default";localStorage.setItem(K,JSON.stringify(s))}}catch(e){}}()</script>'
h = p.read_text()
p.write_text(h.replace('</head>', script + '</head>'))
print('[build-check] Token auto-config injected into Control UI')
PYEOF

# 不修改内部代码，改用外部 WebSocket 监护脚本处理 515 重连

ENV NODE_ENV=production
# 禁用 bundled 插件发现（改由 global symlink 提供）；用空目录替代 /dev/null 避免 ENOTDIR 警告
RUN mkdir -p /app/openclaw/empty-bundled-plugins
ENV OPENCLAW_BUNDLED_PLUGINS_DIR=/app/openclaw/empty-bundled-plugins
RUN chown -R node:node /app

# 创建 ~/.openclaw 目录结构
RUN mkdir -p /home/node/.openclaw/workspace /home/node/.openclaw/credentials
# Note: openclaw.json is NOT copied here - it will be restored from Dataset by openclaw_sync.py
# The new persistence system backs up and restores the entire ~/.openclaw directory

# 持久化脚本（完整目录备份） & DNS 修复
COPY --chown=node:node scripts /home/node/scripts
COPY --chown=node:node openclaw.json /home/node/scripts/openclaw.json.default
RUN chmod +x /home/node/scripts/entrypoint.sh
RUN chmod +x /home/node/scripts/sync_hf.py
RUN chown -R node:node /home/node

USER node
ENV HOME=/home/node
ENV PATH="/home/node/.local/bin:$PATH"
WORKDIR /home/node

CMD ["/home/node/scripts/entrypoint.sh"]
