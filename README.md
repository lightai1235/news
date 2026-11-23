# 拓界 OpenMind

> **Fork 后第一件事**：到仓库 **Actions** 页手动启用 workflows（GitHub 对 fork 默认禁用 schedule），
> 并在 **Settings → Pages → Source** 选择 **GitHub Actions**。

每天从维基百科 Good/Featured articles 与中文典范/优良条目中随机抽 **3 个非虚构词条**（领域互异、180 天不重复），汇聚全网信源评出每词条 **Top-10 高质量内容**，渲染成纯静态站点发布到 GitHub Pages。

- 无推荐算法、无「猜你喜欢」、无埋点、无无限滚动——每天只有 3 张卡片，看完即止。
- 零密钥可跑：维基外链/参考文献 + arXiv/PubMed + HN/Reddit + DuckDuckGo + bilibili/搜狗微信 + X（DDG 降级）；配 API key 后追加 Serper/Brave/Tavily 搜索与 YouTube 视频元数据。
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

三层过滤：话题级 `state/denylist_topics.b64`（用户自维护，base64 编码）、条目级虚构排除（小说/影视/游戏作品）、来源级 `state/denylist_domains.txt` 一票否决 + `allowlist_domains.txt` 权威加分。所有判定输出理由日志。最终推出的 3 个词条在发布前还会做全文复核（原文 + 中文译文），命中黑名单自动换备用词条。

### 维护话题黑名单

黑名单以 base64 存储（每行一个关键词或条目名，匹配不区分大小写）。修改流程：

```bash
# 1. 解码现有名单到临时文件
python -c "import base64,pathlib; pathlib.Path('topics.txt').write_bytes(base64.b64decode(pathlib.Path('state/denylist_topics.b64').read_text().strip()))"

# 2. 编辑 topics.txt（每行一个词，# 开头为注释）

# 3. 重新编码回去（注释与空行自动剔除）
python -c "import base64,pathlib; lines=[l.strip() for l in pathlib.Path('topics.txt').read_text(encoding='utf-8').splitlines() if l.strip() and not l.strip().startswith('#')]; pathlib.Path('state/denylist_topics.b64').write_text(base64.b64encode('\n'.join(lines).encode('utf-8')).decode('ascii')+'\n', encoding='ascii')"

# 4. 删除临时明文文件
rm topics.txt
```

解码失败时程序会降级读取明文 `state/denylist_topics.txt`（若存在），两者皆无则话题过滤为空。

## 开发

```bash
pytest tests/ -q
ruff check src/ tests/
```
