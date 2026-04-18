# v-skills

`v-skills` 用来收藏外部 skill 仓库的来源，并通过 `git submodule` 跟踪它们的上游更新。

## 为什么用 `git submodule`

不要直接把另一个 Git 仓库当普通目录 `git add` 进当前仓库。那样会出现“仓库里套仓库”的提示，而且外层仓库不会正确记录内部仓库的来源和更新方式。

`git submodule` 适合这个场景：

- 外部 skill 仓库仍然保持独立
- 当前仓库只记录它的 URL 和锁定的提交版本
- 之后可以继续从上游更新

## 添加一个外部 skill 仓库

建议统一放在 `sources/` 目录下：

```bash
git submodule add https://github.com/owner/repo.git sources/repo-name
git commit -m "chore: add skill source repo-name"
```

执行后：

- 当前仓库会新增或更新 `.gitmodules`
- `sources/repo-name` 会成为一个子模块目录
- 主仓库记录这个子模块当前对应的提交

## 首次拉取仓库

如果是首次克隆这个仓库，直接把子模块一起拉下来：

```bash
git clone --recurse-submodules <your-v-skills-url>
```

如果已经克隆过主仓库，再初始化子模块：

```bash
git submodule update --init --recursive
```

## 更新已收藏的外部仓库

把所有子模块更新到各自远程分支的最新状态：

```bash
git submodule update --remote --merge
```

更新后，主仓库里记录的“子模块提交指针”会发生变化，所以还需要提交一次：

```bash
git add .gitmodules sources/
git commit -m "chore: update skill sources"
```

如果只想更新某一个子模块，也可以直接进入对应目录执行：

```bash
cd sources/repo-name
git pull
cd ../..
git add sources/repo-name
git commit -m "chore: update repo-name"
```

## 把误加的嵌套仓库改成子模块

如果你已经把一个独立仓库目录误加进主仓库索引，可以先把它从索引移除：

```bash
git rm --cached -r axton-obsidian-visual-skills
```

然后再按子模块方式重新添加：

```bash
git submodule add <url> axton-obsidian-visual-skills
git commit -m "chore: convert embedded repo to submodule"
```

如果 `git submodule add` 因为目录已存在而失败，先把原目录临时挪走或删除后再重新添加。
