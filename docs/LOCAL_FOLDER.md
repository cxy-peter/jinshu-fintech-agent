# Windows 指定资料文件夹

线上网页直接使用 https://jinshu-workbench.vercel.app/ 。在“资料与上传 → 我的云端资料”选择文件或文件夹即可导入；下面的本机启动方式适用于希望文件保留在指定磁盘、通过本机索引检索的情况。

## 首次准备

下载或克隆最新项目，在仓库根目录打开 Windows **命令提示符 CMD**。使用 Python 3.12（项目支持 3.12、3.13）：

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
set "JINSHU_STORE=sqlite"
START_LOCAL_FOLDER.bat --root "F:\JinshuData"
```

启动器优先使用项目 `.venv`，不会自动安装依赖。F 盘存在时会创建资料目录。没有 F 盘或需要更换目录，可以改成：

```bat
START_LOCAL_FOLDER.bat --root "D:\JinshuData" --port 8080
```

网页默认地址为 http://127.0.0.1:8080/ 。终端需要保持运行。端口被占用可改 `--port 8088`；第一次希望启动前扫描可加 `--scan`。

## 平时使用

1. 将有权使用的 PDF、DOCX、TXT、MD、CSV、JSON 放进指定文件夹。
2. 打开“资料与上传 → 本机文件夹连接”，点击“扫描新增与修改”。
3. 检查扫描结果和失败提示，再到“学习与问答”提问。
4. 点击“只检索原文”可以在不调用模型的情况下查看来源；“查看提取原文”可检查物理 PDF 页码或文本段。
5. 文件新增、修改、移动或删除后再次扫描；系统按内容变化更新索引，失效文件不会继续作为当前证据。

网页允许临时修改资料目录。**每次启动仍按 `--root` 或默认 F 盘配置**，建议为常用目录保留带参数的启动命令。当前是显式扫描，不是后台自动监控整盘。

缓存与索引默认位于 `%USERPROFILE%\.jinshu\local-workbench`，可在启动前用 `JINSHU_DATA_DIR` 调整；资料原文件保留在选定目录。一次最多扫描 200 份支持的文件，单份 12MB、总输入 300MB。扫描版 PDF 需要先做 OCR；当前模块不包含 OCR，也不自动解析 XLSX、ZIP 或 RAR。

## 生成回答

只检索和确定性业务计算不需要模型密钥。要调用 DeepSeek，可在本机启动的 CMD 进程中配置服务端环境变量，再启动：

```bat
set "JINSHU_STORE=sqlite"
set "DEEPSEEK_API_KEY=在本机填写自己的密钥"
START_LOCAL_FOLDER.bat --root "F:\JinshuData"
```

当前启动器**不会自动读取 `.env`**。不要把真实密钥放进仓库、截图或共享启动脚本。网页发送问题前需要确认本轮内容可交给模型；检索本身不会自动上传原文件，模型接收本轮片段及同页核对上下文。

## 与线上版的边界

- 线上 Vercel 无法直接读取用户电脑的 F 盘。线上“选择文件夹并上传”只处理这次明确选择的文件；需要再次选择才能检查后来新增的文件。
- 本机版与线上版使用同一 `index.py → core.app`，但资料和身份各自保存；两者不是自动双向同步。
- 本机目录接口限定本机连接、Host、Origin 和授权根目录，禁止软链接/目录联接越过根目录。不要把当前文件夹接口直接用 Tunnel 暴露公网。
- 本机网页中的资料目录属于单机使用范围；这不是同机多个操作系统用户之间的企业账号隔离。

本轮验证包含 Linux 上同一 Python 启动器的真实 HTTP/Chromium 流程，以及 GitHub Windows 运行时与启动器回归。没有声称已在用户本人电脑或真实 F 盘完成安装。
