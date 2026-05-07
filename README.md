# PRLMAD

中国软件杯 A3 题目原型：基于大模型的个性化资源生成与学习多智能体系统。当前课程知识库选择“操作系统”，通过本地教材入库 + RAG 检索 + 科大讯飞 Spark-X2-Flash 多智能体生成完成个性化学习资源。

## 推荐环境

建议使用 Python 3.12。

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`：

```text
SPARK_API_KEY=Bearer 你的科大讯飞APIpassword
```

当前教材 PDF 是扫描版的概率很高，普通文本抽取拿不到内容，所以 `requirements.txt` 已加入 OCR 依赖。首次安装会比普通项目慢一些，这是正常的。

## 本地导入训练

把教材放在项目根目录的 `knowledge` 文件夹中，目前已检测到：

```text
knowledge/教材-操作系统概念-亚伯拉罕·西尔伯沙茨-械工业出版社.pdf
```

执行本地知识库构建：

```powershell
python run_cli.py train --knowledge-dir knowledge --course 操作系统 --ocr-mode auto
```

如果想先快速调试 OCR 流程，可只处理前 10 页：

```powershell
python run_cli.py train --knowledge-dir knowledge --course 操作系统 --ocr-mode on --ocr-max-pages 10
```

查看已入库文档：

```powershell
python run_cli.py docs
```

检索验证：

```powershell
python run_cli.py search "死锁的必要条件" --course 操作系统
```

## 启动 Streamlit

```powershell
streamlit run streamlit_app.py
```

打开终端输出的地址，通常是：

[http://localhost:8501](http://localhost:8501)

页面里可以完成：

- 扫描 `knowledge` 文件夹并本地导入训练。
- 查看知识库状态。
- 检索教材片段。
- 输入学生画像，调用 Spark-X2-Flash 生成课程讲解、思维导图、题库、实操案例、视频脚本、学习路径和评估方案。

## 命令行生成

```powershell
python run_cli.py generate --course 操作系统 --major 计算机科学与技术 --goal "理解进程同步与死锁" --level "了解基础概念但容易混淆信号量和互斥锁"
```

## 文件作用

```text
streamlit_app.py
  Streamlit 主界面，比赛演示建议主要运行这个文件。

run_cli.py
  命令行入口，负责本地训练、检索、生成和查看文档。

run_web.py
  早期标准库 Web 服务入口，保留作备用；当前推荐 Streamlit。

.env.example
  环境变量模板，复制为 .env 后填写 Spark API Key。

requirements.txt
  项目依赖，包含 Streamlit、Spark 请求库、PDF 解析和 OCR 组件。

knowledge/
  本地教材目录，放 PDF/TXT/MD 课程资料。

data/
  自动生成的本地知识库数据目录，默认数据库是 data/knowledge.sqlite3。

src/prlmad/config.py
  读取 .env 与项目路径配置。

src/prlmad/pdf_loader.py
  PDF/TXT/MD 文档读取；扫描 PDF 会尝试 OCR。

src/prlmad/text_splitter.py
  文本清洗和知识片段切分。

src/prlmad/knowledge_base.py
  SQLite 本地知识库、分词索引和教材检索。

src/prlmad/training.py
  扫描 knowledge 文件夹并执行本地导入训练。

src/prlmad/spark_client.py
  科大讯飞 Spark-X2-Flash HTTP 客户端。

src/prlmad/agents.py
  多智能体协作编排：画像、资源生成、路径规划和评估。

src/prlmad/safety.py
  防幻觉与内容安全提示策略。

src/prlmad/app.py 与 src/prlmad/web/
  标准库 Web 原型，作为 Streamlit 之外的备用实现。

tests/
  基础单元测试，验证切片、知识库检索和智能体编排。
```

## 测试

```powershell
python -m unittest discover -s tests
```

