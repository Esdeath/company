# GitHub 一键发布脚本设计

## 目标

在仓库根目录提供可直接运行的 `./deploy.sh`，将当前工作区的全部新增、修改和删除提交并推送到 GitHub。提交信息固定为 `chore: publish project updates`。

## 结构

- `deploy.sh`：轻量启动器，定位仓库根目录并使用 `python3` 运行 Python 主程序。
- `scripts/publish-github.py`：执行 Git 检查、暂存、提交和推送。
- 自动化测试：在临时 Git 仓库和裸远端中验证发布流程，不访问真实 GitHub。

## 发布流程

1. 确认脚本位于有效 Git 工作树中，并确认存在名为 `origin` 的远端。
2. 获取当前分支；如果处于 detached HEAD 状态，则报错退出。
3. 执行 `git add -A`，纳入所有新增、修改和删除。
4. 检查暂存区：有变化时创建固定信息的提交；没有变化时跳过提交。
5. 将当前分支推送到 `origin`。已有 upstream 时正常推送；没有 upstream 时使用 `git push --set-upstream origin <branch>`。

因此，即使工作区没有新变化，本地已有但尚未推送的提交仍会被发布。

## 错误处理

Python 主程序使用 Git 子进程的退出状态判断成功与否。仓库无效、缺少 `origin`、无法确定当前分支、提交失败或推送失败时立即退出非零状态，并保留 Git 的错误输出。脚本不执行强制推送，不修改远端历史，也不自动运行 `make check`。

## 验证

测试覆盖以下行为：

- 新增、修改和删除会一起进入固定信息的提交并推送到远端。
- 没有工作区变化时不会创建空提交，但会推送现有本地提交。
- 缺少 `origin` 或处于 detached HEAD 时返回失败。
- `deploy.sh` 可执行并能从仓库根目录调用 Python 主程序。
