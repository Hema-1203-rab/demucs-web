# Demucs Web MVP

本项目是一个本地运行的音乐四轨分离 Web 应用。用户上传 `.mp3`、`.wav` 或 `.flac` 文件后，后端创建任务并通过单工作线程执行 Demucs `htdemucs` 四轨分离，前端轮询状态并展示 `vocals`、`drums`、`bass`、`other` 四个音轨。

## 当前范围

- FastAPI 后端和原生 HTML/CSS/JavaScript 前端。
- 进程内任务管理器和 `ThreadPoolExecutor(max_workers=1)`。
- 默认真实服务调用 `python -m demucs -n htdemucs`。
- 分离成功后可选择一个或多个音轨，用 FFmpeg 生成 WAV 合并音轨。
- 普通自动化测试使用 fake/mock，不执行真实 Demucs 推理。
- 不包含数据库、Redis、Celery、登录系统或前端框架。

## 环境准备

建议使用 Python 3.10。Windows PowerShell 示例：

```powershell
conda create -n Demucs python=3.10
conda activate Demucs
python -m pip install -r requirements.txt
```

真实分离还需要 PyTorch、Demucs 和 FFmpeg。不要用普通 `pip install torch` 覆盖已有 CUDA 版 PyTorch；先检查当前状态：

```powershell
python -c "import torch; print('torch=', torch.__version__); print('cuda=', torch.cuda.is_available()); print('torch_cuda=', torch.version.cuda)"
```

然后按本机 CUDA 情况安装合适的 PyTorch，再安装 Demucs 和 FFmpeg。FFmpeg 需能被 `ffmpeg -version` 找到。

## 启动

在项目根目录运行：

```powershell
conda activate Demucs
uvicorn backend.app.main:app --reload
```

打开：

```text
http://127.0.0.1:8000
```

分离完成后，页面会继续显示四个独立音轨播放器和下载链接。下方的“合并音轨”区域默认选中四个音轨，可取消任意音轨后点击“生成合并音轨”。后端会使用 FFmpeg `amix` 生成一个 WAV 文件，并在页面中显示单个播放器和“下载合并音轨”链接。

## 测试

本机默认临时目录可能存在权限问题时，使用仓库内临时目录：

```powershell
conda activate Demucs
pytest -q --basetemp .pytest_cache/tmp
python -m compileall backend tests
```

普通测试不会下载模型，也不会运行真实 Demucs。

## API

健康检查：

```http
GET /api/health
```

创建任务：

```http
POST /api/jobs
Content-Type: multipart/form-data

file=<audio file>
```

查询任务：

```http
GET /api/jobs/{job_id}
```

音轨文件：

```http
GET /media/{job_id}/{stem}.wav
```

`stem` 只能是 `vocals`、`drums`、`bass`、`other`。

生成合并音轨：

```http
POST /api/jobs/{job_id}/mixes
Content-Type: application/json

{
  "stems": ["vocals", "bass"]
}
```

响应包含 `stems`、`play_url` 和 `download_url`。合并文件格式为 WAV，存放在对应任务结果目录的 `mixes` 子目录中；同一种音轨组合会按 `vocals`、`drums`、`bass`、`other` 固定顺序复用同一个缓存文件。

合并音轨播放和下载：

```http
GET /media/{job_id}/mixes/{filename}
GET /media/{job_id}/mixes/{filename}/download
```

## 当前环境提示

如果 `/api/health` 中 `demucs_available` 或 `ffmpeg_available` 为 `false`，真实上传任务会失败。先补齐环境，再做真实音频烟雾测试。
