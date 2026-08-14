# ClassReport - 一键式学情报告生成

本项目读取 `data/` 中的 5 份 CSV，按 `docs/` 的 PDF 样例生成每位学员的 5 页夏季班学情报告。

## 一键运行

双击 [生成学情报告.bat](生成学情报告.bat) 即可运行。也可在 `ClassReport` 目录执行：

```powershell
python -m pip install -r requirements.txt
python run.py
```

请确保安装依赖与执行 `run.py` 使用的是同一个 Python 环境。当前工作区可使用 `D:\ProgramFiles\miniforge\python.exe` 替代上面的 `python`。

## 从飞书多维表格同步

`.env` 中配置 `APP_ID` 与 `APP_SECRET` 后，可在生成前下载指定多维表格的最新数据：

```powershell
# 下载飞书数据，并用下载的数据生成报告
python run.py --sync-feishu

# 仅下载并检查多维表格，暂不生成报告
python run.py --sync-feishu --sync-only
```

默认多维表格是项目配置的课情报告 Base，也可使用 `--feishu-url "<Base URL>"` 替换。所有数据表会下载到 `data/feishu_raw/`；名称匹配报告数据结构的表会同时写入 `data/feishu/` 并作为本次生成的数据源。下载清单见 `data/feishu_download_manifest.csv`。

飞书开放平台需为应用开通任一应用身份读取权限：`bitable:app:readonly`、`bitable:app` 或 `base:table:read`。若 Base 启用了高级权限，还需将应用添加为协作者并授予相应角色。

报告会输出到 `output/`：

- `reports/`：按班级分组的个人 PDF；有手机号后四位的报告会以该后四位加密。
- `packages/`：每个班级一个压缩包，内部是对应个人报告。
- `manifests/report_manifest.csv`：生成清单与加密状态。
- `manifests/class_packages.csv`：班级压缩包清单。
- `manifests/data_quality_report.csv`：数据缺失、姓名未匹配等需要人工核对的记录。

## 常用参数

```powershell
# 指定报告日期和老师
python run.py --date 2026-07-19 --teacher "毛远老师"

# 保留已有输出，新增生成结果
python run.py --keep-output

# 调试版：不加密 PDF
python run.py --no-encrypt
```

## 数据规则

- 课堂巩固表作为 15 讲完整名单；每位有效学员生成一份报告。
- 姓名匹配会自动忽略括号中的昵称，例如 `杨赵依（依依）` 与 `杨赵依` 会被视为同一人。
- 入门测、课堂巩固的班级均分使用同班有效成绩计算。
- 期末测评的原始满分在源数据中不固定，因此综合评分使用班级百分位，不把期末原始分硬转为 100 分制。
- 没有手机号后四位的报告会生成但不加密，并在数据核对清单中标出。

## 项目结构

```text
classreport/
  data.py        CSV 读取、姓名规范化、课程/班级映射
  analysis.py    班级统计、排名、板块诊断和建议规则
  pdf_report.py  5 页 PDF 模板、图表和 PDF 加密
  cli.py         一键生成、分班压缩包、清单输出
run.py           项目入口
```
