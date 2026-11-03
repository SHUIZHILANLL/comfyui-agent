# ComfyUI Agent Anima

用自然语言（中/英）指挥 Anima 出图的 ComfyUI 自定义节点：解析指令、扩展 Danbooru 风格标签、写正负面提示词，按**本机已安装节点**选择工作流模板并排队生成。侧边栏可把图铺到画布；同时提供本机 HTTP API，方便外部助手远程驱动。

Natural-language Anima custom node for ComfyUI: prompts, template selection, sidebar canvas load, and a localhost HTTP API. Model weights are not included.

## 安装

把本仓库克隆到 ComfyUI 的 `custom_nodes`（文件夹名可以是仓库名 `comfyui-agent`）：

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/SHUIZHILANLL/comfyui-agent.git
```

重启 ComfyUI。入口是仓库根目录的 `__init__.py`（`WEB_DIRECTORY = ./web`），克隆后即可被加载。默认只用 Python 标准库，无需 `pip install`。

### 默认模型（需自行放置，不要提交权重）

| 角色 | 默认文件名 | 常见目录 |
|------|------------|----------|
| UNET | `anima-aesthetic-v1.1.safetensors` | `models/diffusion_models/` |
| CLIP | `qwen_3_06b_base.safetensors`（`CLIPLoader` type=`stable_diffusion`） | `models/text_encoders/` |
| VAE | `qwen_image_vae.safetensors` | `models/vae/` |

原生 `stock_anima` 采样默认：512×512，KSampler `euler` / `simple`，steps=`30`，cfg=`12.2`。SaveImage 前缀：`agent_anima`。

节点菜单 **Agent Anima** 里的模型下拉会读取本机 `folder_paths`；列表为空时仍显示上述默认文件名。

## 用法

### 侧边栏与画布

重启后打开侧栏 **Anima Agent**（右下角也有同名浮动按钮）：

1. 输入指令，例如：`雨夜里撑伞的银发少女，新海诚风格`
2. 模板下拉：自动 / 原生 / EasyUse / Spectrum / Ref Adapter
3. 可选填写 **参考图** 文件名（必须已在 ComfyUI `input/` 目录，只填文件名）
4. **Plan only** 只看提示词与图；**Run** 排队出图
5. 默认勾选 **显示到画布**：成功后前端调用 `app.loadGraphData(ui_workflow)` 把图铺到当前画布
6. 若画布加载失败，会自动下载 UI JSON，用 **File → Open** 打开。勾选「下载 UI JSON」可主动保存；`POST /agent_anima/load_ui` 只取图、不排队

API 排队（`workflow`）与画布加载相互独立：画布失败不影响 `/run` 出图。响应字段：`workflow`（API）、`ui_workflow`（UI）、`ui_summary`、`load_to_canvas`。

### 节点

| 节点 | 作用 |
|------|------|
| **Anima Agent Prompt Writer** | `command` → positive / negative / notes |
| **Anima Agent Command** | 生成 prompts + API workflow JSON + status；`run_now=true` 时通过本机 HTTP 排队 |

### 示例工作流（在 ComfyUI 里打开）

`workflows/` 里有两份 **UI 格式** JSON，可直接铺到画布（与 API prompt 不同）：

| 文件 | 内容 |
|------|------|
| [`workflows/Anima_Agent_Stock.json`](workflows/Anima_Agent_Stock.json) | 原生 UNET + CLIP + VAE + KSampler + VAEDecode + SaveImage |
| [`workflows/Anima_Agent_Ref.json`](workflows/Anima_Agent_Ref.json) | 在原生链路上增加 `LoadImage` + `AnimaRefAdapter`（参考图锁人物） |

打开步骤：

1. 启动已安装本节点的 ComfyUI。
2. 菜单 **File → Open**（或把 JSON 拖进画布）。
3. 选择上面两个文件之一。
4. 确认模型文件名与本机一致后再 Queue。
5. Ref 示例里 `LoadImage` 的文件名是占位符 `ref_catgirl.png`：换成你放在 `input/` 里的参考图，并先装好下方的 Ref Adapter。未安装该节点时，这张图无法运行。

`workflows/anima_agent_api_template.json` 是 **API prompt** 模板（占位符 `POSITIVE_PROMPT_PLACEHOLDER`），给 `/prompt` 或二次开发用，不要用 File → Open 当画布工作流打开。

## 可选依赖：Anima Ref Adapter

人物一致性不是本仓库自带的节点。需要另装：

1. 另装提供 `class_type` `AnimaRefAdapter` 的自定义节点（文件夹名通常为 `ComfyUI-Anima-Ref-Adapter`）
2. LoRA：`models/loras/anima_ref_adapter_v2_r64.safetensors`
3. 参考图放在 ComfyUI **input** 目录，请求里只填文件名，如 `char.png`

未安装或未提供 `ref_image` 时：选了该模板会回退 `stock_anima`，或在 `/plan`、`/run` 返回明确错误（显式指定 `anima_ref_adapter` 却没有参考图）。

推荐参数：分辨率 `832×1216`，cfg `4.5`，steps `30`，sampler `euler`，scheduler `simple`。Adapter：`ref_guidance=4.5`，`correction=apg`，`strength` / `ref_end` / `ref_megapixels=1.0`。提示词只写场景、姿势、镜头、氛围；该模板会尽量剥掉发色、服装、角色名等外貌标签。SaveImage 前缀：`agent_anima_ref`。

指令关键词：`参考图` / `锁人物` / `人物一致` / `ref adapter`，或字段 `template=anima_ref_adapter`、`ref_image=char.png`。也可在指令里写 `参考图:char.png` / `ref_image=char.png`。

```bash
curl -X POST http://127.0.0.1:8188/agent_anima/run \
  -H "Content-Type: application/json" \
  -d '{"command":"用参考图锁人物，咖啡馆靠窗坐着喝咖啡","template":"anima_ref_adapter","ref_image":"char.png","wait":true}'
```

## 节点发现与模板

1. **发现**：`GET /object_info`（短缓存）读取本机已注册节点；可选扫描 `custom_nodes` 文件夹名。
2. **能力摘要**：是否装了 EasyUse Anima / Spectrum / anima-tools / Anima Ref Adapter。
3. **选模板**：按指令关键词或请求里的 `template` 字段；缺节点时回退原生 stock，并在响应里写明 `wanted_template` / `fallback_reason`。
4. **安全**：非回退路径下，不会编造 `object_info` 里不存在的 `class_type`。

| id | 说明 | 条件 |
|----|------|------|
| `stock_anima` | 原生 UNET+CLIP+VAE+KSampler（默认、始终可用） | 无额外依赖 |
| `easyuse_aio` | EasyUse Anima AiO 最小图；schema 不确定则回退 stock | `EasyUseAnimaAIO*` 出现在 object_info |
| `spectrum_ksampler` | 用 Spectrum 采样器替换 KSampler；不兼容则回退 | Spectrum*Sampler 在 object_info |
| `anima_ref_adapter` | 参考图锁人物 | 已安装 `AnimaRefAdapter` + LoRA + `ref_image` |

其它关键词：`aio` / `easyuse` / `一键` → easyuse；`spectrum` → spectrum；`原生` / `默认工作流` → stock。内容尺度跟每次指令走（未提成人向则保持 SFW）。

## HTTP API

默认基址 `http://127.0.0.1:8188`（ComfyUI 需在运行）。

| 方法 | 路径 | 作用 |
|------|------|------|
| GET | `/agent_anima/health` | 存活、默认模型与采样、能力摘要 |
| GET | `/agent_anima/capabilities` | 已发现节点与可选模板（`?force=1` 刷新） |
| POST | `/agent_anima/plan` | 只规划提示词与 API/UI 工作流，不排队 |
| POST | `/agent_anima/run` | 规划并排队；`wait` 默认为 true |
| POST | `/agent_anima/load_ui` | 返回 `ui_workflow` 供画布加载，不排队。可传 `workflow`（API dict）或与 `/plan` 相同的指令字段 |

常用请求字段：`command`，`template`，`ref_image`，`load_to_canvas`，`seed`，`batch_size`，`width`，`height`，`steps`，`cfg`，`unet_name`，`clip_name`，`vae_name`，`positive_prompt`，`negative_prompt`，`use_llm`，`timeout_s`，`comfy_url`，`wait`。

返回里另有：`template_used`，`wanted_template`，`fallback_reason`，`capabilities_note`，`workflow`，`ui_workflow`，`ui_summary`。

```bash
curl http://127.0.0.1:8188/agent_anima/health
curl http://127.0.0.1:8188/agent_anima/capabilities

curl -X POST http://127.0.0.1:8188/agent_anima/plan \
  -H "Content-Type: application/json" \
  -d '{"command":"用 easyuse aio 画樱花树下的猫耳少女","template":"auto"}'

curl -X POST http://127.0.0.1:8188/agent_anima/run \
  -H "Content-Type: application/json" \
  -d '{"command":"樱花树下的猫耳少女","template":"stock_anima","wait":true}'
```

## 可选 LLM 润色

标签扩展默认来自 `data/tag_hints.json`。若要接 OpenAI Chat Completions 兼容接口，只通过环境变量提供地址和密钥，**不要把密钥写入仓库或工作流**：

```bash
# 任意兼容端点均可，例如 DeepSeek
export AGENT_ANIMA_LLM_BASE="https://api.deepseek.com/v1"
export AGENT_ANIMA_LLM_KEY="<your-api-key>"
export AGENT_ANIMA_LLM_MODEL="deepseek-chat"
```

Windows 把 `export` 换成 `set`。未设置密钥时走本地规划，不访问外网。

## 目录

```
__init__.py                 # WEB_DIRECTORY、节点与路由注册
nodes.py                    # Agent Anima 节点
routes.py                   # /agent_anima/*
requirements.txt            # 默认可空（标准库）
tests_selfcheck.py          # 无 ComfyUI 进程的自检
agent/
  discovery.py              # /object_info + 能力摘要
  planner.py
  prompt_writer.py
  workflow_builder.py
  runner.py
  research.py
  ui_graph.py               # API prompt → UI workflow
  templates/
    registry.py
    stock_anima.py
    easyuse_aio.py
    spectrum_ksampler.py
    anima_ref_adapter.py
web/anima_agent.js          # 侧边栏 + 画布加载
workflows/
  Anima_Agent_Stock.json    # 画布示例：原生
  Anima_Agent_Ref.json      # 画布示例：Ref Adapter
  anima_agent_api_template.json
data/tag_hints.json
```

## 自检

不需要启动 ComfyUI：

```bash
python tests_selfcheck.py
```

## 限制

- EasyUse AiO 若必填输入依赖 MODEL/CLIP 等链接，或 `object_info` 不可用，会安全回退到原生图。
- Ref Adapter 需要 `ref_image`（input 文件名）以及已注册的 `AnimaRefAdapter`；否则回退或返回错误。
- `/run` 依赖 ComfyUI 本机 HTTP；排队时请勿关闭 ComfyUI。
- 本仓库不包含 `.safetensors` 权重、用户目录或 API 密钥。
