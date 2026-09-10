# Qwerty Bar

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL%203.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4.svg)](#)
[![Python](https://img.shields.io/badge/python-3.10%2B-yellow.svg)](#)
[![No deps](https://img.shields.io/badge/pip-not%20required-brightgreen.svg)](#)

把 [qwerty-learner](https://github.com/RealKai42/qwerty-learner) 的 VSCode 状态栏练词体验搬到 **Windows 任务栏**上。

不用开 VSCode，也不用开浏览器——单词条直接贴在任务栏空白处，随时摸鱼背单词。

```
▍IELTS chp.3   9/20   spiral   螺旋形的，盘旋的; 盘旋上升; 急剧增长   ♪ ‹ › ⋮
```

## 特性

- **任务栏常驻**：无边框置顶小窗，视觉上等同于长在任务栏里
- **肌肉记忆练词**：逐字母校验，打错整词重打（与上游一致）
- **372 本词库**：CET / IELTS / TOEFL / 考研 / 程序员词库等，按需下载
- **有道发音**：美音 / 英音，本地缓存
- **默写模式**：`Tab` 一键隐藏单词
- **老板键**：`Ctrl+Alt+H` 立刻隐身，`Ctrl+Alt+Q` 全局显隐
- **零第三方依赖**：只要 Python 3.10+ 自带的 tkinter

## 为什么不做成真正的任务栏插件

Windows 11 已移除 Deskband（任务栏工具栏）扩展点，第三方程序无法再往任务栏里塞控件。

本项目采用通行做法：一个**无边框、置顶、不进 Alt-Tab** 的小窗口，自动贴到任务栏空白区域，并周期性重新抢置顶层级，视觉与操作上等同于长在任务栏里。

## 快速开始

### 1. 环境

- Windows 10 / 11
- [Python 3.10+](https://www.python.org/downloads/)（安装时勾选 **Add to PATH**）

### 2. 获取代码

```powershell
git clone https://github.com/tl307440-boop/qwerty-bar.git
cd qwerty-bar
```

### 3. 启动

```
双击 start.bat
```

首次运行会自动下载默认词库（CET-4 / CET-6 / IELTS / 考研 / Coder Dict）。

命令行等价：

```powershell
python fetch_dicts.py          # 下载默认词库
pythonw run.pyw                # 启动（无控制台）
```

更多词库：

```powershell
python fetch_dicts.py --list          # 列出全部词库 id
python fetch_dicts.py toefl gre       # 按 id 下载
python fetch_dicts.py --all           # 全下（约 90MB）
```

## 操作

| 操作 | 说明 |
| --- | --- |
| 单击词条 | 获得焦点（左侧竖条变绿＝可以打字） |
| 直接打字 | 逐字母校验，对的变绿；打错闪红并要求重打 |
| `Backspace` | 退一个字母 |
| `←` `→` / 滚轮 | 上一个 / 下一个单词 |
| `Enter` | 重听发音 |
| `Tab` | 切换默写模式（单词变 `______`） |
| `Esc` | 立刻隐藏 |
| `Ctrl+Alt+Q` | 全局显示 / 隐藏 |
| `Ctrl+Alt+H` | 老板键，直接隐藏 |
| 右键 | 设置菜单 |
| 拖动 | 左右挪动位置 |
| 点词库名 / 点进度 | 快速切词库 / 跳章节 |

## 设置菜单

- **词库 / 章节**：372 本词库，按分类分组；每 20 词一章
- **显示释义 / 音标 / 默写模式 / 单词循环**
- **自动发音**：拼对后自动播放（美音 / 英音）
- **位置**：贴在任务栏上 / 任务栏上方 / 自由拖动；靠左、居中、靠右
- **外观**：跟随系统深浅色、字号、最大宽度
- **开机自启**：写入当前用户 `Run` 注册表项
- 底部显示累计练习词数与正确率

进度按词库分别记忆，退出后下次接着背。

## 文件结构

```
qwerty-bar/
  start.bat            启动（无控制台窗口）
  setup.bat            下载 / 更新词库
  fetch_dicts.py       解析上游 dictionary.ts，生成 catalog 并下载词库
  run.pyw              无控制台入口
  qwerty_bar/
    __main__.py        单实例控制 + 启动
    bar.py             状态栏渲染、打字引擎、菜单
    dicts.py           词库目录、章节切分
    store.py           设置与进度持久化
    audio.py           有道发音 + 提示音
    winapi.py          DPI、任务栏定位、置顶、全局热键、禁用输入法
  data/
    catalog.json       词库索引（可提交）
    dicts/*.json       已下载词库（本地缓存，不提交）
    state.json         个人设置与进度（不提交）
    audio/*.mp3        发音缓存（不提交）
```

## 已知问题

- **中文输入法**：程序会对自身窗口调用 `ImmAssociateContext(NULL)` 关掉 IME，否则按键会被拼音候选框吃掉。词条获得焦点时无需手动切英文输入法。
- **重复启动**：第二次运行不会开新进程，只会把已隐藏的词条叫回来。
- **任务栏自动隐藏**：建议改用「任务栏上方」或「自由拖动」模式。
- 词条获得焦点时，原先窗口会暂时失去焦点——打字必需；按 `Esc` 或点回原窗口即可。

## 致谢 & 上游

- 设计思想与词库来自 [RealKai42/qwerty-learner](https://github.com/RealKai42/qwerty-learner)（GPL-3.0）
- 发音来自有道词典开放接口
- 词库文件在运行时从上游仓库拉取，本仓库不重新分发词库内容

## License

本项目以 [GPL-3.0](LICENSE) 发布（与上游 qwerty-learner 保持一致）。
