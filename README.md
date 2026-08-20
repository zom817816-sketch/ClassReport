# 📚 ClassReport｜一键式学情报告生成器

将课堂巩固、入班测和期末测评数据，自动整理为**按学生生成的多页学情报告 PDF**；支持从飞书多维表格同步数据，并可打包为无需安装 Python 的教师端程序。

> 面向课程老师与教务同事设计：选择数据源 → 点击生成 → 分发班级压缩包。

| 能力 | 说明 |
| --- | --- |
| 📊 学情分析 | 自动计算班级位置、分项表现、五维诊断与规则化建议 |
| 🧾 成品报告 | 每位学员一份 PDF，按班级归档并生成交付清单 |
| ☁️ 飞书同步 | 从飞书多维表格下载最新数据后直接生成 |
| 🎨 四种视觉模板 | 标准专业、手绘卡通、孟菲斯几何、校园笔记 |
| 🔐 交付保护 | 可按学生手机号后四位为 PDF 加密，并记录异常数据 |

---

## 🚀 教师使用：最快 3 步

如果你拿到的是已打包的教师端，请优先阅读发布包内的[教师版使用说明](教师版使用说明.md)。日常操作只需：

1. 首次使用时配置飞书访问凭据和目标多维表格；
2. 双击 `ClassReportGenerator.exe`；
3. 在界面中选择报告模板并点击生成，到 `output\packages` 获取各班级压缩包。

> 教师端为单文件 EXE，不需要安装 Python。首次启动时会解压运行组件，等待数秒即可。

### 报告模板

| 模板 | 适用场景 | 命令值 |
| --- | --- | --- |
| 标准专业风 | 正式课程交付、家长沟通 | `standard` |
| 手绘卡通风 | 低龄课程、轻松亲和的反馈 | `cartoon` |
| 孟菲斯几何风 | 活力课程、视觉化展示 | `memphis` |
| 校园笔记风 | 学习成长记录、校园主题内容 | `notebook` |

---

## 💻 本地运行

### 1. 安装依赖

在 `ClassReport` 目录中执行：

```powershell
python -m pip install -r requirements.txt
```

如本机使用 Miniforge，也可明确指定 Python：

```powershell
& 'D:\ProgramFiles\miniforge\python.exe' -m pip install -r requirements.txt
```

### 2. 一键生成

将符合规则的 CSV 数据放入 `data/` 后，双击[生成学情报告.bat](生成学情报告.bat)，或执行：

```powershell
python run.py
```

默认会清理旧的 `output/` 并生成本次结果。如需保留既有输出：

```powershell
python run.py --keep-output
```

### 3. 查看交付物

```text
output/
├─ reports/                 # 按班级分组的个人 PDF
├─ packages/                # 可直接交付的班级压缩包
└─ manifests/
   ├─ report_manifest.csv   # 报告生成与加密状态
   ├─ class_packages.csv    # 班级压缩包清单
   └─ data_quality_report.csv # 缺失、未匹配等待核对的数据
```

---

## ☁️ 从飞书多维表格同步

复制配置模板并填写必要项（请勿把真实凭据提交到代码仓库）：

```powershell
Copy-Item teacher_config.env.example .env
```

`.env` 支持两种认证方式：

- `USER_ACCESS_TOKEN`：使用有目标多维表格查看权限的飞书用户令牌；
- `APP_ID` + `APP_SECRET`：使用应用身份，应用也必须有相应多维表格权限。

建议填写 `FEISHU_APP_TOKEN` 来切换目标 Base；它是 Base 链接中的 `app_token`。也可以填写完整的 `FEISHU_URL`。

```powershell
# 下载飞书数据并生成报告
python run.py --sync-feishu

# 只下载并检查数据，不生成 PDF
python run.py --sync-feishu --sync-only

# 下载后执行预检，不生成 PDF
python run.py --sync-feishu --validate-only
```

下载的原始表会保存在 `data/feishu_raw/`，可用于追溯；匹配为报告结构的数据会写入 `data/feishu/`。下载清单见 `data/feishu_download_manifest.csv`。

> 飞书应用需要开通与多维表格读取相关的权限（如 `bitable:app:readonly`）；如 Base 开启高级权限，还需要将应用或令牌所属用户加入协作者并授予相应角色。

---

## 🛠️ 常用命令

```powershell
# 指定报告日期、指导老师和视觉模板
python run.py --date 2026-08-20 --teacher "小明老师" --template notebook

# 生成其他风格
python run.py --template standard
python run.py --template cartoon
python run.py --template memphis

# 指定本地数据目录
python run.py --data-dir data/feishu

# 调试用：不为 PDF 加密（交付给学生前请勿使用）
python run.py --no-encrypt
```

运行全部参数：

```powershell
python run.py --help
```

---

## 📦 打包教师端

管理员电脑中执行以下命令，生成 Windows 单文件教师端：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_gui_release.ps1
```

完成后，最新发布包会出现在 `release/`。将其中的 EXE（或 ZIP）交给受控设备上的教师即可使用。

### 凭据与分发提醒

- 构建脚本可将当前所需配置嵌入教师端，便于首次使用；因此**发布包属于敏感文件**，仅应发送给受控设备和授权人员。
- 不要通过公开群聊、公开网盘或代码仓库传播 `.env`、`app_credentials.env` 或包含真实凭据的发布包。
- 用户访问令牌可能会过期；出现鉴权失败时，在 GUI 的“飞书用户令牌”中更新令牌，或由管理员重新配置后发版。
- 每份学生 PDF 默认以手机号后四位加密；手机号缺失时会生成未加密文件，并在数据质量清单中标记。

---

## 🧠 数据规则与诊断逻辑

- 课堂巩固表作为完整学员名单的基础；每位有效学员生成一份报告。
- 姓名匹配会忽略括号中的昵称，例如 `杨赵依（依依）` 与 `杨赵依` 视作同一人。
- 入班测、课堂巩固的班级均分按同班有效成绩计算。
- 期末测评原始满分并不固定，因此综合评价以班级百分位为主，不会强行换算成 100 分制。
- “核心判断与建议”“多维诊断”等文字由可审阅的规则组合生成，不依赖外部 AI 服务。
- 缺失成绩、异常字段和姓名未匹配等信息均会写入 `data_quality_report.csv`，请在交付前核对。

---

## 🗂️ 项目结构

```text
ClassReport/
├─ assets/                  # 图标、视觉资源
├─ classreport/
│  ├─ data.py               # CSV 读取、字段清洗、姓名规范化
│  ├─ analysis.py           # 统计、排名、诊断与建议规则
│  ├─ feishu.py             # 飞书多维表格下载与认证
│  ├─ pdf_report.py         # PDF 模板、图表、加密
│  └─ cli.py                # 生成、压缩、清单输出
├─ data/                    # 本地源数据与飞书同步数据
├─ docs/                    # 模板参考、设计说明与反馈记录
├─ output/                  # 当前生成结果（已忽略）
├─ release/                 # 教师端发布包（已忽略）
├─ run.py                   # 命令行入口
└─ build_gui_release.ps1    # GUI 教师端构建脚本
```

## ❓ 常见问题

**飞书连接失败怎么办？** 先确认令牌未过期、目标 Base 的 `app_token` 正确，并确认令牌所属用户或飞书应用已被授予该多维表格访问权限。

**模板选择会丢失吗？** 不会。GUI 会将所选模板保存到 EXE 同目录的配置文件，下一次自动沿用。

**如何查看数据是否完整？** 生成结束后打开 `output/manifests/data_quality_report.csv`；其中记录了缺失、未匹配和需要人工确认的数据。

**可以只使用本地 CSV 吗？** 可以。不带 `--sync-feishu` 执行即可读取 `data/` 中的数据生成。

---

如需调整报告内容或新增模板，请先在 `docs/` 中记录需求与视觉参考，再修改 `classreport/pdf_report.py` 并进行 PDF 页面预览核对。
