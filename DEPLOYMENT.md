# yangbin 实例部署

本项目保留上游来源信息，当前维护及部署名称为 `yangbin`。Java 包和 Go 模块路径已同步改名；本实例运行 Python 后端和 Vue 前端。

## 构建

```powershell
cd frontend
npm ci
npm run build
```

前端默认使用同源 `/api`；本地 Vite 将请求代理到 8567。生产环境由 Python 服务同时提供 `frontend/dist` 和 API，因此登录 Cookie、SSE 不需要跨域配置。

## Linux 用户目录安装

推荐目录结构为 `~/apps/yangbin-passage/{app,runtime,data,logs,run}`。不需要 sudo 或 Docker。服务器需已有 MariaDB 服务端二进制及 `mysql_install_db`；脚本只复用程序，使用自己的数据目录、账号和端口。conda 的 `mariadb` 包是 Python 连接器，不能替代服务端。

```bash
ROOT="$HOME/apps/yangbin-passage"
mkdir -p "$ROOT/app"
conda create -y -p "$ROOT/runtime" --override-channels -c conda-forge python=3.12 redis-server=7 supervisor uv
# 将项目的 python-backend、frontend/dist、sql、deploy 放入 $ROOT/app
cd "$ROOT/app/python-backend"
"$ROOT/runtime/bin/uv" sync --frozen --no-dev --python "$ROOT/runtime/bin/python"
"$ROOT/app/python-backend/.venv/bin/python" "$ROOT/app/deploy/service.py" setup
```

默认只监听 `127.0.0.1:18567`。受控内网可在 setup 时指定 `--bind 0.0.0.0`。数据库及 Redis 分别只监听本机 13307、16380。

初次安装建立独立数据目录和完整表结构，去掉 SQL 中的演示账号，建立 `yangbin` 管理员。随机管理员密码保存在部署根目录 `secrets.json`，权限为 600。不要提交或公开该文件。已有实例再次执行 setup 会复用数据和凭据；正常更新使用 restart，不重复执行 SQL 迁移。

## 模型与可选服务

编辑服务器 `app/python-backend/.env`：

```dotenv
DASHSCOPE_API_KEY=your-private-key
DASHSCOPE_MODEL=qwen-plus
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

以上字段也支持兼容 Chat Completions 的其他服务，需将 Base URL、模型名及 Key 配套填写。没有模型密钥时可以登录和管理文章，创建文章会明确提示未配置，不消耗配额。

Pexels、Gemini 生图、腾讯云 COS、Stripe 需各自配置；未启用的图片服务使用已有降级策略。没有 COS 配置时 URL 图片保留原链接；字节类型图片不具备持久化存储，会降级。Mermaid CLI 需要另行安装。支付未配置时不能购买会员。

## 运维及验证

```bash
ROOT="$HOME/apps/yangbin-passage"
PY="$ROOT/app/python-backend/.venv/bin/python"
"$PY" "$ROOT/app/deploy/service.py" status
"$PY" "$ROOT/app/deploy/service.py" restart
"$PY" "$ROOT/app/deploy/service.py" stop
"$PY" "$ROOT/app/deploy/service.py" start
"$PY" "$ROOT/app/deploy/verify.py"
# 接通模型后，生成一篇真实文章（会调用模型并产生服务商费用）
"$PY" "$ROOT/app/deploy/verify.py" --live
```

Supervisor 负责进程异常退出后的自动恢复。`setup` 不会修改系统服务或 crontab。运行 `deploy/install_autostart.py` 会追加一条用户级 `@reboot`，保留已有条目并备份原 crontab；本次实例已配置，整机重启恢复尚未实测。

API 日志在 `logs/api.log`，数据库日志在 `logs/mysql-error.log`。更新前备份 `data/`、`secrets.json` 和 `.env`，替换代码及前端资源、同步依赖后重启 API。Python 仅运行一个 worker，确保内存 SSE 通道和异步任务位于同一进程。

## 盐值改名

Java、Go、Python 示例配置的密码盐值统一为 `yangbin`，SQL 演示账号密码哈希已按 `MD5(12345678 + yangbin)` 更新。已有使用其他盐值生成密码的数据库不能通过直接替换配置完成密码迁移；应保留原盐值或执行密码重置。本次新实例使用独立数据库。

## 已有私有模型配置导入

如果已有包含 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 的服务器私有 JSON，可在获得该配置所有者授权后执行 `deploy/configure_model.py /path/to/private-model-config.json`，然后重启 API。脚本只在服务器内部更新 `.env`，不回显密钥。

本次验证结果见 [DEPLOYMENT-VALIDATION.md](DEPLOYMENT-VALIDATION.md)。
