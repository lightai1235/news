# 拓界 OpenMind

> **Fork 后第一件事**：到仓库 **Actions** 页手动启用 workflows（GitHub 对 fork 默认禁用 schedule），
> 并在 **Settings → Pages → Source** 选择 **GitHub Actions**。

每天从维基百科 Good/Featured articles 与中文典范/优良条目中随机抽 **3 个非虚构词条**（领域互异、180 天不重复），汇聚全网信源评出每词条 **Top-10 高质量内容**，渲染成纯静态站点发布到 GitHub Pages。

- 无推荐算法、无「猜你喜欢」、无埋点、无无限滚动——每天只有 3 张卡片，看完即止。
- 零密钥可跑（维基外链信源）；配 API key 后信源矩阵逐步增强。
- git 即数据库：`served.json` 与 `site/` 在同一次 commit 内更新，失败天然回滚。

## 在线地址

`https://lightai1235.github.io/news/`

## 本地运行

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Windows；Linux 用 .venv/bin/pip
.venv/Scripts/pip install -e . --no-deps

python -m openmind pool --refresh        # 首次建池（约 1.5 万条，需外网）
python -m openmind run --date 2026-11-19 # 生成一期
python -m http.server 8000 --directory site/
```

需要外网时可使用本地代理：

```powershell
$env:http_proxy="http://127.0.0.1:1081"; $env:https_proxy="http://127.0.0.1:1081"
```

### CLI

| 命令 | 说明 |
| --- | --- |
| `python -m openmind pool [--refresh]` | 构建/刷新候选池（>7 天自动刷新） |
| `python -m openmind run [--date YYYY-MM-DD] [--force] [--stage S]` | 生成一期；默认今天；同日已存在则跳过；`--stage` 断点调试（sample/wiki/queries/discover/score/brief/render） |

## 可选 API key（GitHub Secrets）

| Secret | 用途 |
| --- | --- |
| `SERPER_API_KEY` / `BRAVE_API_KEY` / `TAVILY_API_KEY` | 搜索引擎信源（任一即可） |
| `YOUTUBE_API_KEY` | YouTube 视频信源 |
| `X_BEARER_TOKEN` | X Recent Search |
| `LLM_API_KEY` | 查询扩展 + 中文导读 + 批量合规复核 |

缺 key 不报错：对应信源自动跳过并记入 `health.json`。

## 自动化

- `.github/workflows/daily.yml`：UTC 00:00（= 北京 08:00）定时 + 手动 dispatch；生成 → commit/push → deploy-pages。
- `.github/workflows/ci.yml`：push/PR 跑 pytest + ruff（Python 3.12）。
- 公开仓库 60 天无活动会停用 schedule；每日 commit 即活动。

## 合规

三层过滤：话题级 `state/denylist_topics.txt`（用户自维护）、条目级虚构排除（小说/影视/游戏作品）、来源级 `state/denylist_domains.txt` 一票否决 + `allowlist_domains.txt` 权威加分。所有判定输出理由日志。

## 开发

```bash
pytest tests/ -q
ruff check src/ tests/
```

设计依据：`SPEC.md`；任务分解：`tasks/plan.md` / `tasks/todo.md`。
