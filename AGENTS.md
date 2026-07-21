# AGENTS.md

## 1. 项目概述

本项目是一个运行在本地的音乐四轨分离 Web 应用。

用户在浏览器中上传一个音乐文件，后端调用 Demucs 的 `htdemucs` 模型完成四轨分离，并在前端展示以下结果：

- `vocals`：人声
- `drums`：鼓
- `bass`：贝斯
- `other`：其他乐器

每个分离音轨都应当能够：

1. 在浏览器中直接播放；
2. 单独下载保存；
3. 在任务失败时显示可理解的错误信息。

本项目的首要目标是帮助项目作者学习和实践 Coding Agent 的使用流程，而不是构建可公开运营的商业服务。

---

## 2. MVP 范围

### 2.1 必须实现

- 上传单个音频文件；
- 支持至少 `.mp3`、`.wav` 和 `.flac`；
- 创建一个独立的任务 ID；
- 后端异步执行 Demucs 四轨分离；
- 前端显示任务状态：
  - `queued`
  - `running`
  - `succeeded`
  - `failed`
- 分离完成后展示四个 HTML 音频播放器；
- 每个音轨提供独立下载链接；
- 对不支持的格式、空文件、超大文件和模型执行失败给出明确提示；
- 提供一个简单的健康检查接口；
- 提供最基本的自动化测试和运行说明。

### 2.2 暂不实现

除非用户明确要求，否则不要加入以下功能：

- 用户注册、登录和权限系统；
- 数据库；
- Redis、Celery、RabbitMQ 或其他外部任务队列；
- 多用户并发调度；
- 云端部署；
- 实时音频流分离；
- 精确百分比进度条；
- 波形图、频谱图或多轨混音器；
- 音量、静音、Solo、时间轴同步等 DAW 功能；
- 六轨分离；
- 吉他主音与节奏音轨分离；
- 模型训练或微调；
- 长期保存用户文件；
- React、Vue、Next.js 或其他前端框架。

精确进度百分比不是 MVP 要求。前端只需要显示“排队中、正在分离、已完成、失败”等阶段状态，不要依赖解析 Demucs 命令行日志来伪造精确进度。

---

## 3. 推荐技术栈

- Python 3.10；
- FastAPI；
- Uvicorn；
- 原生 HTML、CSS、JavaScript；
- Demucs；
- PyTorch；
- FFmpeg；
- pytest；
- httpx 或 FastAPI TestClient。

前端文件和后端代码应当放在不同目录，但 MVP 可以由同一个 FastAPI 进程提供 API、静态页面和音频文件，以减少部署复杂度。

不要为了“前后端分离”而额外引入 Node.js 构建链。

---

## 4. 推荐项目结构

```text
demucs-web/
├─ AGENTS.md
├─ README.md
├─ requirements.txt
├─ .gitignore
├─ .env.example
├─ backend/
│  └─ app/
│     ├─ __init__.py
│     ├─ main.py
│     ├─ config.py
│     ├─ schemas.py
│     ├─ api/
│     │  ├─ __init__.py
│     │  └─ routes.py
│     └─ services/
│        ├─ __init__.py
│        ├─ demucs_service.py
│        ├─ job_manager.py
│        └─ file_service.py
├─ frontend/
│  ├─ index.html
│  ├─ app.js
│  └─ styles.css
├─ data/
│  └─ jobs/
│     └─ .gitkeep
├─ scripts/
│  └─ check_environment.py
└─ tests/
   ├─ test_api.py
   ├─ test_file_service.py
   └─ test_job_manager.py
```

保持结构简单。只有在现有文件已经明显过长或职责混乱时，才继续拆分模块。

---

## 5. 系统架构约束

### 5.1 Web 服务

FastAPI 负责：

- 接收上传文件；
- 创建任务；
- 查询任务状态；
- 提供前端静态文件；
- 提供分离后的音频文件；
- 提供下载响应。

### 5.2 任务执行

MVP 使用进程内任务管理器：

- 使用内存字典记录任务状态；
- 使用锁保护共享状态；
- 使用单工作线程或 `ThreadPoolExecutor(max_workers=1)` 串行执行分离任务；
- 同一时刻只运行一个 Demucs 任务，避免显存竞争；
- 服务重启后任务记录丢失是可接受的。

不要为 MVP 引入数据库或外部任务队列。

### 5.3 Demucs 调用方式

优先通过独立子进程调用 Demucs CLI，而不是把大量 Demucs 内部实现耦合进 Web 层。

推荐形式：

```bash
python -m demucs -n htdemucs -o <output_dir> <input_file>
```

实际参数必须先通过以下命令确认：

```bash
python -m demucs --help
```

Python 中必须使用参数列表调用 `subprocess.run` 或 `subprocess.Popen`：

```python
[
    sys.executable,
    "-m",
    "demucs",
    "-n",
    "htdemucs",
    "-o",
    str(output_dir),
    str(input_path),
]
```

禁止：

- 使用 `shell=True`；
- 拼接未经验证的用户文件名到 shell 字符串；
- 假定模型输出目录而不进行检查；
- 在请求处理函数中直接同步等待整个分离过程完成。

---

## 6. API 约定

### 6.1 健康检查

```http
GET /api/health
```

建议响应：

```json
{
  "status": "ok",
  "demucs_available": true,
  "ffmpeg_available": true,
  "device": "cuda"
}
```

健康检查不应触发完整模型推理。

### 6.2 创建分离任务

```http
POST /api/jobs
Content-Type: multipart/form-data
```

表单字段：

```text
file=<audio file>
```

成功响应状态码建议为 `202 Accepted`：

```json
{
  "job_id": "uuid",
  "status": "queued"
}
```

### 6.3 查询任务

```http
GET /api/jobs/{job_id}
```

排队或运行中：

```json
{
  "job_id": "uuid",
  "status": "running",
  "message": "正在进行四轨分离",
  "outputs": null,
  "error": null
}
```

完成：

```json
{
  "job_id": "uuid",
  "status": "succeeded",
  "message": "分离完成",
  "outputs": {
    "vocals": "/media/<job_id>/vocals.wav",
    "drums": "/media/<job_id>/drums.wav",
    "bass": "/media/<job_id>/bass.wav",
    "other": "/media/<job_id>/other.wav"
  },
  "error": null
}
```

失败：

```json
{
  "job_id": "uuid",
  "status": "failed",
  "message": "分离失败",
  "outputs": null,
  "error": "可供用户理解的简短错误信息"
}
```

不要将完整 Python 堆栈、绝对路径或系统隐私信息直接返回给前端。

### 6.4 音频访问

```http
GET /media/{job_id}/{stem}.wav
```

`stem` 只能是：

- `vocals`
- `drums`
- `bass`
- `other`

必须阻止路径穿越。

---

## 7. 文件管理规则

每个任务使用 UUID，并建立独立目录：

```text
data/jobs/<job_id>/
├─ input/
│  └─ source.<ext>
├─ output/
├─ logs/
│  └─ demucs.log
└─ result/
   ├─ vocals.wav
   ├─ drums.wav
   ├─ bass.wav
   └─ other.wav
```

要求：

- 不要直接使用用户提供的文件名作为目录名；
- 仅保留安全的扩展名；
- 所有路径使用 `pathlib.Path`；
- 所有任务文件必须位于配置的 `data/jobs` 根目录内；
- 不允许代码删除任务目录之外的任何文件；
- 保存上传文件时采用分块复制，不要一次性读入整个文件；
- 文件大小限制应通过配置项控制；
- 默认只接受常见音频格式；
- MIME 类型只能作为辅助判断，不能完全信任；
- 可在服务启动时清理超过指定时间的旧任务；
- 自动清理不是第一阶段的阻塞项。

---

## 8. 音频与模型规则

默认模型使用：

```text
htdemucs
```

预期输出必须包含：

```text
vocals.wav
drums.wav
bass.wav
other.wav
```

如果缺少任意音轨，任务应标记为失败，并记录实际输出目录内容。

设备选择规则：

1. 若 `torch.cuda.is_available()` 为真，则使用 CUDA；
2. 否则回退到 CPU；
3. 前端只显示当前设备，不允许用户在 MVP 中随意切换设备。

首次运行可能需要下载模型权重。代码必须把下载失败视为可诊断错误，而不是无限等待。

在 Windows 上，应检查 FFmpeg 是否可用，以提高 MP3、M4A 等格式的兼容性。

不要擅自升级、降级或重装 PyTorch。修改 PyTorch 前必须先运行：

```bash
python -c "import torch; print('torch=', torch.__version__); print('cuda=', torch.cuda.is_available()); print('torch_cuda=', torch.version.cuda)"
```

如果现有环境已经能够使用 CUDA，禁止用普通 `pip install torch` 覆盖成 CPU 版本。

---

## 9. 本地开发命令

以下命令以 Windows PowerShell 为主要示例。

### 9.1 创建环境

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 9.2 检查环境

```powershell
ffmpeg -version
python -m demucs --help
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)"
python scripts/check_environment.py
```

### 9.3 启动服务

```powershell
uvicorn backend.app.main:app --reload
```

默认访问地址：

```text
http://127.0.0.1:8000
```

### 9.4 运行测试

```powershell
pytest -q
```

提交修改前至少运行：

```powershell
pytest -q
python -m compileall backend
```

如果项目后续加入格式化或静态检查工具，再把对应命令补充到本文件中。

---

## 10. 后端编码规范

- 使用 Python 类型标注；
- 使用 `pathlib.Path`，避免手工拼接路径；
- 使用标准 `logging`，不要用散乱的 `print`；
- API 层只负责参数接收、状态码和响应结构；
- Demucs 调用放在 `demucs_service.py`；
- 任务状态管理放在 `job_manager.py`；
- 上传校验和路径处理放在 `file_service.py`；
- 状态字符串使用枚举或受约束的字面量；
- 不捕获后完全忽略异常；
- 面向用户的错误简短明确，详细错误写入日志；
- 不在模块导入阶段启动模型推理；
- 不在测试中下载模型；
- 不把绝对路径暴露给前端；
- 新增依赖前先说明必要性。

---

## 11. 前端编码规范

- 使用原生 HTML、CSS、JavaScript；
- 页面保持单页、简洁；
- 必须有文件选择区域和开始按钮；
- 上传期间禁用重复提交；
- 前端轮询任务状态，但失败或完成后必须停止轮询；
- 网络错误时允许用户重新查询或重新提交；
- 完成后生成四张音轨卡片；
- 每张卡片包含：
  - 音轨名称；
  - `<audio controls>`；
  - 下载链接；
- 不实现虚假的百分比进度；
- 不引入大型 UI 库；
- 所有用户可见提示使用中文；
- 保证按钮、标签和错误信息清楚可读。

---

## 12. 测试要求

普通测试不得运行真实 Demucs 推理。

必须通过 mock 或 fake service 测试：

- 合法与非法文件扩展名；
- 文件大小限制；
- UUID 任务目录生成；
- `queued -> running -> succeeded` 状态转换；
- `queued -> running -> failed` 状态转换；
- Demucs 子进程返回非零状态码；
- 缺失某个输出音轨；
- 查询不存在的任务；
- 非法 stem 名称；
- API 上传和状态查询；
- 路径穿越防护。

真实模型只用于手动冒烟测试。

建议准备一个较短、可合法使用的测试音频，执行：

1. 上传；
2. 等待分离；
3. 检查四个输出文件；
4. 在浏览器中依次播放；
5. 下载一个音轨；
6. 检查日志中没有未处理异常。

不要把受版权保护的测试音乐提交到仓库。

---

## 13. Agent 工作规则

### 13.1 开始任务前

Agent 必须：

1. 阅读本文件；
2. 阅读 `README.md`；
3. 查看项目目录；
4. 查看与当前任务直接相关的代码；
5. 用简短文字说明准备修改哪些文件以及为什么；
6. 优先实施最小可验证改动。

不要一上来重构整个项目。

### 13.2 修改过程中

Agent 应当：

- 将任务拆成小步骤；
- 每一步尽量保持项目可运行；
- 复用已有代码；
- 不进行与任务无关的格式化或重命名；
- 不随意改变公开 API；
- 不改变模型、输出 stem 名称或目录约定；
- 不添加数据库、前端框架或任务队列；
- 遇到环境问题时先收集准确诊断信息；
- 不声称没有实际运行过的命令已经通过。

### 13.3 完成任务后

Agent 必须报告：

- 修改了哪些文件；
- 每个修改解决了什么问题；
- 运行了哪些命令；
- 哪些测试通过；
- 哪些步骤由于环境限制没有验证；
- 是否存在遗留风险；
- 下一步最合理的单一任务是什么。

如果测试失败，不得隐藏失败结果。

### 13.4 指令优先级

发生冲突时遵循：

1. 用户当前对话中的明确要求；
2. 距离被修改文件最近的 `AGENTS.md`；
3. 项目根目录的本文件；
4. README 和代码中的一般约定。

任何安全限制都不得被低优先级说明覆盖。

---

## 14. 禁止事项

除非用户明确授权，否则 Agent 不得：

- 删除整个 `data` 目录；
- 删除任务目录之外的用户文件；
- 上传音频到第三方服务；
- 在代码或日志中写入密钥；
- 提交模型权重和大体积音频；
- 使用 `shell=True`；
- 关闭文件类型和路径校验；
- 自动安装未知来源的二进制文件；
- 覆盖当前可用的 CUDA/PyTorch 环境；
- 用假数据冒充真实 Demucs 输出；
- 为实现简单功能引入复杂框架；
- 在没有测试的情况下进行大范围重构。

---

## 15. 推荐开发里程碑

### Milestone 0：环境验证

目标：

- Demucs CLI 能够对一个短音频生成四轨；
- PyTorch 设备状态明确；
- FFmpeg 可用；
- 记录实际输出目录结构。

本阶段不要编写 Web 界面。

### Milestone 1：后端骨架

目标：

- FastAPI 启动；
- `/api/health` 可访问；
- 文件上传与校验可用；
- 创建任务 ID；
- 使用 fake separation 生成四个测试音频或固定测试结果。

本阶段不接入真实 Demucs。

### Milestone 2：Demucs 服务

目标：

- 封装 Demucs 子进程；
- 捕获日志和退出码；
- 找到并规范化四个输出文件；
- 错误能够转成失败任务状态。

### Milestone 3：任务状态

目标：

- 上传接口立即返回任务 ID；
- 单工作线程执行任务；
- 状态接口可轮询；
- 服务不会因一次模型失败而崩溃。

### Milestone 4：前端

目标：

- 上传；
- 状态显示；
- 四轨播放器；
- 单独下载；
- 错误提示。

### Milestone 5：测试与文档

目标：

- 核心测试通过；
- README 包含安装、运行、测试和常见问题；
- 完成一次真实音频冒烟测试；
- 明确记录 Windows、CUDA、FFmpeg 和首次模型下载注意事项。

### Milestone 6：自定义混音

这是用户当前要求实现的功能。

目标：

- 分离成功后允许用户在 `vocals`、`drums`、`bass`、`other` 中选择一个或多个音轨；
- 后端使用 FFmpeg `amix` 生成真实 WAV 合并文件，不重新运行 Demucs；
- 同一组音轨按固定顺序生成可复用缓存文件；
- 前端展示单个合并音轨播放器和下载链接；
- 普通测试通过 mock FFmpeg 覆盖单轨、多轨、四轨、非法输入、缓存复用和下载响应。

一次 Agent 任务原则上只完成一个里程碑，或者一个里程碑中的一个清晰子任务。

---

## 16. MVP 验收标准

满足以下条件时，MVP 才算完成：

- 可以通过文档中的命令启动应用；
- 浏览器能够打开页面；
- 用户能够上传一个受支持的音频；
- 上传后获得任务状态反馈；
- 后端不会阻塞整个 Web 服务；
- Demucs 成功生成 `vocals`、`drums`、`bass` 和 `other`；
- 四个音轨均能在浏览器播放；
- 四个音轨均能单独下载；
- 不支持的文件会被拒绝；
- 模型失败时前端能看到明确错误；
- 普通测试不依赖真实模型和网络；
- `pytest -q` 通过；
- README 与实际命令一致。

---

## 17. 项目设计原则

按以下顺序做决策：

1. 正确；
2. 可验证；
3. 简单；
4. 可维护；
5. 性能；
6. 功能数量。

这是一个学习型本地项目。宁可交付一个能够稳定运行、结构清楚的四轨分离工具，也不要过早构建复杂但无法验证的“完整平台”。
