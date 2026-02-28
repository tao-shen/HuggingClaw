# OpenClaw 持久化存储配置指南

## 概述

本配置实现了 OpenClaw 在 Hugging Face Space 中的**完整持久化存储**，确保容器重启后所有状态都能恢复。

### 核心特性

- **完整目录备份**: 持久化整个 `~/.openclaw` 目录
- **原子操作**: 使用 tar.gz 归档确保备份一致性
- **自动轮转**: 保留最近 5 个备份，自动清理旧备份
- **优雅关闭**: 容器停止时自动执行最终备份

---

## 持久化的目录和文件

### 1. 核心配置
```
~/.openclaw/
├── openclaw.json              # 主配置文件（模型、插件、网关设置）
└── credentials/               # 所有渠道的登录凭证
    ├── whatsapp/
    │   └── default/
    │       └── auth_info_multi.json
    └── telegram/
        └── session.data
```

### 2. 工作空间
```
~/.openclaw/workspace/
├── AGENTS.md                 # 代理定义
├── SOUL.md                   # 灵魂（性格、说话风格）
├── TOOLS.md                  # 可用工具列表
├── MEMORY.md                 # 长期聚合记忆
├── memory/                   # 每日记忆文件
│   ├── 2025-01-15.md
│   └── 2025-01-16.md
└── skills/                   # 技能定义
    ├── my-skill/
    │   └── SKILL.md
    └── ...
```

### 3. 会话历史
```
~/.openclaw/agents/<agentId>/sessions/
├── <sessionId>.jsonl          # 每个会话的完整对话历史
└── sessions.json             # 会话索引
```

### 4. 记忆索引（SQLite）
```
~/.openclaw/memory/
└── <agentId>.sqlite          # 语义搜索索引
```

### 5. QMD 后端（如果启用）
```
~/.openclaw/agents/<agentId>/qmd/
├── xdg-config/              # QMD 配置
├── xdg-cache/               # QMD 缓存
└── sessions/                # QMD 会话导出
```

---

## 排除的文件/目录

以下内容**不会**被持久化（临时文件、缓存、锁文件）：

- `*.lock` - 锁文件
- `*.tmp` - 临时文件
- `*.socket` - Unix socket 文件
- `*.pid` - PID 文件
- `node_modules/` - Node 依赖
- `.cache/` - 缓存目录
- `logs/` - 日志目录

---

## 环境变量配置

在 Hugging Face Space 的 Settings > Variables 中设置：

| 变量名 | 必需 | 默认值 | 说明 |
|--------|------|--------|------|
| `HF_TOKEN` | ✅ | - | Hugging Face 访问令牌（需要写入权限） |
| `OPENCLAW_DATASET_REPO` | ✅ | - | 数据集仓库 ID，如 `username/openclaw-state` |
| `OPENCLAW_HOME` | ❌ | `~/.openclaw` | OpenClaw 主目录 |
| `SYNC_INTERVAL` | ❌ | `300` | 自动备份间隔（秒） |
| `ENABLE_AUX_SERVICES` | ❌ | `false` | 是否启用辅助服务（WA Guardian, QR Manager） |

### 快速配置步骤

1. **创建数据集仓库**
   ```
   在 Hugging Face 上创建一个新的 Dataset 仓库，例如：username/openclaw-state
   设置为 Private（私有）
   ```

2. **获取访问令牌**
   ```
   访问：https://huggingface.co/settings/tokens
   创建新 Token，勾选 "Write" 权限
   ```

3. **配置 Space 变量**
   ```
   HF_TOKEN = hf_xxxxx...（你的 Token）
   OPENCLAW_DATASET_REPO = username/openclaw-state（你的数据集 ID）
   ```

---

## 脚本说明

### openclaw_persist.py

核心持久化模块，提供备份和恢复功能。

```bash
# 备份当前状态
python3 openclaw_persist.py save

# 恢复状态
python3 openclaw_persist.py load

# 查看状态
python3 openclaw_persist.py status
```

### openclaw_sync.py

主同步管理器，被 entrypoint.sh 调用。

功能：
1. 启动时从数据集恢复状态
2. 启动 OpenClaw 网关
3. 后台定期备份
4. 优雅关闭时执行最终备份

---

## 备份文件命名

备份数据集中的文件命名格式：

```
backup-YYYYMMDD_HHMMSS.tar.gz
```

例如：`backup-20250116_143022.tar.gz`

系统会自动保留最近 5 个备份，删除更旧的。

---

## 故障排除

### 备份失败

1. 检查 `HF_TOKEN` 是否有写入权限
2. 检查 `OPENCLAW_DATASET_REPO` 是否正确
3. 查看日志中的错误信息

### 恢复失败

1. 数据集为空是正常的（首次运行）
2. 检查网络连接
3. 尝试手动恢复：`python3 openclaw_persist.py load`

### WhatsApp 凭证丢失

备份包含 WhatsApp 凭证，恢复后应该能自动连接。如果需要重新扫码：

1. 登录 Hugging Face Space
2. 在日志中查找二维码
3. 使用手机 WhatsApp 扫码登录

---

## 与原 sync_hf.py 的区别

| 特性 | sync_hf.py | openclaw_sync.py |
|------|------------|------------------|
| 同步方式 | 逐文件夹同步 | 完整目录 tar 归档 |
| 配置复杂度 | 高（需映射路径） | 低（自动处理） |
| 原子性 | 否 | 是 |
| 回滚能力 | 无 | 有（保留 5 个备份） |
| 文件完整性 | 部分 | 完整 |

---

## 手动备份/恢复命令

### 本地测试

```bash
# 设置环境变量
export HF_TOKEN="hf_..."
export OPENCLAW_DATASET_REPO="username/openclaw-state"

# 手动备份
cd /home/node/scripts
python3 openclaw_persist.py save

# 手动恢复
python3 openclaw_persist.py load

# 查看状态
python3 openclaw_persist.py status
```

---

## 技术实现细节

### 备份过程

1. 检查 `~/.openclaw` 目录
2. 创建 tar.gz 归档（应用排除规则）
3. 上传到 Hugging Face Dataset
4. 旋转备份（保留最近 5 个）
5. 更新本地状态文件

### 恢复过程

1. 从数据集获取最新备份
2. 下载到临时目录
3. 如有本地状态，先创建本地备份
4. 解压到 `~/.openclaw`
5. 验证文件完整性

### 排除规则

```python
EXCLUDE_PATTERNS = [
    "*.lock", "*.tmp", "*.pyc", "*__pycache__*",
    "*.socket", "*.pid", "node_modules", ".DS_Store", ".git",
]

SKIP_DIRS = {".cache", "logs", "temp", "tmp"}
```

---

## 更新日志

- **v8** (2025-01-16): 实现完整目录持久化，使用 tar 归档方式
- **v7** (之前): 使用 sync_hf.py 逐文件夹同步
