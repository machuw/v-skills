# v-skills

`v-skills` 收藏来自外部仓库的 Claude / Codex skills，并把选中的 skill 以软链接的形式铺到本机的 skill 目录下：

- `~/.claude/skills/`
- `~/.codex/skills/`

外部仓库以 `git submodule` 形式存放在 `sources/` 下，改动留在上游；这个仓库只负责三件事：
提交子模块指针、维护一份「挑选哪些 skill」的配置、以及一个跑起来做同步的脚本。

## 仓库结构

```
sources/                 # 上游 skill 仓库（submodule，只读）
config/skill-sync.yaml   # 每个仓库的 whitelist / blacklist
scripts/sync_skills.py   # 同步脚本
tests/test_sync_skills.py
docs/superpowers/specs/  # 设计规范（同步工具行为以此为准）
docs/superpowers/plans/  # 实施计划
```

目前跟踪的 skill 仓库（见 `.gitmodules`）：

- `sources/obsidian-skills` — skill 放在 `skills/<name>/SKILL.md`
- `sources/axton-obsidian-visual-skills` — skill 直接在仓库根下：`<name>/SKILL.md`

同步脚本会自动识别这两种布局。

## 初次使用

```bash
# 克隆时连带拉下所有子模块
git clone --recurse-submodules <this-repo-url>

# 或者已经克隆过主仓库，再单独初始化子模块
git submodule update --init --recursive
```

## 运行同步

从仓库根目录执行：

```bash
python3 scripts/sync_skills.py
```

脚本会：

1. 读取 `config/skill-sync.yaml`；
2. 扫描每个被配置的 `sources/<repo>/`，按规则挑出 skill；
3. 在 `~/.claude/skills/<skill>` 和 `~/.codex/skills/<skill>` 下创建指向
   `sources/<repo>/.../<skill>/` 目录的软链接（不是复制，也不是只链 `SKILL.md`，
   这样 skill 目录里的 `assets/`、`references/` 都能解析到）；
4. 清理上一次由自己创建、本次已不再选中的旧链接；
5. 把本次创建/更新的条目写进本机清单文件（见下文）。

不需要 root、不依赖第三方库：如果系统里装了 PyYAML 会用它，没有也能跑——
脚本自带一个只支持当前配置形状的简易 YAML 解析器。

## 配置 `config/skill-sync.yaml`

```yaml
sources:
  obsidian-skills:
    whitelist: []          # 为空或省略 = 选中该仓库下的全部 skill
    blacklist:
      - json-canvas        # 即使 whitelist 里有，这里列出的也会被排除

  axton-obsidian-visual-skills:
    whitelist:
      - excalidraw-diagram
      - mermaid-visualizer
    blacklist: []
```

规则：

- 没在 `sources` 里出现的仓库会被跳过（不删不加）。
- `whitelist` 为空 → 选中该仓库下全部发现到的 skill；非空 → 只选中列出的。
- `blacklist` 永远在最后减一遍。
- `whitelist` / `blacklist` 里写了不存在的 skill 名，会直接报错退出——这是有意的，防止配置错别字静默失效。

## 本机清单（manifest）

脚本需要区分「自己创建的链接」和「你手工放进去的文件」，为此维护一份本机清单：

```
$XDG_STATE_HOME/v-skills/skill-sync-manifest.json
# 未设置 XDG_STATE_HOME 时落在：
~/.local/state/v-skills/skill-sync-manifest.json
```

它是本机状态，**不要提交进仓库**。脚本只会删除/覆盖清单里记录过的条目，
目标目录里其它文件或链接一律不碰。

会让脚本非零退出的情况：配置格式错误、配置里指定的仓库目录不存在、
不同仓库产生了同名 skill、目标路径已存在但不是本工具记录的软链接。
这些保护是刻意的——宁可报错，也不要默默覆盖你手工放的东西。

## 跑测试

```bash
python3 -m unittest discover -s tests
```

测试用 `tempfile` 构造临时仓库布局和 HOME 目录，不会污染 `~/.claude` 或 `~/.codex`。

## 维护子模块

```bash
# 添加一个新的 skill 上游仓库
git submodule add <git-url> sources/<repo-name>
git commit -m "chore: add skill source <repo-name>"

# 把所有子模块拉到各自远程的最新提交
git submodule update --remote --merge
git add .gitmodules sources/
git commit -m "chore: update skill sources"

# 只更新一个子模块
cd sources/<repo-name> && git pull
cd ../.. && git add sources/<repo-name>
git commit -m "chore: update <repo-name>"
```

### 把误加的嵌套仓库改成子模块

如果曾经直接 `git add` 过一个独立仓库目录，先从索引里摘掉再按子模块方式重加：

```bash
git rm --cached -r sources/<repo-name>
git submodule add <url> sources/<repo-name>
git commit -m "chore: convert embedded repo to submodule"
```

`git submodule add` 因为目录已存在而失败时，先把原目录挪走或删掉再重新添加。
